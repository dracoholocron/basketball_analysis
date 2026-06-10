import os
import argparse
import logging

from utils import read_video, save_video, iter_video_frames, get_video_properties, CourtModeDetector
from utils import read_stub, save_stub
from trackers import PlayerTracker, BallTracker
from team_assigner import TeamAssigner
from court_keypoint_detector import CourtKeypointDetector
from ball_aquisition import BallAquisitionDetector
from pass_and_interception_detector import PassAndInterceptionDetector
from tactical_view_converter import TacticalViewConverter
from speed_and_distance_calculator import SpeedAndDistanceCalculator
from drawers import (
    PlayerTracksDrawer,
    BallTracksDrawer,
    CourtKeypointDrawer,
    TeamBallControlDrawer,
    FrameNumberDrawer,
    PassInterceptionDrawer,
    TacticalViewDrawer,
    SpeedAndDistanceDrawer,
    PoseDrawer,
)
from configs import (
    STUBS_DEFAULT_PATH,
    MULTICLASS_DETECTOR_PATH,
    PLAYER_DETECTOR_PATH,
    BALL_DETECTOR_PATH,
    COURT_KEYPOINT_DETECTOR_PATH,
    OUTPUT_VIDEO_PATH,
)
from configs.settings import CourtProfile, CourtLevel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("basketball_analysis")


def parse_args():
    parser = argparse.ArgumentParser(description="Basketball Video Analysis")
    parser.add_argument("input_video", type=str, help="Path to input video file")
    parser.add_argument(
        "--output_video",
        type=str,
        default=OUTPUT_VIDEO_PATH,
        help="Path to output video file",
    )
    parser.add_argument(
        "--stub_path",
        type=str,
        default=STUBS_DEFAULT_PATH,
        help="Path to stub directory",
    )
    parser.add_argument(
        "--no_stubs",
        action="store_true",
        default=False,
        help="Disable stub caching (always re-run all detectors)",
    )
    parser.add_argument(
        "--team1_jersey",
        type=str,
        default="white shirt",
        help="Description of Team 1 jersey for zero-shot classification",
    )
    parser.add_argument(
        "--team2_jersey",
        type=str,
        default="dark blue shirt",
        help="Description of Team 2 jersey for zero-shot classification",
    )
    return parser.parse_args()


def _resolve_detector_path(multiclass: str, legacy: str) -> str:
    """Return multi-class model path if it exists, else fall back to the legacy model."""
    return multiclass if os.path.exists(multiclass) else legacy


def _stitch_tracks(player_tracks: list[dict], frame_width: int,
                   max_gap_s: float, max_dist_frac: float,
                   fps: float) -> list[dict]:
    """Link fragmented tracks of the same player by spatio-temporal continuity.

    When a track ends and another begins shortly after (≤ max_gap_s) near where the
    first ended, they are almost certainly the same player who was briefly lost
    (occlusion / missed detection). We merge B into A. Continuity-based, so it does
    NOT confuse teammates by appearance. Reduces fragmentation regardless of tracker.
    """
    import math
    stats: dict = {}  # tid -> [first_frame, last_frame, first_center, last_center]
    for i, frame in enumerate(player_tracks):
        for tid, info in frame.items():
            bb = info.get("bbox", [])
            if len(bb) < 4:
                continue
            c = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
            if tid not in stats:
                stats[tid] = [i, i, c, c]
            else:
                stats[tid][1] = i
                stats[tid][3] = c
    if len(stats) < 2:
        return player_tracks

    gap_frames = max(1, int(max_gap_s * fps))
    order = sorted(stats, key=lambda t: stats[t][0])
    parent = {t: t for t in stats}
    active: list[dict] = []  # finished/extending chains: {last, lc, root}
    for t in order:
        f0, _f1, c0, _c1 = stats[t]
        best, bestd = None, 1e18
        for a in active:
            la = a["last"]
            if la < f0 and (f0 - la) <= gap_frames:
                d = math.hypot(c0[0] - a["lc"][0], c0[1] - a["lc"][1])
                gap_s = max(1.0, (f0 - la) / fps)
                if d <= max_dist_frac * frame_width * gap_s and d < bestd:
                    best, bestd = a, d
        if best is not None:
            parent[t] = best["root"]
            best["last"] = stats[t][1]
            best["lc"] = stats[t][3]
        else:
            active.append({"last": stats[t][1], "lc": stats[t][3], "root": t})

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    new: list[dict] = []
    for frame in player_tracks:
        nf: dict = {}
        for tid, info in frame.items():
            r = find(tid) if tid in parent else tid
            if r not in nf:
                nf[r] = info
        new.append(nf)

    n_after = len({find(t) for t in stats})
    logger.info(
        "Tracklet stitching: %d tracks → %d after linking (gap≤%.1fs, dist≤%.0f px/s)",
        len(stats), n_after, max_gap_s, max_dist_frac * frame_width,
    )
    return new


def _ball_center(bt: dict):
    bbox = bt.get(1, {}).get("bbox", [])
    if len(bbox) < 4:
        return None
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _rim_box_sequence(rims_with_t: list[tuple[int, list[float]]],
                      total_frames: int,
                      clamp_margin: int | None = None) -> list[list[float] | None]:
    """Build a per-frame rim box from boxes annotated at different frame indices.

    Each annotation carries the frame it was drawn on (frame_t × fps). For a
    panning camera the rim moves on screen, so we linearly interpolate between
    consecutive annotations of the *same* hoop. With a single annotation this
    degrades to a static box on every frame (correct for a fixed camera).

    ``clamp_margin`` (frames): when set, the box is only emitted within
    ``[first - margin, last + margin]`` and is None outside. Used when several
    distinct hoops are annotated, so a hoop that's only visible during one part of
    the pan does not "exist" (frozen) over the whole video.
    """
    if not rims_with_t:
        return [None] * total_frames
    pts = sorted(rims_with_t, key=lambda p: p[0])
    lo, hi = pts[0][0], pts[-1][0]
    seq: list[list[float] | None] = [None] * total_frames
    for i in range(total_frames):
        if clamp_margin is not None and (i < lo - clamp_margin or i > hi + clamp_margin):
            seq[i] = None
            continue
        if i <= lo:
            seq[i] = list(pts[0][1])
        elif i >= hi:
            seq[i] = list(pts[-1][1])
        else:
            a, b = pts[0], pts[-1]
            for k in range(len(pts) - 1):
                if pts[k][0] <= i <= pts[k + 1][0]:
                    a, b = pts[k], pts[k + 1]
                    break
            span = (b[0] - a[0]) or 1
            t = (i - a[0]) / span
            seq[i] = [a[1][j] + (b[1][j] - a[1][j]) * t for j in range(4)]
    return seq


