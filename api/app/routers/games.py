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
from ..models.team import Team
from ..models.user import User
from ..schemas.game import AnalysisOptions, GameCreate, GameList, GameRead
from ..schemas.job import JobRead
from ..services.storage import get_storage


class CvEventOut(BaseModel):
    idx: int = 0                       # index into the job's cv_events (for inline editing)
    event_type: str
    frame: int
    time_s: Optional[float] = None
    team_id: Optional[int] = None
    player_track_id: Optional[int] = None
    description: Optional[str] = None
    edited: bool = False               # True when a correction overrides the original


class CvEventCorrectionIn(BaseModel):
    new_type: Optional[str] = None
    new_player_track_id: Optional[int] = None


class HighlightOut(BaseModel):
    id: str
    event_type: str
    start_s: float
    end_s: float
    clip_url: Optional[str] = None
    score: float = 0.0
    excitement: float = 0.0

router = APIRouter(prefix="/games", tags=["games"])


@router.get("", response_model=GameList)
async def list_games(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    season_id: Optional[uuid.UUID] = Query(None, description="Filter games by season"),
    team_id: Optional[uuid.UUID] = Query(None, description="Filter games where team is home or away"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    base = select(Game)
    if season_id is not None:
        base = base.where(Game.season_id == season_id)
    if team_id is not None:
        base = base.where((Game.home_team_id == team_id) | (Game.away_team_id == team_id))

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    result = await db.execute(
        base.order_by(Game.created_at.desc()).offset(skip).limit(limit)
    )
    games = list(result.scalars().all())

    # Enrich with team names so listings can show readable labels (e.g. box-score filter).
    team_ids = {g.home_team_id for g in games if g.home_team_id} | \
               {g.away_team_id for g in games if g.away_team_id}
    names: dict = {}
    if team_ids:
        rows = (await db.execute(select(Team).where(Team.id.in_(team_ids)))).scalars().all()
        names = {t.id: t.name for t in rows}
    items = []
    for g in games:
        out = GameRead.model_validate(g)
        out.home_team_name = names.get(g.home_team_id)
        out.away_team_name = names.get(g.away_team_id)
        items.append(out)
    return GameList(items=items, total=total)


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
    out = GameRead.model_validate(game)
    if game.home_team_id:
        ht = await db.get(Team, game.home_team_id)
        out.home_team_name = ht.name if ht else None
    if game.away_team_id:
        at = await db.get(Team, game.away_team_id)
        out.away_team_name = at.name if at else None
    return out


class GameUpdate(BaseModel):
    show_poses: Optional[bool] = None
    court_level: Optional[str] = None
    is_half_court: Optional[bool] = None
    home_team1_jersey: Optional[str] = None
    away_team2_jersey: Optional[str] = None
    home_team_name: Optional[str] = None   # find-or-create Team → home_team_id
    away_team_name: Optional[str] = None   # find-or-create Team → away_team_id
    analysis_start_s: Optional[float] = None  # live-play window start (seconds)
    analysis_end_s: Optional[float] = None    # live-play window end (seconds)
    ball_tracking_quality: Optional[str] = None  # 'small' | 'base_plus' | 'large'
    ball_detector_mode: Optional[str] = None  # 'auto' | 'tracknet' | 'yolo'


async def _find_or_create_team(db: AsyncSession, name: str, org_id) -> Team:
    name = name.strip()
    res = await db.execute(
        select(Team).where(Team.name == name, Team.organization_id == org_id)
    )
    team = res.scalar_one_or_none()
    if team is None:
        team = Team(name=name, organization_id=org_id)
        db.add(team)
        await db.flush()
    return team


@router.patch("/{game_id}", response_model=GameRead)
async def update_game(
    game_id: uuid.UUID,
    payload: GameUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "coach")),
):
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    data = payload.model_dump(exclude_none=True)
    # Team names → find-or-create Team (org-scoped) and link to the game. This both
    # labels the game (names show in metrics) and enables roster-based player mapping.
    home_name = data.pop("home_team_name", None)
    away_name = data.pop("away_team_name", None)
    if home_name:
        game.home_team_id = (await _find_or_create_team(db, home_name, current_user.organization_id)).id
    if away_name:
        game.away_team_id = (await _find_or_create_team(db, away_name, current_user.organization_id)).id
    # Validate SAM 2.1 quality selector; ignore unknown values.
    if data.get("ball_tracking_quality") not in (None, "small", "base_plus", "large"):
        data.pop("ball_tracking_quality", None)
    # Validate ball detector mode; ignore unknown values.
    if data.get("ball_detector_mode") not in (None, "auto", "tracknet", "yolo"):
        data.pop("ball_detector_mode", None)

    for field, value in data.items():
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


