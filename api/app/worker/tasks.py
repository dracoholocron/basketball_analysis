"""
Celery task: run the full basketball analysis pipeline for a job.

This task is executed by the GPU worker container. It:
1. Downloads the raw video from MinIO
2. Runs the analysis pipeline (basketball_analysis.main.run_pipeline)
3. Uploads the annotated video back to MinIO
4. Persists PlayerMetric / FrameMetric rows into PostgreSQL
5. Updates Job.status and Job.current_stage throughout
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import Task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .celery_app import celery_app
from ..core.config import settings as api_settings
from ..models.job import Job, JobStatus, JobStage
from ..models.metrics import FrameMetric, PlayerMetric
from ..models.game_annotation import GameAnnotation
from ..services.storage import StorageService

# Add engine path to sys.path so we can import the basketball_analysis package
_ENGINE_PATH = os.environ.get("ENGINE_PATH", "/app/engine")
if _ENGINE_PATH not in sys.path:
    sys.path.insert(0, _ENGINE_PATH)

logger = logging.getLogger(__name__)


def _sync_engine():
    """Create a synchronous SQLAlchemy engine for use inside Celery tasks."""
    db_url = api_settings.database_url.replace("+asyncpg", "+psycopg2")
    return create_engine(db_url, pool_pre_ping=True)


def _update_job(session: Session, job_id: str, **kwargs) -> None:
    job = session.get(Job, uuid.UUID(job_id))
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        session.commit()


@celery_app.task(bind=True, name="app.worker.tasks.run_analysis", max_retries=0,
                 acks_late=True, reject_on_worker_lost=False)
def run_analysis(
    self: Task,
    job_id: str,
    game_id: str,
    video_s3_key: str,
    court_level: str = "nba",
    court_width_m: float | None = None,
    court_height_m: float | None = None,
    is_half_court: bool = False,
    team1_jersey: str = "white shirt",
    team2_jersey: str = "dark blue shirt",
):
    """Run the full analysis pipeline for one game video."""
    engine = _sync_engine()
    storage = StorageService()

    with Session(engine) as db:
        _update_job(
            db,
            job_id,
            status=JobStatus.RUNNING,
            current_stage=JobStage.READING_VIDEO,
            started_at=datetime.now(timezone.utc),
            progress_pct=5,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # ── 1. Download video ──────────────────────────────────────────────
        local_video = os.path.join(tmp, "input.mp4")
        storage.download_file(api_settings.minio_bucket_videos, video_s3_key, local_video)
        logger.info("Downloaded video to %s", local_video)

        with Session(engine) as db:
            _update_job(db, job_id, current_stage=JobStage.PLAYER_TRACKING, progress_pct=10)

        # ── 2. Import engine ───────────────────────────────────────────────
        try:
            from configs.settings import CourtProfile, CourtLevel
            from main import run_pipeline
        except ImportError as exc:
            with Session(engine) as db:
                _update_job(
                    db,
                    job_id,
                    status=JobStatus.FAILED,
                    current_stage=JobStage.QUEUED,
                    error_message=f"Engine import error: {exc}",
                    finished_at=datetime.now(timezone.utc),
                )
            raise

        # ── 3. Build court profile ─────────────────────────────────────────
        try:
            level = CourtLevel(court_level)
        except ValueError:
            level = CourtLevel.NBA

        profile = CourtProfile(
            level=level,
            width_m=court_width_m,
            height_m=court_height_m,
            half_court=is_half_court,
        )

        # ── 4. Fetch manual annotation (if any) ───────────────────────────
        manual_landmarks = None
        camera_motion = "static"
        with Session(engine) as db:
            ann = db.get(GameAnnotation, None)  # query by game_id below
            from sqlalchemy import select as sa_select
            ann = db.execute(
                sa_select(GameAnnotation).where(GameAnnotation.game_id == uuid.UUID(game_id))
            ).scalar_one_or_none()
            if ann is not None:
                manual_landmarks = ann.landmarks  # list[dict] or None
                camera_motion = ann.camera_motion or "static"
                if manual_landmarks:
                    logger.info(
                        "Using %d manual landmarks for game %s (motion=%s)",
                        len(manual_landmarks), game_id, camera_motion,
                    )

        # ── 5. Run pipeline ────────────────────────────────────────────────
        stub_dir = os.path.join(tmp, "stubs")
        output_video = os.path.join(tmp, "output.mp4")

        # Enable cuDNN benchmark for faster repeated CUDA convolutions
        try:
            import torch
            if torch.cuda.is_available():
                torch.backends.cudnn.benchmark = True
                logger.info("cuDNN benchmark enabled — device: %s", torch.cuda.get_device_name(0))
        except Exception:
            pass

        # Progress callback — updates DB at each pipeline stage
        _STAGE_LABELS = {
            "reading_video":     ("reading_video",     8),
            "player_tracking":   ("player_tracking",  12),
            "ball_tracking":     ("ball_tracking",    30),
            "keypoint_detection":("keypoint_detection",45),
            "team_assignment":   ("team_assignment",  55),
            "ball_acquisition":  ("ball_acquisition", 65),
            "pass_detection":    ("pass_detection",   68),
            "tactical_view":     ("tactical_view",    72),
            "speed_distance":    ("speed_distance",   76),
            "drawing":           ("drawing",          78),
        }

        def _pipeline_progress(stage: str, pct: int) -> None:
            entry = _STAGE_LABELS.get(stage, (stage, pct))
            try:
                with Session(engine) as db:
                    _update_job(db, job_id, current_stage=entry[0], progress_pct=entry[1])
            except Exception:
                pass

        try:
            metrics = run_pipeline(
                input_video=local_video,
                output_video=output_video,
                stub_path=stub_dir,
                use_stubs=False,
                team1_jersey=team1_jersey,
                team2_jersey=team2_jersey,
                court_profile=profile,
                manual_landmarks=manual_landmarks,
                camera_motion=camera_motion,
                on_progress=_pipeline_progress,
            )
        except Exception as exc:
            logger.exception("Pipeline failed for job %s", job_id)
            with Session(engine) as db:
                _update_job(
                    db,
                    job_id,
                    status=JobStatus.FAILED,
                    error_message=str(exc),
                    finished_at=datetime.now(timezone.utc),
                )
            raise

        with Session(engine) as db:
            _update_job(db, job_id, current_stage=JobStage.SAVING_OUTPUT, progress_pct=85)

        # ── 5. Upload annotated video ──────────────────────────────────────
        output_key = f"annotated/{game_id}/{job_id}.mp4"
        storage.upload_local_file(output_video, api_settings.minio_bucket_outputs, output_key)
        logger.info("Uploaded annotated video: %s", output_key)

        # Save source video key so highlights generation can locate the original
        with Session(engine) as db:
            _update_job(db, job_id, source_video_s3_key=video_s3_key)

        # ── 5b. Copy to host-mounted output directory (if available) ──────
        host_outputs = Path("/app/host_outputs")
        if host_outputs.exists():
            host_dir = host_outputs / str(game_id)
            host_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_video, host_dir / f"{job_id}.mp4")
            logger.info("Saved local copy: %s", host_dir / f"{job_id}.mp4")

        with Session(engine) as db:
            _update_job(
                db, job_id, current_stage=JobStage.PERSISTING_METRICS, progress_pct=90
            )

        # ── 6. Persist metrics ─────────────────────────────────────────────
        _persist_metrics(engine, job_id, metrics)

        # ── 7. Build CV events from pipeline metrics ───────────────────────
        cv_events = _build_cv_events(metrics)

        with Session(engine) as db:
            _update_job(
                db,
                job_id,
                status=JobStatus.DONE,
                current_stage=JobStage.COMPLETE,
                progress_pct=100,
                output_s3_key=output_key,
                cv_events_json=cv_events,
                finished_at=datetime.now(timezone.utc),
            )
        logger.info("Job %s completed successfully", job_id)


def _persist_metrics(engine, job_id: str, metrics: dict) -> None:
    """Write PlayerMetric and FrameMetric rows from pipeline output."""
    from collections import Counter, defaultdict

    j_uuid = uuid.UUID(job_id)
    total_frames = metrics.get("total_frames", 0)

    # Raw per-frame sequences from run_pipeline
    ball_acquisition: list[int] = metrics.get("ball_acquisition", [])
    player_assignment: list[dict] = metrics.get("player_assignment", [])
    passes: list[int] = metrics.get("passes", [])
    interceptions: list[int] = metrics.get("interceptions", [])

    # Scalar summaries from run_pipeline
    player_distances: dict = metrics.get("player_total_distance_m", {})
    player_avg_speeds: dict = metrics.get("player_avg_speed_kmh", {})
    player_max_speeds: dict = metrics.get("player_max_speed_kmh", {})

    # Collect all track_ids seen in player_assignment or distance data
    all_track_ids: set[int] = set()
    for frame_dict in player_assignment:
        all_track_ids.update(int(k) for k in frame_dict.keys())
    all_track_ids.update(int(k) for k in player_distances.keys())

    # Per-player: majority-vote team from player_assignment
    team_votes: dict[int, Counter] = defaultdict(Counter)
    for frame_dict in player_assignment:
        for track_id, team_id in frame_dict.items():
            team_votes[int(track_id)][int(team_id)] += 1

    def majority_team(tid: int) -> int | None:
        votes = team_votes.get(tid)
        if not votes:
            return None
        return votes.most_common(1)[0][0]

    # Per-player: possession frames (frames where this track_id held the ball)
    possession_frames: dict[int, int] = defaultdict(int)
    for holder_id in ball_acquisition:
        if holder_id != -1:
            possession_frames[int(holder_id)] += 1

    # Per-player: passes_made — count frames where a pass event for that player's team occurs
    # A pass is attributed to the player holding the ball in the previous frame.
    # passes[frame] == team_id means team made a pass ending at frame.
    # We find which track_id held the ball just before each pass event.
    passes_made: dict[int, int] = defaultdict(int)
    for frame_idx, passing_team in enumerate(passes):
        if passing_team == -1:
            continue
        # Find the passer: the player who held the ball in the previous frame
        prev_idx = frame_idx - 1
        if prev_idx >= 0 and prev_idx < len(ball_acquisition):
            passer_id = ball_acquisition[prev_idx]
            if passer_id != -1:
                passes_made[int(passer_id)] += 1

    # Per-player: interceptions_made — the player who receives possession from opposite team
    interceptions_made: dict[int, int] = defaultdict(int)
    for frame_idx, intercepting_team in enumerate(interceptions):
        if intercepting_team == -1:
            continue
        # Interceptor: player holding the ball at this frame
        if frame_idx < len(ball_acquisition):
            interceptor_id = ball_acquisition[frame_idx]
            if interceptor_id != -1:
                interceptions_made[int(interceptor_id)] += 1

    # Generate display labels: sort by first frame of appearance → #1, #2, …
    ordered_tracks = sorted(
        all_track_ids,
        key=lambda tid: next(
            (i for i, pa in enumerate(player_assignment) if tid in pa), 999999
        ),
    )
    display_labels: dict[int, str] = {
        tid: f"#{i + 1}" for i, tid in enumerate(ordered_tracks)
    }

    # Build PlayerMetric rows — cast everything to native Python types
    player_rows: list[PlayerMetric] = []
    for track_id in all_track_ids:
        tid = int(track_id)
        mt = majority_team(tid)
        row = PlayerMetric(
            job_id=j_uuid,
            track_id=tid,
            display_label=display_labels.get(tid),
            team_id=int(mt) if mt is not None else None,
            total_distance_m=float(player_distances.get(track_id, 0.0)),
            avg_speed_kmh=float(player_avg_speeds.get(track_id, 0.0)),
            max_speed_kmh=float(player_max_speeds.get(track_id, 0.0)),
            possession_frames=int(possession_frames.get(tid, 0)),
            passes_made=int(passes_made.get(tid, 0)),
            interceptions_made=int(interceptions_made.get(tid, 0)),
        )
        player_rows.append(row)

    # Build FrameMetric rows with ball_holder_team resolved per frame
    # Force all values to native Python int — numpy.int64 breaks psycopg2
    frame_rows: list[FrameMetric] = []
    for frame_idx in range(int(total_frames)):
        raw_holder = ball_acquisition[frame_idx] if frame_idx < len(ball_acquisition) else -1
        holder_id = int(raw_holder)
        holder_team: int | None = None
        if holder_id != -1 and frame_idx < len(player_assignment):
            raw_team = player_assignment[frame_idx].get(holder_id)
            if raw_team is None:
                # key might be stored as numpy int — try lookup
                raw_team = next(
                    (v for k, v in player_assignment[frame_idx].items() if int(k) == holder_id),
                    None,
                )
            holder_team = int(raw_team) if raw_team is not None else None

        frame_rows.append(
            FrameMetric(
                job_id=j_uuid,
                frame_number=int(frame_idx),
                ball_holder_track_id=int(holder_id) if holder_id != -1 else None,
                ball_holder_team=int(holder_team) if holder_team is not None else None,
            )
        )

    with Session(engine) as db:
        db.bulk_save_objects(player_rows)
        batch_size = 1000
        for i in range(0, len(frame_rows), batch_size):
            db.bulk_save_objects(frame_rows[i : i + batch_size])
        db.commit()
    logger.info(
        "Persisted %d player metrics, %d frame metrics", len(player_rows), total_frames
    )


def _build_cv_events(metrics: dict) -> list[dict]:
    """Build a list of CV event dicts from pipeline metrics for the CV events tab."""
    fps: float = float(metrics.get("fps", 25.0)) or 25.0
    events: list[dict] = []

    ball_acquisition: list[int] = metrics.get("ball_acquisition", [])
    passes: list[int] = metrics.get("passes", [])
    interceptions: list[int] = metrics.get("interceptions", [])

    def frame_to_s(f: int) -> float:
        return round(f / fps, 2)

    # Pass events — each frame where passes[f] != -1 is a completed pass
    for frame_idx, team_id in enumerate(passes):
        if team_id == -1:
            continue
        # Attribution: find who held the ball in the previous frame
        passer_id = None
        if frame_idx > 0 and (frame_idx - 1) < len(ball_acquisition):
            h = ball_acquisition[frame_idx - 1]
            passer_id = int(h) if h != -1 else None
        events.append({
            "event_type": "pass",
            "frame": int(frame_idx),
            "time_s": frame_to_s(frame_idx),
            "team_id": int(team_id),
            "player_track_id": passer_id,
            "description": f"Pase — equipo {team_id + 1}",
        })

    # Interception / turnover events
    for frame_idx, team_id in enumerate(interceptions):
        if team_id == -1:
            continue
        interceptor_id = None
        if frame_idx < len(ball_acquisition):
            h = ball_acquisition[frame_idx]
            interceptor_id = int(h) if h != -1 else None
        events.append({
            "event_type": "steal",
            "frame": int(frame_idx),
            "time_s": frame_to_s(frame_idx),
            "team_id": int(team_id),
            "player_track_id": interceptor_id,
            "description": f"Robo / pérdida — equipo {team_id + 1}",
        })

    # Sort by frame
    events.sort(key=lambda e: e["frame"])
    logger.info("Built %d CV events from pipeline metrics", len(events))
    return events


@celery_app.task(bind=True, name="app.worker.tasks.generate_highlights", max_retries=0,
                 acks_late=True)
def generate_highlights(
    self: Task,
    job_id: str,
    game_id: str,
    portrait: bool = False,
    pad_before_s: float = 2.0,
    pad_after_s: float = 3.0,
    event_types: list[str] | None = None,
) -> dict:
    """
    Extract highlight clips from the source video based on cv_events_json.

    Uses ffmpeg to cut clips around each event, uploads them to MinIO, and
    saves a JSON manifest so the highlights page can list them.
    """
    import json
    import subprocess

    engine = _sync_engine()
    storage = StorageService()

    with Session(engine) as db:
        job = db.get(Job, uuid.UUID(job_id))
        if job is None:
            logger.error("generate_highlights: job %s not found", job_id)
            return {"error": "job not found"}
        source_key = job.source_video_s3_key
        cv_events: list[dict] = job.cv_events_json or []

    if not source_key:
        logger.warning("generate_highlights: no source_video_s3_key on job %s", job_id)
        return {"error": "source video not available"}

    # Filter by requested event types
    if event_types:
        cv_events = [e for e in cv_events if e.get("event_type") in event_types]

    # Deduplicate nearby events (within 3 s)
    deduped: list[dict] = []
    last_time: float | None = None
    for ev in sorted(cv_events, key=lambda e: e.get("time_s", 0)):
        t = float(ev.get("time_s", 0))
        if last_time is None or t - last_time >= 3.0:
            deduped.append(ev)
            last_time = t

    if not deduped:
        logger.info("generate_highlights: no events to clip for job %s", job_id)
        return {"clips": 0}

    with tempfile.TemporaryDirectory() as tmp:
        local_video = os.path.join(tmp, "source.mp4")
        try:
            storage.download_file(api_settings.minio_bucket_videos, source_key, local_video)
        except Exception as exc:
            logger.error("generate_highlights: could not download source video: %s", exc)
            return {"error": str(exc)}

        # Get video duration via ffprobe
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", local_video],
                capture_output=True, text=True, timeout=30,
            )
            import json as _json
            fmt = _json.loads(probe.stdout).get("format", {})
            video_duration = float(fmt.get("duration", 9999))
        except Exception:
            video_duration = 9999.0

        manifest: list[dict] = []
        clips_dir = os.path.join(tmp, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        vf_filter = "scale=iw*min(1080/iw\\,1920/ih):ih*min(1080/iw\\,1920/ih),pad=1080:1920:(1080-iw)/2:(1920-ih)/2" if portrait else ""

        for i, ev in enumerate(deduped):
            t = float(ev.get("time_s", 0))
            start = max(0.0, t - pad_before_s)
            end = min(video_duration, t + pad_after_s)
            duration = end - start
            if duration < 0.5:
                continue

            clip_name = f"highlight_{i:03d}_{ev.get('event_type', 'event')}.mp4"
            clip_path = os.path.join(clips_dir, clip_name)

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", local_video,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
            ]
            if vf_filter:
                cmd += ["-vf", vf_filter]
            cmd.append(clip_path)

            try:
                subprocess.run(cmd, capture_output=True, timeout=120, check=True)
            except Exception as exc:
                logger.warning("Clip %s failed: %s", clip_name, exc)
                continue

            s3_key = f"highlights/{game_id}/{clip_name}"
            try:
                storage.upload_local_file(clip_path, api_settings.minio_bucket_outputs, s3_key)
            except Exception as exc:
                logger.warning("Could not upload clip %s: %s", clip_name, exc)
                s3_key = None

            manifest.append({
                "id": f"{job_id}_{i}",
                "event_type": ev.get("event_type", "event"),
                "start_s": start,
                "end_s": end,
                "time_s": t,
                "s3_key": s3_key,
                "description": ev.get("description", ""),
            })

        # Upload manifest JSON
        manifest_key = f"highlights/{game_id}/{job_id}_manifest.json"
        manifest_json = json.dumps(manifest).encode()
        try:
            storage.upload_bytes(
                manifest_json,
                api_settings.minio_bucket_outputs,
                manifest_key,
                content_type="application/json",
            )
        except Exception as exc:
            logger.warning("Could not upload highlights manifest: %s", exc)
            manifest_key = None

        with Session(engine) as db:
            _update_job(db, job_id, highlights_manifest_key=manifest_key)

        logger.info(
            "generate_highlights done: %d clips for job %s", len(manifest), job_id
        )
        return {"clips": len(manifest), "manifest_key": manifest_key}