def _global_motion_sequence(video_path: str, total_frames: int) -> list:
    """Per-frame camera-motion homography H[i] (maps frame i-1 → i), one video pass.

    Reuses the same LK+RANSAC global-motion estimator as the court-anchor
    propagation. Used to propagate manual hoop/backboard boxes across the whole
    video so a couple of marks follow the panning camera everywhere."""
    import cv2
    from utils.video_utils import iter_video_frames
    from tactical_view_converter.tactical_view_converter import TacticalViewConverter

    H: list = [None] * total_frames
    prev_gray = None
    for i, frame in enumerate(iter_video_frames(video_path, max_height=720)):
        if i >= total_frames:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            H[i] = TacticalViewConverter._estimate_global_homography(prev_gray, gray)
        prev_gray = gray
    return H


def _propagate_box_seq(boxes_with_t: list[tuple[int, list[float]]], H: list,
                       total_frames: int) -> list[list[float] | None]:
    """Propagate annotated box(es) across ALL frames via the camera-motion homography.

    Each annotation is a keyframe; every frame is assigned to its nearest keyframe and
    the box's 4 corners are warped forward/backward by the chained per-frame homography
    (re-seeded at each keyframe to limit drift), then reduced to an axis-aligned bbox.
    A box for a hoop that is off-screen at some moment warps off-frame on its own, so
    multiple hoops don't interfere. Covers the full video from just 1–2 marks."""
    import cv2
    import numpy as np
    if not boxes_with_t:
        return [None] * total_frames
    pts = sorted(boxes_with_t, key=lambda p: p[0])
    kf_indices = [f for f, _ in pts]

    def nearest_kf(f: int) -> int:
        return min(kf_indices, key=lambda k: abs(f - k))

    def _corners(box: list[float]) -> "np.ndarray":
        x1, y1, x2, y2 = box
        return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)

    def _bbox(c: "np.ndarray") -> list[float]:
        xs, ys = c[:, 0], c[:, 1]
        return [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]

    seq: list[list[float] | None] = [None] * total_frames
    for kf, box in pts:
        base = _corners(box)
        if nearest_kf(kf) == kf:
            seq[kf] = list(box)
        cur = base.copy()
        f = kf + 1
        while f < total_frames and nearest_kf(f) == kf:
            if H[f] is not None:
                cur = cv2.perspectiveTransform(cur.reshape(-1, 1, 2), H[f]).reshape(-1, 2)
            seq[f] = _bbox(cur)
            f += 1
        cur = base.copy()
        f = kf - 1
        while f >= 0 and nearest_kf(f) == kf:
            Hb = H[f + 1]
            if Hb is not None:
                try:
                    cur = cv2.perspectiveTransform(
                        cur.reshape(-1, 1, 2), np.linalg.inv(Hb)
                    ).reshape(-1, 2)
                except np.linalg.LinAlgError:
                    pass
            seq[f] = _bbox(cur)
            f -= 1
    return seq


def _is_made_basket(ball_tracks: list[dict], rim_seq: list,
                    frame: int, fps: float, window_s: float = 0.8,
                    bb_seq: list | None = None) -> bool:
    """Heuristic make/miss: the ball must come from ABOVE (rim x-band OR the backboard
    box), pass THROUGH the rim band, and end up BELOW it within a short window → a
    basket. The optional ``bb_seq`` (per-frame backboard box for the SAME hoop)
    reinforces detection: a ball that touches the board or descends from the board
    area into the rim counts as "from above", catching bank shots and high-arc makes
    that a rim-only check might miss. A miss (rim-out, airball, block) won't produce
    the full above→through→below sequence."""
    w = int(fps * window_s)
    lo = max(0, frame - w)
    hi = min(len(ball_tracks), frame + w + 1)
    above = through = below = False
    for j in range(lo, hi):
        c = _ball_center(ball_tracks[j])
        rb = rim_seq[j] if j < len(rim_seq) else None
        if c is None or rb is None:
            continue
        rb_w = rb[2] - rb[0]
        in_x = (rb[0] - rb_w * 0.2) <= c[0] <= (rb[2] + rb_w * 0.2)
        # Backboard reinforcement: inside the board box, or x-aligned and above its
        # bottom edge, also qualifies as "coming from above" for this hoop.
        bb = bb_seq[j] if (bb_seq is not None and j < len(bb_seq)) else None
        on_board = bool(bb and bb[0] <= c[0] <= bb[2] and c[1] <= bb[3])
        if on_board:
            above = True
        if not in_x:
            continue
        if c[1] < rb[1]:
            above = True
        elif rb[1] <= c[1] <= rb[3]:
            if above:
                through = True
        elif c[1] > rb[3] and through:
            below = True
    return bool(above and through and below)


