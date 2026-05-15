"""
Unit tests for SpeedAndDistanceCalculator.

Uses known positions to verify:
- meter distance calculation (no magic 0.4 factor anymore)
- speed in km/h for a known linear trajectory
"""
import math
import pytest


class TestSpeedAndDistanceCalculator:
    def setup_method(self):
        from speed_and_distance_calculator.speed_and_distance_calculator import (
            SpeedAndDistanceCalculator,
        )
        # 300px × 161px canvas = 28m × 15m, 24 fps
        self.calc = SpeedAndDistanceCalculator(
            width_in_pixels=300,
            height_in_pixels=161,
            width_in_meters=28.0,
            height_in_meters=15.0,
            fps=24.0,
            calibration_factor=1.0,
        )

    def test_meter_distance_known(self):
        """
        Moving from (0,0) to (300,0) in pixels = moving 28m horizontally.
        """
        dist = self.calc._calculate_meter_distance((0, 0), (300, 0))
        assert math.isclose(dist, 28.0, rel_tol=1e-5)

    def test_meter_distance_diagonal(self):
        """
        From (0,0) to (300,161): 28m × 15m diagonal = sqrt(28²+15²) ≈ 31.78m
        """
        dist = self.calc._calculate_meter_distance((0, 0), (300, 161))
        expected = math.sqrt(28**2 + 15**2)
        assert math.isclose(dist, expected, rel_tol=1e-4)

    def test_calculate_distance_returns_per_frame(self):
        """calculate_distance returns one dict per frame."""
        positions = [
            {1: [0, 0]},
            {1: [30, 0]},  # 2.8m in 1 frame
            {1: [60, 0]},
        ]
        distances = self.calc.calculate_distance(positions)
        assert len(distances) == 3
        assert 1 not in distances[0]  # first frame has no previous
        assert 1 in distances[1]
        assert math.isclose(distances[1][1], 2.8, rel_tol=1e-4)

    def test_calculate_speed_known_velocity(self):
        """
        Player moves at constant 2.8m/frame at 24fps = 2.8 * 24 * 3.6 km/h ≈ 241.9 km/h.
        (unrealistic but deterministic for testing)
        """
        # Build distances of exactly 2.8m/frame for 20 frames
        distances = [{1: 2.8}] * 20
        # Insert a frame-0 placeholder (no distance there)
        distances[0] = {}
        # Recalculate with window_size=5
        calc = type(self.calc)(
            width_in_pixels=300,
            height_in_pixels=161,
            width_in_meters=28.0,
            height_in_meters=15.0,
            fps=24.0,
            calibration_factor=1.0,
            window_size=5,
        )
        speeds = calc.calculate_speed(distances, fps=24.0)
        # After enough frames, speed should stabilise
        non_zero_speeds = [s[1] for s in speeds if 1 in s and s[1] > 0]
        assert len(non_zero_speeds) > 0
        expected_speed = (2.8 / 1000) / (1 / 3600 / 24)
        for spd in non_zero_speeds:
            assert math.isclose(spd, expected_speed, rel_tol=0.05), (
                f"Expected ≈{expected_speed:.1f} km/h, got {spd:.1f}"
            )

    def test_court_profiles_scale_distances(self):
        """Smaller court (primaria) → different meter distance for same pixel movement."""
        from speed_and_distance_calculator.speed_and_distance_calculator import (
            SpeedAndDistanceCalculator,
        )
        from configs.settings import CourtProfile, CourtLevel

        profile = CourtProfile.from_level(CourtLevel.PRIMARIA)
        calc = SpeedAndDistanceCalculator(
            width_in_pixels=profile.display_w_px,
            height_in_pixels=profile.display_h_px,
            width_in_meters=profile.width_m,
            height_in_meters=profile.height_m,
        )
        # 260px wide = 24m wide
        dist = calc._calculate_meter_distance((0, 0), (260, 0))
        assert math.isclose(dist, 24.0, rel_tol=1e-4)
