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
    use_curated_ball: bool = False,
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
        # ── 4a-bis. Curated ball track (from a completed interactive session) ──
        precomputed_ball_track = None
        if use_curated_ball:
            try:
                import json as _json
                from ..models.ball_track_session import BallTrackSession
                with Session(engine) as db:
                    sess = db.query(BallTrackSession).filter(
                        BallTrackSession.game_id == uuid.UUID(game_id),
                        BallTrackSession.status == "done",
                        BallTrackSession.track_key.isnot(None),
                    ).order_by(BallTrackSession.updated_at.desc()).first()
                    _track_key = sess.track_key if sess else None
                if _track_key:
                    _tj = os.path.join(tmp, "curated_track.json")
                    storage.download_file(api_settings.minio_bucket_outputs, _track_key, _tj)
                    with open(_tj) as _f:
                        precomputed_ball_track = {int(k): v for k, v in _json.load(_f).items()}
                    logger.info("Using curated ball track: %d frames (session %s)",
                                len(precomputed_ball_track), sess.id)
                else:
                    logger.warning("use_curated_ball requested but no completed session found")
            except Exception as exc:
                logger.warning("Curated ball track unavailable (%s) — running normal ball stage", exc)

        manual_landmarks = None
        camera_motion = "static"
        team_exemplars = None
        with Session(engine) as db:
            ann = db.get(GameAnnotation, None)  # query by game_id below
            from sqlalchemy import select as sa_select
            ann = db.execute(
                sa_select(GameAnnotation).where(GameAnnotation.game_id == uuid.UUID(game_id))
            ).scalar_one_or_none()
            if ann is not None:
                manual_landmarks = ann.landmarks  # list[dict] or None
                camera_motion = ann.camera_motion or "static"
                team_exemplars = ann.team_exemplars  # dict or None
                if manual_landmarks:
                    logger.info(
                        "Using %d manual landmarks for game %s (motion=%s)",
                        len(manual_landmarks), game_id, camera_motion,
                    )
                if team_exemplars:
                    logger.info(
                        "Using team exemplars for game %s (teams=%s)",
                        game_id, list(team_exemplars.keys()),
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
                _ball_quality = getattr(_g, "ball_tracking_quality", None) or "base_plus"

        # Map SAM 2.1 quality → (checkpoint, config). None → pipeline uses settings default.
        # "efficienttam" = EfficientTAM pilot (Meta, ~1.6-2x faster, comparable quality);
        # the tracker switches backend by the checkpoint/config name.
        _SAM2_BY_QUALITY = {
            "small":        ("models/sam2.1_hiera_small.pt",     "configs/sam2.1/sam2.1_hiera_s.yaml"),
            "base_plus":    ("models/sam2.1_hiera_base_plus.pt", "configs/sam2.1/sam2.1_hiera_b+.yaml"),
            "large":        ("models/sam2.1_hiera_large.pt",     "configs/sam2.1/sam2.1_hiera_l.yaml"),
            "efficienttam": ("models/efficienttam_s.pt",         "configs/efficienttam/efficienttam_s.yaml"),
        }
        sam2_checkpoint, sam2_config = _SAM2_BY_QUALITY.get(
            locals().get("_ball_quality", "base_plus"), (None, None)
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

        # Resolve the ACTIVE model version per role (registry). Falls back to settings
        # defaults for any role without an active version.
        _active = _active_model_paths(engine)
        if _active:
            logger.info("Active model versions: %s", _active)

        try:
            metrics = run_pipeline(
                input_video=local_video,
                output_video=output_video,
                stub_path=stub_dir,
                use_stubs=False,
                player_detector_path=_active.get("player"),
                ball_detector_path=_active.get("ball"),
                court_kp_detector_path=_active.get("court"),
                pose_model_path=_active.get("pose"),
                team1_jersey=team1_jersey,
                team2_jersey=team2_jersey,
                court_profile=profile,
                manual_landmarks=manual_landmarks,
                team_exemplars=team_exemplars,
                precomputed_ball_track=precomputed_ball_track,
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
                sam2_checkpoint=sam2_checkpoint,
                sam2_config=sam2_config,
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
            # Also persist the ball-source debug dump (when BA_BALL_DEBUG) for the audit tool.
            _dbg = output_video + ".ball_debug.json"
            if os.path.exists(_dbg):
                shutil.copy2(_dbg, host_dir / f"{job_id}.ball_debug.json")

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
        # Ignore 0 = "unknown" votes; only fall back to None when a track never got a
        # real (team 1/2) classification. Prevents unclassified tracks → team 1.
        real = {t: c for t, c in votes.items() if t in (1, 2)}
        if not real:
            return None
        return max(real, key=real.get)

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

    min_track_frames = int(float(os.getenv("BA_MIN_TRACK_SECONDS", "1.0")) * fps)
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

        # Drop provisional (no-dorsal) identities that are noise: seen too briefly, OR
        # never classified into a team (team is None → never on a decoded frame, i.e. a
        # blip) AND with zero activity. Identities with a confident dorsal are always
        # kept. This curbs the identity inflation seen on long videos.
        no_activity = (poss + pmade + imade + shots + rebs + steals) == 0
        if dorsal is None and (
            present < min_track_frames or (team is None and no_activity)
        ):
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
    # hoop_present = AUTOMATIC detector coverage (pre manual override) → honest "aros
    # detectados"; manual annotation coverage is shown via the configured-hoops count.
    hoop_auto: list = metrics.get("hoop_auto_present") or metrics.get("hoop_tracks", []) or []
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
                hoop_present=bool(frame_idx < len(hoop_auto) and hoop_auto[frame_idx]),
            )
        )

    with Session(engine) as db:
        job_row = db.get(Job, j_uuid)
        if job_row is None:
            logger.warning(
                "Job %s vanished before metrics persist — skipping %d player rows",
                job_id, len(player_rows),
            )
            return
        db.bulk_save_objects(player_rows)
        batch_size = 1000
        for i in range(0, len(frame_rows), batch_size):
            db.bulk_save_objects(frame_rows[i : i + batch_size])

        # Persist SAM2 drift review-flags to the game's ball annotation (shown in the
        # annotate-ball UI as "segmentos a revisar"). Overwrites previous run's flags.
        flagged = metrics.get("ball_flagged_segments")
        if flagged is not None and job_row.game_id is not None:
            ball_ann = db.query(BallAnnotation).filter(
                BallAnnotation.game_id == job_row.game_id
            ).one_or_none()
            if ball_ann is not None:
                ball_ann.flagged = flagged
                logger.info("Ball review flags persisted: %d segment(s)", len(flagged))
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
def finetune_ball_detector(self: Task, epochs: int = 40, imgsz: int = 960,
                           max_images: int = 4000, batch: int = 8) -> dict:
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
            data=sub_yaml, epochs=epochs, imgsz=imgsz, batch=batch,
            mosaic=1.0, close_mosaic=10, degrees=0.0,
            translate=0.1, scale=0.5, fliplr=0.5,
            workers=0,  # Celery prefork is daemonic → DataLoader cannot fork children
            project="/app/ball_dataset/runs", name="finetune", exist_ok=True,
        )
        best = getattr(model.trainer, "best", None)
        if not best or not os.path.exists(best):
            return {"error": "training produced no best.pt"}
        # Versioned save (do NOT overwrite the active model). Register INACTIVE so the
        # user reviews metrics and activates from /admin/models when ready.
        import time as _time
        ts = _time.strftime("%Y%m%d-%H%M")
        models_dir = os.path.join(engine_path, "models")
        ver_name = f"ball_detector__ft_{ts}.pt"
        ver_path = os.path.join(models_dir, ver_name)
        shutil.copy(best, ver_path)
        metrics = _read_finetune_metrics("/app/ball_dataset/runs/finetune/results.csv")
        _register_model_version("ball", f"models/{ver_name}",
                                label=f"fine-tune {ts}", source="finetune", metrics=metrics)
        logger.info("Ball detector fine-tuned → registered INACTIVE version: %s", ver_path)
        return {"ok": True, "labeled_frames": n_labels, "version": ver_name, "metrics": metrics}
    except Exception as exc:
        logger.exception("finetune_ball_detector failed")
        return {"error": str(exc)}


