import os
import argparse
import logging

from utils import read_video, save_video, get_video_properties, CourtModeDetector
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
    court_image_path: str = "./images/basketball_court.png",
    player_detector_path: str | None = None,
    ball_detector_path: str | None = None,
    court_kp_detector_path: str = COURT_KEYPOINT_DETECTOR_PATH,
    court_profile: CourtProfile | None = None,
):
    """
    Run the full basketball analysis pipeline on a video file.

    Returns a dict with computed metrics (passes, interceptions, ball acquisition per team,
    player distances and speeds) plus the path to the annotated output video.
    """
    # Resolve model paths: prefer YOLO11 multi-class model when available
    _player_path = player_detector_path or _resolve_detector_path(
        MULTICLASS_DETECTOR_PATH, PLAYER_DETECTOR_PATH
    )
    _ball_path = ball_detector_path or _resolve_detector_path(
        MULTICLASS_DETECTOR_PATH, BALL_DETECTOR_PATH
    )
    logger.info("Player detector: %s", _player_path)
    logger.info("Ball detector:   %s", _ball_path)

    logger.info("Reading video: %s", input_video)
    video_frames = read_video(input_video)
    logger.info("Loaded %d frames", len(video_frames))

    player_tracker = PlayerTracker(_player_path)
    ball_tracker = BallTracker(_ball_path)
    court_keypoint_detector = CourtKeypointDetector(court_kp_detector_path)

    player_tracks = player_tracker.get_object_tracks(
        video_frames,
        read_from_stub=use_stubs,
        stub_path=os.path.join(stub_path, "player_track_stubs.pkl"),
    )
    logger.info("Player tracks done")

    ball_tracks = ball_tracker.get_object_tracks(
        video_frames,
        read_from_stub=use_stubs,
        stub_path=os.path.join(stub_path, "ball_track_stubs.pkl"),
    )
    logger.info("Ball tracks done")

    court_keypoints_per_frame = court_keypoint_detector.get_court_keypoints(
        video_frames,
        read_from_stub=use_stubs,
        stub_path=os.path.join(stub_path, "court_key_points_stub.pkl"),
    )
    logger.info("Court keypoints done")

    ball_tracks = ball_tracker.remove_wrong_detections(ball_tracks)
    ball_tracks = ball_tracker.interpolate_ball_positions(ball_tracks)

    team_assigner = TeamAssigner(
        team_1_class_name=team1_jersey,
        team_2_class_name=team2_jersey,
    )
    player_assignment = team_assigner.get_player_teams_across_frames(
        video_frames,
        player_tracks,
        read_from_stub=use_stubs,
        stub_path=os.path.join(stub_path, "player_assignment_stub.pkl"),
    )
    logger.info("Team assignment done")

    ball_aquisition_detector = BallAquisitionDetector()
    ball_aquisition = ball_aquisition_detector.detect_ball_possession(
        player_tracks, ball_tracks
    )

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

    profile = court_profile or CourtProfile(CourtLevel.NBA)

    tactical_view_converter = TacticalViewConverter(
        court_image_path=court_image_path,
        court_profile=profile,
    )
    court_keypoints_per_frame = tactical_view_converter.validate_keypoints(
        court_keypoints_per_frame
    )
    tactical_player_positions = (
        tactical_view_converter.transform_players_to_tactical_view(
            court_keypoints_per_frame, player_tracks
        )
    )

    # Read actual FPS from the video
    try:
        vid_props = get_video_properties(input_video)
        actual_fps = vid_props["fps"] or 24.0
    except Exception:
        actual_fps = 24.0

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
        player_distances_per_frame = [{} for _ in range(len(video_frames))]
        player_speed_per_frame = [{} for _ in range(len(video_frames))]
    else:
        player_distances_per_frame = speed_and_distance_calculator.calculate_distance(
            tactical_player_positions
        )
        player_speed_per_frame = speed_and_distance_calculator.calculate_speed(
            player_distances_per_frame
        )
    logger.info("Speed/distance done")

    player_tracks_drawer = PlayerTracksDrawer()
    ball_tracks_drawer = BallTracksDrawer()
    court_keypoint_drawer = CourtKeypointDrawer()
    team_ball_control_drawer = TeamBallControlDrawer()
    frame_number_drawer = FrameNumberDrawer()
    pass_and_interceptions_drawer = PassInterceptionDrawer()
    tactical_view_drawer = TacticalViewDrawer()
    speed_and_distance_drawer = SpeedAndDistanceDrawer()

    output_video_frames = player_tracks_drawer.draw(
        video_frames, player_tracks, player_assignment, ball_aquisition
    )
    output_video_frames = ball_tracks_drawer.draw(output_video_frames, ball_tracks)
    output_video_frames = court_keypoint_drawer.draw(
        output_video_frames, court_keypoints_per_frame
    )
    output_video_frames = frame_number_drawer.draw(output_video_frames)
    output_video_frames = team_ball_control_drawer.draw(
        output_video_frames, player_assignment, ball_aquisition
    )
    output_video_frames = pass_and_interceptions_drawer.draw(
        output_video_frames, passes, interceptions
    )
    output_video_frames = speed_and_distance_drawer.draw(
        output_video_frames,
        player_tracks,
        player_distances_per_frame,
        player_speed_per_frame,
    )
    output_video_frames = tactical_view_drawer.draw(
        output_video_frames,
        tactical_view_converter.court_image_path,
        tactical_view_converter.width,
        tactical_view_converter.height,
        tactical_view_converter.key_points,
        tactical_player_positions,
        player_assignment,
        ball_aquisition,
    )

    save_video(output_video_frames, output_video)
    logger.info("Saved annotated video to %s", output_video)

    # Build summary metrics
    total_frames = len(video_frames)

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
        "output_video_path": output_video,
        # Raw per-frame sequences needed by _persist_metrics in the worker
        "ball_acquisition": ball_aquisition,          # list[int] — track_id holding ball, -1 if none
        "player_assignment": player_assignment,       # list[dict[track_id, team_id]]
        "passes": passes,                             # list[int] — team_id that passed, -1 if none
        "interceptions": interceptions,               # list[int] — team_id that intercepted, -1 if none
        "fps": actual_fps,
        "is_half_court": is_half_court,
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
