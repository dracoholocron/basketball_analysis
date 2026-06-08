from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user
from ..core.config import settings as api_settings
from ..models.job import Job, JobStatus
from ..models.user import User
from ..schemas.job import JobRead
from ..services.storage import get_storage

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=List[JobRead])
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    game_id: Optional[uuid.UUID] = Query(None, description="Filter jobs by game ID"),
    status: Optional[JobStatus] = Query(None, description="Filter jobs by status"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """List jobs ordered by creation time descending. Optionally filter by game_id and/or status."""
    query = select(Job)
    if game_id is not None:
        query = query.where(Job.game_id == game_id)
    if status is not None:
        query = query.where(Job.status == status)
    query = query.order_by(desc(Job.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Delete a job record. Intended for clearing failed or stuck jobs."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == JobStatus.RUNNING:
        # Mark as failed first so any still-running Celery task knows to stop
        job.status = JobStatus.FAILED
        job.error_message = "Cancelled by user"
        await db.commit()
    await db.delete(job)
    await db.commit()


@router.get("/{job_id}/annotated-video")
async def get_annotated_video(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return a pre-signed URL for the annotated output video as JSON.

    Returns {"url": "..."} with the hostname rewritten to the public MinIO
    endpoint so the browser can reach MinIO directly without auth headers.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.output_s3_key:
        raise HTTPException(status_code=404, detail="Annotated video not yet available")
    storage = get_storage()
    url = storage.get_presigned_url(
        api_settings.minio_bucket_outputs, job.output_s3_key, public=True
    )
    return {"url": url}
