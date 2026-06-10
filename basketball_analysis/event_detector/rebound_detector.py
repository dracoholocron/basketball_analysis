"""
ReboundDetector — detects rebounds from ball trajectory + player proximity.

A rebound is flagged when:
  1. The ball trajectory shows a direction reversal: was descending (y increasing),
     now ascending (y decreasing) — i.e., the ball just hit the rim/floor and bounced.
  2. A player is within proximity of the ball at the reversal point.
  3. A cooldown prevents multiple events for the same play.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

_HISTORY = 12           # frames of ball y-history to analyze trajectory
_BALL_PROXIMITY_PX = 80
_COOLDOWN_FRAMES = 60   # ~2s at 30fps — prevents consecutive triggers per play
_RIM_PROXIMITY_FACTOR = 3.0  # rebound must occur within N·rim-width of a rim box


class ReboundDetector:
    """
    Detect rebounds per player.

    Parameters
    ----------
    history_frames : int
        Number of frames to track ball y-trajectory.
    ball_proximity_px : float
        Maximum pixel distance from ball to player bbox center for a rebound.
    cooldown_frames : int
        Minimum frames between consecutive rebound events.
    """

    def __init__(
        self,
        history_frames: int = _HISTORY,
        ball_proximity_px: float = _BALL_PROXIMITY_PX,
        cooldown_frames: int = _COOLDOWN_FRAMES,
        rim_proximity_factor: float = _RIM_PROXIMITY_FACTOR,
    ) -> None:
        self.history_frames = history_frames
        self.ball_proximity_px = ball_proximity_px
        self.cooldown_frames = cooldown_frames
        self.rim_proximity_factor = rim_proximity_factor
        self._ball_y_history: deque[Optional[float]] = deque(maxlen=history_frames)
        self._last_event_frame: int = -cooldown_frames
        self._events: list[dict] = []

    def update(
        self,
        frame_idx: int,
        pose_frame: dict[int, np.ndarray],
        ball_tracks: dict,
        player_tracks: list[dict],
        rim_box: Optional[list] = None,
    ) -> list[dict]:
        """
        Process one frame. Returns list of new rebound events.

        Parameters
        ----------
        player_tracks : per-frame player dict {track_id: {"bbox": ...}}
        rim_box : [x1,y1,x2,y2] of the active rim this frame (or None). When given,
            a rebound is only counted if the ball is near the rim — kills false
            positives from floor bounces, passes and dribbles elsewhere on court.
        """
        ball_center = _ball_center(ball_tracks)
        ball_y = ball_center[1] if ball_center else None
        self._ball_y_history.append(ball_y)
        new_events: list[dict] = []

        if frame_idx - self._last_event_frame < self.cooldown_frames:
            return new_events

        if not self._is_trajectory_reversal():
            return new_events

        if ball_center is None:
            return new_events

        # Rim-proximity gate: a real rebound happens at the basket. If a rim box is
        # available for this frame, require the ball to be within N·rim-width of it.
        if rim_box is not None and len(rim_box) >= 4:
            rcx = (rim_box[0] + rim_box[2]) / 2
            rcy = (rim_box[1] + rim_box[3]) / 2
            rim_w = max(1.0, rim_box[2] - rim_box[0])
            if np.hypot(ball_center[0] - rcx, ball_center[1] - rcy) > self.rim_proximity_factor * rim_w:
                return new_events

        tracks = player_tracks if isinstance(player_tracks, dict) else {}
        for track_id, info in tracks.items():
            bbox = info.get("bbox", [])
            if len(bbox) < 4:
                continue
            px = (bbox[0] + bbox[2]) / 2
            py = (bbox[1] + bbox[3]) / 2
            dist = np.hypot(px - ball_center[0], py - ball_center[1])
            if dist <= self.ball_proximity_px:
                event = {"type": "rebound", "track_id": track_id, "frame": frame_idx}
                self._events.append(event)
                new_events.append(event)
                self._last_event_frame = frame_idx
                break  # one rebound per frame

        return new_events

    def process_sequence(
        self,
        pose_sequence: list[dict[int, np.ndarray]],
        ball_sequence: list[dict],
        player_sequence: list[dict],
        rim_sequence: Optional[list] = None,
    ) -> list[dict]:
        """``rim_sequence`` (optional): per-frame rim box [x1,y1,x2,y2]|None. When
        provided, rebounds are gated to near the rim (far fewer false positives)."""
        self._ball_y_history.clear()
        self._events.clear()
        self._last_event_frame = -self.cooldown_frames
        for i, (pose_frame, ball_tracks, player_tracks) in enumerate(
            zip(pose_sequence, ball_sequence, player_sequence)
        ):
            rim_box = rim_sequence[i] if (rim_sequence is not None and i < len(rim_sequence)) else None
            self.update(i, pose_frame, ball_tracks, player_tracks, rim_box=rim_box)
        return list(self._events)

    @property
    def events(self) -> list[dict]:
        return list(self._events)

    def _is_trajectory_reversal(self) -> bool:
        """
        True if the ball trajectory shows a clear descent-then-ascent pattern:
        first 60% of history trending down (y increasing), last 40% trending up.
        Requires a minimum net movement to filter out noise.
        """
        valid = [y for y in self._ball_y_history if y is not None]
        if len(valid) < 6:
            return False

        split = max(2, len(valid) * 6 // 10)
        first_part = valid[:split]
        last_part = valid[split:]

        if len(last_part) < 2:
            return False

        first_trend = first_part[-1] - first_part[0]   # positive = descending
        last_trend = last_part[-1] - last_part[0]      # negative = ascending

        # Require a clear bounce in both segments to filter noise (tightened to cut
        # over-counting from small jitters / dribbles).
        return first_trend > 18.0 and last_trend < -12.0


def _ball_center(ball_tracks: dict) -> Optional[tuple[float, float]]:
    ball_info = ball_tracks.get(1, {})
    bbox = ball_info.get("bbox", [])
    if len(bbox) < 4:
        return None
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