@celery_app.task(bind=True, name="app.worker.tasks.export_tensorrt_engine",
                 max_retries=0, acks_late=True)
def export_tensorrt_engine(self: Task, role: str, dynamic: bool = True) -> dict:
    """Export the ACTIVE .pt detector of a role to a TensorRT FP16 .engine and register
    it INACTIVE. Engines are GPU/driver-specific so this MUST run on the GPU worker.

    Loading is transparent: the trackers use ultralytics ``YOLO(path)`` which also loads
    ``.engine``. FP16 keeps mAP ~unchanged; the user validates and activates per role
    from /admin/models (revert = 1 click). See FINE_TUNING.md / MODEL_VERSIONS.md.
    """
    import shutil
    import time as _time
    from ..models.model_version import ModelVersion

    role = (role or "").strip().lower()
    if role not in ("player", "ball", "court", "pose"):
        return {"error": f"unknown role '{role}' (expected player|ball|court|pose)"}

    engine_path = os.environ.get("ENGINE_PATH", "/app/engine")
    if engine_path not in sys.path:
        sys.path.insert(0, engine_path)
    models_dir = os.path.join(engine_path, "models")

    # Resolve the active .pt for the role (fall back to the canonical file).
    sync = _sync_engine()
    rel = None
    with Session(sync) as db:
        active = db.query(ModelVersion).filter(
            ModelVersion.role == role, ModelVersion.is_active.is_(True)
        ).one_or_none()
        if active and active.filename.endswith(".pt"):
            rel = active.filename
    if rel is None:
        rel = f"models/{_CANONICAL[role]}"
    src_pt = os.path.join(engine_path, rel) if not os.path.isabs(rel) else rel
    if not os.path.exists(src_pt):
        return {"error": f"active .pt not found for role '{role}': {src_pt}"}

    # imgsz/batch per role match what the pipeline uses (engines bake input size; dynamic
    # allows batch ≤ max and variable HxW so pose top-down crops still work).
    _imgsz = {
        "player": int(os.environ.get("BA_PLAYER_IMGSZ", "1280")),
        "ball":   int(os.environ.get("BA_BALL_IMGSZ", "960")),
        "court":  int(os.environ.get("BA_COURT_KP_IMGSZ", "1536")),
        "pose":   640,
    }[role]
    _batch = int(os.environ.get(
        "BA_COURT_KP_BATCH_SIZE" if role == "court" else "BA_YOLO_BATCH_SIZE",
        "24" if role == "court" else "32",
    ))

    try:
        from ultralytics import YOLO
        logger.info("TensorRT export: role=%s src=%s imgsz=%d batch=%d (FP16)",
                    role, os.path.basename(src_pt), _imgsz, _batch)
        model = YOLO(src_pt)
        exported = model.export(
            format="engine", half=True, imgsz=_imgsz, batch=_batch,
            dynamic=bool(dynamic), workers=0, device=0, verbose=False,
        )  # writes <stem>.engine next to the .pt
        if not exported or not os.path.exists(str(exported)):
            return {"error": "export produced no .engine (is the 'tensorrt' package installed in the image?)"}
        ts = _time.strftime("%Y%m%d-%H%M")
        ver_name = f"{role}__trt_fp16_{ts}.engine"
        ver_path = os.path.join(models_dir, ver_name)
        shutil.move(str(exported), ver_path)
        _register_model_version(
            role, f"models/{ver_name}",
            label=f"TensorRT FP16 imgsz{_imgsz} {ts}", source="tensorrt",
            metrics={"imgsz": _imgsz, "batch": _batch, "precision": "fp16"},
        )
        logger.info("TensorRT export done → registered INACTIVE: %s", ver_path)
        return {"ok": True, "role": role, "version": ver_name, "imgsz": _imgsz}
    except Exception as exc:
        logger.exception("export_tensorrt_engine failed")
        return {"error": str(exc)}


