"""Experimental 'lab' endpoints — isolated pilots that don't touch production.

SAM 3 pilot: enqueue a text-prompt tracking run (consumed only by the worker-sam3lab
service, profile 'lab') and poll its result. Output video is served via a presigned
URL from the outputs bucket.
"""
from __future__ import annotations

import uuid

from celery.result import AsyncResult
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.config import settings as api_settings
from ..core.deps import require_role
from ..services.storage import StorageService
from ..worker.celery_app import celery_app

router = APIRouter(prefix="/lab", tags=["lab"])
_staff = require_role("admin", "coach")


class Sam3TrackRequest(BaseModel):
    game_id: uuid.UUID
    prompt: str = "basketball"
    start_s: float = 0.0
    end_s: float | None = None


@router.post("/sam3/track")
async def sam3_track(payload: Sam3TrackRequest, _=Depends(_staff)):
    """Enqueue a SAM 3 pilot run. Returns a task_id to poll with /lab/sam3/result."""
    res = celery_app.send_task(
        "app.worker.sam3_tasks.sam3_pilot_track",
        kwargs=dict(
            game_id=str(payload.game_id), prompt=payload.prompt,
            start_s=payload.start_s, end_s=payload.end_s,
        ),
        queue="sam3lab",
    )
    return {"task_id": res.id, "queued": True}


@router.get("/sam3/result/{task_id}")
async def sam3_result(task_id: str, _=Depends(_staff)):
    """Poll a SAM 3 pilot run. While pending → {state}. On success → metrics +
    presigned output video URL. On failure/error → the error message."""
    ar = AsyncResult(task_id, app=celery_app)
    if not ar.ready():
        return {"state": ar.state}  # PENDING | STARTED
    if ar.failed():
        return {"state": "FAILURE", "error": str(ar.result)}
    result = ar.result or {}
    if isinstance(result, dict) and result.get("error"):
        return {"state": "ERROR", "error": result["error"]}
    out_url = None
    if isinstance(result, dict) and result.get("output_key"):
        out_url = StorageService().get_presigned_url(
            api_settings.minio_bucket_outputs, result["output_key"], public=True,
        )
    return {"state": "SUCCESS", "result": result, "output_url": out_url}
