"""Unit tests for PassAndInterceptionDetector."""
import pytest


def _make_simple_acquisition(sequence: list[int]) -> list[int]:
    """sequence[i] = player_id who has ball at frame i (or -1)."""
    return sequence


def _make_assignment(player_teams: dict[int, int], n_frames: int) -> list[dict]:
    """All frames: same team assignment."""
    return [dict(player_teams)] * n_frames


class TestPassAndInterceptionDetector:
    def setup_method(self):
        from pass_and_interception_detector.pass_and_interception_detector import (
            PassAndInterceptionDetector,
        )
        self.det = PassAndInterceptionDetector()

    def test_pass_same_team(self):
        """Ball changes from player 1 to player 2, both on team 1 → pass."""
        ball_acq = [1, 1, 1, 2, 2, 2]
        assignment = _make_assignment({1: 1, 2: 1}, 6)
        passes = self.det.detect_passes(ball_acq, assignment)
        # A pass should be recorded when possession changes within same team
        assert any(p != -1 for p in passes)

    def test_interception_different_team(self):
        """Ball changes from player 1 (team 1) to player 3 (team 2) → interception."""
        ball_acq = [1, 1, 1, 3, 3, 3]
        assignment = _make_assignment({1: 1, 3: 2}, 6)
        interceptions = self.det.detect_interceptions(ball_acq, assignment)
        assert any(i != -1 for i in interceptions)

    def test_no_event_no_change(self):
        """Constant possession → no passes or interceptions."""
        ball_acq = [1, 1, 1, 1, 1]
        assignment = _make_assignment({1: 1}, 5)
        passes = self.det.detect_passes(ball_acq, assignment)
        interceptions = self.det.detect_interceptions(ball_acq, assignment)
        assert all(p == -1 for p in passes)
        assert all(i == -1 for i in interceptions)

    def test_no_event_no_possession(self):
        """All frames have no possession → no events."""
        ball_acq = [-1, -1, -1, -1]
        assignment = _make_assignment({}, 4)
        passes = self.det.detect_passes(ball_acq, assignment)
        interceptions = self.det.detect_interceptions(ball_acq, assignment)
        assert all(p == -1 for p in passes)
        assert all(i == -1 for i in interceptions)
