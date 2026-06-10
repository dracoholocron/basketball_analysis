"""
PoseEstimator — wraps RTMPose (ONNX, SimCC) or falls back to
YOLO-pose (17-keypoint COCO) when the ONNX model is unavailable.

Bundled RTMPose ONNX (``rtmpose_body2d.onnx``) is an RTMPose Wholebody-133
top-down SimCC model (input NCHW ``1×3×256×192``; outputs ``pred_x``/``pred_y``
with 133 keypoints). Keypoint count is inferred from the output shapes, so
COCO-17 checkpoints work too. The first 17 indices of Wholebody-133 are the
COCO body joints, and only those 17 ``(x, y, conf)`` are returned to keep
downstream consumers (skeleton_utils, event detectors) unchanged.

RTMPose model expected at:
    basketball_analysis/models/rtmpose_body2d.onnx
    basketball_analysis/models/rtmpose_body2d.data   (external ONNX data file)

Environment variables
---------------------
BA_DUMMY_MODELS=1   Force dummy mode (synthetic sine-wave keypoints, no GPU needed).
BA_POSE_BACKEND     'rtmpose' | 'yolo' | 'auto' (default: 'auto')
                    'auto' tries RTMPose first, then YOLO, then dummy.
BA_POSE_ORT_CPU=1   Force onnxruntime CPUExecutionProvider only (e.g. validation).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .skeleton_utils import COCO_KEYPOINTS, KP

log = logging.getLogger(__name__)

_DUMMY_MODE: bool = os.environ.get("BA_DUMMY_MODELS", "").lower() in ("1", "true", "yes")
_POSE_BACKEND: str = os.environ.get("BA_POSE_BACKEND", "auto").lower()
_POSE_ORT_CPU: bool = os.environ.get("BA_POSE_ORT_CPU", "").lower() in ("1", "true", "yes")

_COCO17_COUNT = 17
_RTMPOSE_PADDING = 1.25
_RTMPOSE_RGB_MEAN = np.array([123.675, 116.28, 103.53], dtype=np.float32)
_RTMPOSE_RGB_STD = np.array([58.395, 57.12, 57.375], dtype=np.float32)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_model_path(filename: str) -> Optional[Path]:
    """Search for a model file relative to the package root."""
    base = Path(__file__).resolve().parent.parent  # basketball_analysis/
    candidates = [
        base / "models" / filename,
        Path("models") / filename,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _rtm_input_size_from_session(session: object) -> tuple[int, int]:
    """Return model (width, height) from ONNX input NCHW."""
    shape = session.get_inputs()[0].shape
    # dynamic dims may be strings
    h = int(shape[2]) if isinstance(shape[2], (int, np.integer)) else 256
    w = int(shape[3]) if isinstance(shape[3], (int, np.integer)) else 192
    return w, h


def _load_rtmpose() -> Optional[object]:
    """
    Try to load the RTMPose ONNX model via onnxruntime.
    Returns an ort.InferenceSession or None.
    """
    onnx_path = _find_model_path("rtmpose_body2d.onnx")
    if onnx_path is None:
        log.debug("RTMPose ONNX model not found.")
        return None
    try:
        import onnxruntime as ort

        if _POSE_ORT_CPU:
            providers = ["CPUExecutionProvider"]
        else:
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if "CUDAExecutionProvider" in ort.get_available_providers()
                else ["CPUExecutionProvider"]
            )
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.execution_mode = ort.ExecutionMode.ORT_PARALLEL
        opts.intra_op_num_threads = 4
        sess = ort.InferenceSession(str(onnx_path), sess_options=opts, providers=providers)
        log.info("RTMPose loaded: %s  (providers=%s)", onnx_path.name, providers)
        return sess
    except Exception as exc:
        log.warning("Could not load RTMPose: %s", exc)
        return None


def _get_3rd_point(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Third point for a stable affine transform (mmpose-style)."""
    direction = a - b
    return b + np.array([-direction[1], direction[0]], dtype=np.float32)


def _rotate_point(pt: np.ndarray, angle_rad: float) -> np.ndarray:
    sn, cs = np.sin(angle_rad), np.cos(angle_rad)
    rot = np.array([[cs, -sn], [sn, cs]], dtype=np.float32)
    return rot @ pt


