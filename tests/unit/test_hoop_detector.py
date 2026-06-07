"""Unit tests for hoop_detector module."""
import sys
import numpy as np
import pytest

sys.path.insert(0, "Z:/code/basketball_analysis/basketball_analysis")

from hoop_detector import HoopDetector


class TestHoopDetectorDummy:
    def setup_method(self):
        self.hd = HoopDetector(dummy=True)

    def test_detect_returns_four_coords(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        bbox = self.hd.detect(frame)
        assert bbox is not None
        assert len(bbox) == 4

    def test_detect_coords_in_frame(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        x1, y1, x2, y2 = self.hd.detect(frame)
        assert 0 <= x1 < x2 <= 1280
        assert 0 <= y1 < y2 <= 720

    def test_detect_sequence(self):
        frames = [np.zeros((480, 640, 3), dtype=np.uint8)] * 3
        results = self.hd.detect_sequence(frames)
        assert len(results) == 3
        assert all(r is not None for r in results)


class TestHoopDetectorStaticHelpers:
    def test_get_hoop_center(self):
        bbox = {"bbox": [100, 50, 200, 100]}
        center = HoopDetector.get_hoop_center(bbox)
        assert center == pytest.approx((150, 75))

    def test_get_hoop_center_empty(self):
        assert HoopDetector.get_hoop_center({}) is None
        assert HoopDetector.get_hoop_center({"bbox": []}) is None

    def test_get_best_hoop_bbox_returns_highest_conf(self):
        dets = [
            {"bbox": [0, 0, 10, 10], "conf": 0.5},
            {"bbox": [100, 100, 200, 200], "conf": 0.9},
            {"bbox": [50, 50, 60, 60], "conf": 0.3},
        ]
        best = HoopDetector.get_best_hoop_bbox(dets)
        assert best is not None
        assert best["conf"] == 0.9

    def test_get_best_hoop_bbox_empty(self):
        assert HoopDetector.get_best_hoop_bbox([]) is None
