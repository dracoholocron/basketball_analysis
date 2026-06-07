"""
StealTurnoverDetector — detects steals and turnovers from wrist proximity.

A steal/turnover is flagged when:
  1. A player (defender) has their wrist very close to the ball.
  2. Another player (attacker) had possession in recent frames.
  3. Ball possession switches hands within a short window.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from pose_estimator.skeleton_utils import KP

_CONF = 0.3
_WRIST_TO_BALL_PX = 80    # max wrist-to-ball distance to consider a steal
_POSSESSION_WINDOW = 10   # frames to look back for previous possessor


class StealTurnoverDetector:
    """
    Detect steals and turnovers.

    Parameters
    ----------
    wrist_ball_px : float
        Maximum wrist-to-ball pixel distance to consider contact.
    possession_window : int
        Frames to look back for the previous ball possessor.
    """

    def __init__(
        self,
        wrist_ball_px: float = _WRIST_TO_BALL_PX,
        possession_window: int = _POSSESSION_WINDOW,
    ) -> None:
        self.wrist_ball_px = wrist_ball_px
        self.possession_window = possession_window
        self._possession_history: deque[Optional[int]] = deque(maxlen=possession_window)
        self._events: list[dict] = []

    def update(
        self,
        frame_idx: int,
        pose_frame: dict[int, np.ndarray],
        ball_tracks: dict,
    ) -> list[dict]:
        ball_center = _ball_center(ball_tracks)
        new_events: list[dict] = []

        if ball_center is None:
            self._possession_history.append(None)
            return new_events

        # Find who is touching the ball this frame
        current_possessor: Optional[int] = None
        min_dist = self.wrist_ball_px
        for track_id, kps in pose_frame.items():
            for wrist_idx in (KP["right_wrist"], KP["left_wrist"]):
                if kps[wrist_idx, 2] < _CONF:
                    continue
                dist = np.hypot(
                    kps[wrist_idx, 0] - ball_center[0],
                    kps[wrist_idx, 1] - ball_center[1],
                )
                if dist < min_dist:
                    min_dist = dist
                    current_possessor = track_id

        # Check if possession changed
        previous_possessors = [p for p in self._possession_history if p is not None]
        if (
            current_possessor is not None
            and previous_possessors
            and current_possessor != previous_possessors[-1]
        ):
            prev_id = previous_possessors[-1]
            event = {
                "type": "steal",
                "track_id": current_possessor,      # player who gained possession
                "from_track_id": prev_id,           # player who lost it
                "frame": frame_idx,
            }
            self._events.append(event)
            new_events.append(event)

        self._possession_history.append(current_possessor)
        return new_events

    def process_sequence(
        self,
        pose_sequence: list[dict[int, np.ndarray]],
        ball_sequence: list[dict],
    ) -> list[dict]:
        self._possession_history.clear()
        self._events.clear()
        for i, (pose_frame, ball_tracks) in enumerate(zip(pose_sequence, ball_sequence)):
            self.update(i, pose_frame, ball_tracks)
        return list(self._events)

    @property
    def events(self) -> list[dict]:
        return list(self._events)


def _ball_center(ball_tracks: dict) -> Optional[tuple[float, float]]:
    ball_info = ball_tracks.get(1, {})
    bbox = ball_info.get("bbox", [])
    if len(bbox) < 4:
        return None
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
