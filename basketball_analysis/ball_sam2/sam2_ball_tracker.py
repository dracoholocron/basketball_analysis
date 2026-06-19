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

# Public Meta checkpoint URLs (092824 release) + EfficientTAM (Meta, ICCV 2025 — ~1.6-2x
# faster than SAM2 on GPU with comparable quality; same video-predictor API).
_CKPT_URLS = {
    "sam2.1_hiera_small.pt": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt",
    "sam2.1_hiera_tiny.pt": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt",
    "sam2.1_hiera_base_plus.pt": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt",
    "sam2.1_hiera_large.pt": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt",
    "efficienttam_s.pt": "https://huggingface.co/yunyangx/efficient-track-anything/resolve/main/efficienttam_s.pt",
}


class Sam2BallTracker:
    def __init__(self, checkpoint: str, config: str, device: str = "cuda",
                 box_half: float = 18.0, max_ball_px: float = 60.0,
                 chunk_size: int | None = None, stride: int | None = None):
        self.checkpoint = checkpoint
        self.config = config
        self.device = device
        # Optional stride override (else settings.sam2_stride). Used for the adaptive
        # long-video bump computed by the caller.
        self.stride_override = stride
        # A ball at 720p is ~20-40px. Seed SAM2 with a small box around the click
        # (not a bare point) so it segments the ball, not the nearby player.
        self.box_half = box_half
        self.max_ball_px = max_ball_px
        # SAM2 caches per-frame features in RAM → init_state over a whole long
        # video OOMs. Process in chunks, carrying the last ball box forward as the
        # seed for the next chunk to keep continuity. Tunable via BA_SAM2_CHUNK.
        if chunk_size is None:
            chunk_size = int(getattr(settings, "sam2_chunk", 500)) if settings else 500
        self.chunk_size = max(1, chunk_size)

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
        # Backend: SAM2 (default) or EfficientTAM (pilot — same video-predictor API,
        # ~1.6-2x faster). Selected when the checkpoint/config name says "efficienttam".
        _is_etam = "efficienttam" in (self.checkpoint or "").lower() or \
                   "efficienttam" in (self.config or "").lower()
        try:
            import torch
            if _is_etam:
                from efficient_track_anything.build_efficienttam import (
                    build_efficienttam_video_predictor as _build_predictor,
                )
            else:
                from sam2.build_sam import build_sam2_video_predictor as _build_predictor
        except Exception as exc:
            logger.warning(
                "%s not available (%s) — falling back to YOLO ball path",
                "efficient_track_anything" if _is_etam else "sam2", exc,
            )
            return None

        ckpt = self._ensure_checkpoint()
        if ckpt is None:
            return None

        # Group seed clicks by frame index; collect "not visible" frames to blank.
        seeds: dict[int, list[tuple[float, float]]] = {}
        negatives: dict[int, list[tuple[float, float]]] = {}   # "NOT the ball" clicks
        not_visible: set[int] = set()
        for p in ball_points:
            fi = int(round(float(p.get("frame_t", 0.0)) * fps))
            fi = max(0, min(total_frames - 1, fi))
            if p.get("negative"):
                # User marked a wrongly-tracked object (shoe, chair…): feed SAM2 a
                # label-0 point there so its memory rejects that object.
                px = p.get("pixel") or [0, 0]
                negatives.setdefault(fi, []).append(
                    (float(px[0]) * src_scale, float(px[1]) * src_scale)
                )
            elif p.get("visible", True):
                px = p["pixel"]
                seeds.setdefault(fi, []).append(
                    (float(px[0]) * src_scale, float(px[1]) * src_scale)
                )
            else:
                not_visible.add(fi)
        if not seeds:
            return None
        if negatives:
            logger.info("SAM2 ball: %d negative (wrong-object) clicks",
                        sum(len(v) for v in negatives.values()))

        import gc
        import queue
        import shutil
        import threading
        import cv2
        from utils.video_utils import iter_video_frames_prefetch

        stride = max(1, int(self.stride_override if self.stride_override is not None
                            else getattr(settings, "sam2_stride", 1)))
        device = self.device if torch.cuda.is_available() else "cpu"
        results: list[dict] = [{} for _ in range(total_frames)]
        carry_box: list[float] | None = None
        # vos_optimized=True torch.compiles the heavy SAM2 components (image/memory
        # encoder, memory attention) → major VOS speedup with the SAME weights (quality
        # identical; the first chunk pays the compile cost). Falls back to the normal
        # predictor if compile is unsupported on this GPU/driver. Toggle: BA_SAM2_VOS_OPTIMIZED.
        _want_vos = (bool(getattr(settings, "sam2_vos_optimized", True))
                     and device == "cuda" and not _is_etam)
        predictor = None
        if _want_vos:
            try:
                predictor = _build_predictor(
                    self.config, ckpt, device=device, vos_optimized=True,
                )
                logger.info("SAM2: vos_optimized (torch.compile) enabled")
            except Exception as exc:
                logger.warning("SAM2 vos_optimized unavailable (%s) — using standard predictor", exc)
                predictor = None
        if predictor is None:
            predictor = _build_predictor(self.config, ckpt, device=device)
            if _is_etam:
                logger.info("Ball tracker backend: EfficientTAM (%s)", os.path.basename(ckpt))

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
            # Offloads trade SPEED for memory (official SAM2 docs). We track ONE object,
            # so the inference state is small → keep it on GPU by default. The video
            # tensor (~12.6MB/frame fp32) stays on CPU unless explicitly enabled.
            _off_video = bool(getattr(settings, "sam2_offload_video", True))
            _off_state = bool(getattr(settings, "sam2_offload_state", False))
            with torch.inference_mode(), autocast:
                state = predictor.init_state(
                    video_path=chunk_dir,
                    offload_video_to_cpu=_off_video,
                    offload_state_to_cpu=_off_state,
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
                # Negative refinement clicks in this chunk: label-0 points telling SAM2
                # "this object is NOT the ball" (rejects drift onto shoes/chairs). Only
                # valid once the object exists (positive seeds above).
                for fi, pts in negatives.items():
                    if lo <= fi <= hi:
                        li = min(len(src_idx) - 1, max(0, round((fi - lo) / stride)))
                        for (nx, ny) in pts:
                            try:
                                predictor.add_new_points_or_box(
                                    inference_state=state, frame_idx=li, obj_id=1,
                                    points=np.array([[nx, ny]], dtype=np.float32),
                                    labels=np.array([0], dtype=np.int32),
                                )
                            except Exception as exc:
                                logger.debug("SAM2 negative click skipped (f%d): %s", fi, exc)
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

        # Double-buffered pipeline: a producer thread decodes (prefetched) and writes
        # the NEXT chunk's frames to disk while the GPU processes the CURRENT one, so
        # the per-chunk frame-write + setup no longer stalls the GPU (the profile
        # showed ~88%↔5% GPU sawtooth between chunks). Identical results: same chunk
        # boundaries/contents and the consumer processes chunks strictly in order, so
        # carry_box continuity is unchanged. Queue is bounded → disk stays ~2 chunks.
        chunk_q: "queue.Queue" = queue.Queue(maxsize=1)
        _SENTINEL = object()
        _prod_err: list[BaseException] = []

        # Chunk JPEGs in RAM (/dev/shm) instead of WSL-backed disk when available —
        # eliminates per-chunk write+read I/O. Requires shm_size big enough in compose
        # (one chunk of 720p JPEGs ≈ 50–120 MB). Falls back to the default tmp dir.
        _shm_dir = None
        if bool(getattr(settings, "sam2_chunk_in_ram", True)) and os.path.isdir("/dev/shm"):
            _shm_dir = "/dev/shm"

        def _mkchunkdir() -> str:
            if _shm_dir:
                try:
                    return tempfile.mkdtemp(prefix="sam2_chunk_", dir=_shm_dir)
                except OSError:
                    pass
            return tempfile.mkdtemp(prefix="sam2_chunk_")

        def _producer() -> None:
            cd: str | None = None
            sidx: list[int] = []
            loc = 0
            try:
                for gi, frame in enumerate(iter_video_frames_prefetch(video_path, max_height=720)):
                    if gi >= total_frames:
                        break
                    if gi % stride != 0:
                        continue
                    if cd is None:
                        cd = _mkchunkdir()
                        sidx = []
                        loc = 0
                    cv2.imwrite(os.path.join(cd, f"{loc}.jpg"), frame)
                    sidx.append(gi)
                    loc += 1
                    if loc >= self.chunk_size:
                        chunk_q.put((cd, sidx))
                        cd = None
                if cd is not None and loc > 0:
                    chunk_q.put((cd, sidx))
            except BaseException as exc:  # propagate to consumer
                _prod_err.append(exc)
            finally:
                chunk_q.put(_SENTINEL)

        producer = threading.Thread(target=_producer, name="sam2-chunk-writer", daemon=True)
        producer.start()
        try:
            while True:
                item = chunk_q.get()
                if item is _SENTINEL:
                    break
                cd, sidx = item
                try:
                    _process_chunk(cd, sidx)
                finally:
                    shutil.rmtree(cd, ignore_errors=True)
            if _prod_err:
                raise _prod_err[0]

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
            # Drain any buffered chunk dirs so a partial run doesn't leak temp files.
            try:
                while True:
                    leftover = chunk_q.get_nowait()
                    if leftover is _SENTINEL or leftover is None:
                        continue
                    shutil.rmtree(leftover[0], ignore_errors=True)
            except Exception:
                pass

    # ── interactive session (pause → correct → resume) ─────────────────────────
    def track_interactive(
        self,
        video_path: str,
        ball_points: list[dict],
        total_frames: int,
        fps: float,
        src_scale: float = 1.0,
        start_frame: int = 0,
        results: list[dict] | None = None,
        should_pause=None,
        on_progress=None,
    ) -> dict | None:
        """Incremental ball tracking for the interactive session.

        Processes from ``start_frame`` to the end, chunk by chunk (sequential, stride 1
        — corrections need frame precision), updating ``results`` in place. Pauses and
        RETURNS (the Celery task ends; the GPU worker is free while the user thinks) when:
          - ``should_pause()`` is truthy (user pressed Pause; poll throttled by caller),
          - the ball has no accepted mask for > ball_session_lost_s (reason "lost"),
          - drift heuristics fire for ball_session_drift_frames consecutive frames
            (center snap >130px or size >2.2x running median; reason "drift"),
          - a chunk has neither a user seed nor a carry box (ball unknown → "lost").

        ``on_progress(frame_idx, covered, bbox, frame_jpg_path)`` is called every
        ball_session_preview_every frames (jpg path = the decoded chunk frame on disk,
        ready for preview drawing). Returns {"status": "done"|"paused", "pause_reason",
        "pause_frame", "results", "covered"} or None on hard failure.
        """
        _is_etam = "efficienttam" in (self.checkpoint or "").lower() or \
                   "efficienttam" in (self.config or "").lower()
        try:
            import torch
            if _is_etam:
                from efficient_track_anything.build_efficienttam import (
                    build_efficienttam_video_predictor as _build_predictor,
                )
            else:
                from sam2.build_sam import build_sam2_video_predictor as _build_predictor
        except Exception as exc:
            logger.warning("track_interactive: backend unavailable (%s)", exc)
            return None
        ckpt = self._ensure_checkpoint()
        if ckpt is None:
            return None

        import shutil
        from collections import deque

        import cv2

        # Parse clicks (same semantics as track()).
        seeds: dict[int, list[tuple[float, float]]] = {}
        negatives: dict[int, list[tuple[float, float]]] = {}
        not_visible: set[int] = set()
        for p in ball_points or []:
            fi = int(round(float(p.get("frame_t", 0.0)) * fps))
            fi = max(0, min(total_frames - 1, fi))
            px = p.get("pixel") or [0, 0]
            if p.get("negative"):
                negatives.setdefault(fi, []).append(
                    (float(px[0]) * src_scale, float(px[1]) * src_scale))
            elif p.get("visible", True):
                seeds.setdefault(fi, []).append(
                    (float(px[0]) * src_scale, float(px[1]) * src_scale))
            else:
                not_visible.add(fi)

        if results is None:
            results = [{} for _ in range(total_frames)]
        while len(results) < total_frames:
            results.append({})

        device = self.device if torch.cuda.is_available() else "cpu"
        predictor = _build_predictor(self.config, ckpt, device=device)

        lost_pause = max(1, int(float(getattr(settings, "ball_session_lost_s", 2.0)) * fps))
        drift_pause = max(1, int(getattr(settings, "ball_session_drift_frames", 3)))
        preview_every = max(10, int(getattr(settings, "ball_session_preview_every", 100)))

        # Drift state seeded from existing track before start_frame (resume case).
        size_hist: deque = deque(maxlen=200)
        last_center: tuple[float, float] | None = None
        for i in range(max(0, start_frame - 400), start_frame):
            box = results[i].get(1, {}).get("bbox")
            if box:
                size_hist.append(max(box[2] - box[0], box[3] - box[1]))
                last_center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

        _shm = "/dev/shm" if (bool(getattr(settings, "sam2_chunk_in_ram", True))
                              and os.path.isdir("/dev/shm")) else None

        def _mkdir() -> str:
            if _shm:
                try:
                    return tempfile.mkdtemp(prefix="sam2_session_", dir=_shm)
                except OSError:
                    pass
            return tempfile.mkdtemp(prefix="sam2_session_")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("track_interactive: cannot open video %s", video_path)
            return None
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        paused = {"reason": None, "frame": None}
        lost_streak = 0
        lost_start = start_frame
        drift_streak = 0
        drift_start = start_frame
        covered_prior = sum(1 for r in results[:start_frame] if r)
        processed = 0

        def _covered() -> int:
            return covered_prior + sum(1 for r in results[start_frame:] if r)

        autocast = (torch.autocast(device, dtype=torch.bfloat16)
                    if device == "cuda" else _nullctx())
        _off_video = bool(getattr(settings, "sam2_offload_video", True))
        _off_state = bool(getattr(settings, "sam2_offload_state", False))
        gi = start_frame
        try:
            while gi < total_frames and paused["reason"] is None:
                # ── read + write one chunk ───────────────────────────────────
                chunk_dir = _mkdir()
                src_idx: list[int] = []
                while len(src_idx) < self.chunk_size and gi + len(src_idx) < total_frames:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    if frame.shape[0] > 720:
                        s = 720 / frame.shape[0]
                        frame = cv2.resize(frame, (int(frame.shape[1] * s), 720),
                                           interpolation=cv2.INTER_AREA)
                    cv2.imwrite(os.path.join(chunk_dir, f"{len(src_idx)}.jpg"), frame)
                    src_idx.append(gi + len(src_idx))
                if not src_idx:
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                    break
                lo, hi = src_idx[0], src_idx[-1]

                # ── seeds for this chunk: user clicks + carry from the last box ──
                chunk_seeds: dict[int, tuple[float, float]] = {}
                for fi, pts in seeds.items():
                    if lo <= fi <= hi:
                        chunk_seeds[fi - lo] = pts[0]
                if 0 not in chunk_seeds and lo > 0:
                    prev = results[lo - 1].get(1, {}).get("bbox")
                    if prev:
                        chunk_seeds[0] = ((prev[0] + prev[2]) / 2.0, (prev[1] + prev[3]) / 2.0)
                if not chunk_seeds:
                    # Ball position unknown and no seed here → ask the user.
                    paused["reason"], paused["frame"] = "lost", lo
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                    break

                with torch.inference_mode(), autocast:
                    state = predictor.init_state(
                        video_path=chunk_dir,
                        offload_video_to_cpu=_off_video,
                        offload_state_to_cpu=_off_state,
                    )
                    hb = self.box_half
                    for li, (cx, cy) in chunk_seeds.items():
                        box = np.array([cx - hb, cy - hb, cx + hb, cy + hb], dtype=np.float32)
                        predictor.add_new_points_or_box(
                            inference_state=state, frame_idx=li, obj_id=1, box=box,
                            points=np.array([[cx, cy]], dtype=np.float32),
                            labels=np.array([1], dtype=np.int32),
                        )
                    for fi, pts in negatives.items():
                        if lo <= fi <= hi:
                            for (nx, ny) in pts:
                                try:
                                    predictor.add_new_points_or_box(
                                        inference_state=state, frame_idx=fi - lo, obj_id=1,
                                        points=np.array([[nx, ny]], dtype=np.float32),
                                        labels=np.array([0], dtype=np.int32),
                                    )
                                except Exception:
                                    pass

                    for li, _ids, mask_logits in predictor.propagate_in_video(state):
                        if li >= len(src_idx):
                            continue
                        g = src_idx[li]
                        if g in not_visible:
                            results[g] = {}
                            bbox = None
                        else:
                            bbox, score = self._mask_to_bbox(mask_logits[0])
                            results[g] = {1: {"bbox": bbox, "score": score}} if bbox else {}
                        processed += 1

                        # ── lost / drift bookkeeping ─────────────────────────
                        if bbox is None:
                            if lost_streak == 0:
                                lost_start = g
                            lost_streak += 1
                            drift_streak = 0
                        else:
                            lost_streak = 0
                            cx = (bbox[0] + bbox[2]) / 2
                            cy = (bbox[1] + bbox[3]) / 2
                            side = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
                            med = sorted(size_hist)[len(size_hist) // 2] if size_hist else side
                            snap = (last_center is not None and
                                    ((cx - last_center[0]) ** 2 + (cy - last_center[1]) ** 2) ** 0.5 > 130)
                            odd_size = size_hist and (side > 2.2 * med or side < med / 2.2)
                            if snap or odd_size:
                                if drift_streak == 0:
                                    drift_start = g
                                drift_streak += 1
                            else:
                                drift_streak = 0
                                size_hist.append(side)
                            last_center = (cx, cy)

                        if processed % preview_every == 0 and on_progress is not None:
                            try:
                                on_progress(g, _covered(),
                                            results[g].get(1, {}).get("bbox"),
                                            os.path.join(chunk_dir, f"{li}.jpg"))
                            except Exception:
                                pass

                        if should_pause is not None and should_pause():
                            paused["reason"], paused["frame"] = "user", g
                            break
                        if lost_streak >= lost_pause:
                            paused["reason"], paused["frame"] = "lost", lost_start
                            break
                        if drift_streak >= drift_pause:
                            paused["reason"], paused["frame"] = "drift", drift_start
                            break

                    del state
                    if device == "cuda":
                        torch.cuda.empty_cache()
                shutil.rmtree(chunk_dir, ignore_errors=True)
                gi = hi + 1
        finally:
            cap.release()

        status = "paused" if paused["reason"] else "done"
        covered = _covered()
        logger.info(
            "track_interactive: %s at frame %s (reason=%s) — covered %d/%d",
            status, paused["frame"] if paused["reason"] else total_frames,
            paused["reason"], covered, total_frames,
        )
        return {"status": status, "pause_reason": paused["reason"],
                "pause_frame": paused["frame"], "results": results, "covered": covered}

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
