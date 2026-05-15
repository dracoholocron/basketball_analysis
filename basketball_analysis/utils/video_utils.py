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

def iter_video_frames(video_path: str) -> Generator[np.ndarray, None, None]:
    """Yield video frames one at a time, never holding more than one in memory."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
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

def read_video(video_path: str) -> list[np.ndarray]:
    """
    Load all video frames into a list.

    .. warning::
        For long videos this loads the entire video into RAM.
        Prefer :func:`iter_video_frames` or :func:`iter_video_chunks` for large inputs.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    frames: list[np.ndarray] = []
    for frame in iter_video_frames(video_path):
        frames.append(frame)
    logger.debug("read_video: loaded %d frames from %s", len(frames), video_path)
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
    codec: str = "XVID",
) -> None:
    """
    Save a list of annotated frames to a video file.

    Args:
        output_video_frames: Frames in BGR format.
        output_video_path:   Destination file path (.avi or .mp4).
        fps:                 Output frame rate.
        codec:               FourCC codec string (default XVID for AVI).
    """
    if not output_video_frames:
        raise ValueError("output_video_frames is empty — nothing to save")

    _ensure_dir(output_video_path)
    h, w = output_video_frames[0].shape[:2]
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
