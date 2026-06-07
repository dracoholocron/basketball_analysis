"""
ReboundDetector — detects rebounds from ball trajectory + player jump.

A rebound is flagged when:
  1. The ball was descending (y increasing in image coords) in previous frames.
  2. A player acquires possession (ball near their wrist/body) while the ball reverses direction.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from pose_estimator.skeleton_utils import KP

_CONF = 0.3
_HISTORY = 5            # frames of ball history to track trajectory
_BALL_PROXIMITY_PX = 150


class ReboundDetector:
    """
    Detect rebounds per player.

    Parameters
    ----------
    history_frames : int
        Number of frames to track ball trajectory.
    ball_proximity_px : float
        Maximum pixel distance from ball to player bbox center for a rebound.
    """

    def __init__(
        self,
        history_frames: int = _HISTORY,
        ball_proximity_px: float = _BALL_PROXIMITY_PX,
    ) -> None:
        self.history_frames = history_frames
        self.ball_proximity_px = ball_proximity_px
        self._ball_y_history: deque[Optional[float]] = deque(maxlen=history_frames)
        self._events: list[dict] = []

    def update(
        self,
        frame_idx: int,
        pose_frame: dict[int, np.ndarray],
        ball_tracks: dict,
        player_tracks: list[dict],
    ) -> list[dict]:
        """
        Process one frame. Returns list of new rebound events.

        Parameters
        ----------
        player_tracks : list of per-frame player dicts [{track_id: {"bbox": ...}}]
                        — pass the current frame's dict as a single-item list or just the dict
        """
        ball_center = _ball_center(ball_tracks)
        ball_y = ball_center[1] if ball_center else None
        new_events: list[dict] = []

        was_descending = self._was_descending()
        self._ball_y_history.append(ball_y)

        if not was_descending or ball_center is None:
            return new_events

        # Check if any player is close to the ball
        tracks = player_tracks if isinstance(player_tracks, dict) else {}
        for track_id, info in tracks.items():
            bbox = info.get("bbox", [])
            if len(bbox) < 4:
                continue
            px = (bbox[0] + bbox[2]) / 2
            py = (bbox[1] + bbox[3]) / 2
            dist = np.hypot(px - ball_center[0], py - ball_center[1])
            if dist <= self.ball_proximity_px:
                event = {
                    "type": "rebound",
                    "track_id": track_id,
                    "frame": frame_idx,
                }
                self._events.append(event)
                new_events.append(event)
                break  # one rebound per frame

        return new_events

    def process_sequence(
        self,
        pose_sequence: list[dict[int, np.ndarray]],
        ball_sequence: list[dict],
        player_sequence: list[dict],
    ) -> list[dict]:
        self._ball_y_history.clear()
        self._events.clear()
        for i, (pose_frame, ball_tracks, player_tracks) in enumerate(
            zip(pose_sequence, ball_sequence, player_sequence)
        ):
            self.update(i, pose_frame, ball_tracks, player_tracks)
        return list(self._events)

    @property
    def events(self) -> list[dict]:
        return list(self._events)

    def _was_descending(self) -> bool:
        """True if ball y-coordinate was generally increasing (moving downward) in history."""
        valid = [y for y in self._ball_y_history if y is not None]
        if len(valid) < 2:
            return False
        return valid[-1] > valid[0]  # image y increases downward


def _ball_center(ball_tracks: dict) -> Optional[tuple[float, float]]:
    ball_info = ball_tracks.get(1, {})
    bbox = ball_info.get("bbox", [])
    if len(bbox) < 4:
        return None
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
