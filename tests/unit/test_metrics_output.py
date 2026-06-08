"""
Unit tests for metrics output from the pipeline.

Uses stubs/synthetic data to verify that player_max_speed_kmh is populated
and not trivially zero when there is real movement.
"""
import pytest


def _build_speed_samples(n_frames: int, speed: float) -> list[dict]:
    """Return a list of per-frame speed dicts for player 1."""
    frames = [{1: speed}] * n_frames
    frames[0] = {}
    return frames


class TestMetricsOutput:
    def test_max_speed_non_zero_with_movement(self):
        """player_max_speed_kmh should be > 0 when player speed samples exist."""
        from speed_and_distance_calculator.speed_and_distance_calculator import (
            SpeedAndDistanceCalculator,
        )

        calc = SpeedAndDistanceCalculator(
            width_in_pixels=300,
            height_in_pixels=161,
            width_in_meters=28.0,
            height_in_meters=15.0,
            fps=24.0,
            window_size=5,
            max_speed_kmh=40.0,
        )
        distances = _build_speed_samples(30, 0.5)
        speeds = calc.calculate_speed(distances, fps=24.0)

        # Simulate the main.py aggregation logic
        player_speed_samples: dict[int, list[float]] = {}
        for frame_speeds in speeds:
            for pid, spd in frame_speeds.items():
                if spd is not None and spd > 0:
                    player_speed_samples.setdefault(pid, []).append(float(spd))

        player_max_speed = {
            pid: max(samples)
            for pid, samples in player_speed_samples.items()
            if samples
        }

        assert 1 in player_max_speed, "Player 1 should have a max speed entry"
        assert player_max_speed[1] > 0.0, "Max speed should be > 0 for a moving player"
        assert player_max_speed[1] <= 40.0, "Max speed must respect the 40 km/h cap"

    def test_max_speed_no_samples_gives_empty_dict(self):
        """If a player never has valid speed (all 0), their entry is absent from max speed."""
        player_speed_samples: dict[int, list[float]] = {}
        # player 1 has no speed > 0
        for spd in [0.0, 0.0, 0.0]:
            if spd > 0:
                player_speed_samples.setdefault(1, []).append(spd)

        player_max_speed = {
            pid: max(samples)
            for pid, samples in player_speed_samples.items()
            if samples
        }
        assert 1 not in player_max_speed
