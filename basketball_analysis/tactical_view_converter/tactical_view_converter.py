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
    manual_landmarks : list[dict], optional
        Manually annotated court landmarks from the UI.
        Each dict: {"landmark_id": str, "pixel": [x, y], "frame_t": float}.
        When ≥ 4 valid landmarks are provided, they are used as anchor points
        in the homography computation (blended with YOLO-pose keypoints).
    camera_motion : str, optional
        "static" | "moderate" | "moving".  When not "static", per-frame
        landmark positions are tracked via Lucas-Kanade optical flow between
        the annotated keyframes.
    """

    def __init__(
        self,
        court_image_path: str,
        court_profile: Optional[CourtProfile] = None,
        manual_landmarks: Optional[list[dict]] = None,
        camera_motion: str = "static",
        src_scale: float = 1.0,
    ) -> None:
        self.court_image_path = court_image_path
        self.profile = court_profile or CourtProfile(CourtLevel.NBA)
        self.camera_motion = camera_motion
        # Factor to map manual-anchor pixels (stored in the video's intrinsic
        # resolution) into the pipeline's working resolution (frames are
        # downscaled to max height 720p before all inference/drawing).
        self.src_scale = src_scale

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

        # Precompute manual anchor arrays from the landmark catalog
        self._manual_src: Optional[np.ndarray] = None   # pixel positions (Nx2)
        self._manual_tgt: Optional[np.ndarray] = None   # tactical positions (Nx2)
        self._manual_frame_t: list[float] = []          # frame_t per anchor
        self._manual_landmarks: list[dict] = manual_landmarks or []

        # Per-frame anchor sequences, populated by build_manual_anchor_sequence()
        # when the camera moves. None entries fall back to YOLO keypoints.
        self._manual_src_seq: Optional[list[Optional[np.ndarray]]] = None
        self._manual_tgt_seq: Optional[list[Optional[np.ndarray]]] = None

        if manual_landmarks and len(manual_landmarks) >= 4:
            self._build_manual_anchors(manual_landmarks)

        logger.debug(
            "TacticalViewConverter: %s  %dpx×%dpx  %.1fm×%.1fm  half_court=%s  "
            "manual_anchors=%d  camera_motion=%s",
            self.profile.level,
            self.width,
            self.height,
            self.actual_width_in_meters,
            self.actual_height_in_meters,
            self.profile.half_court,
            len(self._manual_src) if self._manual_src is not None else 0,
            self.camera_motion,
        )

    def _landmark_to_tgt(self, landmark_id: str):
        """Return the tactical-view pixel position [tx, ty] for a landmark, or None."""
        try:
            from .landmarks import CATALOG_BY_ID
        except ImportError:
            return None
        cat = CATALOG_BY_ID.get(landmark_id)
        if cat is None:
            return None
        x_m, y_m = cat.tactical_pos(
            self.actual_width_in_meters, self.actual_height_in_meters
        )
        tx = x_m / self.actual_width_in_meters * self.width
        ty = y_m / self.actual_height_in_meters * self.height
        return [tx, ty]

    def _build_manual_anchors(self, manual_landmarks: list[dict]) -> None:
        """Convert landmark dicts to pixel→tactical arrays (flattened, static use)."""
        src, tgt, ts = [], [], []
        for lm in manual_landmarks:
            tgt_pt = self._landmark_to_tgt(lm.get("landmark_id", ""))
            if tgt_pt is None:
                continue
            px = lm["pixel"]
            src.append([px[0] * self.src_scale, px[1] * self.src_scale])
            tgt.append(tgt_pt)
            ts.append(float(lm.get("frame_t", 0.0)))

        if len(src) >= 4:
            self._manual_src = np.array(src, dtype=np.float32)
            self._manual_tgt = np.array(tgt, dtype=np.float32)
            self._manual_frame_t = ts
            logger.info("Manual anchors loaded: %d points", len(src))

    def _group_keyframes(self, fps: float):
        """Group manual landmarks by keyframe index → list of (kf_idx, src Nx2, tgt Nx2).

        Anchors are scaled to the working (720p) resolution and sorted by frame.
        Only keyframes with ≥4 valid anchors are kept.
        """
        from collections import defaultdict

        groups: dict[int, list[tuple[list, list]]] = defaultdict(list)
        for lm in self._manual_landmarks:
            tgt_pt = self._landmark_to_tgt(lm.get("landmark_id", ""))
            if tgt_pt is None:
                continue
            kf = int(round(float(lm.get("frame_t", 0.0)) * fps))
            px = lm["pixel"]
            groups[kf].append(([px[0] * self.src_scale, px[1] * self.src_scale], tgt_pt))

        keyframes = []
        for kf in sorted(groups):
            pairs = groups[kf]
            if len(pairs) < 4:
                continue
            src = np.array([p[0] for p in pairs], dtype=np.float32)
            tgt = np.array([p[1] for p in pairs], dtype=np.float32)
            keyframes.append((kf, src, tgt))
        return keyframes

    def build_manual_anchor_sequence(
        self, video_path: str, total_frames: int, fps: float,
        precomputed_H: Optional[list] = None,
    ) -> None:
        """
        Build per-frame manual-anchor arrays so the homography tracks a moving camera.

        Manual landmarks may be annotated at several keyframes (the UI encourages
        2–3 keyframes for moving cameras). The camera's GLOBAL motion between
        consecutive frames is estimated (hundreds of background features + RANSAC
        homography) and ALL anchors are warped by it, re-seeded to the exact
        annotated positions at each keyframe. Unlike tracking the sparse anchor
        points directly, a global transform never "loses" individual points
        (occlusion/low-texture), giving near-100 % frame coverage.

        For a static camera (or a single keyframe) the estimation is skipped and
        the single anchor set is reused on every frame.
        """
        if not self._manual_landmarks:
            return

        keyframes = self._group_keyframes(fps)
        if not keyframes:
            return

        # Static / single-keyframe: reuse one anchor set everywhere (no drift).
        if self.camera_motion == "static" or len(keyframes) == 1:
            _, src, tgt = keyframes[0]
            self._manual_src_seq = [src] * total_frames
            self._manual_tgt_seq = [tgt] * total_frames
            logger.info(
                "Manual anchor sequence: static — %d anchors reused on all %d frames",
                len(src), total_frames,
            )
            return

        from utils import iter_video_frames

        kf_indices = [kf for kf, _, _ in keyframes]

        # ── 1) Inter-frame homographies H[i] (frame i-1 → i) ─────────────────────
        # H[0] is None; H[i] maps points in frame i-1 to frame i. None when the
        # estimate fails → treated as identity (no motion) when chaining. If a caller
        # already computed this sequence (e.g. the hoop-box propagation), reuse it so
        # the whole pipeline does a SINGLE optical-flow pass instead of two.
        if precomputed_H is not None and len(precomputed_H) >= total_frames:
            H = precomputed_H
            logger.info("Manual anchor sequence: reusing shared camera-motion homography (no extra pass)")
        else:
            H: list[Optional[np.ndarray]] = [None] * total_frames
            prev_gray = None
            for frame_idx, frame in enumerate(iter_video_frames(video_path, max_height=720)):
                if frame_idx >= total_frames:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    H[frame_idx] = self._estimate_global_homography(prev_gray, gray)
                prev_gray = gray

        # ── 2) Assign every frame to its nearest keyframe (midpoint boundaries) ──
        seq_src: list[Optional[np.ndarray]] = [None] * total_frames
        seq_tgt: list[Optional[np.ndarray]] = [None] * total_frames

        def _nearest_kf(f: int) -> int:
            best, bd = kf_indices[0], abs(f - kf_indices[0])
            for kf in kf_indices[1:]:
                d = abs(f - kf)
                if d < bd:
                    bd, best = d, kf
            return best

        # ── 3) Propagate each keyframe's anchors forward & backward over its region
        covered = 0
        for kf, src, tgt in keyframes:
            anchors = src.astype(np.float32).copy()
            # seed the keyframe itself
            if seq_src[kf] is None or _nearest_kf(kf) == kf:
                seq_src[kf], seq_tgt[kf] = anchors.copy(), tgt.copy()
                covered += 1
            # forward: frames kf+1 .. while nearest keyframe is still this one
            cur = anchors.copy()
            f = kf + 1
            while f < total_frames and _nearest_kf(f) == kf:
                if H[f] is not None:
                    cur = cv2.perspectiveTransform(cur.reshape(-1, 1, 2), H[f]).reshape(-1, 2)
                seq_src[f], seq_tgt[f] = cur.copy(), tgt.copy()
                covered += 1
                f += 1
            # backward: frames kf-1 .. while nearest keyframe is still this one
            cur = anchors.copy()
            f = kf - 1
            while f >= 0 and _nearest_kf(f) == kf:
                # invert the (f+1 → f+1-1) transform to step from frame f+1 back to f
                Hb = H[f + 1]
                if Hb is not None:
                    try:
                        cur = cv2.perspectiveTransform(
                            cur.reshape(-1, 1, 2), np.linalg.inv(Hb)
                        ).reshape(-1, 2)
                    except np.linalg.LinAlgError:
                        pass
                seq_src[f], seq_tgt[f] = cur.copy(), tgt.copy()
                covered += 1
                f -= 1

        self._manual_src_seq = seq_src
        self._manual_tgt_seq = seq_tgt
        logger.info(
            "Manual anchor sequence: %d keyframes, bidirectional homography covered %d/%d frames",
            len(keyframes), covered, total_frames,
        )

    @staticmethod
    def _estimate_global_homography(prev_gray: np.ndarray, gray: np.ndarray):
        """
        Estimate the global camera homography between two consecutive frames.

        Tracks many background features (goodFeaturesToTrack + LK) and fits a
        RANSAC homography. RANSAC rejects the minority of moving foreground
        (players) as outliers. Returns a 3x3 matrix or None if too few matches.
        """
        p0 = cv2.goodFeaturesToTrack(
            prev_gray, maxCorners=300, qualityLevel=0.01, minDistance=8
        )
        if p0 is None or len(p0) < 12:
            return None
        lk_params = dict(
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        p1, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, p0, None, **lk_params)
        if p1 is None:
            return None
        good = status.flatten() == 1
        good0 = p0[good].reshape(-1, 2)
        good1 = p1[good].reshape(-1, 2)
        if len(good0) < 12:
            return None
        H, _ = cv2.findHomography(good0, good1, cv2.RANSAC, 3.0)
        return H

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
        Manual landmarks (if provided) are prepended to the YOLO-pose keypoints as
        strong prior anchors before RANSAC inside Homography.
        In half-court mode, points outside the display canvas are discarded.
        """
        tactical_player_positions: list[dict] = []

        for frame_idx, (frame_keypoints, frame_tracks) in enumerate(
            zip(keypoints_list, player_tracks)
        ):
            tactical_positions: dict = {}
            try:
                raw = frame_keypoints.xy.tolist()
                kp_list = raw[0] if raw else []
            except (IndexError, AttributeError):
                kp_list = []

            # YOLO-pose valid keypoints
            valid_indices = [i for i, kp in enumerate(kp_list) if kp[0] > 0 and kp[1] > 0]
            yolo_src = np.array([kp_list[i] for i in valid_indices], dtype=np.float32)
            yolo_tgt = np.array([self.key_points[i] for i in valid_indices], dtype=np.float32)

            # Per-frame manual anchors (optical-flow tracked) take precedence over
            # the static set when a sequence has been built for a moving camera.
            manual_src = self._manual_src
            manual_tgt = self._manual_tgt
            if self._manual_src_seq is not None and frame_idx < len(self._manual_src_seq):
                manual_src = self._manual_src_seq[frame_idx]
                manual_tgt = self._manual_tgt_seq[frame_idx]

            # Select source/target points for homography:
            # ≥6 manual anchors → use ONLY manual (stable, no per-frame YOLO noise)
            # 4-5 manual anchors → blend with YOLO
            # <4 manual anchors → YOLO only
            if manual_src is not None and len(manual_src) >= 6:
                source_points = manual_src
                target_points = manual_tgt
            elif manual_src is not None and len(manual_src) >= 4:
                source_points = (
                    np.vstack([manual_src, yolo_src]) if len(yolo_src) > 0
                    else manual_src
                )
                target_points = (
                    np.vstack([manual_tgt, yolo_tgt]) if len(yolo_src) > 0
                    else manual_tgt
                )
            else:
                source_points = yolo_src
                target_points = yolo_tgt

            if len(source_points) < 4:
                tactical_player_positions.append(tactical_positions)
                continue

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
