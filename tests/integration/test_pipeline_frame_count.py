"""
Integration test: regression for the 'frame 0 skipped' bug.

Validates that len(output_video) == len(input_video) for a synthetic 30-frame clip.
This test runs on CPU (no GPU required) using pre-built stubs.

Requirements: opencv-python-headless, numpy (no YOLO needed, stubs are used).
"""
import os
import sys
import tempfile
import pytest

# Skip if cv2 not available
cv2 = pytest.importorskip("cv2", reason="opencv not installed")


def _count_video_frames(path: str) -> int:
    cap = cv2.VideoCapture(path)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return count


@pytest.mark.integration
def test_output_frame_count_equals_input():
    """
    The annotated output video must have the same number of frames as the input.

    This is the regression test for the 'frame 0 skipped' bug in
    team_ball_control_drawer.py and pass_and_interceptions_drawer.py.
    """
    from tests.integration.synthetic_video import make_synthetic_video, make_synthetic_stubs

    n_frames = 30
    with tempfile.TemporaryDirectory() as tmp:
        video_path = make_synthetic_video(n_frames=n_frames, output_path=os.path.join(tmp, "input.avi"))
        stub_dir = make_synthetic_stubs(n_frames=n_frames, stub_dir=os.path.join(tmp, "stubs"))
        output_path = os.path.join(tmp, "output.avi")

        # Run pipeline using stubs (no YOLO models needed)
        from utils.video_utils import read_video, save_video
        from ball_aquisition.ball_aquisition_detector import BallAquisitionDetector
        from pass_and_interception_detector.pass_and_interception_detector import PassAndInterceptionDetector
        from drawers.team_ball_control_drawer import TeamBallControlDrawer
        from drawers.pass_and_interceptions_drawer import PassInterceptionDrawer
        from drawers.player_tracks_drawer import PlayerTracksDrawer
        from drawers.ball_tracks_drawer import BallTracksDrawer
        from drawers.frame_number_drawer import FrameNumberDrawer
        from utils.stubs_utils import read_stub
        import pickle

        video_frames = read_video(video_path)
        assert len(video_frames) == n_frames, f"Input video should have {n_frames} frames"

        player_tracks = read_stub(True, os.path.join(stub_dir, "player_track_stubs.pkl"))
        ball_tracks = read_stub(True, os.path.join(stub_dir, "ball_track_stubs.pkl"))
        player_assignment = read_stub(True, os.path.join(stub_dir, "player_assignment_stub.pkl"))

        detector = BallAquisitionDetector(min_frames=3)
        ball_acquisition = detector.detect_ball_possession(player_tracks, ball_tracks)

        pi_detector = PassAndInterceptionDetector()
        passes = pi_detector.detect_passes(ball_acquisition, player_assignment)
        interceptions = pi_detector.detect_interceptions(ball_acquisition, player_assignment)

        # Apply all drawers (including the previously buggy ones)
        frames = PlayerTracksDrawer().draw(video_frames, player_tracks, player_assignment, ball_acquisition)
        frames = BallTracksDrawer().draw(frames, ball_tracks)
        frames = FrameNumberDrawer().draw(frames)
        frames = TeamBallControlDrawer().draw(frames, player_assignment, ball_acquisition)
        frames = PassInterceptionDrawer().draw(frames, passes, interceptions)

        assert len(frames) == n_frames, (
            f"Output should have {n_frames} frames but got {len(frames)}"
        )

        save_video(frames, output_path)
        saved_count = _count_video_frames(output_path)
        assert saved_count == n_frames, (
            f"Saved video has {saved_count} frames, expected {n_frames}"
        )