# ── Multipart upload (videos >100MB; bypasses Cloudflare's per-request cap) ──────
# Flow: initiate → (per part) part-url + browser PUT direct to s3.<DOMAIN> → complete.
# Each part is < PART_SIZE (<100MB) so it crosses the tunnel fine.
_MULTIPART_PART_SIZE = 50 * 1024 * 1024  # 50 MB (MinIO min part size is 5MB; max ~10k parts)


class MultipartInitiateIn(BaseModel):
    filename: str
    file_size: int
    content_type: Optional[str] = None


class MultipartInitiateOut(BaseModel):
    upload_id: str
    key: str
    bucket: str
    part_size: int
    total_parts: int


class PartUrlIn(BaseModel):
    upload_id: str
    key: str
    part_number: int


class PartUrlOut(BaseModel):
    url: str
    part_number: int


class MultipartCompleteIn(BaseModel):
    upload_id: str
    key: str
    filename: str
    file_size: int


class MultipartAbortIn(BaseModel):
    upload_id: str
    key: str


@router.post("/{game_id}/video/multipart/initiate", response_model=MultipartInitiateOut)
async def initiate_multipart_upload(
    game_id: uuid.UUID,
    body: MultipartInitiateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "coach")),
):
    """Begin a chunked upload. Returns the upload_id, S3 key and part layout."""
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if body.file_size <= 0:
        raise HTTPException(status_code=400, detail="file_size must be > 0")

    storage = get_storage()
    s3_key = f"raw/{game_id}/{body.filename}"
    upload_id = storage.create_multipart_upload(
        api_settings.minio_bucket_videos,
        s3_key,
        content_type=body.content_type or "video/mp4",
    )
    total_parts = (body.file_size + _MULTIPART_PART_SIZE - 1) // _MULTIPART_PART_SIZE
    return MultipartInitiateOut(
        upload_id=upload_id,
        key=s3_key,
        bucket=api_settings.minio_bucket_videos,
        part_size=_MULTIPART_PART_SIZE,
        total_parts=total_parts,
    )


@router.post("/{game_id}/video/multipart/part-url", response_model=PartUrlOut)
async def get_multipart_part_url(
    game_id: uuid.UUID,
    body: PartUrlIn,
    current_user: User = Depends(require_role("admin", "coach")),
):
    """Presigned PUT URL for one part (signed for the public s3.<DOMAIN> host)."""
    if body.part_number < 1:
        raise HTTPException(status_code=400, detail="part_number must be >= 1")
    storage = get_storage()
    url = storage.presign_upload_part(
        api_settings.minio_bucket_videos,
        body.key,
        body.upload_id,
        body.part_number,
    )
    return PartUrlOut(url=url, part_number=body.part_number)


