import os
import argparse
import logging

from utils import read_video, save_video, iter_video_frames, get_video_properties, CourtModeDetector
from utils import read_stub, save_stub
from trackers import PlayerTracker, BallTracker
from team_assigner import TeamAssigner
from court_keypoint_detector import CourtKeypointDetector
from ball_aquisition import BallAquisitionDetector
from pass_and_interception_detector import PassAndInterceptionDetector
from tactical_view_converter import TacticalViewConverter
from speed_and_distance_calculator import SpeedAndDistanceCalculator
from drawers import (
    PlayerTracksDrawer,
    BallTracksDrawer,
    CourtKeypointDrawer,
    TeamBallControlDrawer,
    FrameNumberDrawer,
    PassInterceptionDrawer,
    TacticalViewDrawer,
    SpeedAndDistanceDrawer,
    PoseDrawer,
)
from configs import (
    STUBS_DEFAULT_PATH,
    MULTICLASS_DETECTOR_PATH,
    PLAYER_DETECTOR_PATH,
    BALL_DETECTOR_PATH,
    COURT_KEYPOINT_DETECTOR_PATH,
    OUTPUT_VIDEO_PATH,
)
from configs.settings import CourtProfile, CourtLevel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("basketball_analysis")


def parse_args():
    parser = argparse.ArgumentParser(description="Basketball Video Analysis")
    parser.add_argument("input_video", type=str, help="Path to input video file")
    parser.add_argument(
        "--output_video",
        type=str,
        default=OUTPUT_VIDEO_PATH,
        help="Path to output video file",
    )
    parser.add_argument(
        "--stub_path",
        type=str,
        default=STUBS_DEFAULT_PATH,
        help="Path to stub directory",
    )
    parser.add_argument(
        "--no_stubs",
        action="store_true",
        default=False,
        help="Disable stub caching (always re-run all detectors)",
    )
    parser.add_argument(
        "--team1_jersey",
        type=str,
        default="white shirt",
        help="Description of Team 1 jersey for zero-shot classification",
    )
    parser.add_argument(
        "--team2_jersey",
        type=str,
        default="dark blue shirt",
        help="Description of Team 2 jersey for zero-shot classification",
    )
    return parser.parse_args()


def _resolve_detector_path(multiclass: str, legacy: str) -> str:
    """Return multi-class model path if it exists, else fall back to the legacy model."""
    return multiclass if os.path.exists(multiclass) else legacy


