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


@celery_app.task(bind=True, name="app.worker.tasks.run_analysis", max_retries=2)
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

        # ── 4. Run pipeline ────────────────────────────────────────────────
        stub_dir = os.path.join(tmp, "stubs")
        output_video = os.path.join(tmp, "output.avi")

        try:
            metrics = run_pipeline(
                input_video=local_video,
                output_video=output_video,
                stub_path=stub_dir,
                use_stubs=False,
                team1_jersey=team1_jersey,
                team2_jersey=team2_jersey,
                court_profile=profile,
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
        output_key = f"annotated/{game_id}/{job_id}.avi"
        storage.upload_local_file(output_video, api_settings.minio_bucket_outputs, output_key)
        logger.info("Uploaded annotated video: %s", output_key)

        # ── 5b. Copy to host-mounted output directory (if available) ──────
        host_outputs = Path("/app/host_outputs")
        if host_outputs.exists():
            host_dir = host_outputs / str(game_id)
            host_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_video, host_dir / f"{job_id}.avi")
            logger.info("Saved local copy: %s", host_dir / f"{job_id}.avi")

        with Session(engine) as db:
            _update_job(
                db, job_id, current_stage=JobStage.PERSISTING_METRICS, progress_pct=90
            )

        # ── 6. Persist metrics ─────────────────────────────────────────────
        _persist_metrics(engine, job_id, metrics)

        with Session(engine) as db:
            _update_job(
                db,
                job_id,
                status=JobStatus.DONE,
                current_stage=JobStage.COMPLETE,
                progress_pct=100,
                output_s3_key=output_key,
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

    # Build PlayerMetric rows
    player_rows: list[PlayerMetric] = []
    for track_id in all_track_ids:
        row = PlayerMetric(
            job_id=j_uuid,
            track_id=track_id,
            display_label=display_labels.get(track_id),
            team_id=majority_team(track_id),
            total_distance_m=float(player_distances.get(track_id, 0.0)),
            avg_speed_kmh=float(player_avg_speeds.get(track_id, 0.0)),
            max_speed_kmh=float(player_max_speeds.get(track_id, 0.0)),
            possession_frames=possession_frames.get(track_id, 0),
            passes_made=passes_made.get(track_id, 0),
            interceptions_made=interceptions_made.get(track_id, 0),
        )
        player_rows.append(row)

    # Build FrameMetric rows with ball_holder_team resolved per frame
    frame_rows: list[FrameMetric] = []
    for frame_idx in range(total_frames):
        holder_id = ball_acquisition[frame_idx] if frame_idx < len(ball_acquisition) else -1
        holder_team: int | None = None
        if holder_id != -1 and frame_idx < len(player_assignment):
            raw = player_assignment[frame_idx].get(holder_id)
            holder_team = int(raw) if raw is not None else None

        frame_rows.append(
            FrameMetric(
                job_id=j_uuid,
                frame_number=frame_idx,
                ball_holder_track_id=holder_id if holder_id != -1 else None,
                ball_holder_team=holder_team,
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
