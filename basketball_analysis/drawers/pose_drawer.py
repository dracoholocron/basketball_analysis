import cv2
import numpy as np

# COCO-17 skeleton connectivity — imported lazily to avoid circular deps
_COCO_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]


class PoseDrawer:
    """
    Draws COCO-17 skeletons (bones + joints) for each tracked player.

    Parameters
    ----------
    player_filter : list[int] | None
        When set, only draw poses for the specified track IDs.
        None (default) draws poses for all players.
    """

    CONF_THRESHOLD = 0.3
    BONE_COLOR  = (0, 255, 255)   # cyan (BGR)
    JOINT_COLOR = (255, 255, 0)   # yellow (BGR)
    BONE_THICKNESS = 2
    JOINT_RADIUS = 3

    def __init__(self, player_filter: list[int] | None = None):
        self.player_filter = player_filter

    def draw_frame(self, frame, frame_num, pose_sequence):
        if frame_num >= len(pose_sequence):
            return frame
        for track_id, keypoints in pose_sequence[frame_num].items():
            if self.player_filter is not None and track_id not in self.player_filter:
                continue
            frame = self._draw_skeleton(frame, keypoints)
        return frame

    def _draw_skeleton(self, frame, keypoints):
        if keypoints is None or len(keypoints) < 17:
            return frame
        kp = np.asarray(keypoints)

        for i, j in _COCO_SKELETON:
            if kp[i][2] > self.CONF_THRESHOLD and kp[j][2] > self.CONF_THRESHOLD:
                pt1 = (int(kp[i][0]), int(kp[i][1]))
                pt2 = (int(kp[j][0]), int(kp[j][1]))
                cv2.line(frame, pt1, pt2, self.BONE_COLOR, self.BONE_THICKNESS)

        for kpi in kp:
            if kpi[2] > self.CONF_THRESHOLD:
                cv2.circle(
                    frame,
                    (int(kpi[0]), int(kpi[1])),
                    self.JOINT_RADIUS,
                    self.JOINT_COLOR,
                    -1,
                )
        return frame