def run_pipeline(
    input_video: str,
    output_video: str = OUTPUT_VIDEO_PATH,
    stub_path: str = STUBS_DEFAULT_PATH,
    use_stubs: bool = True,
    team1_jersey: str = "white shirt",
    team2_jersey: str = "dark blue shirt",
    court_image_path: str | None = None,
    player_detector_path: str | None = None,
    ball_detector_path: str | None = None,
    court_kp_detector_path: str = COURT_KEYPOINT_DETECTOR_PATH,
    court_profile: CourtProfile | None = None,
    manual_landmarks: list[dict] | None = None,
    camera_motion: str = "static",
    on_progress=None,
    chunk_size: int | None = None,
    show_poses: bool = True,
    pose_player_filter: list[int] | None = None,
):
    """
    Run the full basketball analysis pipeline on a video file.

    Parameters
    ----------
    manual_landmarks : list[dict], optional
        Manually annotated court landmarks from the UI.
    camera_motion : str
        "static" | "moderate" | "moving".
    on_progress : callable, optional
        Called as on_progress(stage: str, pct: int) at key milestones.
        stage matches JobStage enum values (e.g. "player_tracking").
    chunk_size : int | None
        Frames loaded into RAM per chunk during inference. None → use
        BA_CHUNK_SIZE env var (default 500). Set to 0 for legacy all-at-once
        path (requires enough RAM for the full video).
    """
    from configs.settings import settings as _settings

    _court_image_path = court_image_path or _settings.court_image_path

    def _progress(stage: str, pct: int) -> None:
        if on_progress:
            try:
                on_progress(stage, pct)
            except Exception:
                pass

    # Resolve chunk_size: explicit arg > env var > default 500
    _chunk_size: int = chunk_size if chunk_size is not None else _settings.chunk_size

    # Resolve model paths: prefer YOLO11 multi-class model when available
    _player_path = player_detector_path or _resolve_detector_path(
        MULTICLASS_DETECTOR_PATH, PLAYER_DETECTOR_PATH
    )
    _ball_path = ball_detector_path or _resolve_detector_path(
        MULTICLASS_DETECTOR_PATH, BALL_DETECTOR_PATH
    )
    logger.info("Player detector: %s", _player_path)
    logger.info("Ball detector:   %s", _ball_path)

    # Read video metadata upfront so both paths have fps + dimensions
    _progress("reading_video", 8)
    try:
        _vid_props = get_video_properties(input_video)
        actual_fps = _vid_props["fps"] or 24.0
        frame_width = _vid_props["width"] or 1280
        _total_frames_hint = _vid_props["total_frames"]
    except Exception:
        actual_fps = 24.0
        frame_width = 1280
        _total_frames_hint = 0

    player_tracker = PlayerTracker(_player_path)
    ball_tracker = BallTracker(_ball_path)
    court_keypoint_detector = CourtKeypointDetector(court_kp_detector_path)

    _player_stub = os.path.join(stub_path, "player_track_stubs.pkl")
    _ball_stub = os.path.join(stub_path, "ball_track_stubs.pkl")
    _court_stub = os.path.join(stub_path, "court_key_points_stub.pkl")
    _assign_stub = os.path.join(stub_path, "player_assignment_stub.pkl")

    if _chunk_size > 0:
        # ── Chunked inference path (O(chunk_size) peak RAM) ─────────────────
        logger.info(
            "Chunked inference mode: chunk_size=%d (~%.0f MB/chunk at 720p)",
            _chunk_size,
            _chunk_size * 2.76,
        )

        _progress("player_tracking", 12)
        _ref_stub = os.path.join(stub_path, "referee_tracks_stub.pkl")
        player_tracks = read_stub(use_stubs, _player_stub)
        referee_tracks: list = read_stub(use_stubs, _ref_stub) or []
        if player_tracks is None:
            sv_player = player_tracker.detect_frames_streaming(input_video, _chunk_size)
            player_tracks = player_tracker.build_tracks_from_sv_detections(sv_player)
            if not referee_tracks:
                referee_tracks = player_tracker.build_referee_tracks_from_sv_detections(sv_player)
                save_stub(_ref_stub, referee_tracks)
            del sv_player
            save_stub(_player_stub, player_tracks)
        logger.info(
            "Player tracks done (%d frames, %d referee detections)",
            len(player_tracks), sum(len(f) for f in referee_tracks),
        )

        _progress("ball_tracking", 30)
        ball_tracks = read_stub(use_stubs, _ball_stub)
        if ball_tracks is None:
            sv_ball = ball_tracker.detect_frames_streaming(input_video, _chunk_size)
            ball_tracks = ball_tracker.build_tracks_from_sv_detections(sv_ball)
            del sv_ball
            save_stub(_ball_stub, ball_tracks)
        logger.info("Ball tracks done (%d frames)", len(ball_tracks))

        _progress("keypoint_detection", 45)
        court_keypoints_per_frame = read_stub(use_stubs, _court_stub)
        if court_keypoints_per_frame is None:
            court_keypoints_per_frame = court_keypoint_detector.get_court_keypoints_streaming(
                input_video, _chunk_size
            )
            save_stub(_court_stub, court_keypoints_per_frame)
        logger.info("Court keypoints done (%d frames)", len(court_keypoints_per_frame))

        _missing_before_sahi = sum(1 for bt in ball_tracks if 1 not in bt)
        if _missing_before_sahi > 0:
            ball_tracks = ball_tracker.refill_missing_with_sahi(input_video, ball_tracks)
        ball_tracks = ball_tracker.remove_wrong_detections(ball_tracks)
        ball_tracks = ball_tracker.interpolate_ball_positions(ball_tracks)

        _progress("team_assignment", 55)
        team_assigner = TeamAssigner(
            team_1_class_name=team1_jersey,
            team_2_class_name=team2_jersey,
        )
        player_assignment = team_assigner.get_player_teams_streaming(
            input_video,
            player_tracks,
            _chunk_size,
            read_from_stub=use_stubs,
            stub_path=_assign_stub,
        )
        logger.info("Team assignment done")

        _progress("pose_estimation", 62)
        if show_poses:
            _pose_stub = os.path.join(stub_path, "pose_sequence_stub.pkl")
            pose_sequence = read_stub(use_stubs, _pose_stub)
            if pose_sequence is None:
                try:
                    from pose_estimator import PoseEstimator
                    _pe = PoseEstimator()
                    logger.info("Running pose estimation (backend=%s)…", _pe._backend)
                    pose_sequence = _pe.estimate_sequence_streaming(
                        input_video, player_tracks, _chunk_size
                    )
                    save_stub(_pose_stub, pose_sequence)
                except Exception as exc:
                    logger.warning("PoseEstimator failed: %s — skipping pose", exc)
                    pose_sequence = [{} for _ in range(len(player_tracks))]
            logger.info("Pose estimation done (%d frames)", len(pose_sequence))
        else:
            logger.info("Pose estimation skipped (show_poses=False)")
            pose_sequence = [{} for _ in range(len(player_tracks))]

        total_frames = len(player_tracks)  # actual frame count after loading

    else:
        # ── Legacy all-at-once path (small videos or when BA_CHUNK_SIZE=0) ──
        logger.info("Legacy inference mode: loading all frames into RAM")
        video_frames = read_video(input_video)
        logger.info("Loaded %d frames", len(video_frames))
        frame_width = video_frames[0].shape[1] if video_frames else frame_width

        _progress("player_tracking", 12)
        _ref_stub = os.path.join(stub_path, "referee_tracks_stub.pkl")
        referee_tracks: list = read_stub(use_stubs, _ref_stub) or []
        player_tracks = player_tracker.get_object_tracks(
            video_frames,
            read_from_stub=use_stubs,
            stub_path=_player_stub,
        )
        logger.info("Player tracks done")

        _progress("ball_tracking", 30)
        ball_tracks = ball_tracker.get_object_tracks(
            video_frames,
            read_from_stub=use_stubs,
            stub_path=_ball_stub,
        )
        logger.info("Ball tracks done")

        _progress("keypoint_detection", 45)
        court_keypoints_per_frame = court_keypoint_detector.get_court_keypoints(
            video_frames,
            read_from_stub=use_stubs,
            stub_path=_court_stub,
        )
        logger.info("Court keypoints done")

        ball_tracks = ball_tracker.remove_wrong_detections(ball_tracks)
        ball_tracks = ball_tracker.interpolate_ball_positions(ball_tracks)

        _progress("team_assignment", 55)
        team_assigner = TeamAssigner(
            team_1_class_name=team1_jersey,
            team_2_class_name=team2_jersey,
        )
        player_assignment = team_assigner.get_player_teams_across_frames(
            video_frames,
            player_tracks,
            read_from_stub=use_stubs,
            stub_path=_assign_stub,
        )
        logger.info("Team assignment done")

        _progress("pose_estimation", 62)
        if show_poses:
            _pose_stub = os.path.join(stub_path, "pose_sequence_stub.pkl")
            pose_sequence = read_stub(use_stubs, _pose_stub)
            if pose_sequence is None:
                try:
                    from pose_estimator import PoseEstimator
                    _pe = PoseEstimator()
                    logger.info("Running pose estimation (backend=%s)…", _pe._backend)
                    pose_sequence = _pe.estimate_sequence(video_frames, player_tracks)
                    save_stub(_pose_stub, pose_sequence)
                except Exception as exc:
                    logger.warning("PoseEstimator failed: %s — skipping pose", exc)
                    pose_sequence = [{} for _ in range(len(video_frames))]
            logger.info("Pose estimation done (%d frames)", len(pose_sequence))
        else:
            logger.info("Pose estimation skipped (show_poses=False)")
            pose_sequence = [{} for _ in range(len(video_frames))]

        total_frames = len(video_frames)  # actual frame count after loading
        del video_frames  # free before draw pass

    # ── Hoop Detection ──────────────────────────────────────────────────────────
    _progress("hoop_detection", 63)
    _hoop_stub = os.path.join(stub_path, "hoop_tracks_stub.pkl")
    hoop_tracks: list = read_stub(use_stubs, _hoop_stub) or []
    if not hoop_tracks:
        try:
            from hoop_detector import HoopDetector
            _hd = HoopDetector()
            logger.info("Running hoop detection…")
            hoop_tracks = _hd.detect_frames_streaming(input_video)
            hoop_tracks = (hoop_tracks + [None] * total_frames)[:total_frames]
            save_stub(_hoop_stub, hoop_tracks)
        except Exception as exc:
            logger.warning("HoopDetector failed: %s — skipping", exc)
            hoop_tracks = [None] * total_frames
    logger.info(
        "Hoop detection done (%d frames, %d with hoop)",
        len(hoop_tracks), sum(1 for h in hoop_tracks if h is not None),
    )

    # ── CV Event Detection (shot, rebound, steal) ───────────────────────────────
    _progress("event_detection", 66)
    _event_stub = os.path.join(stub_path, "cv_events_stub.pkl")
    _ev_cached = read_stub(use_stubs, _event_stub)
    if _ev_cached is not None:
        shot_events = _ev_cached.get("shot_events", [])
        rebound_events = _ev_cached.get("rebound_events", [])
        steal_events = _ev_cached.get("steal_events", [])
    else:
        shot_events: list = []
        rebound_events: list = []
        steal_events: list = []
        try:
            from event_detector import ShotDetector, ReboundDetector, StealTurnoverDetector
            shot_events = ShotDetector().process_sequence(pose_sequence, ball_tracks)
            rebound_events = ReboundDetector().process_sequence(
                pose_sequence, ball_tracks, player_tracks
            )
            steal_events = StealTurnoverDetector().process_sequence(pose_sequence, ball_tracks)
            save_stub(_event_stub, {
                "shot_events": shot_events,
                "rebound_events": rebound_events,
                "steal_events": steal_events,
            })
        except Exception as exc:
            logger.warning("Event detection failed: %s — skipping", exc)
    logger.info(
        "CV events: %d shots, %d rebounds, %d steals",
        len(shot_events), len(rebound_events), len(steal_events),
    )

    # ── DualResolution event windows ────────────────────────────────────────────
    try:
        from dual_resolution import DualResolutionPipeline
        _drp = DualResolutionPipeline()
        event_windows = _drp.find_event_windows(ball_tracks, player_tracks)
        logger.info("DualRes: %d high-action event windows identified", len(event_windows))
    except Exception as exc:
        logger.warning("DualResolutionPipeline failed: %s — skipping", exc)
        event_windows = []

    _progress("ball_acquisition", 65)
    ball_aquisition_detector = BallAquisitionDetector(frame_width=frame_width)
    ball_aquisition = ball_aquisition_detector.detect_ball_possession(
        player_tracks, ball_tracks
    )

    _progress("pass_detection", 68)
    pass_and_interception_detector = PassAndInterceptionDetector()
    passes = pass_and_interception_detector.detect_passes(
        ball_aquisition, player_assignment
    )
    interceptions = pass_and_interception_detector.detect_interceptions(
        ball_aquisition, player_assignment
    )
    logger.info("Passes/interceptions done")

    # Detect court mode (half-court vs full-court)
    court_mode_detector = CourtModeDetector()
    is_half_court = court_mode_detector.detect(court_keypoints_per_frame)
    if is_half_court:
        logger.warning(
            "Half-court detected — speed/distance metrics will be disabled for this video"
        )

    _progress("tactical_view", 72)
    profile = court_profile or CourtProfile(CourtLevel.NBA)

    tactical_view_converter = TacticalViewConverter(
        court_image_path=_court_image_path,
        court_profile=profile,
        manual_landmarks=manual_landmarks,
        camera_motion=camera_motion,
    )
    court_keypoints_per_frame = tactical_view_converter.validate_keypoints(
        court_keypoints_per_frame
    )
    tactical_player_positions = (
        tactical_view_converter.transform_players_to_tactical_view(
            court_keypoints_per_frame, player_tracks
        )
    )

    speed_and_distance_calculator = SpeedAndDistanceCalculator(
        tactical_view_converter.width,
        tactical_view_converter.height,
        tactical_view_converter.actual_width_in_meters,
        tactical_view_converter.actual_height_in_meters,
        fps=actual_fps,
        calibration_factor=profile.calibration_factor,
    )

    if is_half_court:
        # Disable global speed/distance in half-court mode
        player_distances_per_frame = [{} for _ in range(total_frames)]
        player_speed_per_frame = [{} for _ in range(total_frames)]
    else:
        player_distances_per_frame = speed_and_distance_calculator.calculate_distance(
            tactical_player_positions
        )
        player_speed_per_frame = speed_and_distance_calculator.calculate_speed(
            player_distances_per_frame
        )
    logger.info("Speed/distance done")

    _progress("drawing", 78)
    player_tracks_drawer      = PlayerTracksDrawer()
    pose_drawer               = PoseDrawer(player_filter=pose_player_filter)
    ball_tracks_drawer        = BallTracksDrawer()
    court_keypoint_drawer     = CourtKeypointDrawer(
        manual_src=tactical_view_converter._manual_src
    )
    team_ball_control_drawer  = TeamBallControlDrawer()
    frame_number_drawer       = FrameNumberDrawer()
    pass_and_interceptions_drawer = PassInterceptionDrawer()
    tactical_view_drawer      = TacticalViewDrawer()
    speed_and_distance_drawer = SpeedAndDistanceDrawer()

    # Pre-compute team_ball_control array (cheap — just ints, no images)
    team_ball_control = team_ball_control_drawer.get_team_ball_control(
        player_assignment, ball_aquisition
    )

    # Pre-load court image once so tactical drawer doesn't re-read it per frame
    import numpy as _np
    import cv2 as _cv2
    _court_path = tactical_view_converter.court_image_path
    _tac_w = tactical_view_converter.width
    _tac_h = tactical_view_converter.height
    court_image_loaded = _cv2.imread(_court_path) if _court_path else None
    if court_image_loaded is None or court_image_loaded.size == 0:
        court_image_loaded = _np.zeros((_tac_h, _tac_w, 3), dtype=_np.uint8)
        court_image_loaded[:] = (40, 80, 40)
    else:
        court_image_loaded = _cv2.resize(court_image_loaded, (_tac_w, _tac_h))

    # ── Streaming draw pass ──────────────────────────────────────────────────
    # Re-read the source video one frame at a time — no large buffer in memory.

    import shutil as _shutil
    import subprocess as _subprocess
    _is_mp4 = output_video.lower().endswith(".mp4")
    _use_ffmpeg = _is_mp4 and bool(_shutil.which("ffmpeg"))
    _tmp_video = output_video + ".raw.mp4" if _use_ffmpeg else None

    # Determine output frame size from first frame (after potential downscaling)
    _first_frame = None
    for _f in iter_video_frames(input_video):
        if _f.shape[0] > 720:
            _scale = 720 / _f.shape[0]
            _f = _cv2.resize(_f, (int(_f.shape[1] * _scale), 720), interpolation=_cv2.INTER_AREA)
        _first_frame = _f
        break

    if _first_frame is None:
        raise RuntimeError("Could not read any frame from source video for drawing")

    _out_h, _out_w = _first_frame.shape[:2]
    _fourcc = _cv2.VideoWriter_fourcc(*"mp4v")
    _writer_path = _tmp_video if _use_ffmpeg else output_video
    _writer = _cv2.VideoWriter(_writer_path, _fourcc, actual_fps, (_out_w, _out_h))

    _streaming_distances: dict = {}  # accumulated for SpeedAndDistanceDrawer

    for _frame_idx, _frame in enumerate(iter_video_frames(input_video)):
        if _frame_idx >= total_frames:
            break

        # Apply same downscaling as read_video
        if _frame.shape[0] > 720:
            _scale = 720 / _frame.shape[0]
            _frame = _cv2.resize(
                _frame, (int(_frame.shape[1] * _scale), 720),
                interpolation=_cv2.INTER_AREA,
            )

        # Apply all drawers in sequence (each modifies a single frame)
        _frame = player_tracks_drawer.draw_frame(
            _frame, _frame_idx, player_tracks, player_assignment, ball_aquisition
        )
        if show_poses:
            _frame = pose_drawer.draw_frame(_frame, _frame_idx, pose_sequence)
        _frame = ball_tracks_drawer.draw_frame(_frame, _frame_idx, ball_tracks)
        _frame = court_keypoint_drawer.draw_frame(_frame, _frame_idx, court_keypoints_per_frame)
        _frame = frame_number_drawer.draw_frame(_frame, _frame_idx)
        _frame = team_ball_control_drawer.draw_frame(_frame, _frame_idx, team_ball_control)
        _frame = pass_and_interceptions_drawer.draw_frame(
            _frame, _frame_idx, passes, interceptions
        )
        _frame = speed_and_distance_drawer.draw_frame(
            _frame, _frame_idx,
            player_tracks, player_distances_per_frame, player_speed_per_frame,
            _streaming_distances,
        )
        _frame = tactical_view_drawer.draw_frame(
            _frame, _frame_idx,
            court_image_loaded, _tac_w, _tac_h,
            tactical_view_converter.key_points,
            tactical_player_positions,
            player_assignment,
            ball_aquisition,
        )

        _writer.write(_frame)

    _writer.release()
    logger.info("Streaming draw complete: %d frames written", _frame_idx + 1)

    # Re-encode to H.264 for browser compatibility
    if _use_ffmpeg and _tmp_video and os.path.exists(_tmp_video):
        _cmd = [
            "ffmpeg", "-y", "-i", _tmp_video,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-movflags", "+faststart",
            output_video,
        ]
        _result = _subprocess.run(_cmd, capture_output=True)
        try:
            os.remove(_tmp_video)
        except OSError:
            pass
        if _result.returncode != 0:
            logger.warning("ffmpeg re-encode failed: %s", _result.stderr.decode())
            if os.path.exists(_tmp_video):
                os.rename(_tmp_video, output_video)
    logger.info("Saved annotated video to %s", output_video)

    # Build summary metrics
    team1_pos = 0
    team2_pos = 0
    for frame_idx, holder_id in enumerate(ball_aquisition):
        if holder_id == -1:
            continue
        if frame_idx < len(player_assignment):
            team = player_assignment[frame_idx].get(holder_id, -1)
            if team == 1:
                team1_pos += 1
            elif team == 2:
                team2_pos += 1

    team1_passes = sum(1 for p in passes if p == 1)
    team2_passes = sum(1 for p in passes if p == 2)
    team1_interceptions = sum(1 for i in interceptions if i == 1)
    team2_interceptions = sum(1 for i in interceptions if i == 2)

    player_total_distances: dict = {}
    for frame_distances in player_distances_per_frame:
        for pid, dist in frame_distances.items():
            player_total_distances[pid] = player_total_distances.get(pid, 0.0) + dist

    # Per-player speed samples indexed by track_id for avg computation downstream
    player_speed_samples: dict[int, list[float]] = {}
    for frame_speeds in player_speed_per_frame:
        for pid, spd in frame_speeds.items():
            if spd is not None and spd > 0:
                player_speed_samples.setdefault(pid, []).append(float(spd))

    player_avg_speed: dict[int, float] = {
        pid: (sum(samples) / len(samples))
        for pid, samples in player_speed_samples.items()
        if samples
    }

    player_max_speed: dict[int, float] = {
        pid: max(samples)
        for pid, samples in player_speed_samples.items()
        if samples
    }

    metrics = {
        # Summary scalars
        "total_frames": total_frames,
        "team1_possession_frames": team1_pos,
        "team2_possession_frames": team2_pos,
        "team1_passes": team1_passes,
        "team2_passes": team2_passes,
        "team1_interceptions": team1_interceptions,
        "team2_interceptions": team2_interceptions,
        "player_total_distance_m": player_total_distances,
        "player_avg_speed_kmh": player_avg_speed,
        "player_max_speed_kmh": player_max_speed,
        "output_video_path": output_video,
        # Raw per-frame sequences needed by _persist_metrics in the worker
        "ball_acquisition": ball_aquisition,          # list[int] — track_id holding ball, -1 if none
        "player_assignment": player_assignment,       # list[dict[track_id, team_id]]
        "passes": passes,                             # list[int] — team_id that passed, -1 if none
        "interceptions": interceptions,               # list[int] — team_id that intercepted, -1 if none
        "fps": actual_fps,
        "is_half_court": is_half_court,
        # CV event lists from pose-based detectors
        "shot_events": shot_events,
        "rebound_events": rebound_events,
        "steal_events": steal_events,
        # Per-frame hoop bbox (or None when not detected)
        "hoop_tracks": hoop_tracks,
        # Per-frame referee bboxes (negative track IDs to avoid collision)
        "referee_tracks": referee_tracks,
        # High-action frame windows from ball movement analysis [(start, end), ...]
        "event_windows": event_windows,
    }

    return metrics


def main():
    args = parse_args()
    metrics = run_pipeline(
        input_video=args.input_video,
        output_video=args.output_video,
        stub_path=args.stub_path,
        use_stubs=not args.no_stubs,
        team1_jersey=args.team1_jersey,
        team2_jersey=args.team2_jersey,
    )
    logger.info("Pipeline complete. Metrics: %s", metrics)


if __name__ == "__main__":
    main()
