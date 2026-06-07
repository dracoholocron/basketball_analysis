"""
PoseEstimator — wraps RTMPose (ONNX, 133-keypoint Wholebody) or falls back to
YOLO-pose (17-keypoint COCO) when the ONNX model is unavailable.

RTMPose model expected at:
    basketball_analysis/models/rtmpose_body2d.onnx
    basketball_analysis/models/rtmpose_body2d.data   (external ONNX data file)

Environment variables
---------------------
BA_DUMMY_MODELS=1   Force dummy mode (synthetic sine-wave keypoints, no GPU needed).
BA_POSE_BACKEND     'rtmpose' | 'yolo' | 'auto' (default: 'auto')
                    'auto' tries RTMPose first, then YOLO, then dummy.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

from .skeleton_utils import COCO_KEYPOINTS, KP

log = logging.getLogger(__name__)

_DUMMY_MODE: bool = os.environ.get("BA_DUMMY_MODELS", "").lower() in ("1", "true", "yes")
_POSE_BACKEND: str = os.environ.get("BA_POSE_BACKEND", "auto").lower()

# ── RTMPose 133-keypoint → COCO-17 index mapping ──────────────────────────────
# The Wholebody-133 model outputs 133 keypoints per person.
# The first 17 indices correspond 1-to-1 with COCO-17.
_RTM133_TO_COCO17 = list(range(17))   # identity mapping for body keypoints


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_model_path(filename: str) -> Optional[Path]:
    """Search for a model file relative to the package root."""
    base = Path(__file__).resolve().parent.parent  # basketball_analysis/
    candidates = [
        base / "models" / filename,
        Path("models") / filename,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_rtmpose() -> Optional[object]:
    """
    Try to load the RTMPose ONNX model via onnxruntime.
    Returns an ort.InferenceSession or None.
    """
    onnx_path = _find_model_path("rtmpose_body2d.onnx")
    if onnx_path is None:
        log.debug("RTMPose ONNX model not found.")
        return None
    try:
        import onnxruntime as ort

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if "CUDAExecutionProvider" in ort.get_available_providers()
            else ["CPUExecutionProvider"]
        )
        sess = ort.InferenceSession(str(onnx_path), providers=providers)
        log.info("RTMPose loaded: %s  (providers=%s)", onnx_path.name, providers)
        return sess
    except Exception as exc:
        log.warning("Could not load RTMPose: %s", exc)
        return None


def _preprocess_rtmpose(
    frame: np.ndarray,
    bbox: list[float],
    input_size: tuple[int, int] = (192, 256),
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Crop and resize the person bbox for RTMPose inference.

    Returns
    -------
    blob   : (1, 3, H, W) float32 normalized image
    center : (cx, cy)
    scale  : pixel size of the crop side
    """
    import cv2

    x1, y1, x2, y2 = [int(v) for v in bbox]
    h_img, w_img = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w_img, x2), min(h_img, y2)

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        blob = np.zeros((1, 3, input_size[1], input_size[0]), dtype=np.float32)
        return blob, np.array([(x1 + x2) / 2, (y1 + y2) / 2]), float(max(x2 - x1, y2 - y1))

    crop_resized = cv2.resize(crop, input_size)
    # Normalize with ImageNet mean/std
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    blob = (crop_resized[..., ::-1].astype(np.float32) / 255.0 - mean) / std
    blob = blob.transpose(2, 0, 1)[np.newaxis]   # (1, 3, H, W)

    center = np.array([(x1 + x2) / 2, (y1 + y2) / 2], dtype=np.float32)
    scale = float(max(x2 - x1, y2 - y1))
    return blob, center, scale


