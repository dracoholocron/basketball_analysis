"""
Validate RTMPose backend: load ONNX, run one frame, check output shape and ranges.

Usage (from basketball_analysis/):
    $env:BA_POSE_BACKEND="rtmpose"
    $env:BA_POSE_ORT_CPU="1"
    python scripts/validate_rtmpose.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("BA_POSE_BACKEND", "rtmpose")
os.environ.pop("BA_DUMMY_MODELS", None)
os.environ.setdefault("BA_POSE_ORT_CPU", "1")

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pose_estimator import PoseEstimator  # noqa: E402


def _synthetic_frame(h: int = 720, w: int = 1280) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    y_grid, x_grid = np.mgrid[0:h, 0:w]
    frame[..., 0] = (x_grid * 255 // max(w - 1, 1)).astype(np.uint8)
    frame[..., 1] = (y_grid * 255 // max(h - 1, 1)).astype(np.uint8)
    frame[..., 2] = 128
    cx, cy = w // 2, h // 2
    bw, bh = 160, 400
    x1, x2 = cx - bw // 2, cx + bw // 2
    y1, y2 = cy - bh // 2, cy + bh // 2
    frame[y1:y2, x1:x2] = (200, 180, 160)
    return frame


def _print_onnx_io() -> None:
    try:
        import onnxruntime as ort
        from pathlib import Path

        onnx_path = Path(_ROOT) / "models" / "rtmpose_body2d.onnx"
        if not onnx_path.is_file():
            print(f"  ONNX not found: {onnx_path}")
            return
        sess = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        inp = sess.get_inputs()[0]
        print("  ONNX inputs:", [(i.name, i.shape) for i in sess.get_inputs()])
        outs = [(o.name, o.shape) for o in sess.get_outputs()]
        print("  ONNX outputs:", outs)
        shape = inp.shape
        in_h = int(shape[2]) if isinstance(shape[2], int) else 256
        in_w = int(shape[3]) if isinstance(shape[3], int) else 192
        print(f"  input (H, W): ({in_h}, {in_w})")
        if outs and len(outs[0][1]) >= 2 and isinstance(outs[0][1][1], int):
            print(f"  inferred keypoints (output dim 1): {outs[0][1][1]}")
        for name, oshape in outs:
            if not oshape or not isinstance(oshape[-1], int):
                continue
            last = oshape[-1]
            if last % in_w == 0:
                print(f"  {name}: SimCC bins={last}, split_ratio vs W={last / in_w:.2f}")
            if last % in_h == 0 and last != in_w:
                print(f"  {name}: SimCC bins={last}, split_ratio vs H={last / in_h:.2f}")
    except Exception as exc:
        print(f"  ONNX inspect skipped: {exc}")


def main() -> int:
    print("RTMPose validation")
    _print_onnx_io()

    frame = _synthetic_frame()
    h, w = frame.shape[:2]
    tracks = {1: {"bbox": [w // 2 - 80, h // 4, w // 2 + 80, 3 * h // 4]}}

    pe = PoseEstimator()
    assert pe._backend == "rtmpose", f"expected rtmpose backend, got {pe._backend}"

    out = pe.estimate_frame(frame, tracks)
    assert 1 in out, "missing track_id 1 in pose output"
    kps = out[1]
    assert kps.shape == (17, 3), f"expected (17, 3), got {kps.shape}"
    assert np.all(np.isfinite(kps)), "non-finite keypoint values"

    margin_x, margin_y = w * 0.35, h * 0.35
    assert np.all(kps[:, 0] >= -margin_x) and np.all(kps[:, 0] <= w + margin_x)
    assert np.all(kps[:, 1] >= -margin_y) and np.all(kps[:, 1] <= h + margin_y)
    assert np.all(kps[:, 2] >= 0.0) and np.all(kps[:, 2] <= 1.0)

    conf_mean = float(np.mean(kps[:, 2]))
    print("RTMPose validation OK")
    print(f"  backend: {pe._backend}")
    print(f"  input_size (W,H): {pe._rtm_input_size}")
    print(f"  keypoints shape: {kps.shape}")
    print(f"  mean confidence: {conf_mean:.4f}")
    print(f"  x range: [{kps[:, 0].min():.1f}, {kps[:, 0].max():.1f}]")
    print(f"  y range: [{kps[:, 1].min():.1f}, {kps[:, 1].max():.1f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