@router.post("/{game_id}/video/multipart/complete", response_model=VideoAssetRead, status_code=status.HTTP_201_CREATED)
async def complete_multipart_upload(
    game_id: uuid.UUID,
    body: MultipartCompleteIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "coach")),
):
    """Finalize the upload (ETags fetched server-side) and register the VideoAsset."""
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    storage = get_storage()
    try:
        storage.complete_multipart_upload(
            api_settings.minio_bucket_videos, body.key, body.upload_id
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not complete upload: {exc}")

    video_asset = VideoAsset(
        game_id=game_id,
        s3_key=body.key,
        filename=body.filename or "video.mp4",
        file_size_bytes=body.file_size,
    )
    db.add(video_asset)
    await db.commit()
    await db.refresh(video_asset)
    return video_asset


@router.post("/{game_id}/video/multipart/abort", status_code=status.HTTP_204_NO_CONTENT)
async def abort_multipart_upload(
    game_id: uuid.UUID,
    body: MultipartAbortIn,
    current_user: User = Depends(require_role("admin", "coach")),
):
    """Cancel an in-progress multipart upload and free its parts."""
    storage = get_storage()
    storage.abort_multipart_upload(
        api_settings.minio_bucket_videos, body.key, body.upload_id
    )
    return None


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

    # Per-run ball detector mode override → persist onto the game (run_analysis reads it).
    if opts.ball_detector_mode in ("auto", "tracknet", "yolo"):
        game.ball_detector_mode = opts.ball_detector_mode
        await db.commit()

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
            use_curated_ball=opts.use_curated_ball,
            emit_layers=opts.emit_layers,
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
    # Overlay manual corrections (by event index) on the immutable analysis output.
    from ..models.cv_event_correction import CvEventCorrection
    corr_rows = (await db.execute(
        select(CvEventCorrection).where(CvEventCorrection.job_id == job.id)
    )).scalars().all()
    corrections = {c.event_index: c for c in corr_rows}
    out = []
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            continue
        event_type = e.get("event_type") or e.get("type", "unknown")
        track = e.get("player_track_id") or e.get("track_id")
        c = corrections.get(i)
        edited = False
        if c is not None:
            if c.new_type:
                event_type = c.new_type; edited = True
            if c.new_player_track_id is not None:
                track = c.new_player_track_id; edited = True
        out.append(CvEventOut(
            idx=i,
            event_type=event_type,
            frame=int(e.get("frame", 0)),
            time_s=e.get("time_s"),
            team_id=e.get("team_id"),
            player_track_id=track,
            description=e.get("description"),
            edited=edited,
        ))
    return out


@router.get("/{game_id}/shot-heatmap", response_model=dict)
async def get_shot_heatmap(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Shot heatmap (10x6 court grid) built from the analyzed video's CV shot events
    (x_pct/y_pct origins). Empty grid when the latest analysis has no positioned shots."""
    job = (await db.execute(
        select(Job).where(Job.game_id == game_id, Job.status == JobStatus.DONE)
        .order_by(Job.finished_at.desc()).limit(1)
    )).scalar_one_or_none()
    grid = [[0] * 6 for _ in range(10)]
    total = made = positioned = 0
    if job is not None:
        for e in (job.cv_events_json or []):
            if not isinstance(e, dict):
                continue
            et = e.get("event_type") or e.get("type", "")
            if et not in ("shot_attempt", "shot_made", "shot_missed"):
                continue
            total += 1
            if e.get("made") or et == "shot_made":
                made += 1
            x, y = e.get("x_pct"), e.get("y_pct")
            if x is None or y is None:
                continue
            col = min(5, max(0, int(float(x) * 6)))
            row = min(9, max(0, int(float(y) * 10)))
            grid[row][col] += 1
            positioned += 1
    return {
        "heat_grid": grid,
        "total_shots": total,
        "made_shots": made,
        "positioned_shots": positioned,
        "fg_pct": round(made / total, 3) if total else 0.0,
        "source": "cv",
    }


@router.patch("/{game_id}/cv-events/{idx}", response_model=CvEventOut)
async def correct_cv_event(
    game_id: uuid.UUID,
    idx: int,
    payload: CvEventCorrectionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "coach")),
):
    """Override an event's type and/or assigned player track (manual correction). Applied on
    top of the immutable cv_events of the game's latest completed job."""
    from ..models.cv_event_correction import CvEventCorrection
    job = (await db.execute(
        select(Job).where(Job.game_id == game_id, Job.status == JobStatus.DONE)
        .order_by(Job.finished_at.desc()).limit(1)
    )).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="No completed analysis for this game")
    events = job.cv_events_json or []
    if idx < 0 or idx >= len(events):
        raise HTTPException(status_code=404, detail="Event index out of range")

    corr = (await db.execute(
        select(CvEventCorrection).where(
            CvEventCorrection.job_id == job.id, CvEventCorrection.event_index == idx)
    )).scalar_one_or_none()
    if corr is None:
        corr = CvEventCorrection(job_id=job.id, event_index=idx)
        db.add(corr)
    if payload.new_type is not None:
        corr.new_type = payload.new_type or None
    if payload.new_player_track_id is not None:
        corr.new_player_track_id = payload.new_player_track_id
    await db.commit()

    e = events[idx]
    return CvEventOut(
        idx=idx,
        event_type=corr.new_type or e.get("event_type") or e.get("type", "unknown"),
        frame=int(e.get("frame", 0)), time_s=e.get("time_s"), team_id=e.get("team_id"),
        player_track_id=(corr.new_player_track_id
                         if corr.new_player_track_id is not None
                         else (e.get("player_track_id") or e.get("track_id"))),
        description=e.get("description"), edited=True,
    )


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
                score=float(item.get("score", 0.0)),
                excitement=float(item.get("excitement", 0.0)),
            ))
        # Most exciting / relevant first.
        highlights.sort(key=lambda h: h.score, reverse=True)
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
