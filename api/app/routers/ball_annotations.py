"""
Ball annotations router — manual ball marking for SAM2 tracking + fine-tune labels.

Endpoints:
  GET  /games/{game_id}/ball-annotation   — get ball annotation (or null)
  PUT  /games/{game_id}/ball-annotation   — create / update ball points
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, require_role
from ..models.game import Game
from ..models.ball_annotation import BallAnnotation
from ..models.user import User

router = APIRouter(tags=["ball-annotations"])


class BallPoint(BaseModel):
    frame_t: float = 0.0          # seconds in the video
    pixel: list[float]            # [x, y] in intrinsic video resolution
    visible: bool = True          # False = ball NOT present in this frame

    @field_validator("pixel")
    @classmethod
    def _validate_pixel(cls, v: list[float]) -> list[float]:
        if len(v) != 2:
            raise ValueError("pixel must be [x, y]")
        return v


class BallAnnotationUpdate(BaseModel):
    points: list[BallPoint]


class BallAnnotationRead(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    points: Optional[list] = None

    model_config = {"from_attributes": True}


@router.get("/games/{game_id}/ball-annotation", response_model=BallAnnotationRead | None)
async def get_ball_annotation(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return the ball annotation for a game, or null if not yet created."""
    result = await db.execute(
        select(BallAnnotation).where(BallAnnotation.game_id == game_id)
    )
    return result.scalar_one_or_none()


@router.put("/games/{game_id}/ball-annotation", response_model=BallAnnotationRead)
async def upsert_ball_annotation(
    game_id: uuid.UUID,
    payload: BallAnnotationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin", "coach")),
):
    """Create or update the manual ball annotation for a game."""
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    result = await db.execute(
        select(BallAnnotation).where(BallAnnotation.game_id == game_id)
    )
    ann = result.scalar_one_or_none()

    points_data = [p.model_dump() for p in payload.points]

    if ann is None:
        ann = BallAnnotation(game_id=game_id, points=points_data)
        db.add(ann)
    else:
        ann.points = points_data

    await db.commit()
    await db.refresh(ann)
    return ann


@router.post("/admin/finetune-ball")
async def trigger_ball_finetune(
    epochs: int = 60,
    _: User = Depends(require_role("admin")),
):
    """Enqueue a background fine-tune of the ball detector on the accumulated
    SAM2 auto-label dataset. Long-running; runs on the GPU worker."""
    try:
        from ..worker.tasks import finetune_ball_detector
        task = finetune_ball_detector.delay(epochs=epochs)
        return {"task_id": task.id, "status": "queued", "epochs": epochs}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not enqueue fine-tune: {exc}")