def _postprocess_rtmpose(
    output: np.ndarray,
    center: np.ndarray,
    scale: float,
    bbox: list[float],
    input_size: tuple[int, int] = (192, 256),
    n_coco: int = 17,
) -> np.ndarray:
    """
    Convert RTMPose SimCC output to COCO-17 keypoints in image coordinates.

    The Wholebody-133 model uses SimCC (Simple Coordinate Classification) decoding.
    Output shape: (1, 133, 2*W) or separate x/y logits.

    Returns
    -------
    kps : (17, 3) array of (x, y, confidence) in original image pixels
    """
    x1, y1, x2, y2 = bbox
    crop_w = max(int(x2 - x1), 1)
    crop_h = max(int(y2 - y1), 1)

    # output shape: (1, N_kp, simcc_split_ratio * W or H)
    # We receive a tuple (simcc_x, simcc_y) from the session
    if isinstance(output, (list, tuple)) and len(output) == 2:
        simcc_x, simcc_y = output  # each (1, 133, W*r) and (1, 133, H*r)
    else:
        # Fallback: treat as raw heatmap — pick argmax coords
        heatmap = output[0]  # (133, H, W)
        kps = np.zeros((n_coco, 3), dtype=np.float32)
        for i in range(n_coco):
            idx = int(np.argmax(heatmap[i]))
            hm_h, hm_w = heatmap.shape[1], heatmap.shape[2]
            ky, kx = divmod(idx, hm_w)
            conf = float(heatmap[i].max())
            kps[i] = [
                x1 + kx / hm_w * crop_w,
                y1 + ky / hm_h * crop_h,
                conf,
            ]
        return kps

    # SimCC decoding
    simcc_x = simcc_x[0]  # (133, W*r)
    simcc_y = simcc_y[0]  # (133, H*r)

    kps = np.zeros((n_coco, 3), dtype=np.float32)
    for i in range(n_coco):
        x_idx = int(np.argmax(simcc_x[i]))
        y_idx = int(np.argmax(simcc_y[i]))
        conf = float(
            (np.exp(simcc_x[i][x_idx]) / np.sum(np.exp(simcc_x[i]))) *
            (np.exp(simcc_y[i][y_idx]) / np.sum(np.exp(simcc_y[i])))
        ) ** 0.5

        # Map back to image coordinates
        px = x1 + x_idx / simcc_x.shape[1] * crop_w
        py = y1 + y_idx / simcc_y.shape[1] * crop_h
        kps[i] = [px, py, conf]

    return kps


# ── PoseEstimator class ────────────────────────────────────────────────────────

