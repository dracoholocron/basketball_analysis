from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, require_role
from ..core.config import settings as api_settings
from ..models.game import Game
from ..models.job import Job, JobStatus, JobStage
from ..models.video_asset import VideoAsset
from ..models.user import User
from ..schemas.game import GameCreate, GameList, GameRead
from ..schemas.job import JobRead
from ..services.storage import get_storage


class CvEventOut(BaseModel):
    type: str
    frame: int
    track_id: Optional[int] = None
    confidence: Optional[float] = None


class HighlightOut(BaseModel):
    id: str
    event_type: str
    start_s: float
    end_s: float
    clip_url: Optional[str] = None

router = APIRouter(prefix="/games", tags=["games"])


@router.get("", response_model=GameList)
async def list_games(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    total_result = await db.execute(select(func.count()).select_from(Game))
    total = total_result.scalar_one()
    result = await db.execute(select(Game).offset(skip).limit(limit).order_by(Game.created_at.desc()))
    games = result.scalars().all()
    return GameList(items=list(games), total=total)


@router.post("", response_model=GameRead, status_code=status.HTTP_201_CREATED)
async def create_game(
    payload: GameCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "coach")),
):
    game = Game(
        season_id=payload.season_id,
        home_team_id=payload.home_team_id,
        away_team_id=payload.away_team_id,
        game_date=payload.game_date,
        location=payload.location,
        court_level=payload.court_level,
        court_width_m=payload.court_width_m,
        court_height_m=payload.court_height_m,
        is_half_court=payload.is_half_court,
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return game


@router.get("/{game_id}", response_model=GameRead)
async def get_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.post("/{game_id}/video", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_video(
    game_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "coach")),
):
    """Upload a raw video and enqueue the analysis job."""
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    storage = get_storage()
    s3_key = f"raw/{game_id}/{file.filename}"
    content = await file.read()
    storage.upload_file(
        io.BytesIO(content),
        api_settings.minio_bucket_videos,
        s3_key,
        content_type=file.content_type or "video/mp4",
    )

    video_asset = VideoAsset(
        game_id=game_id,
        s3_key=s3_key,
        filename=file.filename or "video.mp4",
        file_size_bytes=len(content),
    )
    db.add(video_asset)
    await db.flush()

    job = Job(
        game_id=game_id,
        video_asset_id=video_asset.id,
        status=JobStatus.PENDING,
        current_stage=JobStage.QUEUED,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue Celery task
    try:
        from ..worker.tasks import run_analysis
        task = run_analysis.delay(
            job_id=str(job.id),
            game_id=str(game_id),
            video_s3_key=s3_key,
            court_level=game.court_level,
            court_width_m=game.court_width_m,
            court_height_m=game.court_height_m,
            is_half_court=game.is_half_court,
        )
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Could not enqueue task: %s", exc)

    return job


@router.get("/{game_id}/cv-events", response_model=List[CvEventOut])
async def get_cv_events(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return CV-detected events (shots, rebounds, steals) from the latest completed job."""
    result = await db.execute(
        select(Job)
        .where(Job.game_id == game_id, Job.status == JobStatus.DONE)
        .order_by(Job.finished_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return []
    events = job.cv_events_json or []
    return [CvEventOut(**e) for e in events if isinstance(e, dict)]


@router.get("/{game_id}/highlights", response_model=List[HighlightOut])
async def list_highlights(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    storage=Depends(get_storage),
):
    """List highlight clips generated from the latest completed analysis job."""
    result = await db.execute(
        select(Job)
        .where(Job.game_id == game_id, Job.status == JobStatus.DONE)
        .order_by(Job.finished_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None or not job.highlights_manifest_key:
        return []

    try:
        import json
        obj = storage.get_object(api_settings.minio_bucket_videos, job.highlights_manifest_key)
        manifest: list[dict] = json.loads(obj.read())
        highlights = []
        for i, item in enumerate(manifest):
            clip_url = None
            if item.get("s3_key"):
                try:
                    clip_url = storage.presigned_get_object(
                        api_settings.minio_bucket_videos,
                        item["s3_key"],
                        expires=3600,
                    )
                except Exception:
                    pass
            highlights.append(HighlightOut(
                id=item.get("id", str(i)),
                event_type=item.get("event_type", "unknown"),
                start_s=item.get("start_s", 0.0),
                end_s=item.get("end_s", 0.0),
                clip_url=clip_url,
            ))
        return highlights
    except Exception:
        return []


@router.post("/{game_id}/highlights/generate", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def generate_highlights(
    game_id: uuid.UUID,
    portrait: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin", "coach")),
):
    """(Re-)trigger highlight generation from the latest job's analysis results."""
    result = await db.execute(
        select(Job)
        .where(Job.game_id == game_id, Job.status == JobStatus.DONE)
        .order_by(Job.finished_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="No completed analysis job found for this game")
    if not job.source_video_s3_key:
        raise HTTPException(status_code=400, detail="Source video not available for highlight generation")

    try:
        from ..worker.gpu_tasks import run_pose_analysis_task
        task = run_pose_analysis_task.delay(
            training_session_id=str(game_id),
            video_s3_key=job.source_video_s3_key,
            pose_enabled=True,
            highlight_event_types=["shot_attempt", "rebound", "steal"],
        )
        return {"task_id": task.id, "status": "queued", "portrait": portrait}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not enqueue task: {exc}")