def _rim_shot_events(ball_tracks: list[dict], rim_seqs: list[list],
                     fps: float, cooldown_s: float = 1.5,
                     bb_seqs: list | None = None) -> list[dict]:
    """Count a shot attempt when the ball center enters the (slightly expanded)
    rim box *of that frame*, debounced by a global cooldown. Each event carries a
    ``made`` flag (make/miss via _is_made_basket, reinforced by the matching backboard
    sequence in ``bb_seqs`` when available). ``rim_seqs``/``bb_seqs`` are aligned lists
    — one per annotated hoop — so the proxy follows a panning camera and supports
    multiple distinct hoops. Geometry-based proxy, more reliable than pose-only when a
    manual rim is provided."""
    events: list[dict] = []
    last = -10 ** 9
    cooldown = int(cooldown_s * fps)
    for i, bt in enumerate(ball_tracks):
        c = _ball_center(bt)
        if c is None:
            continue
        for k, seq in enumerate(rim_seqs):
            rb = seq[i] if i < len(seq) else None
            if rb is None:
                continue
            ex = (rb[2] - rb[0]) * 0.5
            ey = (rb[3] - rb[1]) * 0.5
            if rb[0] - ex <= c[0] <= rb[2] + ex and rb[1] - ey <= c[1] <= rb[3] + ey:
                if i - last >= cooldown:
                    bb_seq = bb_seqs[k] if (bb_seqs and k < len(bb_seqs)) else None
                    made = _is_made_basket(ball_tracks, seq, i, fps, bb_seq=bb_seq)
                    events.append({"type": "shot_attempt", "frame": i,
                                   "track_id": -1, "made": made})
                    last = i
                break
    return events


def _fuse_ball_tracks(yolo_tracks: list[dict], sam2_tracks: list[dict]) -> list[dict]:
    """
    Fuse YOLO and SAM2 per-frame ball tracks.

    - both present & agree (centers within 50px) → keep YOLO (precise).
    - only one present → use it.
    - both present & disagree → use SAM2 (anchored to user clicks, trustworthy
      for off-domain balls).
    """
    import math
    n = len(yolo_tracks)
    out: list[dict] = []
    for i in range(n):
        y = yolo_tracks[i] if i < len(yolo_tracks) else {}
        s = sam2_tracks[i] if i < len(sam2_tracks) else {}
        yc, sc = _ball_center(y), _ball_center(s)
        if yc and sc:
            d = math.hypot(yc[0] - sc[0], yc[1] - sc[1])
            out.append(y if d <= 50 else s)
        elif yc:
            out.append(y)
        elif sc:
            out.append(s)
        else:
            out.append({})
    return out


