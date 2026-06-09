from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse
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
from ..schemas.game import AnalysisOptions, GameCreate, GameList, GameRead
from ..schemas.job import JobRead
from ..services.storage import get_storage


class CvEventOut(BaseModel):
    event_type: str
    frame: int
    time_s: Optional[float] = None
    team_id: Optional[int] = None
    player_track_id: Optional[int] = None
    description: Optional[str] = None


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
        home_team1_jersey=payload.home_team1_jersey,
        away_team2_jersey=payload.away_team2_jersey,
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


class GameUpdate(BaseModel):
    show_poses: Optional[bool] = None
    court_level: Optional[str] = None
    is_half_court: Optional[bool] = None
    home_team1_jersey: Optional[str] = None
    away_team2_jersey: Optional[str] = None


@router.patch("/{game_id}", response_model=GameRead)
async def update_game(
    game_id: uuid.UUID,
    payload: GameUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin", "coach")),
):
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(game, field, value)
    await db.commit()
    await db.refresh(game)
    return game


class VideoAssetRead(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    filename: str
    file_size_bytes: Optional[int] = None

    model_config = {"from_attributes": True}


@router.post("/{game_id}/video", response_model=VideoAssetRead, status_code=status.HTTP_201_CREATED)
async def upload_video(
    game_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "coach")),
):
    """Upload a raw video for a game (does NOT start analysis — call /analyze next)."""
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
    await db.commit()
    await db.refresh(video_asset)
    return video_asset


@router.post("/{game_id}/analyze", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def analyze_game(
    game_id: uuid.UUID,
    opts: AnalysisOptions = Body(default_factory=AnalysisOptions),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "coach")),
):
    """Start analysis of the latest uploaded video for this game."""
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Find the latest video asset
    va_result = await db.execute(
        select(VideoAsset)
        .where(VideoAsset.game_id == game_id)
        .order_by(VideoAsset.uploaded_at.desc())
        .limit(1)
    )
    video_asset = va_result.scalar_one_or_none()
    if not video_asset:
        raise HTTPException(status_code=400, detail="No video uploaded for this game. Upload a video first.")

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

    try:
        from ..worker.tasks import run_analysis
        task = run_analysis.delay(
            job_id=str(job.id),
            game_id=str(game_id),
            video_s3_key=video_asset.s3_key,
            court_level=game.court_level,
            court_width_m=game.court_width_m,
            court_height_m=game.court_height_m,
            is_half_court=game.is_half_court,
            show_poses=game.show_poses,
            team1_jersey=game.home_team1_jersey,
            team2_jersey=game.away_team2_jersey,
            pose_player_filter=opts.pose_player_filter,
        )
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Could not enqueue task: %s", exc)

    return job


@router.get("/{game_id}/raw-video")
async def get_raw_video_url(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return a pre-signed URL for the latest raw (uploaded) video of the game.

    Returns JSON {"url": "..."} so that authenticated browser clients can obtain
    the URL and pass it directly to a <video> element without CORS/auth issues.
    The hostname in the URL is rewritten to the public MinIO endpoint so the
    browser can reach MinIO directly.
    """
    result = await db.execute(
        select(VideoAsset)
        .where(VideoAsset.game_id == game_id)
        .order_by(VideoAsset.uploaded_at.desc())
        .limit(1)
    )
    va = result.scalar_one_or_none()
    if not va:
        raise HTTPException(status_code=404, detail="No video uploaded for this game")
    storage = get_storage()
    url = storage.get_presigned_url(api_settings.minio_bucket_videos, va.s3_key, public=True)
    return {"url": url}


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
    out = []
    for e in events:
        if not isinstance(e, dict):
            continue
        # Support both old "type" key and new "event_type" key
        event_type = e.get("event_type") or e.get("type", "unknown")
        out.append(CvEventOut(
            event_type=event_type,
            frame=int(e.get("frame", 0)),
            time_s=e.get("time_s"),
            team_id=e.get("team_id"),
            player_track_id=e.get("player_track_id") or e.get("track_id"),
            description=e.get("description"),
        ))
    return out


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
        import json as _json
        import io as _io
        raw = storage._client.get_object(
            Bucket=api_settings.minio_bucket_outputs,
            Key=job.highlights_manifest_key,
        )
        manifest: list[dict] = _json.loads(raw["Body"].read())
        highlights = []
        for i, item in enumerate(manifest):
            clip_url = None
            if item.get("s3_key"):
                try:
                    clip_url = storage.get_presigned_url(
                        api_settings.minio_bucket_outputs,
                        item["s3_key"],
                        expiry=3600,
                        public=True,
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
    """(Re-)trigger highlight generation from the latest job's CV events."""
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
        raise HTTPException(
            status_code=400,
            detail=(
                "Source video not recorded for this job. "
                "Re-run the analysis to regenerate with source tracking."
            ),
        )

    cv_events = job.cv_events_json or []
    if not cv_events:
        raise HTTPException(
            status_code=400,
            detail="No CV events found. Re-run the analysis to generate event data first.",
        )

    try:
        from ..worker.tasks import generate_highlights as generate_highlights_task
        task = generate_highlights_task.delay(
            job_id=str(job.id),
            game_id=str(game_id),
            portrait=portrait,
        )
        return {"task_id": task.id, "status": "queued", "portrait": portrait, "events": len(cv_events)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not enqueue task: {exc}")
