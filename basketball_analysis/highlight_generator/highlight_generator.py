"""
HighlightGenerator — creates highlight video clips using FFmpeg.

Given a list of CV events (shots, rebounds, steals, etc.) and the path to the
original video, this module cuts short clips around each event and optionally
merges them into a single highlight reel.

Requires FFmpeg to be installed and available on PATH.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

_DEFAULT_PRE_ROLL  = 2.0   # seconds before event
_DEFAULT_POST_ROLL = 3.0   # seconds after event
_FFMPEG_PRESET     = "fast"
_FFMPEG_CRF        = 23


class HighlightGenerator:
    """
    Generate highlight clips from a source video and a list of CV events.

    Parameters
    ----------
    fps : float
        Frame rate of the source video (used to convert frame indices to timestamps).
    pre_roll_s : float
        Seconds to include before each event.
    post_roll_s : float
        Seconds to include after each event.
    output_dir : str | Path
        Directory where clips will be saved.
    """

    def __init__(
        self,
        fps: float = 30.0,
        pre_roll_s: float = _DEFAULT_PRE_ROLL,
        post_roll_s: float = _DEFAULT_POST_ROLL,
        output_dir: str | Path = "output_videos/highlights",
    ) -> None:
        self.fps = fps
        self.pre_roll_s = pre_roll_s
        self.post_roll_s = post_roll_s
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_clips(
        self,
        video_path: str,
        events: list[dict],
        event_types: Optional[list[str]] = None,
        portrait: bool = False,
    ) -> list[dict]:
        """
        Cut individual clips around each event and save to output_dir.

        Parameters
        ----------
        video_path : str
            Path to the source video file.
        events : list of {"type": str, "frame": int, ...}
        event_types : filter to only these event types (e.g. ["shot_attempt"])
        portrait : bool
            If True, output 9:16 portrait crops instead of 16:9 landscape.

        Returns
        -------
        List of {"clip_path": str, "event": dict, "start_s": float, "end_s": float}
        """
        if not _ffmpeg_available():
            log.warning("FFmpeg not found — returning empty highlights list")
            return []

        if event_types:
            events = [e for e in events if e.get("type") in event_types]

        results = []
        for i, event in enumerate(events):
            frame_idx = event.get("frame", 0)
            start_s = max(0.0, frame_idx / self.fps - self.pre_roll_s)
            end_s = frame_idx / self.fps + self.post_roll_s
            duration = end_s - start_s

            event_type = event.get("type", "event").replace("_", "-")
            clip_name = f"highlight_{i:03d}_{event_type}_f{frame_idx}.mp4"
            clip_path = self.output_dir / clip_name

            vf = _portrait_filter() if portrait else "null"
            success = self._cut_clip(video_path, start_s, duration, str(clip_path), vf)
            if success:
                results.append({
                    "clip_path": str(clip_path),
                    "event": event,
                    "start_s": start_s,
                    "end_s": end_s,
                })

        log.info("Generated %d highlight clips in %s", len(results), self.output_dir)
        return results

    def generate_reel(
        self,
        clips: list[dict],
        output_path: Optional[str] = None,
        title_card_s: float = 0.5,
    ) -> Optional[str]:
        """
        Concatenate clips into a single highlight reel.

        Parameters
        ----------
        clips : output from generate_clips()
        output_path : destination .mp4 path (defaults to output_dir/highlight_reel.mp4)

        Returns
        -------
        Path to the reel file, or None on failure.
        """
        if not clips:
            return None
        if not _ffmpeg_available():
            return None

        output_path = output_path or str(self.output_dir / "highlight_reel.mp4")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            concat_file = f.name
            for clip in clips:
                f.write(f"file '{clip['clip_path']}'\n")

        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            log.info("Highlight reel saved: %s", output_path)
            return output_path
        except subprocess.CalledProcessError as exc:
            log.error("FFmpeg reel concat failed: %s", exc.stderr.decode())
            return None
        finally:
            os.unlink(concat_file)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _cut_clip(
        self,
        source: str,
        start_s: float,
        duration: float,
        output: str,
        vf: str = "null",
    ) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_s),
            "-i", source,
            "-t", str(duration),
            "-vf", vf,
            "-preset", _FFMPEG_PRESET,
            "-crf", str(_FFMPEG_CRF),
            "-movflags", "+faststart",
            output,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as exc:
            log.error("FFmpeg clip cut failed: %s", exc.stderr.decode()[:300])
            return False


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _portrait_filter() -> str:
    """FFmpeg video filter to crop to 9:16 portrait from center."""
    return "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920"
