"""
Skeleton utilities for basketball pose analysis.

Supports two keypoint schemas:
  - COCO-17  : standard 17-point body keypoints (used by YOLO-pose)
  - Wholebody-133: RTMPose Wholebody (133 keypoints — body + hands + face + feet)

When using the 133-keypoint model the first 17 indices are body keypoints that
match the COCO-17 layout, so all COCO-17 helpers work unchanged.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

# ── COCO-17 keypoint index map ─────────────────────────────────────────────────
KP: dict[str, int] = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}

# COCO-17 skeleton connectivity (for drawing)
COCO_KEYPOINTS: list[str] = list(KP.keys())

COCO_SKELETON: list[tuple[int, int]] = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

# Wholebody-133: wrist indices (same as COCO-17 for the body portion)
WHOLEBODY_LEFT_WRIST = 9
WHOLEBODY_RIGHT_WRIST = 10

_CONF_THRESHOLD = 0.3   # keypoints below this are treated as invisible


def joint_angle(
    kps: np.ndarray,
    a: int,
    b: int,
    c: int,
    conf_thresh: float = _CONF_THRESHOLD,
) -> Optional[float]:
    """
    Compute the angle at keypoint *b* formed by the triangle a-b-c.

    Parameters
    ----------
    kps : np.ndarray, shape (N, 3)  — (x, y, confidence) per keypoint
    a, b, c : int — keypoint indices
    conf_thresh : float — minimum confidence to consider a keypoint visible

    Returns
    -------
    Angle in degrees, or None if any keypoint is below the confidence threshold.
    """
    if kps.shape[0] <= max(a, b, c):
        return None

    pa, pb, pc = kps[a], kps[b], kps[c]
    if pa[2] < conf_thresh or pb[2] < conf_thresh or pc[2] < conf_thresh:
        return None

    ba = np.array([pa[0] - pb[0], pa[1] - pb[1]], dtype=float)
    bc = np.array([pc[0] - pb[0], pc[1] - pb[1]], dtype=float)

    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    if norm_ba < 1e-6 or norm_bc < 1e-6:
        return None

    cos_angle = np.clip(np.dot(ba, bc) / (norm_ba * norm_bc), -1.0, 1.0)
    return float(math.degrees(math.acos(cos_angle)))


def wrist_position(
    kps: np.ndarray,
    side: str = "right",
    conf_thresh: float = _CONF_THRESHOLD,
) -> Optional[tuple[float, float]]:
    """
    Return (x, y) of the requested wrist, or None if not visible.

    side : 'left' | 'right'
    """
    idx = KP["right_wrist"] if side == "right" else KP["left_wrist"]
    if kps.shape[0] <= idx:
        return None
    kp = kps[idx]
    if kp[2] < conf_thresh:
        return None
    return float(kp[0]), float(kp[1])


def hip_center(
    kps: np.ndarray,
    conf_thresh: float = _CONF_THRESHOLD,
) -> Optional[tuple[float, float]]:
    """Return the midpoint between left and right hips, or None."""
    lh, rh = kps[KP["left_hip"]], kps[KP["right_hip"]]
    if lh[2] < conf_thresh or rh[2] < conf_thresh:
        return None
    return float((lh[0] + rh[0]) / 2), float((lh[1] + rh[1]) / 2)


def shoulder_center(
    kps: np.ndarray,
    conf_thresh: float = _CONF_THRESHOLD,
) -> Optional[tuple[float, float]]:
    """Return the midpoint between left and right shoulders, or None."""
    ls, rs = kps[KP["left_shoulder"]], kps[KP["right_shoulder"]]
    if ls[2] < conf_thresh or rs[2] < conf_thresh:
        return None
    return float((ls[0] + rs[0]) / 2), float((ls[1] + rs[1]) / 2)
