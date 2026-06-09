"""
Video I/O utilities with streaming support.

Functions:
- read_video:          Load all frames into a list (kept for compatibility with small clips).
- iter_video_frames:   Generator that yields frames one-by-one (O(1) memory per frame).
- iter_video_chunks:   Generator that yields non-overlapping batches of frames.
- get_video_properties: Return fps, width, height, total_frames without loading frames.
- save_video:          Write a list of annotated frames to an output video file.
- save_video_from_iter: Write frames from an iterator without loading all into RAM.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator, Iterator
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ── Video metadata ─────────────────────────────────────────────────────────────

def get_video_properties(video_path: str) -> dict:
    """Return basic metadata about a video without reading any frames."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")
    props = {
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    cap.release()
    return props


# ── Streaming generators ───────────────────────────────────────────────────────

def iter_video_frames(
    video_path: str,
    max_height: int = 0,
) -> Generator[np.ndarray, None, None]:
    """
    Yield video frames one at a time, never holding more than one in memory.

    Parameters
    ----------
    max_height : int
        If > 0, downscale frames whose height exceeds this value while
        preserving aspect ratio.  Pass 720 in all streaming detection passes
        so that bounding-box coordinates stay in the same 720p space that the
        draw pass uses.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if max_height > 0 and frame.shape[0] > max_height:
                scale = max_height / frame.shape[0]
                new_w = int(frame.shape[1] * scale)
                frame = cv2.resize(frame, (new_w, max_height), interpolation=cv2.INTER_AREA)
            yield frame
    finally:
        cap.release()


def iter_video_chunks(
    video_path: str,
    chunk_size: int = 64,
) -> Generator[list[np.ndarray], None, None]:
    """
    Yield non-overlapping lists of `chunk_size` consecutive frames.

    The last chunk may be smaller than `chunk_size`.
    """
    chunk: list[np.ndarray] = []
    for frame in iter_video_frames(video_path):
        chunk.append(frame)
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


# ── Legacy in-memory loader (kept for small videos / stubs workflows) ──────────

# Honour BA_MAX_FRAMES env var (0 or unset = no limit).
_ENV_MAX_FRAMES: Optional[int] = int(os.environ.get("BA_MAX_FRAMES", "0")) or None


def read_video(
    video_path: str,
    max_height: int = 720,
    frame_step: int = 1,
    max_frames: Optional[int] = _ENV_MAX_FRAMES,
) -> list[np.ndarray]:
    """
    Load video frames into a list with optional memory guards:

    - ``max_height``: Downscale frames if their height exceeds this value (default 720p).
    - ``frame_step``:  Only keep every N-th frame (default 1 → all frames).
    - ``max_frames``:  Cap on total frames loaded. ``None`` (default) means no limit.
                       Override at runtime with the ``BA_MAX_FRAMES`` env var.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    frames: list[np.ndarray] = []
    for idx, frame in enumerate(iter_video_frames(video_path)):
        if idx % frame_step != 0:
            continue
        if frame.shape[0] > max_height:
            scale = max_height / frame.shape[0]
            new_w = int(frame.shape[1] * scale)
            frame = cv2.resize(frame, (new_w, max_height), interpolation=cv2.INTER_AREA)
        frames.append(frame)
        if max_frames is not None and len(frames) >= max_frames:
            logger.warning(
                "read_video: reached max_frames=%d cap — truncating '%s'",
                max_frames,
                video_path,
            )
            break

    logger.info(
        "read_video: loaded %d frames from '%s' (step=%d, max_h=%d)",
        len(frames),
        video_path,
        frame_step,
        max_height,
    )
    return frames


# ── Writers ────────────────────────────────────────────────────────────────────

def _ensure_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def save_video(
    output_video_frames: list[np.ndarray],
    output_video_path: str,
    fps: float = 24.0,
    codec: str | None = None,
) -> None:
    """
    Save a list of annotated frames to a video file.

    For .mp4 output, first writes with mp4v via OpenCV then re-encodes to
    H.264 using ffmpeg (if available) for browser compatibility.

    Args:
        output_video_frames: Frames in BGR format.
        output_video_path:   Destination file path (.avi or .mp4).
        fps:                 Output frame rate.
        codec:               FourCC codec string override (rarely needed).
    """
    import shutil
    import subprocess
    import tempfile

    if not output_video_frames:
        raise ValueError("output_video_frames is empty — nothing to save")

    is_mp4 = output_video_path.lower().endswith(".mp4")

    if codec is None:
        codec = "mp4v" if is_mp4 else "XVID"

    _ensure_dir(output_video_path)
    h, w = output_video_frames[0].shape[:2]

    # Write frames using OpenCV
    if is_mp4 and shutil.which("ffmpeg"):
        # Write raw frames to a temp file, then re-encode to H.264 with ffmpeg
        tmp_path = output_video_path + ".tmp.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, fps, (w, h))
        try:
            for frame in output_video_frames:
                out.write(frame)
        finally:
            out.release()
        # Re-encode to H.264 for browser compatibility
        cmd = [
            "ffmpeg", "-y", "-i", tmp_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-movflags", "+faststart",  # enables progressive streaming
            output_video_path,
        ]
        result = subprocess.run(cmd, capture_output=True)
        try:
            import os
            os.remove(tmp_path)
        except OSError:
            pass
        if result.returncode != 0:
            logger.warning("ffmpeg re-encode failed: %s", result.stderr.decode())
            # Rename tmp as output if ffmpeg failed
            import os
            if os.path.exists(tmp_path):
                os.rename(tmp_path, output_video_path)
    else:
        fourcc = cv2.VideoWriter_fourcc(*codec)
        out = cv2.VideoWriter(output_video_path, fourcc, fps, (w, h))
        try:
            for frame in output_video_frames:
                out.write(frame)
        finally:
            out.release()

    logger.debug("save_video: wrote %d frames to %s", len(output_video_frames), output_video_path)


def save_video_from_iter(
    frames_iter: Iterator[np.ndarray],
    output_video_path: str,
    width: int,
    height: int,
    fps: float = 24.0,
    codec: str = "XVID",
) -> int:
    """
    Write frames from an iterator to disk without accumulating them in memory.

    Returns the total number of frames written.
    """
    _ensure_dir(output_video_path)
    fourcc = cv2.VideoWriter_fourcc(*codec)
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))
    count = 0
    try:
        for frame in frames_iter:
            out.write(frame)
            count += 1
    finally:
        out.release()
    logger.debug(
        "save_video_from_iter: wrote %d frames to %s", count, output_video_path
    )
    return count
