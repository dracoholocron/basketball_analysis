"""
SAM 3 pilot task (ISOLATED lab). Runs on the `worker-sam3lab` service (profile
'lab') only — the production worker never consumes the `sam3lab` queue. SAM 3 is
imported lazily inside the engine module, so importing this file is safe everywhere.

Flow: download a game's analyzed source video → run SAM 3 concept tracking for a
text prompt → re-encode to H.264 → upload to the outputs bucket → return the key +
coverage. The frontend polls the task result and presigns the output for playback.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import uuid

from celery import Task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .celery_app import celery_app
from ..core.config import settings as api_settings
from ..models.job import Job, JobStatus
from ..services.storage import StorageService

logger = logging.getLogger(__name__)

_ENGINE_PATH = os.environ.get("ENGINE_PATH", "/app/engine")


def _sync_engine():
    url = api_settings.database_url.replace("+asyncpg", "+psycopg2")
    return create_engine(url, pool_pre_ping=True)


@celery_app.task(bind=True, name="app.worker.sam3_tasks.sam3_pilot_track", max_retries=0)
def sam3_pilot_track(self: Task, game_id: str, prompt: str = "basketball",
                     start_s: float = 0.0, end_s: float | None = None) -> dict:
    if _ENGINE_PATH not in sys.path:
        sys.path.insert(0, _ENGINE_PATH)

    engine = _sync_engine()
    storage = StorageService()

    # Latest analyzed source video for the game.
    with Session(engine) as db:
        job = db.execute(
            select(Job).where(Job.game_id == uuid.UUID(game_id), Job.status == JobStatus.DONE)
            .order_by(Job.finished_at.desc()).limit(1)
        ).scalar_one_or_none()
        source_key = job.source_video_s3_key if job else None
    if not source_key:
        return {"error": "no analyzed source video for this game"}

    run_id = uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory() as tmp:
        local_video = os.path.join(tmp, "source.mp4")
        try:
            storage.download_file(api_settings.minio_bucket_videos, source_key, local_video)
        except Exception as exc:
            return {"error": f"download failed: {exc}"}

        # Frame window
        try:
            from utils.video_utils import get_video_properties
            fps = get_video_properties(local_video).get("fps") or 24.0
        except Exception:
            fps = 24.0
        start_f = int(round(start_s * fps))
        end_f = int(round(end_s * fps)) if end_s else None

        raw_out = os.path.join(tmp, "sam3_raw.mp4")
        try:
            from sam3_lab import Sam3Tracker
            tracker = Sam3Tracker()
            result = tracker.track_video(local_video, prompt, raw_out, start_f=start_f, end_f=end_f)
        except Exception as exc:
            logger.exception("sam3_pilot_track failed")
            return {"error": str(exc)}
        if "error" in result:
            return result

        # Re-encode to browser-friendly H.264
        out_mp4 = os.path.join(tmp, "sam3.mp4")
        enc = subprocess.run(
            ["ffmpeg", "-y", "-i", raw_out, "-c:v", "libx264", "-preset", "fast",
             "-crf", "23", "-movflags", "+faststart", out_mp4],
            capture_output=True,
        )
        final = out_mp4 if enc.returncode == 0 and os.path.exists(out_mp4) else raw_out

        out_key = f"lab/sam3/{game_id}/{run_id}.mp4"
        try:
            storage.upload_local_file(final, api_settings.minio_bucket_outputs, out_key)
        except Exception as exc:
            return {"error": f"upload failed: {exc}"}

    logger.info("SAM3 pilot done: game=%s prompt=%s coverage=%.1f%%",
                game_id, prompt, result.get("coverage_pct", 0))
    return {
        "ok": True, "game_id": game_id, "prompt": prompt,
        "coverage_pct": result.get("coverage_pct"),
        "frames": result.get("frames"), "frames_with_object": result.get("frames_with_object"),
        "output_key": out_key,
    }
