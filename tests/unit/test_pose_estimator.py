"""Unit tests for pose_estimator module."""
import math
import sys
import numpy as np
import pytest

from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "basketball_analysis"
sys.path.insert(0, str(_PKG_ROOT))

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


class TestRTMPoseBackend:
    """RTMPose ONNX path (skipped when model or onnxruntime unavailable)."""

    @staticmethod
    def _model_path():
        return _PKG_ROOT / "models" / "rtmpose_body2d.onnx"

    def test_preprocess_blob_shape(self):
        pytest.importorskip("onnxruntime")
        if not self._model_path().is_file():
            pytest.skip("rtmpose_body2d.onnx not present")

        import numpy as np
        from pose_estimator.pose_estimator import _preprocess_rtmpose

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[200:600, 500:700] = 180
        blob, meta = _preprocess_rtmpose(frame, [500, 200, 700, 600], (192, 256))
        assert blob.shape == (1, 3, 256, 192)
        assert "inv_warp" in meta
        assert meta["input_size"] == (192, 256)

    def test_postprocess_simcc_maps_center_to_bbox(self):
        from pose_estimator.pose_estimator import _postprocess_rtmpose, _preprocess_rtmpose

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        bbox = [560.0, 180.0, 720.0, 620.0]
        _blob, meta = _preprocess_rtmpose(frame, bbox, (192, 256))
        inp_w, inp_h = meta["input_size"]
        split = 2.0
        n_kp = 17
        simcc_x = np.full((n_kp, int(inp_w * split)), -10.0, dtype=np.float32)
        simcc_y = np.full((n_kp, int(inp_h * split)), -10.0, dtype=np.float32)
        cx_bin = int(inp_w * split * 0.5)
        cy_bin = int(inp_h * split * 0.5)
        simcc_x[0, cx_bin] = 10.0
        simcc_y[0, cy_bin] = 10.0
        kps = _postprocess_rtmpose((simcc_x, simcc_y), meta)
        assert kps.shape == (17, 3)
        bx_cx = (bbox[0] + bbox[2]) * 0.5
        bx_cy = (bbox[1] + bbox[3]) * 0.5
        assert abs(kps[0, 0] - bx_cx) < 80.0
        assert abs(kps[0, 1] - bx_cy) < 120.0
        assert 0.0 <= kps[0, 2] <= 1.0

    def test_rtmpose_estimate_frame(self, monkeypatch):
        pytest.importorskip("onnxruntime")
        if not self._model_path().is_file():
            pytest.skip("rtmpose_body2d.onnx not present")

        monkeypatch.setenv("BA_POSE_BACKEND", "rtmpose")
        monkeypatch.delenv("BA_DUMMY_MODELS", raising=False)
        monkeypatch.setenv("BA_POSE_ORT_CPU", "1")

        import importlib
        import pose_estimator.pose_estimator as pe_mod

        importlib.reload(pe_mod)

        pe = pe_mod.PoseEstimator()
        if pe._backend != "rtmpose":
            pytest.skip("RTMPose session could not be loaded")

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[180:620, 560:720] = (200, 180, 160)
        tracks = {1: {"bbox": [560, 180, 720, 620]}}
        result = pe.estimate_frame(frame, tracks)
        assert 1 in result
        kps = result[1]
        assert kps.shape == (17, 3)
        assert np.all(np.isfinite(kps))
        assert np.all((kps[:, 2] >= 0.0) & (kps[:, 2] <= 1.0))
        h, w = frame.shape[:2]
        assert np.all(kps[:, 0] >= -w * 0.5) and np.all(kps[:, 0] <= w * 1.5)
        assert np.all(kps[:, 1] >= -h * 0.5) and np.all(kps[:, 1] <= h * 1.5)
