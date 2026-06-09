"""
GPU Celery tasks for pose-enabled analysis pipeline.

Extends the base run_analysis task with:
- PoseEstimator (RTMPose / YOLO-pose)
- ShotDetector, ReboundDetector, StealTurnoverDetector
- HoopDetector
- HighlightGenerator
- DualResolutionPipeline
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone

from celery import Task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .celery_app import celery_app
from ..core.config import settings as api_settings
from ..models.job import Job, JobStatus, JobStage
from ..services.storage import StorageService

_ENGINE_PATH = os.environ.get("ENGINE_PATH", "/app/engine")
if _ENGINE_PATH not in sys.path:
    sys.path.insert(0, _ENGINE_PATH)

logger = logging.getLogger(__name__)


def _sync_engine():
    db_url = api_settings.database_url.replace("+asyncpg", "+psycopg2")
    return create_engine(db_url, pool_pre_ping=True)


def _update_job(session: Session, job_id: str, **kwargs) -> None:
    job = session.get(Job, uuid.UUID(job_id))
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        session.commit()


@celery_app.task(
    bind=True,
    name="app.worker.gpu_tasks.run_pose_analysis_task",
    queue="gpu",
    max_retries=1,
)
def run_pose_analysis_task(
    self: Task,
    training_session_id: str,
    video_s3_key: str,
    pose_enabled: bool = True,
    highlight_event_types: list[str] | None = None,
) -> dict:
    """
    Run pose-enabled analysis on a training session video.

    Steps
    -----
    1. Download video from MinIO
    2. Run player + ball detection (YOLO11 multi-class)
    3. Run pose estimation (RTMPose if available, else YOLO-pose)
    4. Detect events: shots, rebounds, steals
    5. Detect hoop position
    6. Generate highlight clips
    7. Upload results to MinIO
    8. Return summary dict

    Parameters
    ----------
    training_session_id : str UUID
    video_s3_key : str  MinIO key of the source video
    pose_enabled : bool  Run pose estimation (disable for speed)
    highlight_event_types : list of event types to clip (default: all)
    """
    storage = StorageService()
    db_engine = _sync_engine()
    session_uuid = uuid.UUID(training_session_id)

    logger.info("GPU task started: session=%s  video=%s", training_session_id, video_s3_key)

    with tempfile.TemporaryDirectory() as tmp:
        # ── 1. Download video ──────────────────────────────────────────────
        local_video = os.path.join(tmp, "input.mp4")
        try:
            storage.download_file(api_settings.minio_bucket_videos, video_s3_key, local_video)
        except Exception as exc:
            logger.warning("Could not download video %s: %s — using local path", video_s3_key, exc)
            local_video = video_s3_key  # allow local path for dev

        # ── 2. Import engine ───────────────────────────────────────────────
        try:
            from utils import get_video_properties
            from trackers import PlayerTracker, BallTracker
            from configs.settings import settings as engine_settings
            from configs import MULTICLASS_DETECTOR_PATH, PLAYER_DETECTOR_PATH, BALL_DETECTOR_PATH
        except ImportError as exc:
            logger.error("Engine import failed: %s", exc)
            return {"error": str(exc), "session_id": training_session_id}

        # ── 3. Video properties + streaming detection ──────────────────────
        vid_props = get_video_properties(local_video)
        fps = vid_props["fps"] or 24.0
        total_frames = vid_props["total_frames"] or 0
        logger.info("Video: %d frames at %.1f fps", total_frames, fps)

        detector_path = (
            MULTICLASS_DETECTOR_PATH
            if os.path.exists(MULTICLASS_DETECTOR_PATH)
            else PLAYER_DETECTOR_PATH
        )
        player_tracker = PlayerTracker(detector_path)
        ball_tracker = BallTracker(
            MULTICLASS_DETECTOR_PATH
            if os.path.exists(MULTICLASS_DETECTOR_PATH)
            else BALL_DETECTOR_PATH
        )

        from configs.settings import settings as engine_settings
        chunk_size = engine_settings.chunk_size or 500

        logger.info("Running player detection (streaming)...")
        sv_player = player_tracker.detect_frames_streaming(local_video, chunk_size)
        player_tracks = player_tracker.build_tracks_from_sv_detections(sv_player)
        del sv_player

        logger.info("Running ball detection (streaming)...")
        sv_ball = ball_tracker.detect_frames_streaming(local_video, chunk_size)
        ball_tracks = ball_tracker.build_tracks_from_sv_detections(sv_ball)
        del sv_ball
        ball_tracks = ball_tracker.interpolate_ball_positions(ball_tracks)
        total_frames = len(player_tracks)

        # ── 4. Hoop detection ──────────────────────────────────────────────
        hoop_bbox = None
        try:
            from hoop_detector import HoopDetector
            from utils.video_utils import iter_video_frames
            hoop_det = HoopDetector()
            for i, frame in enumerate(iter_video_frames(local_video, max_height=720)):
                if i % 10 == 0:
                    hoop_bbox = hoop_det.detect(frame)
                    if hoop_bbox:
                        break
            logger.info("Hoop detected: %s", hoop_bbox)
        except Exception as exc:
            logger.warning("HoopDetector failed: %s", exc)

        # ── 5. Pose estimation ─────────────────────────────────────────────
        pose_sequence: list[dict] = [{} for _ in range(total_frames)]
        if pose_enabled:
            try:
                from pose_estimator import PoseEstimator
                pe = PoseEstimator()
                logger.info("Running pose estimation (backend=%s)...", pe._backend)
                pose_sequence = pe.estimate_sequence_streaming(
                    local_video, player_tracks, chunk_size
                )
                logger.info("Pose estimation complete")
            except Exception as exc:
                logger.warning("PoseEstimator failed: %s — skipping pose", exc)

        # ── 6. Event detection ─────────────────────────────────────────────
        cv_events: list[dict] = []
        try:
            from event_detector import ShotDetector, ReboundDetector, StealTurnoverDetector

            shot_events = ShotDetector().process_sequence(pose_sequence, ball_tracks)
            rebound_events = ReboundDetector().process_sequence(
                pose_sequence, ball_tracks, player_tracks
            )
            steal_events = StealTurnoverDetector().process_sequence(pose_sequence, ball_tracks)

            cv_events = shot_events + rebound_events + steal_events
            cv_events.sort(key=lambda e: e.get("frame", 0))
            logger.info(
                "Events: %d shots, %d rebounds, %d steals",
                len(shot_events), len(rebound_events), len(steal_events),
            )
        except Exception as exc:
            logger.warning("Event detection failed: %s", exc)

        # ── 7. Highlight generation ────────────────────────────────────────
        highlights: list[dict] = []
        highlights_dir = os.path.join(tmp, "highlights")
        try:
            from highlight_generator import HighlightGenerator
            hg = HighlightGenerator(
                fps=fps,
                output_dir=highlights_dir,
            )
            highlights = hg.generate_clips(
                local_video,
                cv_events,
                event_types=highlight_event_types,
            )
            logger.info("Generated %d highlight clips", len(highlights))

            # Upload highlights to MinIO
            for h in highlights:
                clip_path = h["clip_path"]
                clip_name = os.path.basename(clip_path)
                s3_key = f"highlights/{training_session_id}/{clip_name}"
                try:
                    storage.upload_local_file(
                        clip_path, api_settings.minio_bucket_outputs, s3_key
                    )
                    h["s3_key"] = s3_key
                except Exception as exc:
                    logger.warning("Could not upload highlight %s: %s", clip_name, exc)
        except Exception as exc:
            logger.warning("Highlight generation failed: %s", exc)

        # ── 8. Serialize pose data for storage ────────────────────────────
        pose_data: list[dict] = []
        if pose_enabled and any(pose_sequence):
            try:
                from pose_estimator import PoseEstimator
                pose_data = PoseEstimator.keypoints_to_serializable(pose_sequence)
            except Exception:
                pass

        result = {
            "session_id": training_session_id,
            "total_frames": total_frames,
            "fps": fps,
            "hoop_bbox": hoop_bbox,
            "cv_events": cv_events,
            "highlights": [
                {k: v for k, v in h.items() if k != "clip_path"}
                for h in highlights
            ],
            "pose_keypoints_count": len(pose_data),
            "pose_data_sample": pose_data[:5] if pose_data else [],
        }

        logger.info(
            "GPU task complete: session=%s  events=%d  highlights=%d",
            training_session_id, len(cv_events), len(highlights),
        )
        return result
