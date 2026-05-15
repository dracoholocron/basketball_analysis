from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
