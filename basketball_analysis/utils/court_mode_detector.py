"""
CourtModeDetector — infer half-court vs. full-court from detected keypoints.

Heuristic: count how many of the 18 canonical keypoints are visible on average
across the first N frames.  If fewer than `half_court_kp_threshold` are visible
the game is treated as half-court and global speed/distance are disabled.
"""
from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

# Keypoint indices that belong exclusively to the right half of the court
# (indices 10-15 in our 18-point layout).
RIGHT_HALF_INDICES = {10, 11, 12, 13, 14, 15}
LEFT_HALF_INDICES = {0, 1, 2, 3, 4, 5, 8, 9}


class CourtModeDetector:
    """
    Detect whether the video shows a full court or a single half-court.

    Parameters
    ----------
    probe_frames : int
        Number of frames to probe at the start of the video.
    min_right_kp : int
        Minimum number of right-half keypoints that must be detected (on average)
        to classify the footage as full-court.
    """

    def __init__(self, probe_frames: int = 30, min_right_kp: int = 2) -> None:
        self.probe_frames = probe_frames
        self.min_right_kp = min_right_kp

    def detect(self, keypoints_list: Sequence) -> bool:
        """
        Return True if the video is in half-court mode.

        Parameters
        ----------
        keypoints_list :
            Output of CourtKeypointDetector (list of YOLO Results objects).
        """
        n = min(self.probe_frames, len(keypoints_list))
        if n == 0:
            return False

        right_kp_counts: list[int] = []
        for frame_kp in keypoints_list[:n]:
            try:
                raw = frame_kp.xy.tolist()
                kp_list = raw[0] if raw else []
            except (IndexError, AttributeError):
                kp_list = []
            count = sum(
                1
                for i in RIGHT_HALF_INDICES
                if i < len(kp_list) and kp_list[i][0] > 0 and kp_list[i][1] > 0
            )
            right_kp_counts.append(count)

        avg_right_kp = sum(right_kp_counts) / n
        is_half = avg_right_kp < self.min_right_kp
        logger.info(
            "CourtModeDetector: avg right-half KP=%.2f → %s",
            avg_right_kp,
            "HALF-COURT" if is_half else "FULL-COURT",
        )
        return is_half
