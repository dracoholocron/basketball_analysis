"""
TacticalViewConverter — converts player pixel positions to a top-down court map.

Now parametrized via CourtProfile so it works for NBA, FIBA-youth, primaria,
and mini-basket courts without hard-coded dimensions.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Optional

import cv2
import numpy as np

from .homography import Homography
from utils import get_foot_position, measure_distance
from configs.settings import CourtProfile, CourtLevel

logger = logging.getLogger(__name__)


def _build_keypoints(w_px: int, h_px: int, w_m: float, h_m: float) -> list[tuple[int, int]]:
    """
    Build the 18 canonical tactical-view keypoints scaled to a given pixel canvas.

    The layout mirrors the 18 YOLO-pose keypoints defined during model training:
    6 on the left edge, 2 on the midline, 2 on the left free-throw line,
    6 on the right edge, 2 on the right free-throw line.

    Free-throw line distance from baseline: 5.79 m (NBA/FIBA).
    Lane-width anchors at 5.18 m and 10 m from the bottom edge.
    Corner arc at 0.91 m from the bottom edge.
    """
    # Vertical anchor values in metres (from bottom edge)
    y_corner_arc = 0.91
    y_lane_bottom = 5.18
    y_lane_top = 10.0
    y_corner_top = h_m - 0.91

    # Horizontal distance from baseline to free-throw line
    x_ft = 5.79

    def px(x_m: float, y_m: float) -> tuple[int, int]:
        return (int(x_m / w_m * w_px), int(y_m / h_m * h_px))

    return [
        # Left edge (x=0)
        px(0, 0),
        px(0, y_corner_arc),
        px(0, y_lane_bottom),
        px(0, y_lane_top),
        px(0, y_corner_top),
        px(0, h_m),

        # Midline (x = w_m/2)
        px(w_m / 2, h_m),
        px(w_m / 2, 0),

        # Left free-throw line
        px(x_ft, y_lane_bottom),
        px(x_ft, y_lane_top),

        # Right edge (x = w_m)
        px(w_m, h_m),
        px(w_m, y_corner_top),
        px(w_m, y_lane_top),
        px(w_m, y_lane_bottom),
        px(w_m, y_corner_arc),
        px(w_m, 0),

        # Right free-throw line
        px(w_m - x_ft, y_lane_bottom),
        px(w_m - x_ft, y_lane_top),
    ]


class TacticalViewConverter:
    """
    Project player positions from camera space to a top-down court diagram.

    Parameters
    ----------
    court_image_path : str
        Path to the background court diagram image.
    court_profile : CourtProfile, optional
        Court dimensions / level.  Defaults to NBA if not supplied.
    """

    def __init__(
        self,
        court_image_path: str,
        court_profile: Optional[CourtProfile] = None,
    ) -> None:
        self.court_image_path = court_image_path
        self.profile = court_profile or CourtProfile(CourtLevel.NBA)

        self.width: int = self.profile.display_w_px
        self.height: int = self.profile.display_h_px
        self.actual_width_in_meters: float = self.profile.width_m
        self.actual_height_in_meters: float = self.profile.height_m

        self.key_points: list[tuple[int, int]] = _build_keypoints(
            self.width,
            self.height,
            self.actual_width_in_meters,
            self.actual_height_in_meters,
        )

        logger.debug(
            "TacticalViewConverter: %s  %dpx×%dpx  %.1fm×%.1fm  half_court=%s",
            self.profile.level,
            self.width,
            self.height,
            self.actual_width_in_meters,
            self.actual_height_in_meters,
            self.profile.half_court,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def validate_keypoints(self, keypoints_list: list) -> list:
        """
        Zero out detected keypoints whose proportional distances to neighbouring
        keypoints deviate more than 80 % from the expected tactical-view ratios.
        """
        keypoints_list = deepcopy(keypoints_list)

        for frame_idx, frame_keypoints in enumerate(keypoints_list):
            try:
                raw = frame_keypoints.xy.tolist()
                kp_list = raw[0] if raw else []
            except (IndexError, AttributeError):
                kp_list = []

            detected_indices = [
                i for i, kp in enumerate(kp_list) if kp[0] > 0 and kp[1] > 0
            ]
            if len(detected_indices) < 3:
                continue

            invalid_keypoints: list[int] = []
            for i in detected_indices:
                other_indices = [
                    idx
                    for idx in detected_indices
                    if idx != i and idx not in invalid_keypoints
                ]
                if len(other_indices) < 2:
                    continue
                j, k = other_indices[0], other_indices[1]

                d_ij = measure_distance(kp_list[i], kp_list[j])
                d_ik = measure_distance(kp_list[i], kp_list[k])
                t_ij = measure_distance(self.key_points[i], self.key_points[j])
                t_ik = measure_distance(self.key_points[i], self.key_points[k])

                if t_ij > 0 and t_ik > 0 and d_ik > 0:
                    prop_detected = d_ij / d_ik
                    prop_tactical = t_ij / t_ik
                    error = abs(prop_detected - prop_tactical) / prop_tactical
                    if error > 0.8:
                        keypoints_list[frame_idx].xy[0][i] *= 0
                        keypoints_list[frame_idx].xyn[0][i] *= 0
                        invalid_keypoints.append(i)

        return keypoints_list

    def transform_players_to_tactical_view(
        self,
        keypoints_list: list,
        player_tracks: list,
    ) -> list[dict]:
        """
        Map player foot positions from video coordinates to tactical-view coordinates.

        Returns a list of per-frame dicts: {player_id: (x_px, y_px)}.
        In half-court mode, points outside the display canvas are discarded.
        """
        tactical_player_positions: list[dict] = []

        for frame_keypoints, frame_tracks in zip(keypoints_list, player_tracks):
            tactical_positions: dict = {}
            try:
                raw = frame_keypoints.xy.tolist()
                kp_list = raw[0] if raw else []
            except (IndexError, AttributeError):
                kp_list = []

            valid_indices = [i for i, kp in enumerate(kp_list) if kp[0] > 0 and kp[1] > 0]
            if len(valid_indices) < 4:
                tactical_player_positions.append(tactical_positions)
                continue

            source_points = np.array(
                [kp_list[i] for i in valid_indices], dtype=np.float32
            )
            target_points = np.array(
                [self.key_points[i] for i in valid_indices], dtype=np.float32
            )

            try:
                homography = Homography(source_points, target_points)
                for player_id, player_data in frame_tracks.items():
                    player_pos = np.array([get_foot_position(player_data["bbox"])])
                    tactical_pos = homography.transform_points(player_pos)
                    tx, ty = tactical_pos[0]
                    if 0 <= tx <= self.width and 0 <= ty <= self.height:
                        tactical_positions[player_id] = [float(tx), float(ty)]
            except (ValueError, cv2.error) as exc:
                logger.debug("Homography failed frame: %s", exc)

            tactical_player_positions.append(tactical_positions)

        return tactical_player_positions
