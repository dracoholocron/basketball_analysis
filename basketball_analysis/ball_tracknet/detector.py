"""TrackNetDetector — drop-in ball detector that replaces YOLO for the streaming path.

Usage
-----
det = TrackNetDetector("models/tracknet_ball.pt")
for frame_idx, bbox in det.detect_video(video_path):
    ...   # bbox = [x1,y1,x2,y2] at 720p or None

The detector buffers 3 frames (sliding window) and runs inference on the middle
frame.  First and last frames of the video use the nearest available neighbour
(edge-clamp). Minimum confidence threshold is configurable.
"""
from __future__ import annotations

import logging
import os
from typing import Iterator

import cv2
import numpy as np
import torch

from .model import INPUT_HW, BALL_RADIUS_PX, TrackNetV2

logger = logging.getLogger(__name__)

_DEFAULT_CONF = 0.5    # heatmap peak threshold to emit a detection
_DEVICE_CACHE: dict[str, torch.device] = {}


def _get_device() -> torch.device:
    if "dev" not in _DEVICE_CACHE:
        _DEVICE_CACHE["dev"] = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _DEVICE_CACHE["dev"]


def _preprocess(frames: list[np.ndarray]) -> torch.Tensor:
    """Stack 3 BGR frames → (1,9,H,W) float32 tensor on the correct device."""
    hw = INPUT_HW
    resized = [cv2.resize(f, (hw[1], hw[0])).astype(np.float32) / 255.0
               for f in frames]
    inp = np.concatenate(resized, axis=2)          # (H,W,9)
    t = torch.from_numpy(inp).permute(2, 0, 1).unsqueeze(0)   # (1,9,H,W)
    return t.to(_get_device())


def _heatmap_to_bbox(hm: np.ndarray, orig_h: int, orig_w: int,
                     conf_thresh: float = _DEFAULT_CONF,
                     radius_px: int = BALL_RADIUS_PX
                     ) -> list[float] | None:
    """Convert a (H,W) heatmap to an xyxy bbox in the original frame resolution."""
    peak_val = float(hm.max())
    if peak_val < conf_thresh:
        return None
    py, px = np.unravel_index(np.argmax(hm), hm.shape)
    # Scale back from INPUT_HW to original resolution
    scale_x = orig_w / INPUT_HW[1]
    scale_y = orig_h / INPUT_HW[0]
    cx = px * scale_x
    cy = py * scale_y
    r = radius_px  # fixed radius at 720p  (video is already max-height-720p)
    return [cx - r, cy - r, cx + r, cy + r]


class TrackNetDetector:
    """Wraps a trained TrackNetV2 model for per-frame ball detection.

    Parameters
    ----------
    model_path   Path to a .pt file saved with torch.save(model.state_dict(), ...).
    conf         Heatmap peak confidence threshold (0–1).
    device       Force a device string ("cuda"/"cpu"), or None to auto-detect.
    """

    def __init__(self, model_path: str, conf: float = _DEFAULT_CONF,
                 device: str | None = None) -> None:
        self.conf = conf
        self._model_path = model_path
        dev_str = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._device = torch.device(dev_str)
        self._model: TrackNetV2 | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not os.path.exists(self._model_path):
            raise FileNotFoundError(f"TrackNet model not found: {self._model_path}")
        m = TrackNetV2()
        state = torch.load(self._model_path, map_location=self._device, weights_only=True)
        m.load_state_dict(state)
        m.to(self._device)
        m.eval()
        self._model = m
        logger.info("TrackNet loaded from %s on %s", self._model_path, self._device)

    @torch.inference_mode()
    def _infer(self, frames: list[np.ndarray]) -> np.ndarray:
        """Run one forward pass; returns a (H,W) heatmap as float32 numpy."""
        self._load()
        inp = _preprocess(frames)
        out = self._model(inp)           # (1,1,H,W)
        return out[0, 0].cpu().numpy()

    def detect_video(
        self,
        video_path: str,
        max_height: int = 720,
    ) -> Iterator[tuple[int, list[float] | None]]:
        """Yield (frame_idx, bbox_xyxy_or_None) for every frame in the video.

        Frames are decoded at `max_height` (to match training resolution).
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {video_path}")

        frame_idx = 0
        pending: list[tuple[int, np.ndarray]] = []  # (original_idx, frame)

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            h, w = frame.shape[:2]
            if h > max_height:
                scale = max_height / h
                frame = cv2.resize(frame, (int(w * scale), max_height))
            pending.append((frame_idx, frame))
            frame_idx += 1

            if len(pending) == 3:
                # Emit the middle frame
                _, mid_frame = pending[1]
                hm = self._infer([p[1] for p in pending])
                orig_h, orig_w = mid_frame.shape[:2]
                bbox = _heatmap_to_bbox(hm, orig_h, orig_w, self.conf)
                yield pending[1][0], bbox
                pending.pop(0)

        # Flush remaining (last 1–2 frames): edge-clamp
        while pending:
            frames_3 = [pending[0][1]] * 3
            if len(pending) >= 2:
                frames_3 = [pending[0][1], pending[0][1], pending[1][1]]
            mid_fi, mid_frame = pending[0]
            hm = self._infer(frames_3)
            orig_h, orig_w = mid_frame.shape[:2]
            bbox = _heatmap_to_bbox(hm, orig_h, orig_w, self.conf)
            yield mid_fi, bbox
            pending.pop(0)

        cap.release()

    def detect_frames_streaming(
        self, video_path: str, chunk_size: int = 500
    ) -> list[dict]:
        """Mimic BallTracker.build_tracks_from_sv_detections output format:
        list[dict] where each element is {1: {"bbox": [x1,y1,x2,y2]}} or {}.
        """
        results: list[dict] = []
        for fi, bbox in self.detect_video(video_path):
            if len(results) <= fi:
                results.extend([{}] * (fi - len(results) + 1))
            if bbox is not None:
                results[fi] = {1: {"bbox": bbox}}
        return results