@celery_app.task(bind=True, name="app.worker.tasks.ball_track_session_run",
                 max_retries=0, acks_late=True)
def ball_track_session_run(self: Task, session_id: str,
                           resume_from_frame: int | None = None) -> dict:
    """Interactive ball-tracking session runner (pause → correct → resume).

    Runs SAM2 ball propagation incrementally from `resume_from_frame` (or a smart
    default), checkpointing the partial track to MinIO and ending the task whenever it
    pauses (user request / ball lost / drift) so the GPU worker is free while the user
    corrects. Resume = a new invocation of this task.
    """
    import json as _json

    from ..models.ball_track_session import BallTrackSession
    from ..models.video_asset import VideoAsset
    from ..models.game import Game

    _engine_path = os.environ.get("ENGINE_PATH", "/app/engine")
    if _engine_path not in sys.path:
        sys.path.insert(0, _engine_path)

    engine = _sync_engine()
    storage = StorageService()
    s_uuid = uuid.UUID(session_id)

    with Session(engine) as db:
        sess = db.get(BallTrackSession, s_uuid)
        if sess is None or sess.status == "cancelled":
            return {"skipped": True}
        game_id = sess.game_id
        pause_frame_prev = sess.pause_frame
        track_key_prev = sess.track_key
        sess.status = "running"
        sess.pause_requested = False
        sess.error_message = None
        db.commit()
        # Latest source video + ball clicks + SAM2 quality for this game.
        va = db.query(VideoAsset).filter(VideoAsset.game_id == game_id).order_by(
            VideoAsset.uploaded_at.desc()).first()
        video_key = va.s3_key if va else None
        ball_ann = db.query(BallAnnotation).filter(
            BallAnnotation.game_id == game_id).one_or_none()
        ball_points = list(ball_ann.points or []) if ball_ann else []
        _g = db.get(Game, game_id)
        _quality = (getattr(_g, "ball_tracking_quality", None) or "base_plus") if _g else "base_plus"

    def _fail(msg: str) -> dict:
        with Session(engine) as db:
            s = db.get(BallTrackSession, s_uuid)
            if s:
                s.status = "error"
                s.error_message = msg[:480]
                db.commit()
        logger.error("ball session %s: %s", session_id, msg)
        return {"error": msg}

    if not video_key:
        return _fail("no video uploaded for this game")
    if not ball_points or not any(p.get("visible", True) and not p.get("negative")
                                  for p in ball_points):
        return _fail("no ball clicks — annotate at least one ball position first")

    # Source video cached on the stubs volume (resumes don't re-download).
    cache_dir = os.path.join(os.environ.get("ENGINE_PATH", "/app/engine"),
                             "stubs", "session_cache")
    os.makedirs(cache_dir, exist_ok=True)
    local_video = os.path.join(cache_dir, f"{game_id}.mp4")
    if not os.path.exists(local_video):
        try:
            storage.download_file(api_settings.minio_bucket_videos, video_key, local_video)
        except Exception as exc:
            return _fail(f"video download failed: {exc}")

    try:
        from utils.video_utils import get_video_properties
        props = get_video_properties(local_video)
        fps = float(props.get("fps") or 25.0)
        total_frames = int(props.get("total_frames") or 0)
        height = int(props.get("height") or 720)
    except Exception as exc:
        return _fail(f"video probe failed: {exc}")
    src_scale = (720.0 / height) if height > 720 else 1.0

    # Resume point: find the best seed frame so SAM2 has a real ball annotation.
    # Priority: 1) explicit arg, 2) earliest positive annotation AT OR AFTER pause
    # (user scrubbed forward to where ball is visible and clicked it), 3) latest
    # annotation before pause (user corrected just before stop), 4) pause frame itself.
    start_frame = 0
    if resume_from_frame is not None:
        start_frame = max(0, int(resume_from_frame))
    elif pause_frame_prev is not None:
        _pos = [int(round(float(p.get("frame_t", 0)) * fps))
                for p in ball_points
                if p.get("visible", True) and not p.get("negative")]
        _after  = sorted(f for f in _pos if f >= pause_frame_prev)
        _before = sorted(f for f in _pos if f < pause_frame_prev)
        if _after:
            start_frame = _after[0]     # user's forward correction
        elif _before:
            start_frame = _before[-1]   # latest annotation before pause
        else:
            start_frame = int(pause_frame_prev)

    # Partial track from the previous leg (truncate from the resume point).
    results: list[dict] = [{} for _ in range(total_frames)]
    if track_key_prev and start_frame > 0:
        try:
            tj = os.path.join(cache_dir, f"{session_id}_track.json")
            storage.download_file(api_settings.minio_bucket_outputs, track_key_prev, tj)
            with open(tj) as f:
                prev = {int(k): v for k, v in _json.load(f).items()}
            for fi, bbox in prev.items():
                if 0 <= fi < start_frame:
                    results[fi] = {1: {"bbox": bbox}}
        except Exception as exc:
            logger.warning("session %s: prior track load failed (%s) — restarting", session_id, exc)
            start_frame = 0

    # SAM2 checkpoint per the game's quality selector (same map as run_analysis).
    _BY_QUALITY = {
        "small":        ("models/sam2.1_hiera_small.pt",     "configs/sam2.1/sam2.1_hiera_s.yaml"),
        "base_plus":    ("models/sam2.1_hiera_base_plus.pt", "configs/sam2.1/sam2.1_hiera_b+.yaml"),
        "large":        ("models/sam2.1_hiera_large.pt",     "configs/sam2.1/sam2.1_hiera_l.yaml"),
        "efficienttam": ("models/efficienttam_s.pt",         "configs/efficienttam/efficienttam_s.yaml"),
    }
    ckpt, cfg = _BY_QUALITY.get(_quality, _BY_QUALITY["base_plus"])

    import time as _time
    import cv2

    preview_key = f"sessions/{session_id}/preview.jpg"
    track_key = f"sessions/{session_id}/track.json"
    _last_pause_check = [0.0]
    _pause_flag = [False]

    def should_pause() -> bool:
        now = _time.time()
        if now - _last_pause_check[0] >= 2.0:        # throttle DB polls
            _last_pause_check[0] = now
            with Session(engine) as db:
                s = db.get(BallTrackSession, s_uuid)
                _pause_flag[0] = bool(s and (s.pause_requested or s.status == "cancelled"))
        return _pause_flag[0]

    def on_progress(frame_idx: int, covered: int, bbox, jpg_path: str) -> None:
        with Session(engine) as db:
            s = db.get(BallTrackSession, s_uuid)
            if s:
                s.current_frame = int(frame_idx)
                s.total_frames = int(total_frames)
                s.fps = fps
                s.coverage_pct = round(100.0 * covered / max(1, total_frames), 1)
                s.preview_key = preview_key
                db.commit()
        try:
            img = cv2.imread(jpg_path)
            if img is not None:
                if bbox:
                    x1, y1, x2, y2 = (int(v) for v in bbox)
                    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 165, 255), 3)
                if img.shape[1] > 640:
                    sc = 640 / img.shape[1]
                    img = cv2.resize(img, (640, int(img.shape[0] * sc)))
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    import io
                    storage.upload_file(io.BytesIO(buf.tobytes()),
                                        api_settings.minio_bucket_outputs,
                                        preview_key, content_type="image/jpeg")
        except Exception:
            pass

    try:
        from ball_sam2 import Sam2BallTracker
        tracker = Sam2BallTracker(ckpt, cfg)
        out = tracker.track_interactive(
            local_video, ball_points, total_frames, fps, src_scale=src_scale,
            start_frame=start_frame, results=results,
            should_pause=should_pause, on_progress=on_progress,
        )
    except Exception as exc:
        logger.exception("ball session %s crashed", session_id)
        return _fail(str(exc))
    if out is None:
        return _fail("tracker unavailable (sam2/efficienttam import or checkpoint failed)")

    # Persist the (partial or full) track.
    track = {str(i): r[1]["bbox"] for i, r in enumerate(out["results"]) if 1 in r}
    try:
        import io
        storage.upload_file(io.BytesIO(_json.dumps(track).encode()),
                            api_settings.minio_bucket_outputs, track_key,
                            content_type="application/json")
    except Exception as exc:
        return _fail(f"track upload failed: {exc}")

    with Session(engine) as db:
        s = db.get(BallTrackSession, s_uuid)
        if s is None:
            return {"ok": True}
        s.track_key = track_key
        s.coverage_pct = round(100.0 * out["covered"] / max(1, total_frames), 1)
        s.total_frames = total_frames
        s.fps = fps
        if s.status == "cancelled":
            pass
        elif out["status"] == "done":
            s.status = "done"
            s.pause_reason = None
            s.pause_frame = None
            s.current_frame = total_frames
        else:
            s.status = "waiting_user"
            s.pause_reason = out["pause_reason"]
            s.pause_frame = int(out["pause_frame"] or 0)
            s.current_frame = int(out["pause_frame"] or 0)
        s.pause_requested = False
        db.commit()
        final_status = s.status
    logger.info("ball session %s leg finished: %s (covered %d/%d)",
                session_id, final_status, out["covered"], total_frames)
    return {"ok": True, "status": final_status, "covered": out["covered"]}


