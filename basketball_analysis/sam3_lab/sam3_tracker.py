"""
Sam3Tracker — ISOLATED pilot for Meta SAM 3 concept tracking via Ultralytics.

Tracks an object described by a TEXT PROMPT (e.g. "basketball") across a video,
with no manual clicks — to evaluate SAM 3 vs the production SAM 2 ball pipeline.

This module is intentionally self-contained: it does NOT import ball_sam2 or the
analysis pipeline, and SAM 3 is imported lazily so importing this file is safe even
on workers that don't have SAM 3 installed (the production worker). It degrades with
a clear message if SAM 3 / the gated `sam3.pt` weights are unavailable.

Prereq: download `sam3.pt` from Hugging Face (gated) into the model dir.
Docs: https://docs.ultralytics.com/models/sam-3
"""
from __future__ import annotations

import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

_DEFAULT_WEIGHTS = "/app/sam3_models/sam3.pt"


class Sam3Tracker:
    def __init__(self, weights: str | None = None, conf: float = 0.25):
        self.weights = weights or os.environ.get("BA_SAM3_WEIGHTS", _DEFAULT_WEIGHTS)
        self.conf = conf
        self._predictor = None
        self._err: str | None = None

    @property
    def available(self) -> bool:
        return self._load() is None

    def _load(self) -> str | None:
        """Lazily build the SAM3 semantic predictor. Returns an error string or None."""
        if self._predictor is not None:
            return None
        if self._err is not None:
            return self._err
        if not os.path.exists(self.weights):
            self._err = (
                f"SAM 3 weights not found at {self.weights}. Request access on Hugging "
                f"Face and place sam3.pt in the sam3_models volume."
            )
            return self._err
        try:
            import torch
            from ultralytics.models.sam import SAM3SemanticPredictor
            self._predictor = SAM3SemanticPredictor(overrides=dict(
                conf=self.conf, task="segment", mode="predict",
                model=self.weights, half=torch.cuda.is_available(), save=False, verbose=False,
            ))
            logger.info("SAM3 predictor ready (weights=%s)", self.weights)
            return None
        except Exception as exc:  # ultralytics too old / SAM3 not installed
            self._err = f"SAM 3 unavailable: {exc}"
            logger.warning(self._err)
            return self._err

    def track_video(self, video_path: str, prompt: str, out_path: str,
                    start_f: int = 0, end_f: int | None = None,
                    max_height: int = 720) -> dict:
        """Run per-frame concept detection for `prompt`, draw the best box, write an
        annotated mp4, and return coverage stats. Per-frame (SAM 3's open-vocabulary
        detector) — a pilot proxy for tracking, robust without the temporal API."""
        err = self._load()
        if err is not None:
            return {"error": err}

        import cv2
        from utils.video_utils import iter_video_frames

        writer = None
        frames = 0
        with_obj = 0
        prompt_list = [prompt]
        try:
            for idx, frame in enumerate(iter_video_frames(video_path, max_height=max_height)):
                if idx < start_f:
                    continue
                if end_f is not None and idx > end_f:
                    break
                frames += 1
                if writer is None:
                    h, w = frame.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(out_path, fourcc, 24.0, (w, h))
                box = self._best_box(frame, prompt_list)
                if box is not None:
                    with_obj += 1
                    x1, y1, x2, y2 = [int(v) for v in box]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
                    cv2.putText(frame, prompt, (x1, max(0, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
                writer.write(frame)
        finally:
            if writer is not None:
                writer.release()

        if frames == 0:
            return {"error": "no frames processed"}
        return {
            "ok": True, "prompt": prompt, "frames": frames,
            "frames_with_object": with_obj,
            "coverage_pct": round(100.0 * with_obj / frames, 1),
            "output_path": out_path,
        }

    def _best_box(self, frame: np.ndarray, prompt_list: list[str]):
        """Highest-confidence detection box for the prompt on one frame, or None."""
        try:
            self._predictor.set_image(frame)
            results = self._predictor(text=prompt_list)
        except Exception as exc:
            logger.debug("SAM3 frame inference failed: %s", exc)
            return None
        best, best_conf = None, -1.0
        for r in (results or []):
            boxes = getattr(r, "boxes", None)
            if boxes is None or len(boxes) == 0:
                continue
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy() if boxes.conf is not None else np.ones(len(xyxy))
            for b, c in zip(xyxy, confs):
                if c > best_conf:
                    best, best_conf = b.tolist(), float(c)
        return best
