"""
Training session endpoints — video upload, pose analysis, results.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user
from ..core.config import settings as api_settings
from ..models.training import TrainingSession, PoseKeypoints, ShootingFormMetric
from ..models.user import User
from ..services.storage import get_storage

router = APIRouter(prefix="/training", tags=["training"])


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class TrainingSessionCreate(BaseModel):
    sport_drill: Optional[str] = None


class ShootingMetricOut(BaseModel):
    frame: int
    person_id: int
    elbow_l: Optional[float] = None
    elbow_r: Optional[float] = None
    knee_l: Optional[float] = None
    knee_r: Optional[float] = None
    hip_l: Optional[float] = None
    hip_r: Optional[float] = None
    torso_lean: Optional[float] = None
    back_angle: Optional[float] = None
    release_angle: Optional[float] = None
    depth: Optional[float] = None

    class Config:
        from_attributes = True


class KeypointOut(BaseModel):
    frame: int
    person_id: int
    keypoints: Optional[list] = None
    bbox: Optional[dict] = None
    hoop_bbox: Optional[dict] = None

    class Config:
        from_attributes = True


class TrainingSessionOut(BaseModel):
    id: uuid.UUID
    sport_drill: Optional[str] = None
    status: str
    video_s3_key: Optional[str] = None
    created_at: datetime
    celery_task_id: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class TrainingSessionDetail(TrainingSessionOut):
    metrics: List[ShootingMetricOut] = []
    keypoints: List[KeypointOut] = []


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[TrainingSessionOut])
async def list_training_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List training sessions for the current user."""
    result = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.user_id == current_user.id)
        .order_by(TrainingSession.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("", response_model=TrainingSessionOut, status_code=status.HTTP_201_CREATED)
async def create_training_session(
    payload: TrainingSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new training session."""
    session = TrainingSession(
        user_id=current_user.id,
        sport_drill=payload.sport_drill,
        status="pending",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{session_id}", response_model=TrainingSessionDetail)
async def get_training_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a training session with its metrics and keypoints."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(TrainingSession)
        .where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == current_user.id,
        )
        .options(
            selectinload(TrainingSession.metrics),
            selectinload(TrainingSession.keypoints),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found")
    return session


@router.post("/{session_id}/upload-video", response_model=TrainingSessionOut)
async def upload_training_video(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage=Depends(get_storage),
):
    """Upload a video file for a training session and queue pose analysis."""
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found")

    # Upload video to MinIO
    s3_key = f"training/{session_id}/{file.filename}"
    content = await file.read()
    storage.upload_fileobj(
        io.BytesIO(content),
        api_settings.minio_bucket_videos,
        s3_key,
        content_type=file.content_type or "video/mp4",
    )

    # Queue pose analysis Celery task
    try:
        from ..worker.gpu_tasks import run_pose_analysis_task
        task = run_pose_analysis_task.delay(
            training_session_id=str(session_id),
            video_s3_key=s3_key,
            pose_enabled=True,
        )
        session.celery_task_id = task.id
        session.status = "analyzing"
    except Exception:
        session.status = "uploaded"

    session.video_s3_key = s3_key
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/{session_id}/analyze", response_model=dict)
async def trigger_analysis(
    session_id: uuid.UUID,
    pose_enabled: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """(Re-)trigger pose analysis for a session that already has a video uploaded."""
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found")
    if not session.video_s3_key:
        raise HTTPException(status_code=400, detail="No video uploaded for this session")

    from ..worker.gpu_tasks import run_pose_analysis_task
    task = run_pose_analysis_task.delay(
        training_session_id=str(session_id),
        video_s3_key=session.video_s3_key,
        pose_enabled=pose_enabled,
    )
    session.celery_task_id = task.id
    session.status = "analyzing"
    await db.commit()
    return {"task_id": task.id, "status": "queued"}


@router.get("/{session_id}/cv-events", response_model=List[dict])
async def get_cv_events(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return CV-detected events (shots, rebounds, steals) for a session."""
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found")

    # CV events are stored as keypoints metadata or returned from task result
    # For now return from keypoints hoop_bbox as a placeholder
    kp_result = await db.execute(
        select(PoseKeypoints)
        .where(PoseKeypoints.session_id == session_id)
        .order_by(PoseKeypoints.frame)
        .limit(5)
    )
    kps = kp_result.scalars().all()
    return [{"frame": k.frame, "person_id": k.person_id, "hoop_detected": k.hoop_bbox is not None} for k in kps]


@router.get("/{session_id}/highlights", response_model=List[dict])
async def list_highlights(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List generated highlight clips for a training session."""
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found")
    return []


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_training_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a training session and all its data."""
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found")
    await db.delete(session)
    await db.commit()
