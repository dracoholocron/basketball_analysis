"""
Unit tests for BallAquisitionDetector.

Uses fully synthetic bounding boxes — no YOLO models required.
"""
import pytest


def _make_player_tracks(positions: list[dict]) -> list[dict]:
    """Build player_tracks list from {player_id: (cx, cy, w, h)} dicts."""
    frames = []
    for frame in positions:
        frame_tracks = {}
        for pid, (cx, cy, w, h) in frame.items():
            frame_tracks[pid] = {"bbox": [cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2]}
        frames.append(frame_tracks)
    return frames


def _make_ball_tracks(positions: list[tuple | None]) -> list[dict]:
    """Build ball_tracks list from (cx, cy, w, h) tuples or None."""
    frames = []
    for pos in positions:
        if pos is None:
            frames.append({})
        else:
            cx, cy, w, h = pos
            frames.append({1: {"bbox": [cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2]}})
    return frames


class TestBallAquisitionDetector:
    def setup_method(self):
        from ball_aquisition.ball_aquisition_detector import BallAquisitionDetector
        # Use min_frames=3 for fast tests
        self.det = BallAquisitionDetector(min_frames=3, possession_threshold=60, containment_threshold=0.8)

    def test_high_containment_wins(self):
        """Player whose bbox fully contains the ball should win over distant player."""
        # Player 1: ball is fully inside (containment = 1.0)
        # Player 2: ball is far away
        player_tracks = _make_player_tracks([
            {1: (100, 100, 80, 120), 2: (300, 300, 60, 90)}
        ] * 5)
        # Ball centered on player 1's bbox
        ball_tracks = _make_ball_tracks([(100, 100, 20, 20)] * 5)

        result = self.det.detect_ball_possession(player_tracks, ball_tracks)
        # After min_frames confirmed possession, player 1 should hold it
        assert any(r == 1 for r in result), f"Expected player 1 to hold ball, got {result}"

    def test_min_frames_respected(self):
        """Possession should not be confirmed until min_frames consecutive frames."""
        player_tracks = _make_player_tracks([{1: (100, 100, 80, 120)}] * 2)
        ball_tracks = _make_ball_tracks([(100, 100, 20, 20)] * 2)
        result = self.det.detect_ball_possession(player_tracks, ball_tracks)
        # Only 2 frames, min_frames=3 → should be all -1
        assert all(r == -1 for r in result), f"Expected no possession yet, got {result}"

    def test_no_ball_no_possession(self):
        """If ball is missing all frames, possession list should be all -1."""
        player_tracks = _make_player_tracks([{1: (100, 100, 80, 120)}] * 10)
        ball_tracks = _make_ball_tracks([None] * 10)
        result = self.det.detect_ball_possession(player_tracks, ball_tracks)
        assert all(r == -1 for r in result)

    def test_distance_fallback(self):
        """When no high containment, closest player within threshold should win."""
        # Player 1 at (100, 100), Player 2 at (200, 200)
        # Ball at (105, 100) — very close to player 1, far from player 2
        player_tracks = _make_player_tracks([
            {1: (100, 100, 30, 50), 2: (200, 200, 30, 50)}
        ] * 5)
        ball_tracks = _make_ball_tracks([(105, 100, 15, 15)] * 5)
        # containment will be < threshold, but distance to player 1 is ~5px
        det = type(self.det)(min_frames=3, possession_threshold=60, containment_threshold=0.99)
        result = det.detect_ball_possession(player_tracks, ball_tracks)
        assert any(r == 1 for r in result), f"Expected player 1 closest, got {result}"

    def test_possession_resets_on_lost_ball(self):
        """Losing the ball for N frames should reset the consecutive count."""
        # 2 frames with ball on player 1, then 2 frames no ball, then 2 frames again
        player_tracks = _make_player_tracks([{1: (100, 100, 80, 120)}] * 6)
        ball_tracks = _make_ball_tracks(
            [(100, 100, 20, 20), (100, 100, 20, 20), None, None, (100, 100, 20, 20), (100, 100, 20, 20)]
        )
        result = self.det.detect_ball_possession(player_tracks, ball_tracks)
        # With min_frames=3, the 2+2 pattern should not confirm possession
        assert result[1] == -1  # only 2 frames, not 3
        assert result[4] == -1  # reset + only 2 frames again
