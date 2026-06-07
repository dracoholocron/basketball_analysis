"""
HoopDetector — locates the basketball hoop in each frame.

Uses the YOLO11 multi-class model (which includes a "Hoop" class) to detect
the hoop bounding box. Falls back to the dedicated player/ball model if the
multi-class model is unavailable.

In dummy mode (BA_DUMMY_MODELS=1) a synthetic hoop position is returned.
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

_DUMMY_MODE: bool = os.environ.get("BA_DUMMY_MODELS", "").lower() in ("1", "true", "yes")
_HOOP_CLASS_NAMES = ("Hoop", "hoop", "basket", "rim")


def _find_model(filename: str) -> Optional[Path]:
    base = Path(__file__).resolve().parent.parent
    for p in [base / "models" / filename, Path("models") / filename]:
        if p.exists():
            return p
    return None


class HoopDetector:
    """
    Detect the basketball hoop bounding box in frames.

    Parameters
    ----------
    model_path : str | None
        Path to a YOLO model that includes a "Hoop" class.
        Defaults to yolo11_multiclass.pt, then player_detector.pt.
    conf : float
        Detection confidence threshold.
    dummy : bool
        Force dummy mode.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        conf: float = 0.4,
        dummy: bool = False,
    ) -> None:
        self._dummy = dummy or _DUMMY_MODE
        self._model = None
        self.conf = conf

        if not self._dummy:
            path = model_path or _find_model("yolo11_multiclass.pt") or _find_model("player_detector.pt")
            if path:
                try:
                    from ultralytics import YOLO
                    self._model = YOLO(str(path))
                    log.info("HoopDetector loaded: %s", path)
                except Exception as exc:
                    log.warning("HoopDetector model load failed: %s — using dummy", exc)
                    self._dummy = True
            else:
                log.warning("No YOLO model found for HoopDetector — using dummy mode")
                self._dummy = True

    # ── Public API ─────────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> Optional[list[float]]:
        """
        Detect hoop in a single frame.

        Returns
        -------
        [x1, y1, x2, y2] bounding box of the best hoop detection, or None.
        """
        if self._dummy:
            return self._dummy_hoop(frame)
        return self._detect_yolo(frame)

    def detect_sequence(self, frames: list[np.ndarray]) -> list[Optional[list[float]]]:
        """Detect hoop in each frame, returning a list of bboxes (or None per frame)."""
        return [self.detect(f) for f in frames]

    # ── Static helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def get_hoop_center(bbox: dict) -> Optional[tuple[float, float]]:
        """
        Get the center point of a hoop bbox dict.

        Parameters
        ----------
        bbox : {"bbox": [x1, y1, x2, y2]}
        """
        b = bbox.get("bbox", [])
        if len(b) < 4:
            return None
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

    @staticmethod
    def get_best_hoop_bbox(detections: list[dict]) -> Optional[dict]:
        """Return the highest-confidence detection from a list."""
        if not detections:
            return None
        return max(detections, key=lambda d: d.get("conf", 0))

    # ── Internal ───────────────────────────────────────────────────────────────

    def _detect_yolo(self, frame: np.ndarray) -> Optional[list[float]]:
        results = self._model.predict(frame, conf=self.conf, verbose=False)
        if not results:
            return None
        det = results[0]
        names = det.names
        names_inv = {v.lower(): k for k, v in names.items()}

        best_bbox = None
        best_conf = 0.0
        for hoop_name in _HOOP_CLASS_NAMES:
            cls_id = names_inv.get(hoop_name.lower())
            if cls_id is None:
                continue
            for box in det.boxes:
                if int(box.cls[0]) == cls_id and float(box.conf[0]) > best_conf:
                    best_conf = float(box.conf[0])
                    best_bbox = box.xyxy[0].tolist()

        return best_bbox

    def _dummy_hoop(self, frame: np.ndarray) -> list[float]:
        h, w = frame.shape[:2]
        cx, cy = w * 0.75, h * 0.25
        hw, hh = w * 0.03, h * 0.02
        return [cx - hw, cy - hh, cx + hw, cy + hh]