# ── Model version registry helpers (worker side — has the models_data volume) ──────

_MODELS_ROLE_PATTERNS = [
    ("player", ("player_detector", "player")),
    ("ball",   ("ball_detector", "ball")),
    ("court",  ("court_keypoint", "court")),
    ("pose",   ("pose",)),
]
_CANONICAL = {
    "player": "player_detector.pt",
    "ball": "ball_detector_model.pt",
    "court": "court_keypoint_detector.pt",
    "pose": "yolo11n-pose.pt",
}


def _role_for_file(name: str) -> str | None:
    low = name.lower()
    if low.startswith("sam2") or low.startswith("sam3") or "multiclass" in low:
        return None
    for role, pats in _MODELS_ROLE_PATTERNS:
        if any(p in low for p in pats):
            return role
    return None


def _read_finetune_metrics(results_csv: str) -> dict | None:
    try:
        import csv as _csv
        with open(results_csv) as f:
            rows = list(_csv.DictReader(f))
        if not rows:
            return None
        last = rows[-1]
        def g(k):
            for kk in last:
                if kk.strip() == k:
                    try:
                        return round(float(last[kk]), 4)
                    except ValueError:
                        return None
            return None
        return {"epochs": len(rows), "mAP50": g("metrics/mAP50(B)"),
                "mAP50-95": g("metrics/mAP50-95(B)"), "precision": g("metrics/precision(B)"),
                "recall": g("metrics/recall(B)")}
    except Exception:
        return None


