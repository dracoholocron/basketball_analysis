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
from ..models.ball_annotation import BallAnnotation
from ..models.hoop_annotation import HoopAnnotation
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
    show_poses: bool = True,
    pose_player_filter: list[int] | None = None,
):
    """Run the full analysis pipeline for one game video."""
    engine = _sync_engine()
    storage = StorageService()

    with Session(engine) as db:
        # Idempotency / staleness guards. A long task (>~1h) can be re-delivered by
        # the broker; without this it would re-run the whole ~1h pipeline.
        _job = db.get(Job, uuid.UUID(job_id))
        if _job is None:
            logger.warning(
                "Job %s no longer exists in DB — aborting stale analysis task", job_id
            )
            return
        if _job.status == JobStatus.DONE:
            logger.warning(
                "Job %s already DONE — skipping duplicate/re-delivered task", job_id
            )
            return
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

        # ── 4b. Fetch manual ball annotation (for SAM2 tracking) ───────────
        ball_points = None
        with Session(engine) as db:
            from sqlalchemy import select as sa_select
            ball_ann = db.execute(
                sa_select(BallAnnotation).where(BallAnnotation.game_id == uuid.UUID(game_id))
            ).scalar_one_or_none()
            if ball_ann is not None and ball_ann.points:
                ball_points = ball_ann.points  # list[dict] {frame_t, pixel, visible}
                logger.info(
                    "Using %d manual ball points for game %s", len(ball_points), game_id,
                )

        # ── 4c. Fetch manual hoop annotation ───────────────────────────────
        hoop_boxes = None
        with Session(engine) as db:
            from sqlalchemy import select as sa_select
            hoop_ann = db.execute(
                sa_select(HoopAnnotation).where(HoopAnnotation.game_id == uuid.UUID(game_id))
            ).scalar_one_or_none()
            if hoop_ann is not None and hoop_ann.hoops:
                hoop_boxes = hoop_ann.hoops  # list[dict] {frame_t, bbox, kind}
                logger.info(
                    "Using %d manual hoop boxes for game %s", len(hoop_boxes), game_id,
                )

        # ── 4d. Team names (overlay) + game window (exclude warm-up/pre-game) ──
        team1_name = team2_name = None
        analysis_start_s = 0.0
        analysis_end_s = None
        with Session(engine) as db:
            from ..models.game import Game as _Game
            from ..models.team import Team as _Team
            _g = db.get(_Game, uuid.UUID(game_id))
            if _g is not None:
                if _g.home_team_id:
                    _ht = db.get(_Team, _g.home_team_id)
                    team1_name = _ht.name if _ht else None
                if _g.away_team_id:
                    _at = db.get(_Team, _g.away_team_id)
                    team2_name = _at.name if _at else None
                analysis_start_s = float(getattr(_g, "analysis_start_s", 0.0) or 0.0)
                analysis_end_s = getattr(_g, "analysis_end_s", None)
                if analysis_start_s or analysis_end_s:
                    logger.info(
                        "Game window: %.0fs – %s", analysis_start_s,
                        f"{analysis_end_s:.0f}s" if analysis_end_s else "end",
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
            "pose_estimation":   ("pose_estimation",  62),
            "hoop_detection":    ("hoop_detection",   63),
            "event_detection":   ("event_detection",  66),
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
                show_poses=show_poses,
                pose_player_filter=pose_player_filter,
                ball_points=ball_points,
                hoop_boxes=hoop_boxes,
                team1_name=team1_name,
                team2_name=team2_name,
                analysis_start_s=analysis_start_s,
                analysis_end_s=analysis_end_s,
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


def _build_roster_map(engine, job_uuid) -> dict[tuple[int, str], uuid.UUID]:
    """Map (team_no, dorsal) -> players.id using the game's home/away rosters.

    team_no 1 = home team, 2 = away team (matches pipeline team1/team2). Returns
    empty when there is no game/roster, so analysis still works without a roster.
    """
    from ..models.game import Game
    from ..models.player import Player

    out: dict[tuple[int, str], uuid.UUID] = {}
    try:
        with Session(engine) as db:
            job = db.get(Job, job_uuid)
            if job is None or job.game_id is None:
                return out
            game = db.get(Game, job.game_id)
            if game is None:
                return out
            team_no_by_uuid = {}
            if game.home_team_id:
                team_no_by_uuid[game.home_team_id] = 1
            if game.away_team_id:
                team_no_by_uuid[game.away_team_id] = 2
            if not team_no_by_uuid:
                return out
            players = (
                db.query(Player)
                .filter(Player.team_id.in_(list(team_no_by_uuid.keys())))
                .all()
            )
            for p in players:
                if not p.jersey_number or p.team_id not in team_no_by_uuid:
                    continue
                out[(team_no_by_uuid[p.team_id], str(p.jersey_number))] = p.id
    except Exception as exc:
        logger.warning("Roster map unavailable: %s", exc)
    return out


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

    # Per-player: shots / rebounds / steals from pose-based event detectors
    from collections import defaultdict as _dd
    shots_attempted: dict[int, int] = _dd(int)
    shots_made: dict[int, int] = _dd(int)
    shots_missed: dict[int, int] = _dd(int)
    rebounds_made: dict[int, int] = _dd(int)
    steals_cv_made: dict[int, int] = _dd(int)

    fps_attr = float(metrics.get("fps", 25.0)) or 25.0

    def _attribute_shooter(frame: int | None, default_tid: int) -> int:
        """Rim-shot events have no shooter (track_id=-1). Attribute to the last
        player who held the ball within ~1.5s before the shot."""
        if default_tid != -1:
            return default_tid
        if frame is None:
            return -1
        back = int(fps_attr * 1.5)
        for j in range(int(frame), max(-1, int(frame) - back), -1):
            if 0 <= j < len(ball_acquisition) and int(ball_acquisition[j]) != -1:
                return int(ball_acquisition[j])
        return -1

    for ev in metrics.get("shot_events", []):
        tid = _attribute_shooter(ev.get("frame"), int(ev.get("track_id", -1)))
        shots_attempted[tid] += 1
        if "made" in ev:
            if ev.get("made"):
                shots_made[tid] += 1
            else:
                shots_missed[tid] += 1
    for ev in metrics.get("rebound_events", []):
        rebounds_made[int(ev.get("track_id", -1))] += 1
    for ev in metrics.get("steal_events", []):
        steals_cv_made[int(ev.get("track_id", -1))] += 1

    # ── Identity consolidation (jersey OCR) ─────────────────────────────────
    # Fragmented tracks for the same athlete share a (team, dorsal). Merge them
    # so 1000s of tracks collapse into the real players. Tracks without a
    # confident dorsal stay as their own provisional identity (no count inflation).
    jersey_numbers_raw: dict = metrics.get("jersey_numbers", {}) or {}
    jersey_of: dict[int, str] = {int(k): str(v) for k, v in jersey_numbers_raw.items()}

    fps = float(metrics.get("fps", 25.0)) or 25.0
    first_seen: dict[int, int] = {}
    frames_present: dict[int, int] = defaultdict(int)
    for i, pa in enumerate(player_assignment):
        for tid in pa:
            t = int(tid)
            if t not in first_seen:
                first_seen[t] = i
            frames_present[t] += 1

    # Group tracks → canonical identity key
    groups: dict[tuple, list[int]] = defaultdict(list)
    for tid in all_track_ids:
        dorsal = jersey_of.get(tid)
        team = majority_team(tid)
        if dorsal:
            key = ("J", team, dorsal)          # consolidate by (team, dorsal)
        else:
            key = ("T", tid)                    # provisional: track stays alone
        groups[key].append(tid)

    # Order identities by earliest appearance for stable #N labels
    def _group_first(members: list[int]) -> int:
        return min((first_seen.get(t, 999999) for t in members), default=999999)

    ordered_keys = sorted(groups, key=lambda k: _group_first(groups[k]))

    # Optional roster map: (team_id 1/2, dorsal) -> players.id
    roster_map = _build_roster_map(engine, j_uuid)

    min_track_frames = int(float(os.getenv("BA_MIN_TRACK_SECONDS", "0.5")) * fps)
    dropped_short = 0
    player_rows: list[PlayerMetric] = []
    ordinal = 0
    for key in ordered_keys:
        members = groups[key]
        canonical = min(members, key=lambda t: first_seen.get(t, 999999))
        if key[0] == "J":
            team = key[1]
            dorsal = key[2]
        else:
            dorsal = None
            team = majority_team(canonical)
            for m in members:  # fall back to any member with a team vote
                if team is None:
                    team = majority_team(m)

        # Aggregate metrics across all merged tracks
        tot_dist = sum(float(player_distances.get(t, 0.0)) for t in members)
        avg_samples = [float(player_avg_speeds.get(t, 0.0)) for t in members
                       if float(player_avg_speeds.get(t, 0.0)) > 0]
        avg_speed = (sum(avg_samples) / len(avg_samples)) if avg_samples else 0.0
        max_speed = max((float(player_max_speeds.get(t, 0.0)) for t in members), default=0.0)
        poss = sum(int(possession_frames.get(t, 0)) for t in members)
        pmade = sum(int(passes_made.get(t, 0)) for t in members)
        imade = sum(int(interceptions_made.get(t, 0)) for t in members)
        shots = sum(int(shots_attempted.get(t, 0)) for t in members)
        made = sum(int(shots_made.get(t, 0)) for t in members)
        missed = sum(int(shots_missed.get(t, 0)) for t in members)
        rebs = sum(int(rebounds_made.get(t, 0)) for t in members)
        steals = sum(int(steals_cv_made.get(t, 0)) for t in members)
        # Minutes played: union of frames where any merged track is on court.
        present = sum(int(frames_present.get(t, 0)) for t in members)
        minutes = (present / fps) / 60.0 if fps else 0.0

        # Drop provisional (no-dorsal) identities seen too briefly — these are
        # detection blips / partial occlusions, not real players. Identities with a
        # confident dorsal are always kept.
        if dorsal is None and present < min_track_frames:
            dropped_short += 1
            continue

        ordinal += 1
        label = f"#{dorsal}" if dorsal else f"#{ordinal}"
        player_id = roster_map.get((team, dorsal)) if dorsal and team in (1, 2) else None

        player_rows.append(PlayerMetric(
            job_id=j_uuid,
            track_id=int(canonical),
            display_label=label,
            jersey_number=str(dorsal) if dorsal else None,
            team_id=int(team) if team is not None else None,
            player_id=player_id,
            minutes_played=float(minutes),
            total_distance_m=tot_dist,
            avg_speed_kmh=avg_speed,
            max_speed_kmh=max_speed,
            possession_frames=poss,
            passes_made=pmade,
            interceptions_made=imade,
            shots_attempted=shots,
            shots_made=made,
            shots_missed=missed,
            rebounds=rebs,
            steals_cv=steals,
        ))

    logger.info(
        "Identity consolidation: %d raw tracks → %d identities (%d with dorsal, %d short provisional dropped)",
        len(all_track_ids), len(player_rows),
        sum(1 for r in player_rows if r.jersey_number), dropped_short,
    )

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
        if db.get(Job, j_uuid) is None:
            logger.warning(
                "Job %s vanished before metrics persist — skipping %d player rows",
                job_id, len(player_rows),
            )
            return
        db.bulk_save_objects(player_rows)
        batch_size = 1000
        for i in range(0, len(frame_rows), batch_size):
            db.bulk_save_objects(frame_rows[i : i + batch_size])
        db.commit()
    logger.info(
        "Persisted %d player metrics, %d frame metrics", len(player_rows), total_frames
    )

    # Unified player-game stats (CV family) for mapped athletes → season aggregation
    _upsert_player_game_stats_cv(engine, j_uuid, player_rows)


def _upsert_player_game_stats_cv(engine, job_uuid, player_rows: list) -> None:
    """Upsert the CV/tracking family into player_game_stats for rows mapped to a real
    player. One row per (player_id, game_id); coexists with box-score data (source)."""
    from ..models.game import Game
    from ..models.player_game_stats import PlayerGameStats

    mapped = [r for r in player_rows if r.player_id is not None]
    if not mapped:
        return
    try:
        with Session(engine) as db:
            job = db.get(Job, job_uuid)
            if job is None or job.game_id is None:
                return
            game = db.get(Game, job.game_id)
            if game is None:
                return
            team_uuid_by_no = {1: game.home_team_id, 2: game.away_team_id}
            for r in mapped:
                existing = db.query(PlayerGameStats).filter(
                    PlayerGameStats.player_id == r.player_id,
                    PlayerGameStats.game_id == game.id,
                ).one_or_none()
                pgs = existing or PlayerGameStats(player_id=r.player_id, game_id=game.id)
                pgs.season_id = game.season_id
                pgs.team_id = team_uuid_by_no.get(r.team_id)
                pgs.job_id = job_uuid
                pgs.minutes_played = r.minutes_played or 0.0
                pgs.distance_m = r.total_distance_m or 0.0
                pgs.avg_speed_kmh = r.avg_speed_kmh or 0.0
                pgs.max_speed_kmh = r.max_speed_kmh or 0.0
                pgs.possession_frames = r.possession_frames or 0
                pgs.shots_attempted_cv = r.shots_attempted or 0
                pgs.shots_made_cv = r.shots_made or 0
                pgs.shots_missed_cv = r.shots_missed or 0
                pgs.rebounds_cv = r.rebounds or 0
                pgs.steals_cv = r.steals_cv or 0
                pgs.passes_cv = r.passes_made or 0
                pgs.source = "both" if (existing and existing.pts is not None) else "cv"
                if existing is None:
                    db.add(pgs)
            db.commit()
            logger.info("player_game_stats: upserted %d CV rows", len(mapped))
    except Exception as exc:
        logger.warning("player_game_stats CV upsert failed: %s", exc)


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

    # Shot attempt events (pose-based: wrist elevated + ball near wrist)
    for ev in metrics.get("shot_events", []):
        _tid = int(ev.get("track_id", -1))
        events.append({
            "event_type": "shot_attempt",
            "frame": int(ev["frame"]),
            "time_s": frame_to_s(ev["frame"]),
            "player_track_id": _tid if _tid != -1 else None,
            "description": "Intento de tiro" if _tid == -1 else f"Intento de tiro — jugador {_tid}",
        })

    # Rebound events (pose-based: ball descending then reversing + player proximity)
    for ev in metrics.get("rebound_events", []):
        _tid = int(ev.get("track_id", -1))
        events.append({
            "event_type": "rebound",
            "frame": int(ev["frame"]),
            "time_s": frame_to_s(ev["frame"]),
            "player_track_id": _tid if _tid != -1 else None,
            "description": "Rebote" if _tid == -1 else f"Rebote — jugador {_tid}",
        })

    # Steal events (pose-based: wrist proximity + possession change)
    for ev in metrics.get("steal_events", []):
        events.append({
            "event_type": "steal_pose",
            "frame": int(ev["frame"]),
            "time_s": frame_to_s(ev["frame"]),
            "player_track_id": int(ev["track_id"]),
            "description": f"Robo — jugador {ev['track_id']} de jugador {ev.get('from_track_id', '?')}",
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
    max_clips: int = 25,
    w_audio: float = 0.8,
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

    if not cv_events:
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

        # ── Score, merge & rank events (audio excitement + type relevance) ──
        try:
            from audio import AudioExcitement
            excite = AudioExcitement.from_video(local_video)
        except Exception as exc:
            logger.warning("AudioExcitement init failed: %s", exc)
            excite = None

        _TYPE_W = {
            "shot_attempt": 1.0, "steal": 0.9, "steal_cv": 0.9, "steal_pose": 0.9,
            "rebound": 0.35, "pass": 0.2,
        }
        scored = []
        for ev in cv_events:
            t = float(ev.get("time_s", 0))
            exc = excite.at(t) if excite is not None else 0.0
            score = 0.6 * _TYPE_W.get(ev.get("event_type", ""), 0.4) + w_audio * exc
            scored.append({"t": t, "score": score, "exc": exc, "ev": ev})

        # Merge events within 3 s, keeping the highest-scoring one per cluster.
        scored.sort(key=lambda d: d["t"])
        merged: list[dict] = []
        for item in scored:
            if merged and item["t"] - merged[-1]["t"] < 3.0:
                if item["score"] > merged[-1]["score"]:
                    merged[-1] = item
            else:
                merged.append(item)

        # Rank by score; keep the top `max_clips`.
        merged.sort(key=lambda d: d["score"], reverse=True)
        selected = merged[: max(1, max_clips)]
        logger.info(
            "Highlights: %d events → %d merged → top %d (audio=%s)",
            len(cv_events), len(merged), len(selected),
            "on" if (excite is not None and excite.available) else "off",
        )

        manifest: list[dict] = []
        clips_dir = os.path.join(tmp, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        vf_filter = "scale=iw*min(1080/iw\\,1920/ih):ih*min(1080/iw\\,1920/ih),pad=1080:1920:(1080-iw)/2:(1920-ih)/2" if portrait else ""

        for i, item in enumerate(selected):
            ev = item["ev"]
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
                "score": round(float(item["score"]), 3),
                "excitement": round(float(item["exc"]), 3),
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


@celery_app.task(bind=True, name="app.worker.tasks.finetune_ball_detector",
                 max_retries=0, acks_late=True)
def finetune_ball_detector(self: Task, epochs: int = 40, imgsz: int = 1280,
                           max_images: int = 4000) -> dict:
    """
    Fine-tune the ball detector on the accumulated SAM2 auto-label dataset
    (/app/ball_dataset, produced when BA_BALL_EXPORT_DATASET=true during analysis).

    Transfer-learns from the current ball model (head re-init to 1 class 'Ball'),
    then backs up and swaps the model in the models volume. Long-running.
    """
    import glob
    import random
    import shutil

    dataset = "/app/ball_dataset"
    data_yaml = os.path.join(dataset, "data.yaml")
    if not os.path.exists(data_yaml):
        return {"error": f"no dataset at {data_yaml} — run analyses with ball annotation + BA_BALL_EXPORT_DATASET first"}

    n_labels = len(glob.glob(os.path.join(dataset, "labels", "train", "*.txt")))
    if n_labels < 20:
        return {"error": f"too few labeled frames ({n_labels}); annotate more games first"}

    # ── Subsample near-duplicate frames to a diverse subset ──────────────────
    # The export is ~every frame → tons of consecutive near-dupes. Stride-sample
    # (keeps spread across games/time) to cap at max_images, then 90/10 train/val.
    imgs = sorted(glob.glob(os.path.join(dataset, "images", "train", "*.jpg")))
    if len(imgs) > max_images:
        stride = len(imgs) // max_images
        imgs = imgs[::stride][:max_images]
    random.seed(0)
    random.shuffle(imgs)
    n_val = max(1, int(len(imgs) * 0.1))
    val_list, train_list = imgs[:n_val], imgs[n_val:]
    train_txt = os.path.join(dataset, "train_subset.txt")
    val_txt = os.path.join(dataset, "val_subset.txt")
    with open(train_txt, "w") as f:
        f.write("\n".join(train_list))
    with open(val_txt, "w") as f:
        f.write("\n".join(val_list))
    sub_yaml = os.path.join(dataset, "data_subset.yaml")
    with open(sub_yaml, "w") as f:
        f.write(f"path: {dataset}\ntrain: train_subset.txt\nval: val_subset.txt\nnc: 1\nnames: ['Ball']\n")

    engine_path = os.environ.get("ENGINE_PATH", "/app/engine")
    base = os.path.join(engine_path, "models", "ball_detector_model.pt")
    if base not in sys.path:
        sys.path.insert(0, engine_path)

    try:
        from ultralytics import YOLO
        logger.info(
            "Fine-tuning ball detector: %d total labels → %d subset (%d train / %d val), epochs=%d, imgsz=%d",
            n_labels, len(imgs), len(train_list), len(val_list), epochs, imgsz,
        )
        model = YOLO(base)
        model.train(
            data=sub_yaml, epochs=epochs, imgsz=imgsz,
            mosaic=1.0, close_mosaic=10, degrees=0.0,
            translate=0.1, scale=0.5, fliplr=0.5,
            workers=0,  # Celery prefork is daemonic → DataLoader cannot fork children
            project="/app/ball_dataset/runs", name="finetune", exist_ok=True,
        )
        best = getattr(model.trainer, "best", None)
        if not best or not os.path.exists(best):
            return {"error": "training produced no best.pt"}
        # backup + swap
        shutil.copy(base, base + ".bak")
        shutil.copy(best, base)
        logger.info("Ball detector fine-tuned and swapped in: %s ← %s", base, best)
        return {"ok": True, "labeled_frames": n_labels, "best": str(best)}
    except Exception as exc:
        logger.exception("finetune_ball_detector failed")
        return {"error": str(exc)}