def run_pipeline(
    input_video: str,
    output_video: str = OUTPUT_VIDEO_PATH,
    stub_path: str = STUBS_DEFAULT_PATH,
    use_stubs: bool = True,
    team1_jersey: str = "white shirt",
    team2_jersey: str = "dark blue shirt",
    court_image_path: str | None = None,
    player_detector_path: str | None = None,
    ball_detector_path: str | None = None,
    court_kp_detector_path: str = COURT_KEYPOINT_DETECTOR_PATH,
    court_profile: CourtProfile | None = None,
    manual_landmarks: list[dict] | None = None,
    camera_motion: str = "static",
    on_progress=None,
    chunk_size: int | None = None,
    show_poses: bool = True,
    pose_player_filter: list[int] | None = None,
    ball_points: list[dict] | None = None,
    hoop_boxes: list[dict] | None = None,
):
    """
    Run the full basketball analysis pipeline on a video file.

    Parameters
    ----------
    manual_landmarks : list[dict], optional
        Manually annotated court landmarks from the UI.
    camera_motion : str
        "static" | "moderate" | "moving".
    on_progress : callable, optional
        Called as on_progress(stage: str, pct: int) at key milestones.
        stage matches JobStage enum values (e.g. "player_tracking").
    chunk_size : int | None
        Frames loaded into RAM per chunk during inference. None → use
        BA_CHUNK_SIZE env var (default 500). Set to 0 for legacy all-at-once
        path (requires enough RAM for the full video).
    """
    from configs.settings import settings as _settings

    _court_image_path = court_image_path or _settings.court_image_path

    def _progress(stage: str, pct: int) -> None:
        if on_progress:
            try:
                on_progress(stage, pct)
            except Exception:
                pass

    # Resolve chunk_size: explicit arg > env var > default 500
    _chunk_size: int = chunk_size if chunk_size is not None else _settings.chunk_size

    # Resolve model paths: prefer YOLO11 multi-class model when available
    _player_path = player_detector_path or _resolve_detector_path(
        MULTICLASS_DETECTOR_PATH, PLAYER_DETECTOR_PATH
    )
    _ball_path = ball_detector_path or _resolve_detector_path(
        MULTICLASS_DETECTOR_PATH, BALL_DETECTOR_PATH
    )
    logger.info("Player detector: %s", _player_path)
    logger.info("Ball detector:   %s", _ball_path)

    # Read video metadata upfront so both paths have fps + dimensions
    _progress("reading_video", 8)
    try:
        _vid_props = get_video_properties(input_video)
        actual_fps = _vid_props["fps"] or 24.0
        frame_width = _vid_props["width"] or 1280
        _intrinsic_height = _vid_props["height"] or 720
        _total_frames_hint = _vid_props["total_frames"]
    except Exception:
        actual_fps = 24.0
        frame_width = 1280
        _intrinsic_height = 720
        _total_frames_hint = 0

    # Manual anchors are stored in the video's intrinsic pixel space, but all
    # inference/drawing runs on frames downscaled to max height 720p. Compute the
    # factor to map anchors into that working space (1.0 when video is ≤720p tall).
    _manual_src_scale = 720.0 / _intrinsic_height if _intrinsic_height > 720 else 1.0

    player_tracker = PlayerTracker(_player_path)
    ball_tracker = BallTracker(_ball_path)
    court_keypoint_detector = CourtKeypointDetector(court_kp_detector_path)

    _player_stub = os.path.join(stub_path, "player_track_stubs.pkl")
    _ball_stub = os.path.join(stub_path, "ball_track_stubs.pkl")
    _court_stub = os.path.join(stub_path, "court_key_points_stub.pkl")
    _assign_stub = os.path.join(stub_path, "player_assignment_stub.pkl")

    # Jersey number per track (track_id -> dorsal str); populated by OCR when enabled.
    jersey_numbers: dict[int, str] = {}

    if _chunk_size > 0:
        # ── Chunked inference path (O(chunk_size) peak RAM) ─────────────────
        logger.info(
            "Chunked inference mode: chunk_size=%d (~%.0f MB/chunk at 720p)",
            _chunk_size,
            _chunk_size * 2.76,
        )

        _progress("player_tracking", 12)
        _ref_stub = os.path.join(stub_path, "referee_tracks_stub.pkl")
        player_tracks = read_stub(use_stubs, _player_stub)
        referee_tracks: list = read_stub(use_stubs, _ref_stub) or []
        if player_tracks is None:
            player_tracks, _refs = player_tracker.get_tracks_streaming(
                input_video, max_height=_settings.player_max_h, target_height=720,
            )
            if getattr(_settings, "track_stitch", True):
                player_tracks = _stitch_tracks(
                    player_tracks, frame_width,
                    max_gap_s=getattr(_settings, "track_stitch_max_gap_s", 1.0),
                    max_dist_frac=getattr(_settings, "track_stitch_max_dist_frac", 0.10),
                    fps=actual_fps,
                )
            if not referee_tracks:
                referee_tracks = _refs
                save_stub(_ref_stub, referee_tracks)
            save_stub(_player_stub, player_tracks)
        logger.info(
            "Player tracks done (%d frames, %d referee detections)",
            len(player_tracks), sum(len(f) for f in referee_tracks),
        )

        _progress("ball_tracking", 30)
        ball_tracks = read_stub(use_stubs, _ball_stub)
        if ball_tracks is None:
            sv_ball = ball_tracker.detect_frames_streaming(input_video, _chunk_size)
            ball_tracks = ball_tracker.build_tracks_from_sv_detections(sv_ball)
            del sv_ball
            save_stub(_ball_stub, ball_tracks)
        logger.info("Ball tracks done (%d frames)", len(ball_tracks))

        _progress("keypoint_detection", 45)
        court_keypoints_per_frame = read_stub(use_stubs, _court_stub)
        if court_keypoints_per_frame is None:
            court_keypoints_per_frame = court_keypoint_detector.get_court_keypoints_streaming(
                input_video, _chunk_size
            )
            save_stub(_court_stub, court_keypoints_per_frame)
        logger.info("Court keypoints done (%d frames)", len(court_keypoints_per_frame))

        _missing_before_sahi = sum(1 for bt in ball_tracks if 1 not in bt)
        _raw_detected = len(ball_tracks) - _missing_before_sahi
        logger.info(
            "Ball raw detection rate: %d/%d frames (%.1f%%) before SAHI",
            _raw_detected, len(ball_tracks),
            100.0 * _raw_detected / max(len(ball_tracks), 1),
        )

        # ── SAM2 ball propagation (when manual ball points exist) ───────────
        # Color-agnostic; fuse with YOLO: keep YOLO where it agrees/is precise,
        # use SAM2 to fill gaps and resolve disagreements (anchored to clicks).
        if ball_points and getattr(_settings, "ball_sam2", True):
            try:
                from ball_sam2 import Sam2BallTracker
                sam2 = Sam2BallTracker(_settings.sam2_checkpoint, _settings.sam2_config)
                sam2_tracks = sam2.track(
                    input_video, ball_points, len(ball_tracks), actual_fps,
                    src_scale=_manual_src_scale,
                )
                if sam2_tracks is not None:
                    # Export SAM2 boxes as YOLO auto-labels for fine-tuning (purpose 2).
                    if getattr(_settings, "ball_export_dataset", False):
                        try:
                            import uuid as _uuid
                            from ball_sam2.export_dataset import export_yolo_dataset
                            _nv = {
                                int(round(float(p.get("frame_t", 0.0)) * actual_fps))
                                for p in ball_points if not p.get("visible", True)
                            }
                            _written = export_yolo_dataset(
                                input_video, sam2_tracks, "/app/ball_dataset",
                                game_id=_uuid.uuid4().hex[:8], not_visible_frames=_nv,
                            )
                            logger.info("Ball dataset export: %d labeled frames", _written)
                        except Exception as exc:
                            logger.warning("Ball dataset export failed: %s", exc)
                    ball_tracks = _fuse_ball_tracks(ball_tracks, sam2_tracks)
                    _m = sum(1 for bt in ball_tracks if 1 not in bt)
                    logger.info(
                        "Ball after SAM2 fusion: %d/%d frames have ball (%.1f%%)",
                        len(ball_tracks) - _m, len(ball_tracks),
                        100.0 * (len(ball_tracks) - _m) / max(len(ball_tracks), 1),
                    )
            except Exception as exc:
                logger.warning("SAM2 ball fusion skipped: %s", exc)

        _missing_before_sahi = sum(1 for bt in ball_tracks if 1 not in bt)
        if _missing_before_sahi > 0:
            ball_tracks = ball_tracker.refill_missing_with_sahi(input_video, ball_tracks)
        ball_tracks = ball_tracker.remove_wrong_detections(ball_tracks)
        ball_tracks = ball_tracker.apply_kalman_smoothing(ball_tracks)
        ball_tracks = ball_tracker.interpolate_ball_positions(ball_tracks)

        _progress("team_assignment", 55)
        team_assigner = TeamAssigner(
            team_1_class_name=team1_jersey,
            team_2_class_name=team2_jersey,
        )
        player_assignment = team_assigner.get_player_teams_streaming(
            input_video,
            player_tracks,
            _chunk_size,
            read_from_stub=use_stubs,
            stub_path=_assign_stub,
        )
        logger.info("Team assignment done")

        # ── Jersey number OCR (player identity) ─────────────────────────────
        # Read dorsales per track from NATIVE-resolution crops, vote per tracklet.
        # Used downstream to consolidate fragmented tracks into real athletes.
        if getattr(_settings, "jersey_ocr", False):
            try:
                from jersey_ocr import JerseyOCR
                _ocr = JerseyOCR()
                jersey_numbers = _ocr.read_tracklets(
                    input_video, player_tracks,
                    src_scale=_manual_src_scale,
                    sample_every=getattr(_settings, "jersey_ocr_sample_every", 10),
                    min_votes=getattr(_settings, "jersey_ocr_min_votes", 3),
                )
                logger.info("Jersey OCR: %d tracks have a dorsal", len(jersey_numbers))
            except Exception as exc:
                logger.warning("Jersey OCR skipped: %s", exc)

        _progress("pose_estimation", 62)
        if show_poses:
            _pose_stub = os.path.join(stub_path, "pose_sequence_stub.pkl")
            pose_sequence = read_stub(use_stubs, _pose_stub)
            if pose_sequence is None:
                try:
                    from pose_estimator import PoseEstimator
                    _pe = PoseEstimator()
                    logger.info("Running pose estimation (backend=%s)…", _pe._backend)
                    pose_sequence = _pe.estimate_sequence_streaming(
                        input_video, player_tracks, _chunk_size
                    )
                    save_stub(_pose_stub, pose_sequence)
                except Exception as exc:
                    logger.warning("PoseEstimator failed: %s — skipping pose", exc)
                    pose_sequence = [{} for _ in range(len(player_tracks))]
            logger.info("Pose estimation done (%d frames)", len(pose_sequence))
        else:
            logger.info("Pose estimation skipped (show_poses=False)")
            pose_sequence = [{} for _ in range(len(player_tracks))]

        total_frames = len(player_tracks)  # actual frame count after loading

    else:
        # ── Legacy all-at-once path (small videos or when BA_CHUNK_SIZE=0) ──
        logger.info("Legacy inference mode: loading all frames into RAM")
        video_frames = read_video(input_video)
        logger.info("Loaded %d frames", len(video_frames))
        frame_width = video_frames[0].shape[1] if video_frames else frame_width

        _progress("player_tracking", 12)
        _ref_stub = os.path.join(stub_path, "referee_tracks_stub.pkl")
        referee_tracks: list = read_stub(use_stubs, _ref_stub) or []
        player_tracks = player_tracker.get_object_tracks(
            video_frames,
            read_from_stub=use_stubs,
            stub_path=_player_stub,
        )
        logger.info("Player tracks done")

        _progress("ball_tracking", 30)
        ball_tracks = ball_tracker.get_object_tracks(
            video_frames,
            read_from_stub=use_stubs,
            stub_path=_ball_stub,
        )
        logger.info("Ball tracks done")

        _progress("keypoint_detection", 45)
        court_keypoints_per_frame = court_keypoint_detector.get_court_keypoints(
            video_frames,
            read_from_stub=use_stubs,
            stub_path=_court_stub,
        )
        logger.info("Court keypoints done")

        ball_tracks = ball_tracker.remove_wrong_detections(ball_tracks)
        ball_tracks = ball_tracker.apply_kalman_smoothing(ball_tracks)
        ball_tracks = ball_tracker.interpolate_ball_positions(ball_tracks)

        _progress("team_assignment", 55)
        team_assigner = TeamAssigner(
            team_1_class_name=team1_jersey,
            team_2_class_name=team2_jersey,
        )
        player_assignment = team_assigner.get_player_teams_across_frames(
            video_frames,
            player_tracks,
            read_from_stub=use_stubs,
            stub_path=_assign_stub,
        )
        logger.info("Team assignment done")

        _progress("pose_estimation", 62)
        if show_poses:
            _pose_stub = os.path.join(stub_path, "pose_sequence_stub.pkl")
            pose_sequence = read_stub(use_stubs, _pose_stub)
            if pose_sequence is None:
                try:
                    from pose_estimator import PoseEstimator
                    _pe = PoseEstimator()
                    logger.info("Running pose estimation (backend=%s)…", _pe._backend)
                    pose_sequence = _pe.estimate_sequence(video_frames, player_tracks)
                    save_stub(_pose_stub, pose_sequence)
                except Exception as exc:
                    logger.warning("PoseEstimator failed: %s — skipping pose", exc)
                    pose_sequence = [{} for _ in range(len(video_frames))]
            logger.info("Pose estimation done (%d frames)", len(pose_sequence))
        else:
            logger.info("Pose estimation skipped (show_poses=False)")
            pose_sequence = [{} for _ in range(len(video_frames))]

        total_frames = len(video_frames)  # actual frame count after loading
        del video_frames  # free before draw pass

    # ── Hoop Detection ──────────────────────────────────────────────────────────
    _progress("hoop_detection", 63)
    _hoop_stub = os.path.join(stub_path, "hoop_tracks_stub.pkl")
    hoop_tracks: list = read_stub(use_stubs, _hoop_stub) or []
    if not hoop_tracks:
        try:
            from hoop_detector import HoopDetector
            _hd = HoopDetector()
            logger.info("Running hoop detection…")
            hoop_tracks = _hd.detect_frames_streaming(input_video)
            hoop_tracks = (hoop_tracks + [None] * total_frames)[:total_frames]
            save_stub(_hoop_stub, hoop_tracks)
        except Exception as exc:
            logger.warning("HoopDetector failed: %s — skipping", exc)
            hoop_tracks = [None] * total_frames
    logger.info(
        "Hoop detection done (%d frames, %d with hoop)",
        len(hoop_tracks), sum(1 for h in hoop_tracks if h is not None),
    )

    # ── Manual hoop override (boxes are trusted over the YOLO hoop detector) ─────
    # Each rim box carries the frame it was annotated on (frame_t × fps) and a
    # hoop_id identifying which physical hoop it belongs to. Boxes are grouped by
    # hoop_id; within each hoop we interpolate a per-frame box (follows a panning
    # camera). When several hoops are annotated, each is only "active" around the
    # frames it was marked on, so a hoop visible in one part of the pan doesn't
    # exist (frozen) over the whole video.
    _rim_seqs: list[list] = []
    _bb_seqs: list[list | None] = []   # backboard sequence aligned per hoop with _rim_seqs
    _rim_boxes_720: list[list[float]] = []
    _motion_H = None   # shared camera-motion homography (reused by court-anchor pass)
    if hoop_boxes:
        from collections import defaultdict as _dd

        def _grouped_by_hoop(kind: str) -> dict[int, list[tuple[int, list[float]]]]:
            g: dict[int, list[tuple[int, list[float]]]] = _dd(list)
            for b in hoop_boxes:
                if b.get("kind", "rim") != kind or len(b.get("bbox", [])) != 4:
                    continue
                box = [float(v) * _manual_src_scale for v in b["bbox"]]
                fidx = max(0, min(total_frames - 1,
                                  int(round(float(b.get("frame_t", 0.0)) * actual_fps))))
                g[int(b.get("hoop_id", 0))].append((fidx, box))
            return g

        # Boxes with no explicit kind default to "rim" inside _grouped_by_hoop.
        groups = _grouped_by_hoop("rim")
        bb_groups = _grouped_by_hoop("backboard")
        if groups:
            multi = len(groups) > 1

            # Camera-motion propagation: from a couple of marks, warp each box across
            # ALL frames following the pan (off-screen hoops drift off-frame on their
            # own, so the rim is available video-wide without windowing). Falls back to
            # time-interpolation (windowed) when no motion is estimable.
            _H = None
            if getattr(_settings, "hoop_propagate", True):
                try:
                    _H = _global_motion_sequence(input_video, total_frames)
                    _motion_H = _H   # reuse for the court-anchor pass (one OF pass total)
                except Exception as exc:
                    logger.warning("Hoop motion estimation failed: %s", exc)
            _have_motion = bool(_H) and any(h is not None for h in _H)

            def _seq(pts):
                if not pts:
                    return None
                if _have_motion:
                    return _propagate_box_seq(pts, _H, total_frames)
                # No motion → time-interpolate; window only with several hoops + ≥2 marks.
                m = int(actual_fps * 2) if (multi and len(pts) >= 2) else None
                return _rim_box_sequence(pts, total_frames, clamp_margin=m)

            for hid in sorted(groups):
                _rim_seqs.append(_seq(groups[hid]))
                # Pair the SAME hoop's backboard so it reinforces this rim's makes.
                _bb_seqs.append(_seq(bb_groups[hid]) if bb_groups.get(hid) else None)
            _rim_boxes_720 = [box for pts in groups.values() for _, box in pts]
            # hoop_tracks (metrics only; not drawn): first active hoop box per frame
            hoop_tracks = []
            for i in range(total_frames):
                b = next((s[i] for s in _rim_seqs if s[i] is not None), None)
                hoop_tracks.append(list(b) if b is not None else None)
            logger.info(
                "Manual hoop: %d hoop(s), %d rim box(es) at frames %s, %d backboard box(es) → %s",
                len(groups), len(_rim_boxes_720),
                sorted({f for pts in groups.values() for f, _ in pts}),
                sum(len(v) for v in bb_groups.values()),
                "camera-motion propagated (full video)" if _have_motion
                else ("interpolated, windowed per hoop" if multi else "interpolated"),
            )

    # ── CV Event Detection (shot, rebound, steal) ───────────────────────────────
    _progress("event_detection", 66)
    _event_stub = os.path.join(stub_path, "cv_events_stub.pkl")
    _ev_cached = read_stub(use_stubs, _event_stub)
    if _ev_cached is not None:
        shot_events = _ev_cached.get("shot_events", [])
        rebound_events = _ev_cached.get("rebound_events", [])
        steal_events = _ev_cached.get("steal_events", [])
    else:
        shot_events: list = []
        rebound_events: list = []
        steal_events: list = []
        try:
            from event_detector import ShotDetector, ReboundDetector, StealTurnoverDetector
            shot_events = ShotDetector().process_sequence(pose_sequence, ball_tracks)
            rebound_events = ReboundDetector().process_sequence(
                pose_sequence, ball_tracks, player_tracks, rim_sequence=hoop_tracks
            )
            steal_events = StealTurnoverDetector().process_sequence(
                pose_sequence, ball_tracks, player_assignment
            )
            save_stub(_event_stub, {
                "shot_events": shot_events,
                "rebound_events": rebound_events,
                "steal_events": steal_events,
            })
        except Exception as exc:
            logger.warning("Event detection failed: %s — skipping", exc)

    # Manual rim → ball-reaches-rim shot proxy (more reliable than pose-only when a
    # rim box is provided). Replaces pose-based shots to avoid double counting.
    if _rim_boxes_720:
        _rim_shots = _rim_shot_events(ball_tracks, _rim_seqs, actual_fps, bb_seqs=_bb_seqs)
        logger.info(
            "Manual rim shots: %d (replacing %d pose-based)",
            len(_rim_shots), len(shot_events),
        )
        shot_events = _rim_shots

    logger.info(
        "CV events: %d shots, %d rebounds, %d steals",
        len(shot_events), len(rebound_events), len(steal_events),
    )

    # ── DualResolution event windows ────────────────────────────────────────────
    try:
        from dual_resolution import DualResolutionPipeline
        _drp = DualResolutionPipeline()
        event_windows = _drp.find_event_windows(ball_tracks, player_tracks)
        logger.info("DualRes: %d high-action event windows identified", len(event_windows))
    except Exception as exc:
        logger.warning("DualResolutionPipeline failed: %s — skipping", exc)
        event_windows = []

    _progress("ball_acquisition", 65)
    ball_aquisition_detector = BallAquisitionDetector(frame_width=frame_width)
    ball_aquisition = ball_aquisition_detector.detect_ball_possession(
        player_tracks, ball_tracks
    )

    _progress("pass_detection", 68)
    pass_and_interception_detector = PassAndInterceptionDetector()
    passes = pass_and_interception_detector.detect_passes(
        ball_aquisition, player_assignment
    )
    interceptions = pass_and_interception_detector.detect_interceptions(
        ball_aquisition, player_assignment
    )
    logger.info("Passes/interceptions done")

    # Detect court mode (half-court vs full-court)
    court_mode_detector = CourtModeDetector()
    is_half_court = court_mode_detector.detect(court_keypoints_per_frame)
    if is_half_court:
        logger.warning(
            "Half-court detected — speed/distance metrics will be disabled for this video"
        )

    _progress("tactical_view", 72)
    profile = court_profile or CourtProfile(CourtLevel.NBA)

    tactical_view_converter = TacticalViewConverter(
        court_image_path=_court_image_path,
        court_profile=profile,
        manual_landmarks=manual_landmarks,
        camera_motion=camera_motion,
        src_scale=_manual_src_scale,
    )
    court_keypoints_per_frame = tactical_view_converter.validate_keypoints(
        court_keypoints_per_frame
    )
    # Build per-frame manual-anchor sequence (optical-flow tracked for moving
    # cameras; static reuse otherwise). No-op when no manual landmarks exist.
    tactical_view_converter.build_manual_anchor_sequence(
        input_video, total_frames, actual_fps, precomputed_H=_motion_H
    )
    tactical_player_positions = (
        tactical_view_converter.transform_players_to_tactical_view(
            court_keypoints_per_frame, player_tracks
        )
    )

    speed_and_distance_calculator = SpeedAndDistanceCalculator(
        tactical_view_converter.width,
        tactical_view_converter.height,
        tactical_view_converter.actual_width_in_meters,
        tactical_view_converter.actual_height_in_meters,
        fps=actual_fps,
        calibration_factor=profile.calibration_factor,
    )

    if is_half_court:
        # Disable global speed/distance in half-court mode
        player_distances_per_frame = [{} for _ in range(total_frames)]
        player_speed_per_frame = [{} for _ in range(total_frames)]
    else:
        player_distances_per_frame = speed_and_distance_calculator.calculate_distance(
            tactical_player_positions
        )
        player_speed_per_frame = speed_and_distance_calculator.calculate_speed(
            player_distances_per_frame
        )
    logger.info("Speed/distance done")

    _progress("drawing", 78)
    player_tracks_drawer      = PlayerTracksDrawer()
    pose_drawer               = PoseDrawer(player_filter=pose_player_filter)
    ball_tracks_drawer        = BallTracksDrawer()
    court_keypoint_drawer     = CourtKeypointDrawer(
        manual_src=tactical_view_converter._manual_src,
        manual_src_seq=tactical_view_converter._manual_src_seq,
    )
    team_ball_control_drawer  = TeamBallControlDrawer()
    frame_number_drawer       = FrameNumberDrawer()
    pass_and_interceptions_drawer = PassInterceptionDrawer()
    tactical_view_drawer      = TacticalViewDrawer()
    speed_and_distance_drawer = SpeedAndDistanceDrawer()

    # Pre-compute team_ball_control array (cheap — just ints, no images)
    team_ball_control = team_ball_control_drawer.get_team_ball_control(
        player_assignment, ball_aquisition
    )

    # Pre-load court image once so tactical drawer doesn't re-read it per frame
    import numpy as _np
    import cv2 as _cv2
    _court_path = tactical_view_converter.court_image_path
    _tac_w = tactical_view_converter.width
    _tac_h = tactical_view_converter.height
    court_image_loaded = _cv2.imread(_court_path) if _court_path else None
    if court_image_loaded is None or court_image_loaded.size == 0:
        court_image_loaded = _np.zeros((_tac_h, _tac_w, 3), dtype=_np.uint8)
        court_image_loaded[:] = (40, 80, 40)
    else:
        court_image_loaded = _cv2.resize(court_image_loaded, (_tac_w, _tac_h))

    # ── Streaming draw pass ──────────────────────────────────────────────────
    # Re-read the source video one frame at a time — no large buffer in memory.

    import shutil as _shutil
    import subprocess as _subprocess
    _is_mp4 = output_video.lower().endswith(".mp4")
    _use_ffmpeg = _is_mp4 and bool(_shutil.which("ffmpeg"))
    _tmp_video = output_video + ".raw.mp4" if _use_ffmpeg else None

    # Determine output frame size from first frame (after potential downscaling)
    _first_frame = None
    for _f in iter_video_frames(input_video):
        if _f.shape[0] > 720:
            _scale = 720 / _f.shape[0]
            _f = _cv2.resize(_f, (int(_f.shape[1] * _scale), 720), interpolation=_cv2.INTER_AREA)
        _first_frame = _f
        break

    if _first_frame is None:
        raise RuntimeError("Could not read any frame from source video for drawing")

    _out_h, _out_w = _first_frame.shape[:2]
    _fourcc = _cv2.VideoWriter_fourcc(*"mp4v")
    _writer_path = _tmp_video if _use_ffmpeg else output_video
    _writer = _cv2.VideoWriter(_writer_path, _fourcc, actual_fps, (_out_w, _out_h))

    _streaming_distances: dict = {}  # accumulated for SpeedAndDistanceDrawer

    for _frame_idx, _frame in enumerate(iter_video_frames(input_video)):
        if _frame_idx >= total_frames:
            break

        # Apply same downscaling as read_video
        if _frame.shape[0] > 720:
            _scale = 720 / _frame.shape[0]
            _frame = _cv2.resize(
                _frame, (int(_frame.shape[1] * _scale), 720),
                interpolation=_cv2.INTER_AREA,
            )

        # Apply all drawers in sequence (each modifies a single frame)
        _frame = player_tracks_drawer.draw_frame(
            _frame, _frame_idx, player_tracks, player_assignment, ball_aquisition
        )
        if show_poses:
            _frame = pose_drawer.draw_frame(_frame, _frame_idx, pose_sequence)
        _frame = ball_tracks_drawer.draw_frame(_frame, _frame_idx, ball_tracks)
        _frame = court_keypoint_drawer.draw_frame(_frame, _frame_idx, court_keypoints_per_frame)
        _frame = frame_number_drawer.draw_frame(_frame, _frame_idx)
        _frame = team_ball_control_drawer.draw_frame(_frame, _frame_idx, team_ball_control)
        _frame = pass_and_interceptions_drawer.draw_frame(
            _frame, _frame_idx, passes, interceptions
        )
        _frame = speed_and_distance_drawer.draw_frame(
            _frame, _frame_idx,
            player_tracks, player_distances_per_frame, player_speed_per_frame,
            _streaming_distances,
        )
        _frame = tactical_view_drawer.draw_frame(
            _frame, _frame_idx,
            court_image_loaded, _tac_w, _tac_h,
            tactical_view_converter.key_points,
            tactical_player_positions,
            player_assignment,
            ball_aquisition,
        )

        _writer.write(_frame)

    _writer.release()
    logger.info("Streaming draw complete: %d frames written", _frame_idx + 1)

    # Re-encode to H.264 for browser compatibility
    if _use_ffmpeg and _tmp_video and os.path.exists(_tmp_video):
        _cmd = [
            "ffmpeg", "-y", "-i", _tmp_video,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-movflags", "+faststart",
            output_video,
        ]
        _result = _subprocess.run(_cmd, capture_output=True)
        try:
            os.remove(_tmp_video)
        except OSError:
            pass
        if _result.returncode != 0:
            logger.warning("ffmpeg re-encode failed: %s", _result.stderr.decode())
            if os.path.exists(_tmp_video):
                os.rename(_tmp_video, output_video)
    logger.info("Saved annotated video to %s", output_video)

    # Build summary metrics
    team1_pos = 0
    team2_pos = 0
    for frame_idx, holder_id in enumerate(ball_aquisition):
        if holder_id == -1:
            continue
        if frame_idx < len(player_assignment):
            team = player_assignment[frame_idx].get(holder_id, -1)
            if team == 1:
                team1_pos += 1
            elif team == 2:
                team2_pos += 1

    team1_passes = sum(1 for p in passes if p == 1)
    team2_passes = sum(1 for p in passes if p == 2)
    team1_interceptions = sum(1 for i in interceptions if i == 1)
    team2_interceptions = sum(1 for i in interceptions if i == 2)

    player_total_distances: dict = {}
    for frame_distances in player_distances_per_frame:
        for pid, dist in frame_distances.items():
            player_total_distances[pid] = player_total_distances.get(pid, 0.0) + dist

    # Per-player speed samples indexed by track_id for avg computation downstream
    player_speed_samples: dict[int, list[float]] = {}
    for frame_speeds in player_speed_per_frame:
        for pid, spd in frame_speeds.items():
            if spd is not None and spd > 0:
                player_speed_samples.setdefault(pid, []).append(float(spd))

    player_avg_speed: dict[int, float] = {
        pid: (sum(samples) / len(samples))
        for pid, samples in player_speed_samples.items()
        if samples
    }

    player_max_speed: dict[int, float] = {
        pid: max(samples)
        for pid, samples in player_speed_samples.items()
        if samples
    }

    metrics = {
        # Summary scalars
        "total_frames": total_frames,
        "team1_possession_frames": team1_pos,
        "team2_possession_frames": team2_pos,
        "team1_passes": team1_passes,
        "team2_passes": team2_passes,
        "team1_interceptions": team1_interceptions,
        "team2_interceptions": team2_interceptions,
        "player_total_distance_m": player_total_distances,
        "player_avg_speed_kmh": player_avg_speed,
        "player_max_speed_kmh": player_max_speed,
        "output_video_path": output_video,
        # Raw per-frame sequences needed by _persist_metrics in the worker
        "ball_acquisition": ball_aquisition,          # list[int] — track_id holding ball, -1 if none
        "player_assignment": player_assignment,       # list[dict[track_id, team_id]]
        "jersey_numbers": jersey_numbers,             # dict[track_id, dorsal str] from OCR voting
        "passes": passes,                             # list[int] — team_id that passed, -1 if none
        "interceptions": interceptions,               # list[int] — team_id that intercepted, -1 if none
        "fps": actual_fps,
        "is_half_court": is_half_court,
        # CV event lists from pose-based detectors
        "shot_events": shot_events,
        "rebound_events": rebound_events,
        "steal_events": steal_events,
        # Per-frame hoop bbox (or None when not detected)
        "hoop_tracks": hoop_tracks,
        # Per-frame referee bboxes (negative track IDs to avoid collision)
        "referee_tracks": referee_tracks,
        # High-action frame windows from ball movement analysis [(start, end), ...]
        "event_windows": event_windows,
    }

    return metrics


def main():
    args = parse_args()
    metrics = run_pipeline(
        input_video=args.input_video,
        output_video=args.output_video,
        stub_path=args.stub_path,
        use_stubs=not args.no_stubs,
        team1_jersey=args.team1_jersey,
        team2_jersey=args.team2_jersey,
    )
    logger.info("Pipeline complete. Metrics: %s", metrics)


if __name__ == "__main__":
    main()