def _get_warp_matrix(
    center: np.ndarray,
    scale: np.ndarray,
    rot: float,
    output_size: tuple[int, int],
    shift: tuple[float, float] = (0.0, 0.0),
    inv: bool = False,
) -> np.ndarray:
    """Affine warp between image space and model input (width, height)."""
    import cv2

    shift_v = np.array(shift, dtype=np.float32)
    src_w = scale[0]
    dst_w, dst_h = output_size

    rot_rad = np.deg2rad(rot)
    src_dir = _rotate_point(np.array([0.0, src_w * -0.5], dtype=np.float32), rot_rad)
    dst_dir = np.array([0.0, dst_w * -0.5], dtype=np.float32)

    src = np.zeros((3, 2), dtype=np.float32)
    dst = np.zeros((3, 2), dtype=np.float32)
    src[0, :] = center + scale * shift_v
    src[1, :] = center + src_dir + scale * shift_v
    dst[0, :] = [dst_w * 0.5, dst_h * 0.5]
    dst[1, :] = np.array([dst_w * 0.5, dst_h * 0.5], dtype=np.float32) + dst_dir

    src[2, :] = _get_3rd_point(src[0, :], src[1, :])
    dst[2, :] = _get_3rd_point(dst[0, :], dst[1, :])

    if inv:
        return cv2.getAffineTransform(dst, src)
    return cv2.getAffineTransform(src, dst)


def _box2cs(
    box_xywh: list[float],
    aspect_ratio: float,
    padding: float = _RTMPOSE_PADDING,
) -> tuple[np.ndarray, np.ndarray]:
    """BBox (x, y, w, h) → center and scale with fixed aspect ratio."""
    x, y, w, h = box_xywh
    center = np.array([x + w * 0.5, y + h * 0.5], dtype=np.float32)
    if w > aspect_ratio * h:
        h = w / aspect_ratio
    elif w < aspect_ratio * h:
        w = h * aspect_ratio
    scale = np.array([w, h], dtype=np.float32) * padding
    return center, scale


def _affine_transform(pt: np.ndarray, mat: np.ndarray) -> np.ndarray:
    out = mat @ np.array([pt[0], pt[1], 1.0], dtype=np.float32)
    return out[:2]


