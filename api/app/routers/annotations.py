"""
Annotations router — manual court homography calibration.

Endpoints:
  GET  /landmarks/catalog              — list all available court landmarks
  GET  /games/{game_id}/annotation     — get annotation for a game (or null)
  PUT  /games/{game_id}/annotation     — create / update annotation landmarks
  POST /games/{game_id}/detect-motion  — auto-detect camera motion in the video
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, require_role
from ..core.config import settings as api_settings
from ..models.game import Game
from ..models.game_annotation import GameAnnotation
from ..models.job import Job, JobStatus
from ..models.user import User
from ..models.video_asset import VideoAsset
from ..services.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotations"])

# ── Pydantic schemas ────────────────────────────────────────────────────────


class LandmarkPoint(BaseModel):
    landmark_id: str
    pixel: list[float]   # [x, y]
    frame_t: float = 0.0  # seconds in the video

    @field_validator("pixel")
    @classmethod
    def _validate_pixel(cls, v: list[float]) -> list[float]:
        if len(v) != 2:
            raise ValueError("pixel must be [x, y]")
        return v


class AnnotationUpdate(BaseModel):
    landmarks: list[LandmarkPoint]
    camera_motion: Optional[str] = None  # "static" | "moderate" | "moving"

    @field_validator("landmarks")
    @classmethod
    def _min_landmarks(cls, v: list[LandmarkPoint]) -> list[LandmarkPoint]:
        if len(v) < 4:
            raise ValueError("At least 4 landmarks required for homography")
        return v


class AnnotationRead(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    landmarks: Optional[list] = None
    camera_motion: Optional[str] = None

    model_config = {"from_attributes": True}


class LandmarkCatalogItem(BaseModel):
    id: str
    label: str
    category: str


class MotionResult(BaseModel):
    motion: str
    ssim_avg: Optional[float] = None
    ssim_samples: list[float] = []


# ── Landmark catalog (static data, no engine dependency) ────────────────────

_LANDMARK_CATALOG: list[dict] = [
    # Corners
    {"id": "corner_tl",     "label": "Court corner - Top Left",              "category": "corner"},
    {"id": "corner_tr",     "label": "Court corner - Top Right",             "category": "corner"},
    {"id": "corner_br",     "label": "Court corner - Bottom Right",          "category": "corner"},
    {"id": "corner_bl",     "label": "Court corner - Bottom Left",           "category": "corner"},
    # Center
    {"id": "center_circle",  "label": "Center circle - center",             "category": "circle"},
    {"id": "midline_top",    "label": "Midline - Top edge",                  "category": "line"},
    {"id": "midline_bottom", "label": "Midline - Bottom edge",               "category": "line"},
    # Left key
    {"id": "ftline_left",    "label": "Free-throw line - Left",              "category": "key"},
    {"id": "key_tl_left",    "label": "Left key - Top-Left corner",          "category": "key"},
    {"id": "key_bl_left",    "label": "Left key - Bottom-Left corner",       "category": "key"},
    {"id": "key_tr_left",    "label": "Left key - Top-Right corner",         "category": "key"},
    {"id": "key_br_left",    "label": "Left key - Bottom-Right corner",      "category": "key"},
    # Right key
    {"id": "ftline_right",   "label": "Free-throw line - Right",             "category": "key"},
    {"id": "key_tl_right",   "label": "Right key - Top-Left corner",         "category": "key"},
    {"id": "key_bl_right",   "label": "Right key - Bottom-Left corner",      "category": "key"},
    {"id": "key_tr_right",   "label": "Right key - Top-Right corner",        "category": "key"},
    {"id": "key_br_right",   "label": "Right key - Bottom-Right corner",     "category": "key"},
    # Hoops
    {"id": "hoop_left",      "label": "Hoop - Left baseline center",         "category": "hoop"},
    {"id": "hoop_right",     "label": "Hoop - Right baseline center",        "category": "hoop"},
]


@router.get("/landmarks/catalog", response_model=list[LandmarkCatalogItem])
async def get_landmark_catalog(_: User = Depends(get_current_user)):
    """Return all available court landmark definitions."""
    return _LANDMARK_CATALOG


# ── Per-game annotation CRUD ────────────────────────────────────────────────


@router.get("/games/{game_id}/annotation", response_model=AnnotationRead | None)
async def get_annotation(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return the annotation for a game, or null if not yet created."""
    result = await db.execute(
        select(GameAnnotation).where(GameAnnotation.game_id == game_id)
    )
    return result.scalar_one_or_none()


@router.put("/games/{game_id}/annotation", response_model=AnnotationRead)
async def upsert_annotation(
    game_id: uuid.UUID,
    payload: AnnotationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin", "coach")),
):
    """Create or update the court landmark annotation for a game."""
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    result = await db.execute(
        select(GameAnnotation).where(GameAnnotation.game_id == game_id)
    )
    ann = result.scalar_one_or_none()

    landmarks_data = [lm.model_dump() for lm in payload.landmarks]

    if ann is None:
        ann = GameAnnotation(
            game_id=game_id,
            landmarks=landmarks_data,
            camera_motion=payload.camera_motion,
        )
        db.add(ann)
    else:
        ann.landmarks = landmarks_data
        if payload.camera_motion is not None:
            ann.camera_motion = payload.camera_motion

    await db.commit()
    await db.refresh(ann)
    return ann


# ── Camera motion detection ─────────────────────────────────────────────────


@router.post("/games/{game_id}/detect-motion", response_model=MotionResult)
async def detect_motion(
    game_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin", "coach")),
):
    """
    Download the game's raw video and classify camera motion.
    Saves the result in game_annotations.camera_motion.
    """
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Find the latest raw video for this game
    va_result = await db.execute(
        select(VideoAsset)
        .where(VideoAsset.game_id == game_id)
        .order_by(VideoAsset.uploaded_at.desc())
    )
    video_asset = va_result.scalar_one_or_none()
    if not video_asset:
        raise HTTPException(status_code=404, detail="No video uploaded for this game")

    storage = get_storage()
    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, "video.mp4")

    try:
        storage.download_file(api_settings.minio_bucket_videos, video_asset.s3_key, local_path)
    except Exception as exc:
        logger.error("Failed to download video for motion detection: %s", exc)
        raise HTTPException(status_code=500, detail="Could not download video")

    from ..services.motion_detection import detect_camera_motion
    result_data = detect_camera_motion(local_path)

    # Persist the motion result into the annotation row
    ann_result = await db.execute(
        select(GameAnnotation).where(GameAnnotation.game_id == game_id)
    )
    ann = ann_result.scalar_one_or_none()
    if ann is None:
        ann = GameAnnotation(game_id=game_id, camera_motion=result_data["motion"])
        db.add(ann)
    else:
        ann.camera_motion = result_data["motion"]

    await db.commit()

    # Clean up temp file in background
    background_tasks.add_task(_cleanup, local_path, tmp_dir)

    return MotionResult(
        motion=result_data["motion"],
        ssim_avg=result_data.get("ssim_avg"),
        ssim_samples=result_data.get("ssim_samples", []),
    )


def _cleanup(path: str, directory: str) -> None:
    import shutil
    try:
        shutil.rmtree(directory, ignore_errors=True)
    except Exception:
        pass
