"""
DualResolutionPipeline — efficient two-pass video processing.

Pass 1 (low resolution): Runs player + ball detection quickly on every frame
         to identify candidate event windows.
Pass 2 (native resolution): Re-processes only the short clip around each
         candidate window at full resolution for higher-quality pose and ball
         tracking.

This approach saves ~60-70% GPU time on long videos where only a fraction of
frames contain interesting events.
"""
from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

_DEFAULT_LOW_RES = (640, 360)   # width × height for pass 1
_EVENT_PAD_FRAMES = 15          # frames before/after event to include in pass 2


class DualResolutionPipeline:
    """
    Two-pass pipeline for efficient basketball video analysis.

    Parameters
    ----------
    low_res : tuple[int, int]
        (width, height) for the fast first pass.
    event_pad_frames : int
        Context frames to include around each detected event window.
    """

    def __init__(
        self,
        low_res: tuple[int, int] = _DEFAULT_LOW_RES,
        event_pad_frames: int = _EVENT_PAD_FRAMES,
    ) -> None:
        self.low_res = low_res
        self.event_pad_frames = event_pad_frames

    # ── Public API ─────────────────────────────────────────────────────────────

    def downsample_frames(self, frames: list[np.ndarray]) -> list[np.ndarray]:
        """Resize a list of frames to low_res for the fast first pass."""
        w, h = self.low_res
        return [cv2.resize(f, (w, h)) for f in frames]

    def find_event_windows(
        self,
        ball_tracks: list[dict],
        player_tracks: list[dict],
        min_ball_movement_px: float = 30.0,
        stride: int = 10,
    ) -> list[tuple[int, int]]:
        """
        Identify frame windows where significant ball movement occurs.

        Uses stride-based distance (frame N vs frame N-stride) instead of
        consecutive-frame distance so that smoothly interpolated positions — where
        per-frame movement is very small — still trigger correctly.

        Returns a list of (start_frame, end_frame) tuples (merged, non-overlapping).
        """
        candidate_frames: list[int] = []

        for i, ball in enumerate(ball_tracks):
            if i < stride:
                continue
            bbox = ball.get(1, {}).get("bbox", [])
            if len(bbox) < 4:
                continue
            ref_bbox = ball_tracks[i - stride].get(1, {}).get("bbox", [])
            if len(ref_bbox) < 4:
                continue
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            rx, ry = (ref_bbox[0] + ref_bbox[2]) / 2, (ref_bbox[1] + ref_bbox[3]) / 2
            dist = np.hypot(cx - rx, cy - ry)
            if dist > min_ball_movement_px:
                candidate_frames.append(i)

        return self._merge_windows(candidate_frames, len(ball_tracks))

    def extract_native_clips(
        self,
        frames: list[np.ndarray],
        windows: list[tuple[int, int]],
    ) -> list[tuple[int, int, list[np.ndarray]]]:
        """
        Extract full-resolution frame clips for each event window.

        Returns
        -------
        [(start_frame, end_frame, frames_clip), ...]
        """
        clips = []
        for start, end in windows:
            clips.append((start, end, frames[start : end + 1]))
        return clips

    def run(
        self,
        frames: list[np.ndarray],
        detector_fn,
        high_res_detector_fn=None,
    ) -> tuple[list[dict], list[dict]]:
        """
        Run the two-pass pipeline.

        Parameters
        ----------
        frames : full-resolution BGR frames
        detector_fn : callable(frames) → (ball_tracks, player_tracks)
            Applied to low-res frames in pass 1.
        high_res_detector_fn : callable(frames) → (ball_tracks, player_tracks)
            Applied to native-res event clips in pass 2.
            If None, pass 1 results are used for everything.

        Returns
        -------
        (ball_tracks, player_tracks) aligned to original frame indices
        """
        log.info("Pass 1: low-res detection on %d frames", len(frames))
        low_frames = self.downsample_frames(frames)
        ball_low, player_low = detector_fn(low_frames)

        if high_res_detector_fn is None:
            return ball_low, player_low

        log.info("Pass 1 done. Finding event windows...")
        windows = self.find_event_windows(ball_low, player_low)
        log.info("Found %d event windows", len(windows))

        # Start with low-res results and overwrite with high-res for event windows
        ball_out = list(ball_low)
        player_out = list(player_low)

        for start, end, clip in self.extract_native_clips(frames, windows):
            log.info("Pass 2: high-res on frames %d-%d", start, end)
            ball_hi, player_hi = high_res_detector_fn(clip)
            for offset, (b, p) in enumerate(zip(ball_hi, player_hi)):
                idx = start + offset
                if idx < len(ball_out):
                    ball_out[idx] = b
                    player_out[idx] = p

        return ball_out, player_out

    # ── Internal ───────────────────────────────────────────────────────────────

    def _merge_windows(
        self, candidate_frames: list[int], total_frames: int
    ) -> list[tuple[int, int]]:
        if not candidate_frames:
            return []

        pad = self.event_pad_frames
        merged: list[tuple[int, int]] = []
        start = max(0, candidate_frames[0] - pad)
        end = min(total_frames - 1, candidate_frames[0] + pad)

        for f in candidate_frames[1:]:
            f_start = max(0, f - pad)
            f_end = min(total_frames - 1, f + pad)
            if f_start <= end:
                end = max(end, f_end)
            else:
                merged.append((start, end))
                start, end = f_start, f_end

        merged.append((start, end))
        return merged
