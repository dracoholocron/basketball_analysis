"""
Sam2BallTracker — propagate manually-clicked ball positions across a video with
SAM 2 (Meta). Color-agnostic → robust for off-domain balls (e.g. gray) where the
YOLO detector struggles.

Input: ball annotations [{frame_t, pixel:[x,y] (intrinsic res), visible}].
Output: per-frame ball tracks {1: {"bbox":[x1,y1,x2,y2], "score":s}} or {} in the
        720p pipeline coordinate space (matching detection/draw).

Everything is best-effort: any failure (sam2 missing, checkpoint missing, OOM)
logs a warning and returns None so the pipeline falls back to the YOLO ball path.
"""
from __future__ import annotations

import logging
import os
import tempfile
import urllib.request

import numpy as np

try:
    from configs.settings import settings
except Exception:  # pragma: no cover - settings always available in pipeline
    settings = None

logger = logging.getLogger(__name__)

# Public Meta checkpoint URLs (092824 release)
_CKPT_URLS = {
    "sam2.1_hiera_small.pt": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt",
    "sam2.1_hiera_tiny.pt": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt",
    "sam2.1_hiera_base_plus.pt": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt",
}


class Sam2BallTracker:
    def __init__(self, checkpoint: str, config: str, device: str = "cuda",
                 box_half: float = 18.0, max_ball_px: float = 60.0,
                 chunk_size: int = 500):
        self.checkpoint = checkpoint
        self.config = config
        self.device = device
        # A ball at 720p is ~20-40px. Seed SAM2 with a small box around the click
        # (not a bare point) so it segments the ball, not the nearby player.
        self.box_half = box_half
        self.max_ball_px = max_ball_px
        # SAM2 caches per-frame features in RAM → init_state over a whole long
        # video OOMs. Process in chunks, carrying the last ball box forward as the
        # seed for the next chunk to keep continuity.
        self.chunk_size = chunk_size

    # ── checkpoint handling ─────────────────────────────────────────────────
    def _ensure_checkpoint(self) -> str | None:
        path = self.checkpoint
        if not os.path.isabs(path):
            # resolve relative to the engine package root
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, self.checkpoint)
        if os.path.exists(path):
            return path
        fname = os.path.basename(path)
        url = _CKPT_URLS.get(fname)
        if url is None:
            logger.warning("SAM2 checkpoint %s missing and no download URL known", fname)
            return None
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            logger.info("Downloading SAM2 checkpoint %s …", fname)
            urllib.request.urlretrieve(url, path)
            return path
        except Exception as exc:
            logger.warning("SAM2 checkpoint download failed: %s", exc)
            return None

    # ── main entry ──────────────────────────────────────────────────────────
    def track(
        self,
        video_path: str,
        ball_points: list[dict],
        total_frames: int,
        fps: float,
        src_scale: float = 1.0,
    ) -> list[dict] | None:
        """Return per-frame ball tracks in 720p space, or None on failure."""
        if not ball_points:
            return None
        try:
            import torch
            from sam2.build_sam import build_sam2_video_predictor
        except Exception as exc:
            logger.warning("sam2 not available (%s) — falling back to YOLO ball path", exc)
            return None

        ckpt = self._ensure_checkpoint()
        if ckpt is None:
            return None

        # Group seed clicks by frame index; collect "not visible" frames to blank.
        seeds: dict[int, list[tuple[float, float]]] = {}
        not_visible: set[int] = set()
        for p in ball_points:
            fi = int(round(float(p.get("frame_t", 0.0)) * fps))
            fi = max(0, min(total_frames - 1, fi))
            if p.get("visible", True):
                px = p["pixel"]
                seeds.setdefault(fi, []).append(
                    (float(px[0]) * src_scale, float(px[1]) * src_scale)
                )
            else:
                not_visible.add(fi)
        if not seeds:
            return None

        import gc
        import shutil
        import cv2
        from utils.video_utils import iter_video_frames

        stride = max(1, int(getattr(settings, "sam2_stride", 1)))
        device = self.device if torch.cuda.is_available() else "cpu"
        results: list[dict] = [{} for _ in range(total_frames)]
        carry_box: list[float] | None = None
        predictor = build_sam2_video_predictor(self.config, ckpt, device=device)

        def _process_chunk(chunk_dir: str, src_idx: list[int]) -> None:
            """Run SAM2 over one on-disk chunk; src_idx[local] = source frame index."""
            nonlocal carry_box
            if not src_idx:
                return
            lo, hi = src_idx[0], src_idx[-1]
            # seeds: user clicks whose source frame falls in this chunk → nearest local
            chunk_seeds: dict[int, tuple[float, float]] = {}
            for fi, pts in seeds.items():
                if lo <= fi <= hi:
                    li = min(len(src_idx) - 1, max(0, round((fi - lo) / stride)))
                    chunk_seeds[li] = pts[0]
            if carry_box is not None and 0 not in chunk_seeds:
                chunk_seeds[0] = ((carry_box[0] + carry_box[2]) / 2.0,
                                  (carry_box[1] + carry_box[3]) / 2.0)
            if not chunk_seeds:
                carry_box = None
                return
            autocast = (torch.autocast(device, dtype=torch.bfloat16)
                        if device == "cuda" else _nullctx())
            with torch.inference_mode(), autocast:
                state = predictor.init_state(
                    video_path=chunk_dir, offload_video_to_cpu=True, offload_state_to_cpu=True,
                )
                hb = self.box_half
                first_local = min(chunk_seeds)
                for li, (cx, cy) in chunk_seeds.items():
                    box = np.array([cx - hb, cy - hb, cx + hb, cy + hb], dtype=np.float32)
                    predictor.add_new_points_or_box(
                        inference_state=state, frame_idx=li, obj_id=1, box=box,
                        points=np.array([[cx, cy]], dtype=np.float32),
                        labels=np.array([1], dtype=np.int32),
                    )
                for reverse in (False, True):
                    if reverse and first_local == 0:
                        continue
                    for li, _ids, mask_logits in predictor.propagate_in_video(state, reverse=reverse):
                        if li >= len(src_idx):
                            continue
                        gi = src_idx[li]
                        if gi in not_visible:
                            results[gi] = {}
                            continue
                        bbox, score = self._mask_to_bbox(mask_logits[0])
                        if bbox is not None:
                            results[gi] = {1: {"bbox": bbox, "score": score}}
            carry_box = results[hi].get(1, {}).get("bbox") if results[hi] else None
            del state
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()

        # Single pass over the video: write frames into rolling chunk dirs (disk
        # bounded to ~chunk_size frames) and process each chunk as it fills.
        chunk_dir: str | None = None
        src_idx: list[int] = []
        local = 0
        try:
            for gi, frame in enumerate(iter_video_frames(video_path, max_height=720)):
                if gi >= total_frames:
                    break
                if gi % stride != 0:
                    continue
                if chunk_dir is None:
                    chunk_dir = tempfile.mkdtemp(prefix="sam2_chunk_")
                    src_idx = []
                    local = 0
                cv2.imwrite(os.path.join(chunk_dir, f"{local}.jpg"), frame)
                src_idx.append(gi)
                local += 1
                if local >= self.chunk_size:
                    _process_chunk(chunk_dir, src_idx)
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                    chunk_dir = None
            if chunk_dir is not None and local > 0:
                _process_chunk(chunk_dir, src_idx)

            covered = sum(1 for r in results if r)
            logger.info(
                "SAM2 ball: covered %d/%d frames from %d seed clicks (chunk=%d, stride=%d)",
                covered, total_frames, sum(len(v) for v in seeds.values()),
                self.chunk_size, stride,
            )
            return results
        except Exception as exc:
            logger.warning("SAM2 ball tracking failed: %s — falling back to YOLO", exc)
            return None
        finally:
            if chunk_dir is not None:
                shutil.rmtree(chunk_dir, ignore_errors=True)

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _extract_frames(video_path: str, out_dir: str, total_frames: int) -> int:
        """Write frames as <idx>.jpg at max height 720p (pipeline space)."""
        import cv2
        from utils.video_utils import iter_video_frames
        count = 0
        for i, frame in enumerate(iter_video_frames(video_path, max_height=720)):
            if i >= total_frames:
                break
            cv2.imwrite(os.path.join(out_dir, f"{i}.jpg"), frame)
            count += 1
        return count

    def _mask_to_bbox(self, mask_logit) -> tuple[list[float] | None, float]:
        m = (mask_logit > 0.0).cpu().numpy()
        if m.ndim == 3:
            m = m[0]
        ys, xs = np.where(m)
        if xs.size == 0:
            return None, 0.0
        x1, x2 = float(xs.min()), float(xs.max())
        y1, y2 = float(ys.min()), float(ys.max())
        w, h = x2 - x1, y2 - y1
        # Reject masks too large to be a ball (likely latched onto a player) and
        # very non-square blobs.
        if w > self.max_ball_px or h > self.max_ball_px:
            return None, 0.0
        if max(w, h) > 6 and min(w, h) / max(w, h) < 0.4:
            return None, 0.0
        score = float(min(1.0, m.sum() / 400.0))  # rough area-based confidence
        return [x1, y1, x2, y2], score


class _nullctx:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False
