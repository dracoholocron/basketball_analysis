"""Unit tests for pose_estimator module."""
import math
import sys
import numpy as np
import pytest

sys.path.insert(0, "Z:/code/basketball_analysis/basketball_analysis")

from pose_estimator.skeleton_utils import (
    KP, COCO_KEYPOINTS, COCO_SKELETON, joint_angle, wrist_position, hip_center,
)
from pose_estimator import PoseEstimator


def _kps(**kwargs) -> np.ndarray:
    kps = np.zeros((17, 3), dtype=np.float32)
    for name, (x, y) in kwargs.items():
        kps[KP[name]] = [x, y, 0.9]
    return kps


class TestSkeletonUtils:
    def test_coco_keypoints_count(self):
        assert len(COCO_KEYPOINTS) == 17

    def test_coco_skeleton_is_pairs(self):
        for pair in COCO_SKELETON:
            assert len(pair) == 2
            assert all(0 <= i < 17 for i in pair)

    def test_kp_index_map_complete(self):
        expected = ["nose", "left_eye", "right_eye", "left_ear", "right_ear",
                    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                    "left_wrist", "right_wrist", "left_hip", "right_hip",
                    "left_knee", "right_knee", "left_ankle", "right_ankle"]
        for key in expected:
            assert key in KP

    def test_joint_angle_right_angle(self):
        # A=(0,0), B=(1,0), C=(1,1) → 90° at B
        kps = np.array([[0,0,0.9],[1,0,0.9],[1,1,0.9]], dtype=np.float32)
        angle = joint_angle(kps, 0, 1, 2)
        assert angle is not None
        assert abs(angle - 90.0) < 1e-3

    def test_joint_angle_straight(self):
        kps = np.array([[0,0,0.9],[1,0,0.9],[2,0,0.9]], dtype=np.float32)
        angle = joint_angle(kps, 0, 1, 2)
        assert angle is not None
        assert abs(angle - 180.0) < 0.1

    def test_joint_angle_low_confidence(self):
        kps = np.array([[0,0,0.1],[1,0,0.9],[2,0,0.9]], dtype=np.float32)
        assert joint_angle(kps, 0, 1, 2) is None

    def test_joint_angle_out_of_bounds(self):
        kps = np.zeros((5, 3), dtype=np.float32)
        assert joint_angle(kps, 0, 1, 20) is None

    def test_wrist_position_right(self):
        kps = _kps(right_wrist=(100, 200))
        pos = wrist_position(kps, "right")
        assert pos is not None
        assert pos == pytest.approx((100, 200))

    def test_wrist_position_invisible(self):
        kps = np.zeros((17, 3), dtype=np.float32)
        assert wrist_position(kps, "right") is None

    def test_hip_center(self):
        kps = _kps(left_hip=(100, 200), right_hip=(200, 200))
        center = hip_center(kps)
        assert center is not None
        assert center == pytest.approx((150, 200))


class TestPoseEstimatorDummy:
    def setup_method(self):
        self.pe = PoseEstimator(dummy=True)

    def test_backend_is_dummy(self):
        assert self.pe._backend == "dummy"

    def test_estimate_frame_returns_17_kps(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracks = {1: {"bbox": [100, 100, 200, 300]}}
        result = self.pe.estimate_frame(frame, tracks)
        assert 1 in result
        assert result[1].shape == (17, 3)

    def test_estimate_frame_empty_tracks(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = self.pe.estimate_frame(frame, {})
        assert result == {}

    def test_estimate_sequence_length(self):
        frames = [np.zeros((480, 640, 3), dtype=np.uint8)] * 5
        tracks = [{1: {"bbox": [100, 100, 200, 300]}}] * 5
        seq = self.pe.estimate_sequence(frames, tracks)
        assert len(seq) == 5
        assert all(1 in f for f in seq)

    def test_keypoints_to_serializable(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracks = {1: {"bbox": [0, 0, 100, 200]}, 2: {"bbox": [200, 0, 300, 200]}}
        pose_seq = [self.pe.estimate_frame(frame, tracks)]
        serial = self.pe.keypoints_to_serializable(pose_seq)
        assert len(serial) == 2
        rec = serial[0]
        assert "track_id" in rec
        assert "frame" in rec
        assert "keypoints" in rec
        assert len(rec["keypoints"]) == 17
        assert len(rec["keypoints"][0]) == 3
