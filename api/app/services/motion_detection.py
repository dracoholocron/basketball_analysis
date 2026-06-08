"""
Camera motion detection using SSIM (Structural Similarity Index).

Samples 5 frames across the video and computes SSIM between the first
frame and each of the others.  Returns a motion classification:

  - "static"   — SSIM avg > 0.90  (camera barely moved)
  - "moderate" — 0.70 ≤ SSIM ≤ 0.90  (some movement; recommend multi-keyframe)
  - "moving"   — SSIM avg < 0.70  (significant movement; multi-keyframe required)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SSIM_HIGH = 0.90
_SSIM_LOW  = 0.70


def detect_camera_motion(video_path: str) -> dict:
    """
    Returns:
        {
            "motion": "static" | "moderate" | "moving",
            "ssim_avg": float,
            "ssim_samples": [float, ...],
        }

    Falls back to {"motion": "unknown"} if cv2 or skimage are unavailable,
    or if the video cannot be read.
    """
    try:
        import cv2
        from skimage.metrics import structural_similarity as ssim  # type: ignore
    except ImportError as exc:
        logger.warning("motion_detection deps missing (%s) — returning unknown", exc)
        return {"motion": "unknown", "ssim_avg": None, "ssim_samples": []}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Cannot open video: %s", video_path)
        return {"motion": "unknown", "ssim_avg": None, "ssim_samples": []}

    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if n_frames < 2:
        cap.release()
        return {"motion": "static", "ssim_avg": 1.0, "ssim_samples": []}

    sample_idxs = [int(n_frames * i / 5) for i in range(5)]
    frames: list = []
    for idx in sample_idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    cap.release()

    if len(frames) < 2:
        return {"motion": "unknown", "ssim_avg": None, "ssim_samples": []}

    # Resize all frames to the same size as frames[0] (should already be same)
    h, w = frames[0].shape
    ssim_vals: list[float] = []
    for other in frames[1:]:
        if other.shape != (h, w):
            other = cv2.resize(other, (w, h))
        score, _ = ssim(frames[0], other, full=True)
        ssim_vals.append(float(score))

    avg = sum(ssim_vals) / len(ssim_vals)

    if avg > _SSIM_HIGH:
        motion = "static"
    elif avg < _SSIM_LOW:
        motion = "moving"
    else:
        motion = "moderate"

    return {"motion": motion, "ssim_avg": round(avg, 4), "ssim_samples": ssim_vals}