def _preprocess_rtmpose(
    frame: np.ndarray,
    bbox: list[float],
    input_size: tuple[int, int] = (192, 256),
    padding: float = _RTMPOSE_PADDING,
) -> tuple[np.ndarray, dict[str, Any]]:
    """
    Aspect-ratio-preserving affine warp of the person bbox to model input size.

    Returns
    -------
    blob : (1, 3, H, W) float32 normalized RGB (mmpose / RTMPose convention)
    meta : center, scale, input_size, inv_warp matrix for decoding
    """
    import cv2

    inp_w, inp_h = input_size
    aspect_ratio = inp_w / inp_h

    x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
    box_xywh = [x1, y1, max(x2 - x1, 1.0), max(y2 - y1, 1.0)]
    center, scale = _box2cs(box_xywh, aspect_ratio, padding)

    warp_mat = _get_warp_matrix(center, scale, 0.0, (inp_w, inp_h), inv=False)
    warped = cv2.warpAffine(
        frame,
        warp_mat,
        (inp_w, inp_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )

    rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
    img = (rgb.astype(np.float32) - _RTMPOSE_RGB_MEAN) / _RTMPOSE_RGB_STD
    blob = img.transpose(2, 0, 1)[np.newaxis]

    meta = {
        "center": center,
        "scale": scale,
        "input_size": input_size,
        "inv_warp": _get_warp_matrix(center, scale, 0.0, (inp_w, inp_h), inv=True),
    }
    return blob, meta


def _simcc_confidence(simcc_x_row: np.ndarray, simcc_y_row: np.ndarray) -> float:
    """
    SimCC keypoint score, mmpose `get_simcc_maximum` convention: the mean of the
    raw per-axis maxima of the (un-softmaxed) SimCC responses.

    The previous implementation used the softmax *peak probability* over hundreds
    of bins, which yields tiny values (~0.002) — far below any usable threshold —
    so every joint was filtered out and no skeletons were ever drawn. The raw
    maxima are in a usable ~0..1 range comparable to a confidence threshold.
    """
    return float(0.5 * (float(simcc_x_row.max()) + float(simcc_y_row.max())))


def _pair_simcc_xy(
    a: np.ndarray,
    b: np.ndarray,
    inp_w: int,
    inp_h: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Assign two SimCC tensors to (simcc_x, simcc_y) using bin counts vs input size."""
    err_ab = abs(a.shape[1] / inp_w - b.shape[1] / inp_h)
    err_ba = abs(b.shape[1] / inp_w - a.shape[1] / inp_h)
    if err_ab <= err_ba:
        return a, b
    return b, a


def _postprocess_rtmpose(
    output: np.ndarray | list | tuple,
    meta: dict[str, Any],
    n_coco: int = _COCO17_COUNT,
) -> np.ndarray:
    """
    Convert RTMPose SimCC outputs to COCO-17 keypoints in image coordinates.

    Detects keypoint count from output shape; returns the first ``n_coco`` joints.

    Returns
    -------
    kps : (17, 3) array of (x, y, confidence) in original image pixels
    """
    inp_w, inp_h = meta["input_size"]
    inv_warp = meta["inv_warp"]

    if isinstance(output, (list, tuple)) and len(output) == 2:
        out_a, out_b = output[0], output[1]
        if out_a.ndim == 3:
            out_a = out_a[0]
            out_b = out_b[0]
        simcc_x, simcc_y = _pair_simcc_xy(out_a, out_b, inp_w, inp_h)
    else:
        heatmap = np.asarray(output)
        if heatmap.ndim == 4:
            heatmap = heatmap[0]
        n_kp = heatmap.shape[0]
        n_out = min(n_kp, n_coco)
        kps = np.zeros((n_coco, 3), dtype=np.float32)
        for i in range(n_out):
            idx = int(np.argmax(heatmap[i]))
            hm_h, hm_w = heatmap.shape[1], heatmap.shape[2]
            ky, kx = divmod(idx, hm_w)
            conf = float(heatmap[i].max())
            pt = _affine_transform(
                np.array([kx / max(hm_w - 1, 1) * inp_w, ky / max(hm_h - 1, 1) * inp_h]),
                inv_warp,
            )
            kps[i] = [pt[0], pt[1], np.clip(conf, 0.0, 1.0)]
        return kps

    n_kp = simcc_x.shape[0]
    split_x = simcc_x.shape[1] / inp_w
    split_y = simcc_y.shape[1] / inp_h
    n_out = min(n_kp, n_coco)

    kps = np.zeros((n_coco, 3), dtype=np.float32)
    for i in range(n_out):
        x_idx = int(np.argmax(simcc_x[i]))
        y_idx = int(np.argmax(simcc_y[i]))
        conf = np.clip(_simcc_confidence(simcc_x[i], simcc_y[i]), 0.0, 1.0)

        px_in = x_idx / split_x
        py_in = y_idx / split_y
        pt = _affine_transform(np.array([px_in, py_in], dtype=np.float32), inv_warp)
        kps[i] = [pt[0], pt[1], conf]

    return kps


# ── PoseEstimator class ────────────────────────────────────────────────────────

class PoseEstimator:
    """
    Estimate 2-D body keypoints for each tracked player.

    Backends (auto-detected):
    1. RTMPose ONNX (SimCC COCO-17 for the bundled model; returns first 17 joints)
    2. YOLO-pose (COCO-17, fallback)
    3. Dummy (synthetic sine-wave data, for testing / BA_DUMMY_MODELS=1)

    Parameters
    ----------
    model_path : optional path override for the YOLO-pose backend
    dummy : force dummy mode regardless of environment variable
    """

    def __init__(self, model_path: Optional[str] = None, dummy: bool = False) -> None:
        self._dummy = dummy or _DUMMY_MODE
        self._backend = "dummy"
        self._session = None
        self._yolo_model = None
        self._rtm_input_size: tuple[int, int] = (192, 256)
        # Resolve the inference device once (used by YOLO-pose predict calls).
        try:
            from configs.settings import settings as _s
            self._device = _s.resolve_device()
        except Exception:
            self._device = "cpu"

        if not self._dummy:
            if _POSE_BACKEND in ("rtmpose", "auto"):
                self._session = _load_rtmpose()
                if self._session is not None:
                    self._backend = "rtmpose"
                    self._rtm_input_size = _rtm_input_size_from_session(self._session)

            if self._session is None and _POSE_BACKEND in ("yolo", "auto"):
                self._yolo_model = self._try_load_yolo(model_path)
                if self._yolo_model is not None:
                    self._backend = "yolo"

            if self._session is None and self._yolo_model is None:
                log.warning(
                    "No pose model found — falling back to dummy mode. "
                    "Set BA_DUMMY_MODELS=0 and place RTMPose ONNX files in models/."
                )
                self._dummy = True

        log.info("PoseEstimator backend: %s", self._backend)

    @staticmethod
    def _try_load_yolo(model_path: Optional[str] = None) -> Optional[object]:
        # Prefer a bundled model file; otherwise fall back to the model name so
        # ultralytics auto-downloads it. yolo11n-pose is robust on small/distant
        # players where the RTMPose ONNX decode collapses the upper body.
        yolo_path = (
            model_path
            or _find_model_path("yolo11n-pose.pt")
            or _find_model_path("yolov8n-pose.pt")
            or "yolo11n-pose.pt"
        )
        try:
            from ultralytics import YOLO
            model = YOLO(str(yolo_path))
            log.info("YOLO-pose loaded: %s", yolo_path)
            return model
        except Exception as exc:
            log.warning("Could not load YOLO-pose: %s", exc)
            return None

    # ── Public API ─────────────────────────────────────────────────────────────

    def estimate_frame(
        self,
        frame: np.ndarray,
        player_tracks: dict[int, dict],
    ) -> dict[int, np.ndarray]:
        """
        Run pose estimation for all tracked players in one frame.

        Parameters
        ----------
        frame : BGR numpy array (H, W, 3)
        player_tracks : {track_id: {"bbox": [x1, y1, x2, y2]}}

        Returns
        -------
        {track_id: np.ndarray (17, 3)}  — (x, y, confidence) in image pixels
        """
        if not player_tracks:
            return {}

        if self._dummy:
            return self._dummy_frame(player_tracks)

        if self._backend == "rtmpose":
            return self._rtmpose_frame(frame, player_tracks)

        if self._backend == "yolo":
            return self._yolo_frame(frame, player_tracks)

        return {}

    def estimate_sequence(
        self,
        frames: list[np.ndarray],
        tracks: list[dict[int, dict]],
    ) -> list[dict[int, np.ndarray]]:
        """Run estimate_frame for each frame in a sequence."""
        return [
            self.estimate_frame(frame, player_tracks)
            for frame, player_tracks in zip(frames, tracks)
        ]

    def estimate_sequence_streaming(
        self,
        video_path: str,
        player_tracks: list[dict[int, dict]],
        chunk_size: int,
        max_height: int = 720,
    ) -> list[dict[int, np.ndarray]]:
        """
        Run pose estimation over the full video in memory-efficient chunks.

        Reads frames at max_height=720 so player bbox crops align with the same
        720p coordinate space used by detection and the draw pass.
        """
        from utils.video_utils import iter_video_frames

        pose_sequence: list[dict[int, np.ndarray]] = []
        total = len(player_tracks)

        for frame_num, frame in enumerate(iter_video_frames(video_path, max_height=max_height)):
            if frame_num >= total:
                break
            pose_sequence.append(
                self.estimate_frame(frame, player_tracks[frame_num])
            )

        return pose_sequence

    # ── Backend implementations ────────────────────────────────────────────────

    def _rtmpose_frame(
        self,
        frame: np.ndarray,
        player_tracks: dict[int, dict],
    ) -> dict[int, np.ndarray]:
        results: dict[int, np.ndarray] = {}
        input_name = self._session.get_inputs()[0].name
        output_names = [o.name for o in self._session.get_outputs()]

        for track_id, info in player_tracks.items():
            bbox = info.get("bbox", [])
            if len(bbox) < 4:
                continue
            blob, meta = _preprocess_rtmpose(frame, bbox, self._rtm_input_size)
            raw = self._session.run(output_names, {input_name: blob})
            kps = _postprocess_rtmpose(raw, meta)
            results[track_id] = kps

        return results

    def _yolo_frame(
        self,
        frame: np.ndarray,
        player_tracks: dict[int, dict],
    ) -> dict[int, np.ndarray]:
        if not player_tracks:
            return {}
        try:
            from configs.settings import settings as _s
            topdown = getattr(_s, "pose_topdown", True)
        except Exception:
            topdown = True
        if topdown:
            return self._yolo_frame_topdown(frame, player_tracks)

        results: dict[int, np.ndarray] = {}
        yolo_results = self._yolo_model.predict(frame, verbose=False)
        if not yolo_results or yolo_results[0].keypoints is None:
            return results

        kps_all = yolo_results[0].keypoints.data.cpu().numpy()  # (N, 17, 3)
        boxes_all = yolo_results[0].boxes.xyxy.cpu().numpy()    # (N, 4)

        for track_id, info in player_tracks.items():
            bbox = info.get("bbox", [])
            if len(bbox) < 4:
                continue
            best_idx, best_iou = -1, 0.0
            for i, yolo_box in enumerate(boxes_all):
                iou = _box_iou(bbox, yolo_box.tolist())
                if iou > best_iou:
                    best_iou, best_idx = iou, i
            if best_idx >= 0 and best_iou > 0.1:
                results[track_id] = kps_all[best_idx]
        return results

    def _yolo_frame_topdown(
        self,
        frame: np.ndarray,
        player_tracks: dict[int, dict],
    ) -> dict[int, np.ndarray]:
        """Run YOLO-pose on each tracked player's (padded, upscaled) crop so small
        distant players still produce a skeleton. Keypoints are mapped back to
        full-frame coordinates."""
        import cv2

        results: dict[int, np.ndarray] = {}
        H, W = frame.shape[:2]
        crops, metas = [], []
        for track_id, info in player_tracks.items():
            bbox = info.get("bbox", [])
            if len(bbox) < 4:
                continue
            x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
            bw, bh = x2 - x1, y2 - y1
            if bw < 2 or bh < 2:
                continue
            # pad 20% and clip
            px, py = bw * 0.2, bh * 0.2
            cx1 = max(0, int(x1 - px)); cy1 = max(0, int(y1 - py))
            cx2 = min(W, int(x2 + px)); cy2 = min(H, int(y2 + py))
            crop = frame[cy1:cy2, cx1:cx2]
            if crop.size == 0:
                continue
            # upscale small crops so the pose model has enough pixels
            ch = cy2 - cy1
            scale = 1.0
            if ch < 256:
                scale = 256.0 / ch
                crop = cv2.resize(crop, (int((cx2 - cx1) * scale), int(ch * scale)),
                                  interpolation=cv2.INTER_LINEAR)
            crops.append(crop)
            metas.append((track_id, cx1, cy1, scale))

        if not crops:
            return results

        preds = self._yolo_model.predict(crops, verbose=False, device=self._device)
        for (track_id, ox, oy, scale), r in zip(metas, preds):
            if r.keypoints is None or len(r.keypoints) == 0:
                continue
            kdata = r.keypoints.data.cpu().numpy()  # (N,17,3)
            if r.boxes is not None and len(r.boxes) > 1:
                # pick the most confident person in the crop
                confs = r.boxes.conf.cpu().numpy()
                kp = kdata[int(confs.argmax())]
            else:
                kp = kdata[0]
            kp = kp.copy()
            kp[:, 0] = kp[:, 0] / scale + ox
            kp[:, 1] = kp[:, 1] / scale + oy
            results[track_id] = kp
        return results

    def _dummy_frame(
        self,
        player_tracks: dict[int, dict],
        t: float | None = None,
    ) -> dict[int, np.ndarray]:
        import time
        t = t if t is not None else time.time()
        results: dict[int, np.ndarray] = {}
        for track_id, info in player_tracks.items():
            bbox = info.get("bbox", [0, 0, 100, 200])
            x1, y1, x2, y2 = bbox[:4]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            height = y2 - y1

            kps = np.zeros((17, 3), dtype=np.float32)
            for i in range(17):
                kps[i] = [
                    cx + (i - 8) * 5 + 3 * np.sin(t + i),
                    cy - height * 0.4 + i * (height * 0.8 / 16),
                    0.85,
                ]
            results[track_id] = kps
        return results

    # ── Serialisation ──────────────────────────────────────────────────────────

    @staticmethod
    def keypoints_to_serializable(
        pose_sequence: list[dict[int, np.ndarray]],
    ) -> list[dict]:
        """
        Convert a sequence of {track_id: (17,3) array} dicts to JSON-safe dicts.

        Returns
        -------
        [
          {
            "track_id": int,
            "frame": int,
            "keypoints": [[x, y, conf], ...],   # length 17
          },
          ...
        ]
        """
        out: list[dict] = []
        for frame_idx, frame_poses in enumerate(pose_sequence):
            for track_id, kps in frame_poses.items():
                out.append(
                    {
                        "track_id": int(track_id),
                        "frame": frame_idx,
                        "keypoints": kps.tolist(),
                    }
                )
        return out


# ── Geometry helpers ───────────────────────────────────────────────────────────

def _box_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a[:4]
    bx1, by1, bx2, by2 = b[:4]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / max(ua, 1e-6)
