"""
StealTurnoverDetector — detects steals/turnovers from a confirmed change of ball
possession between OPPOSING teams.

A steal/turnover is flagged when:
  1. A player holds the ball (wrist near the ball) for a few consecutive frames
     → "confirmed possessor".
  2. The confirmed possessor changes to a player on the OPPOSING team.
  3. A cooldown has elapsed since the last steal (debounce).

Without the team check + confirmation + cooldown the previous version emitted a
"steal" on every frame the nearest-wrist player flickered (e.g. during a scrum),
producing hundreds of false events. Passes between team-mates are explicitly NOT
steals.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from pose_estimator.skeleton_utils import KP

try:
    from configs.settings import settings as _settings
    _CONF = _settings.event_pose_conf_threshold
except Exception:
    _CONF = 0.12
_WRIST_TO_BALL_PX = 70     # max wrist-to-ball distance to consider contact
_MIN_HOLD_FRAMES = 3       # consecutive frames of contact to confirm possession
_COOLDOWN_FRAMES = 30      # ~1s at 30fps — min gap between steal events


class StealTurnoverDetector:
    """
    Detect steals / turnovers (possession changes between opposing teams).

    Parameters
    ----------
    wrist_ball_px : float
        Maximum wrist-to-ball pixel distance to consider contact.
    min_hold_frames : int
        Consecutive contact frames required to confirm a possessor.
    cooldown_frames : int
        Minimum frames between consecutive steal events.
    """

    def __init__(
        self,
        wrist_ball_px: float = _WRIST_TO_BALL_PX,
        min_hold_frames: int = _MIN_HOLD_FRAMES,
        cooldown_frames: int = _COOLDOWN_FRAMES,
    ) -> None:
        self.wrist_ball_px = wrist_ball_px
        self.min_hold_frames = min_hold_frames
        self.cooldown_frames = cooldown_frames
        self._candidate: Optional[int] = None      # nearest-wrist player this run
        self._candidate_streak: int = 0
        self._confirmed: Optional[int] = None       # last confirmed possessor
        self._last_event_frame: int = -cooldown_frames
        self._events: list[dict] = []

    def update(
        self,
        frame_idx: int,
        pose_frame: dict[int, np.ndarray],
        ball_tracks: dict,
        team_of: Optional[dict] = None,
    ) -> list[dict]:
        ball_center = _ball_center(ball_tracks)
        new_events: list[dict] = []
        if ball_center is None:
            return new_events

        # Nearest wrist to the ball this frame (within range, confident enough)
        nearest: Optional[int] = None
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
                    nearest = track_id

        # Track how long the same player has been the nearest contact
        if nearest is not None and nearest == self._candidate:
            self._candidate_streak += 1
        else:
            self._candidate = nearest
            self._candidate_streak = 1 if nearest is not None else 0

        # Confirm a possessor once contact is sustained
        if self._candidate is not None and self._candidate_streak >= self.min_hold_frames:
            new_possessor = self._candidate
            if (
                self._confirmed is not None
                and new_possessor != self._confirmed
                and frame_idx - self._last_event_frame >= self.cooldown_frames
                and _is_opposing(team_of, new_possessor, self._confirmed)
            ):
                event = {
                    "type": "steal",
                    "track_id": new_possessor,        # gained possession
                    "from_track_id": self._confirmed, # lost possession
                    "frame": frame_idx,
                }
                self._events.append(event)
                new_events.append(event)
                self._last_event_frame = frame_idx
            self._confirmed = new_possessor

        return new_events

    def process_sequence(
        self,
        pose_sequence: list[dict[int, np.ndarray]],
        ball_sequence: list[dict],
        player_assignment: Optional[list[dict]] = None,
    ) -> list[dict]:
        self._candidate = None
        self._candidate_streak = 0
        self._confirmed = None
        self._last_event_frame = -self.cooldown_frames
        self._events.clear()
        for i, (pose_frame, ball_tracks) in enumerate(zip(pose_sequence, ball_sequence)):
            team_of = (
                player_assignment[i]
                if player_assignment is not None and i < len(player_assignment)
                else None
            )
            self.update(i, pose_frame, ball_tracks, team_of)
        return list(self._events)

    @property
    def events(self) -> list[dict]:
        return list(self._events)


def _is_opposing(team_of: Optional[dict], a: int, b: int) -> bool:
    """
    True if players a and b are on different teams. When team info is unavailable
    we cannot tell a steal from a pass, so require it (return False) to avoid the
    historical over-counting.
    """
    if not team_of:
        return False
    ta = team_of.get(a, team_of.get(int(a)) if a is not None else None)
    tb = team_of.get(b, team_of.get(int(b)) if b is not None else None)
    if ta is None or tb is None:
        return False
    return ta != tb


def _ball_center(ball_tracks: dict) -> Optional[tuple[float, float]]:
    ball_info = ball_tracks.get(1, {})
    bbox = ball_info.get("bbox", [])
    if len(bbox) < 4:
        return None
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