def _register_model_version(role: str, filename: str, label: str | None,
                            source: str, metrics: dict | None,
                            activate_if_none: bool = False) -> None:
    """Upsert a ModelVersion row (by role+filename). Optionally activate when the role
    has no active version yet."""
    from ..models.model_version import ModelVersion
    engine = _sync_engine()
    with Session(engine) as db:
        existing = db.query(ModelVersion).filter(
            ModelVersion.role == role, ModelVersion.filename == filename
        ).one_or_none()
        if existing is None:
            has_active = db.query(ModelVersion).filter(
                ModelVersion.role == role, ModelVersion.is_active.is_(True)
            ).first() is not None
            mv = ModelVersion(
                role=role, filename=filename, label=label, source=source, metrics=metrics,
                is_active=(activate_if_none and not has_active),
            )
            db.add(mv)
        else:
            if metrics is not None:
                existing.metrics = metrics
        db.commit()


@celery_app.task(bind=True, name="app.worker.tasks.scan_models", max_retries=0)
def scan_models(self: Task) -> dict:
    """Register model files in the models_data volume into the registry (idempotent).
    Activates the canonical file for any role that has no active version yet."""
    import glob
    from ..models.model_version import ModelVersion
    engine_path = os.environ.get("ENGINE_PATH", "/app/engine")
    models_dir = os.path.join(engine_path, "models")
    found = 0
    for path in glob.glob(os.path.join(models_dir, "*.pt")):
        name = os.path.basename(path)
        role = _role_for_file(name)
        if role is None:
            continue
        _register_model_version(role, f"models/{name}", label=name, source="builtin",
                                metrics=None, activate_if_none=False)
        found += 1
    # Ensure each role has an active version (prefer canonical).
    engine = _sync_engine()
    activated = {}
    with Session(engine) as db:
        for role in ("player", "ball", "court", "pose"):
            has_active = db.query(ModelVersion).filter(
                ModelVersion.role == role, ModelVersion.is_active.is_(True)
            ).first()
            if has_active:
                continue
            canonical = f"models/{_CANONICAL[role]}"
            pick = db.query(ModelVersion).filter(
                ModelVersion.role == role, ModelVersion.filename == canonical
            ).one_or_none() or db.query(ModelVersion).filter(
                ModelVersion.role == role
            ).order_by(ModelVersion.created_at.asc()).first()
            if pick:
                pick.is_active = True
                activated[role] = pick.filename
        db.commit()
    logger.info("scan_models: registered %d files; activated defaults: %s", found, activated)
    return {"ok": True, "registered": found, "activated": activated}


def _active_model_paths(engine) -> dict:
    """role -> absolute model path for the ACTIVE version (only roles with an active row)."""
    from ..models.model_version import ModelVersion
    engine_path = os.environ.get("ENGINE_PATH", "/app/engine")
    out: dict[str, str] = {}
    try:
        with Session(engine) as db:
            for mv in db.query(ModelVersion).filter(ModelVersion.is_active.is_(True)).all():
                rel = mv.filename
                out[mv.role] = rel if os.path.isabs(rel) else os.path.join(engine_path, rel)
    except Exception as exc:
        logger.warning("active model paths unavailable: %s", exc)
    return out
