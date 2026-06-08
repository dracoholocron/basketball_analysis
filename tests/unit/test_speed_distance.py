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
        Player moves at constant 0.1m/frame at 24fps = 0.1 * 24 * 3.6 km/h = 8.64 km/h.
        Uses a realistic speed so the 40 km/h cap does not interfere.
        """
        distances = [{1: 0.1}] * 30
        distances[0] = {}
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
        non_zero_speeds = [s[1] for s in speeds if 1 in s and s[1] > 0]
        assert len(non_zero_speeds) > 0
        # 0.1m/frame * 24fps * 3.6 = 8.64 km/h
        expected_speed = (0.1 / 1000) / (1 / 3600 / 24)
        for spd in non_zero_speeds:
            assert math.isclose(spd, expected_speed, rel_tol=0.05), (
                f"Expected ≈{expected_speed:.2f} km/h, got {spd:.2f}"
            )

    def test_speed_clamped_at_40_kmh(self):
        """Positions that would yield >40 km/h must be clamped to 40."""
        from speed_and_distance_calculator.speed_and_distance_calculator import (
            SpeedAndDistanceCalculator,
        )
        calc = SpeedAndDistanceCalculator(
            width_in_pixels=300,
            height_in_pixels=161,
            width_in_meters=28.0,
            height_in_meters=15.0,
            fps=24.0,
            calibration_factor=1.0,
            window_size=5,
            max_speed_kmh=40.0,
        )
        # 2.8m/frame at 24fps ≈ 241.9 km/h — should be clamped to 40
        distances = [{1: 2.8}] * 30
        distances[0] = {}
        speeds = calc.calculate_speed(distances, fps=24.0)
        non_zero = [s[1] for s in speeds if 1 in s and s[1] > 0]
        assert len(non_zero) > 0
        for spd in non_zero:
            assert spd <= 40.0, f"Speed {spd:.1f} km/h exceeded 40 km/h cap"

    def test_max_speed_computed(self):
        """player_max_speed should be >= player_avg_speed for any player."""
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
        # Vary distances to get different speeds across frames
        distances = [{1: 0.5 + (i % 5) * 0.1} for i in range(30)]
        distances[0] = {}
        speeds = calc.calculate_speed(distances, fps=24.0)
        samples = [s[1] for s in speeds if 1 in s and s[1] > 0]
        assert samples, "Expected speed samples"
        avg_speed = sum(samples) / len(samples)
        max_speed = max(samples)
        assert max_speed >= avg_speed

    def test_speed_window_25_frames(self):
        """Window size of 25 frames should require 25 distance samples before reporting speed."""
        from speed_and_distance_calculator.speed_and_distance_calculator import (
            SpeedAndDistanceCalculator,
        )
        calc = SpeedAndDistanceCalculator(
            width_in_pixels=300,
            height_in_pixels=161,
            width_in_meters=28.0,
            height_in_meters=15.0,
            fps=24.0,
            window_size=25,
            max_speed_kmh=40.0,
        )
        distances = [{1: 0.5}] * 30
        distances[0] = {}
        speeds = calc.calculate_speed(distances, fps=24.0)
        # frames before window fills should report 0.0 (or absent)
        early_speeds = [s.get(1, 0.0) for s in speeds[:24]]
        assert all(spd == 0.0 for spd in early_speeds), (
            f"Expected no speed before window fills, got {early_speeds}"
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

    def test_regression_no_speed_inflation(self):
        """Regression: with the 40 km/h cap, average reported speed must be <= 40 km/h."""
        from speed_and_distance_calculator.speed_and_distance_calculator import (
            SpeedAndDistanceCalculator,
        )
        calc = SpeedAndDistanceCalculator(
            width_in_pixels=300,
            height_in_pixels=161,
            width_in_meters=28.0,
            height_in_meters=15.0,
            fps=24.0,
            window_size=25,
            max_speed_kmh=40.0,
        )
        # Simulate noisy large movements that would previously inflate speed
        import random
        random.seed(42)
        distances = [{1: random.uniform(0.1, 5.0)} for _ in range(60)]
        distances[0] = {}
        speeds = calc.calculate_speed(distances, fps=24.0)
        non_zero = [s[1] for s in speeds if 1 in s and s[1] > 0]
        assert non_zero, "Should have some speed readings"
        avg = sum(non_zero) / len(non_zero)
        assert avg <= 40.0, f"Average speed {avg:.1f} km/h exceeds the 40 km/h cap"
        assert all(s <= 40.0 for s in non_zero), "All speeds must be <= 40 km/h"
