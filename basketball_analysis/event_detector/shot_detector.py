"""
ShotDetector — detects shot attempts from pose + ball trajectory.

A shot is flagged when:
  1. A player's shooting wrist is elevated above their shoulder.
  2. The ball is within proximity of that player.
  3. These conditions persist for a minimum number of frames.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

import numpy as np

from pose_estimator.skeleton_utils import KP, joint_angle, wrist_position

_CONF = 0.3
_MIN_FRAMES = 3          # consecutive frames required to confirm a shot
_BALL_PROXIMITY_PX = 120  # max distance from wrist to ball center


class ShotDetector:
    """
    Detect shot attempts per player across a video sequence.

    Parameters
    ----------
    min_frames : int
        Minimum consecutive frames a player must be in shooting pose.
    ball_proximity_px : float
        Maximum pixel distance from wrist to ball to consider possession during shot.
    """

    def __init__(
        self,
        min_frames: int = _MIN_FRAMES,
        ball_proximity_px: float = _BALL_PROXIMITY_PX,
    ) -> None:
        self.min_frames = min_frames
        self.ball_proximity_px = ball_proximity_px
        self._counters: dict[int, int] = defaultdict(int)
        self._events: list[dict] = []

    def update(
        self,
        frame_idx: int,
        pose_frame: dict[int, np.ndarray],
        ball_tracks: dict,
    ) -> list[dict]:
        """
        Process one frame. Returns list of new shot events detected this frame.

        Parameters
        ----------
        frame_idx : int
        pose_frame : {track_id: (17,3) keypoints}
        ball_tracks : {1: {"bbox": [x1,y1,x2,y2]}} or {}
        """
        ball_center = _ball_center(ball_tracks)
        new_events: list[dict] = []

        active_ids = set()
        for track_id, kps in pose_frame.items():
            if _is_shooting_pose(kps) and _ball_near_wrist(kps, ball_center, self.ball_proximity_px):
                active_ids.add(track_id)
                self._counters[track_id] += 1
                if self._counters[track_id] == self.min_frames:
                    event = {
                        "type": "shot_attempt",
                        "track_id": track_id,
                        "frame": frame_idx,
                    }
                    self._events.append(event)
                    new_events.append(event)
            else:
                self._counters[track_id] = 0

        # Reset counters for players no longer in frame
        for tid in list(self._counters):
            if tid not in active_ids and tid not in pose_frame:
                self._counters[tid] = 0

        return new_events

    def process_sequence(
        self,
        pose_sequence: list[dict[int, np.ndarray]],
        ball_sequence: list[dict],
    ) -> list[dict]:
        """Run over a full sequence and return all detected shot events."""
        self._counters.clear()
        self._events.clear()
        for i, (pose_frame, ball_tracks) in enumerate(zip(pose_sequence, ball_sequence)):
            self.update(i, pose_frame, ball_tracks)
        return list(self._events)

    @property
    def events(self) -> list[dict]:
        return list(self._events)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ball_center(ball_tracks: dict) -> Optional[tuple[float, float]]:
    ball_info = ball_tracks.get(1, {})
    bbox = ball_info.get("bbox", [])
    if len(bbox) < 4:
        return None
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def _is_shooting_pose(kps: np.ndarray, conf: float = _CONF) -> bool:
    """True when either wrist is above the same-side shoulder (shooting motion)."""
    for wrist_name, shoulder_name in [
        ("right_wrist", "right_shoulder"),
        ("left_wrist", "left_shoulder"),
    ]:
        wi, si = KP[wrist_name], KP[shoulder_name]
        if kps[wi, 2] >= conf and kps[si, 2] >= conf:
            # In image coords, y increases downward → wrist above shoulder = lower y value
            if kps[wi, 1] < kps[si, 1]:
                return True
    return False


def _ball_near_wrist(
    kps: np.ndarray,
    ball_center: Optional[tuple[float, float]],
    max_dist: float,
) -> bool:
    if ball_center is None:
        return True  # can't rule it out without ball info
    for wrist_name in ("right_wrist", "left_wrist"):
        pos = wrist_position(kps, side=wrist_name.split("_")[0])
        if pos is not None:
            dist = np.hypot(pos[0] - ball_center[0], pos[1] - ball_center[1])
            if dist <= max_dist:
                return True
    return False