class PoseEstimator:
    """
    Estimate 2-D body keypoints for each tracked player.

    Backends (auto-detected):
    1. RTMPose ONNX (Wholebody-133, preferred — most accurate for sports)
    2. YOLO-pose (COCO-17, fallback)
    3. Dummy (synthetic sine-wave data, for testing / BA_DUMMY_MODELS=1)

    Parameters
    ----------
    model_path : optional path override for the YOLO-pose backend
    dummy : force dummy mode regardless of environment variable
    """

    def __init__(self, model_path: Optional[str] = None, dummy: bool = False) -> None:
        self._dummy = dummy or _DUMMY_MODE
        self._backend = "dummy"
        self._session = None
        self._yolo_model = None

        if not self._dummy:
            if _POSE_BACKEND in ("rtmpose", "auto"):
                self._session = _load_rtmpose()
                if self._session is not None:
                    self._backend = "rtmpose"

            if self._session is None and _POSE_BACKEND in ("yolo", "auto"):
                self._yolo_model = self._try_load_yolo(model_path)
                if self._yolo_model is not None:
                    self._backend = "yolo"

            if self._session is None and self._yolo_model is None:
                log.warning(
                    "No pose model found — falling back to dummy mode. "
                    "Set BA_DUMMY_MODELS=0 and place RTMPose ONNX files in models/."
                )
                self._dummy = True

        log.info("PoseEstimator backend: %s", self._backend)

    @staticmethod
    def _try_load_yolo(model_path: Optional[str] = None) -> Optional[object]:
        yolo_path = model_path or _find_model_path("yolov8n-pose.pt")
        if yolo_path is None:
            return None
        try:
            from ultralytics import YOLO
            return YOLO(str(yolo_path))
        except Exception as exc:
            log.warning("Could not load YOLO-pose: %s", exc)
            return None

    # ── Public API ─────────────────────────────────────────────────────────────

    def estimate_frame(
        self,
        frame: np.ndarray,
        player_tracks: dict[int, dict],
    ) -> dict[int, np.ndarray]:
        """
        Run pose estimation for all tracked players in one frame.

        Parameters
        ----------
        frame : BGR numpy array (H, W, 3)
        player_tracks : {track_id: {"bbox": [x1, y1, x2, y2]}}

        Returns
        -------
        {track_id: np.ndarray (17, 3)}  — (x, y, confidence) in image pixels
        """
        if not player_tracks:
            return {}

        if self._dummy:
            return self._dummy_frame(player_tracks)

        if self._backend == "rtmpose":
            return self._rtmpose_frame(frame, player_tracks)

        if self._backend == "yolo":
            return self._yolo_frame(frame, player_tracks)

        return {}

    def estimate_sequence(
        self,
        frames: list[np.ndarray],
        tracks: list[dict[int, dict]],
    ) -> list[dict[int, np.ndarray]]:
        """Run estimate_frame for each frame in a sequence."""
        return [
            self.estimate_frame(frame, player_tracks)
            for frame, player_tracks in zip(frames, tracks)
        ]

    # ── Backend implementations ────────────────────────────────────────────────

    def _rtmpose_frame(
        self,
        frame: np.ndarray,
        player_tracks: dict[int, dict],
    ) -> dict[int, np.ndarray]:
        results: dict[int, np.ndarray] = {}
        input_name = self._session.get_inputs()[0].name
        output_names = [o.name for o in self._session.get_outputs()]

        for track_id, info in player_tracks.items():
            bbox = info.get("bbox", [])
            if len(bbox) < 4:
                continue
            blob, center, scale = _preprocess_rtmpose(frame, bbox)
            raw = self._session.run(output_names, {input_name: blob})
            kps = _postprocess_rtmpose(raw, center, scale, bbox)
            results[track_id] = kps

        return results

    def _yolo_frame(
        self,
        frame: np.ndarray,
        player_tracks: dict[int, dict],
    ) -> dict[int, np.ndarray]:
        results: dict[int, np.ndarray] = {}
        if not player_tracks:
            return results

        yolo_results = self._yolo_model.predict(frame, verbose=False)
        if not yolo_results or yolo_results[0].keypoints is None:
            return results

        kps_all = yolo_results[0].keypoints.data.cpu().numpy()  # (N, 17, 3)
        boxes_all = yolo_results[0].boxes.xyxy.cpu().numpy()    # (N, 4)

        for track_id, info in player_tracks.items():
            bbox = info.get("bbox", [])
            if len(bbox) < 4:
                continue
            # Match track bbox to the nearest YOLO detection
            best_idx, best_iou = -1, 0.0
            for i, yolo_box in enumerate(boxes_all):
                iou = _box_iou(bbox, yolo_box.tolist())
                if iou > best_iou:
                    best_iou, best_idx = iou, i
            if best_idx >= 0 and best_iou > 0.1:
                results[track_id] = kps_all[best_idx]  # (17, 3)

        return results

    def _dummy_frame(
        self,
        player_tracks: dict[int, dict],
        t: float | None = None,
    ) -> dict[int, np.ndarray]:
        import time
        t = t if t is not None else time.time()
        results: dict[int, np.ndarray] = {}
        for track_id, info in player_tracks.items():
            bbox = info.get("bbox", [0, 0, 100, 200])
            x1, y1, x2, y2 = bbox[:4]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            height = y2 - y1

            kps = np.zeros((17, 3), dtype=np.float32)
            for i in range(17):
                kps[i] = [
                    cx + (i - 8) * 5 + 3 * np.sin(t + i),
                    cy - height * 0.4 + i * (height * 0.8 / 16),
                    0.85,
                ]
            results[track_id] = kps
        return results

    # ── Serialisation ──────────────────────────────────────────────────────────

    @staticmethod
    def keypoints_to_serializable(
        pose_sequence: list[dict[int, np.ndarray]],
    ) -> list[dict]:
        """
        Convert a sequence of {track_id: (17,3) array} dicts to JSON-safe dicts.

        Returns
        -------
        [
          {
            "track_id": int,
            "frame": int,
            "keypoints": [[x, y, conf], ...],   # length 17
          },
          ...
        ]
        """
        out: list[dict] = []
        for frame_idx, frame_poses in enumerate(pose_sequence):
            for track_id, kps in frame_poses.items():
                out.append(
                    {
                        "track_id": int(track_id),
                        "frame": frame_idx,
                        "keypoints": kps.tolist(),
                    }
                )
        return out


# ── Geometry helpers ───────────────────────────────────────────────────────────

def _box_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a[:4]
    bx1, by1, bx2, by2 = b[:4]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / max(ua, 1e-6)
