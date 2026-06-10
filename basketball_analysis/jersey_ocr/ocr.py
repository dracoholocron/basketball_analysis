"""
JerseyOCR — read players' jersey numbers per track and vote per tracklet.

Strategy for distant footage: crop each tracked player from the NATIVE-resolution
frame (not the 720p pipeline frame) for maximum detail, upscale, and OCR the torso
region with a digits-only reader. Aggregate readings per track_id by voting → a
stable jersey number per track. Used to consolidate fragmented tracks into real
player identities (team, number).

Best-effort: if easyocr is unavailable, returns no numbers and the pipeline falls
back to track-level identities.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict

import numpy as np

logger = logging.getLogger(__name__)


class JerseyOCR:
    def __init__(self, model_dir: str = "/app/engine/models/easyocr"):
        self._reader = None
        try:
            import os
            os.makedirs(model_dir, exist_ok=True)
            import easyocr
            import torch
            self._reader = easyocr.Reader(
                ["en"], gpu=torch.cuda.is_available(),
                model_storage_directory=model_dir, verbose=False,
            )
            logger.info("JerseyOCR: easyocr ready (gpu=%s)", torch.cuda.is_available())
        except Exception as exc:
            logger.warning("JerseyOCR unavailable (%s) — jersey numbers disabled", exc)

    @property
    def available(self) -> bool:
        return self._reader is not None

    def read_tracklets(
        self,
        video_path: str,
        player_tracks: list[dict],
        src_scale: float = 1.0,
        sample_every: int = 10,
        min_votes: int = 3,
    ) -> dict[int, str]:
        """Return {track_id: jersey_number_str} for tracks with a confident reading."""
        if not self.available:
            return {}
        import cv2
        from utils.video_utils import iter_video_frames

        inv = (1.0 / src_scale) if src_scale else 1.0  # 720p bbox → native px
        votes: dict[int, Counter] = defaultdict(Counter)
        total = len(player_tracks)

        # One native-resolution pass; OCR only on sampled frames (cost control).
        for fi, frame in enumerate(iter_video_frames(video_path, max_height=0)):
            if fi >= total:
                break
            if fi % sample_every != 0:
                continue
            H, W = frame.shape[:2]
            for tid, info in player_tracks[fi].items():
                bbox = info.get("bbox", [])
                if len(bbox) < 4:
                    continue
                # 720p bbox → native, then torso region (chest/back number area)
                x1, y1, x2, y2 = [v * inv for v in bbox[:4]]
                bw, bh = x2 - x1, y2 - y1
                if bh < 24:  # too small even at native res
                    continue
                tx1 = int(max(0, x1 + bw * 0.12))
                tx2 = int(min(W, x2 - bw * 0.12))
                ty1 = int(max(0, y1 + bh * 0.15))
                ty2 = int(min(H, y1 + bh * 0.55))
                if tx2 - tx1 < 8 or ty2 - ty1 < 8:
                    continue
                crop = frame[ty1:ty2, tx1:tx2]
                num = self._read_number(crop)
                if num:
                    votes[tid][num] += 1

        out: dict[int, str] = {}
        for tid, c in votes.items():
            num, n = c.most_common(1)[0]
            if n >= min_votes:
                out[tid] = num
        logger.info(
            "JerseyOCR: read numbers for %d/%d tracks (min_votes=%d)",
            len(out), len({t for f in player_tracks for t in f}), min_votes,
        )
        return out

    def _read_number(self, crop: np.ndarray) -> str | None:
        import cv2
        h = crop.shape[0]
        if h < 64:  # upscale small crops for legibility
            s = 64.0 / h
            crop = cv2.resize(crop, (int(crop.shape[1] * s), 64), interpolation=cv2.INTER_CUBIC)
        try:
            results = self._reader.readtext(
                crop, allowlist="0123456789", detail=1, paragraph=False,
            )
        except Exception:
            return None
        best, best_conf = None, 0.0
        for _box, text, conf in results:
            t = "".join(ch for ch in text if ch.isdigit())
            if t and len(t) <= 2 and conf > best_conf and conf >= 0.4:
                best, best_conf = t, conf
        return best
