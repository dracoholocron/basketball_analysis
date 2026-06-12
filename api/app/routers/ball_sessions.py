"""Ball tracking session router — interactive pause → correct → resume.

Endpoints:
  POST /games/{game_id}/ball-session          — start a new session (or restart)
  GET  /games/{game_id}/ball-session          — status + presigned preview URL
  POST /games/{game_id}/ball-session/pause    — request a soft pause
  POST /games/{game_id}/ball-session/resume   — resume from the last pause frame
  POST /games/{game_id}/ball-session/cancel   — cancel / abandon
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings as api_settings
from ..core.database import get_db
from ..core.deps import get_current_user, require_role
from ..models.ball_track_session import BallTrackSession
from ..models.game import Game
from ..models.user import User
from ..services.storage import StorageService

router = APIRouter(tags=["ball-sessions"])
_staff = require_role("admin", "coach")

_TERMINAL = {"done", "cancelled", "error"}
_ACTIVE = {"queued", "running"}


# ── response schema ───────────────────────────────────────────────────────────

class BallSessionRead(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    status: str
    current_frame: int
    total_frames: int
    fps: float
    coverage_pct: float
    pause_reason: str | None = None
    pause_frame: int | None = None
    pause_requested: bool
    preview_url: str | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


# ── helpers ───────────────────────────────────────────────────────────────────

def _enqueue(session_id: str, resume_from_frame: int | None = None) -> str:
    from ..worker.tasks import ball_track_session_run
    t = ball_track_session_run.delay(
        session_id=session_id,
        resume_from_frame=resume_from_frame,
    )
    return t.id


def _preview_url(sess: BallTrackSession) -> str | None:
    if not sess.preview_key:
        return None
    try:
        return StorageService().get_presigned_url(
            api_settings.minio_bucket_outputs, sess.preview_key, public=True
        )
    except Exception:
        return None


async def _latest_session(game_id: uuid.UUID, db: AsyncSession) -> BallTrackSession | None:
    result = await db.execute(
        select(BallTrackSession)
        .where(BallTrackSession.game_id == game_id)
        .order_by(desc(BallTrackSession.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


def _to_read(sess: BallTrackSession) -> BallSessionRead:
    return BallSessionRead(
        id=sess.id,
        game_id=sess.game_id,
        status=sess.status,
        current_frame=sess.current_frame,
        total_frames=sess.total_frames,
        fps=sess.fps,
        coverage_pct=sess.coverage_pct,
        pause_reason=sess.pause_reason,
        pause_frame=sess.pause_frame,
        pause_requested=sess.pause_requested,
        preview_url=_preview_url(sess),
        error_message=sess.error_message,
    )


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/games/{game_id}/ball-session", response_model=BallSessionRead)
async def start_ball_session(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_staff),
):
    """Start a fresh interactive ball-tracking session for a game.

    If an active session already exists it is cancelled first. If a completed
    session exists a new one is created (re-run from scratch).
    """
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Cancel any running/queued sessions.
    existing = await db.execute(
        select(BallTrackSession).where(
            BallTrackSession.game_id == game_id,
            BallTrackSession.status.in_(list(_ACTIVE)),
        )
    )
    for s in existing.scalars().all():
        s.status = "cancelled"
    await db.flush()

    sess = BallTrackSession(game_id=game_id, status="queued")
    db.add(sess)
    await db.commit()
    await db.refresh(sess)

    try:
        _enqueue(str(sess.id))
    except Exception as exc:
        sess.status = "error"
        sess.error_message = f"Could not enqueue: {exc}"[:480]
        await db.commit()
        raise HTTPException(status_code=503, detail=str(exc))

    return _to_read(sess)


@router.get("/games/{game_id}/ball-session", response_model=BallSessionRead | None)
async def get_ball_session(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return the latest ball-tracking session for a game, or null."""
    sess = await _latest_session(game_id, db)
    return _to_read(sess) if sess else None


@router.post("/games/{game_id}/ball-session/pause", response_model=BallSessionRead)
async def pause_ball_session(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_staff),
):
    """Signal the running session to pause at the next safe checkpoint (≤2 s)."""
    sess = await _latest_session(game_id, db)
    if not sess:
        raise HTTPException(status_code=404, detail="No active session")
    if sess.status not in _ACTIVE:
        raise HTTPException(status_code=409, detail=f"Session is already {sess.status}")
    sess.pause_requested = True
    await db.commit()
    await db.refresh(sess)
    return _to_read(sess)


@router.post("/games/{game_id}/ball-session/resume", response_model=BallSessionRead)
async def resume_ball_session(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_staff),
):
    """Resume a paused/waiting session from its last pause frame.

    Ball annotations (corrected clicks / negative marks) must be saved via the
    PUT /games/{game_id}/ball-annotation endpoint BEFORE calling resume — the
    task reads them fresh at startup.
    """
    sess = await _latest_session(game_id, db)
    if not sess:
        raise HTTPException(status_code=404, detail="No session found")
    if sess.status not in ("waiting_user", "error"):
        raise HTTPException(status_code=409, detail=f"Session status is '{sess.status}'; only waiting_user or error sessions can be resumed")

    sess.status = "queued"
    sess.pause_requested = False
    sess.error_message = None
    await db.commit()
    await db.refresh(sess)

    try:
        _enqueue(str(sess.id), resume_from_frame=sess.pause_frame)
    except Exception as exc:
        sess.status = "error"
        sess.error_message = f"Could not enqueue: {exc}"[:480]
        await db.commit()
        raise HTTPException(status_code=503, detail=str(exc))

    return _to_read(sess)


@router.post("/games/{game_id}/ball-session/cancel", response_model=BallSessionRead)
async def cancel_ball_session(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_staff),
):
    """Cancel the latest session (the worker detects this on next poll ≤2 s)."""
    sess = await _latest_session(game_id, db)
    if not sess:
        raise HTTPException(status_code=404, detail="No session found")
    if sess.status in _TERMINAL:
        raise HTTPException(status_code=409, detail=f"Session already {sess.status}")
    sess.status = "cancelled"
    await db.commit()
    await db.refresh(sess)
    return _to_read(sess)
