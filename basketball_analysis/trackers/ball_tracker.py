import logging
import os

from ultralytics import YOLO
import supervision as sv
import numpy as np
import pandas as pd
from utils import read_stub, save_stub
from configs.settings import settings

logger = logging.getLogger(__name__)

# When BA_DUMMY_MODELS=true the real ball detector is replaced by a yolov8n.pt
# checkpoint trained on COCO.  COCO does not have a "Ball" class; instead we
# accept class "sports ball" (COCO id 32) so the pipeline can still run end-to-end
# for smoke / E2E tests without real models.
_DUMMY_MODE: bool = os.environ.get("BA_DUMMY_MODELS", "").lower() in ("1", "true", "yes")
_BALL_CLASS_ALIASES: tuple[str, ...] = ("Ball", "basketball")
if _DUMMY_MODE:
    _BALL_CLASS_ALIASES = _BALL_CLASS_ALIASES + ("sports ball",)


class BallTracker:
    """
    Basketball detection and tracking using YOLO.

    Parameters
    ----------
    model_path : str
        Path to the YOLO ball detection .pt model.
    conf : float
        Detection confidence threshold.  Lowered to 0.35 by default to
        handle smaller balls (size 5/6) in school games.
    iou : float
        NMS IoU threshold.
    """

    def __init__(
        self,
        model_path: str,
        conf: float | None = None,
        iou: float | None = None,
    ) -> None:
        self._device = settings.resolve_device()
        self.model = YOLO(model_path)
        self.model.to(self._device)
        logger.info("BallTracker loaded on device: %s", self._device)
        self.conf = conf if conf is not None else settings.ball_detector_conf
        self.iou = iou if iou is not None else settings.ball_detector_nms

    def detect_frames(self, frames: list) -> list:
        """
        Detect the ball in batches.

        Args:
            frames: Video frames (BGR numpy arrays).

        Returns:
            YOLO results list, one entry per frame.
        """
        batch_size = settings.yolo_batch_size
        detections: list = []
        for i in range(0, len(frames), batch_size):
            batch_results = self.model.predict(
                frames[i : i + batch_size],
                conf=self.conf,
                iou=self.iou,
                device=self._device,
                )
            detections += batch_results
        return detections

    def detect_frames_streaming(
        self, video_path: str, chunk_size: int, max_height: int = 720
    ) -> list[sv.Detections]:
        """
        YOLO ball detection over the full video using frame-by-frame iteration.

        Reads frames via iter_video_frames (max_height=720 by default) so that
        bounding-box coordinates are always in the same 720p space as the draw
        pass.  Frames are batched for GPU throughput without loading the entire
        video into RAM.
        """
        from utils.video_utils import iter_video_frames

        all_sv: list[sv.Detections] = []
        self._cls_names: dict | None = None
        batch: list = []
        batch_size = settings.yolo_batch_size

        def _flush(frames: list) -> None:
            for r in self.model.predict(
                frames, conf=self.conf, iou=self.iou, verbose=False, device=self._device,            ):
                if self._cls_names is None:
                    self._cls_names = r.names
                all_sv.append(sv.Detections.from_ultralytics(r))

        for frame in iter_video_frames(video_path, max_height=max_height):
            batch.append(frame)
            if len(batch) == batch_size:
                _flush(batch)
                batch = []
        if batch:
            _flush(batch)

        logger.info(
            "BallTracker.detect_frames_streaming: %d frames detected (max_h=%d)",
            len(all_sv), max_height,
        )
        return all_sv

    def build_tracks_from_sv_detections(
        self, sv_detections: list[sv.Detections]
    ) -> list[dict]:
        """
        Build ball tracks from pre-computed sv.Detections (no frame data needed).

        Selects the highest-confidence ball detection per frame, same logic as
        get_object_tracks. Requires self._cls_names (set by detect_frames_streaming).
        """
        cls_names = getattr(self, "_cls_names", None) or {}
        cls_names_inv = {v: k for k, v in cls_names.items()}

        tracks: list[dict] = []
        for det_sv in sv_detections:
            tracks.append({})
            chosen_bbox = None
            max_confidence = 0.0

            for i in range(len(det_sv)):
                bbox = det_sv.xyxy[i].tolist()
                cls_id = int(det_sv.class_id[i])
                confidence = float(det_sv.confidence[i]) if det_sv.confidence is not None else 0.0

                if any(
                    alias in cls_names_inv and cls_id == cls_names_inv[alias]
                    for alias in _BALL_CLASS_ALIASES
                ):
                    if confidence > max_confidence:
                        chosen_bbox = bbox
                        max_confidence = confidence

            if chosen_bbox is not None:
                tracks[-1][1] = {"bbox": chosen_bbox}

        logger.info(
            "BallTracker.build_tracks_from_sv_detections: %d frames processed",
            len(tracks),
        )
        return tracks

    def get_object_tracks(self, frames, read_from_stub=False, stub_path=None):
        """
        Get ball tracking results for a sequence of frames with optional caching.

        Args:
            frames (list): List of video frames to process.
            read_from_stub (bool): Whether to attempt reading cached results.
            stub_path (str): Path to the cache file.

        Returns:
            list: List of dictionaries containing ball tracking information for each frame.
        """
        tracks = read_stub(read_from_stub,stub_path)
        if tracks is not None:
            if len(tracks) == len(frames):
                return tracks

        detections = self.detect_frames(frames)

        tracks=[]

        for frame_num, detection in enumerate(detections):
            cls_names = detection.names
            cls_names_inv = {v:k for k,v in cls_names.items()}

            # Covert to supervision Detection format
            detection_supervision = sv.Detections.from_ultralytics(detection)

            tracks.append({})
            chosen_bbox =None
            max_confidence = 0
            
            for frame_detection in detection_supervision:
                bbox = frame_detection[0].tolist()
                cls_id = frame_detection[3]
                confidence = frame_detection[2]
                
                # Accept any recognised ball class name (real or dummy alias)
                if any(
                    alias in cls_names_inv and cls_id == cls_names_inv[alias]
                    for alias in _BALL_CLASS_ALIASES
                ):
                    if max_confidence < confidence:
                        chosen_bbox = bbox
                        max_confidence = confidence

            if chosen_bbox is not None:
                tracks[frame_num][1] = {"bbox":chosen_bbox}

        save_stub(stub_path,tracks)
        
        return tracks

    def refill_missing_with_sahi(
        self,
        video_path: str,
        ball_tracks: list[dict],
        tile_size: int = 640,
        overlap: float = 0.25,
        sahi_conf: float | None = None,
        min_gap_frames: int = 8,
    ) -> list[dict]:
        """
        Selective SAHI: re-run tiled detection only on long gaps where no ball was found.

        Short gaps (< min_gap_frames) are skipped because pandas interpolation handles
        them accurately. Only long consecutive gaps justify the per-frame SAHI cost.
        Iterates the video once; stops early when all target frames are covered.
        """
        all_missing = sorted(i for i, bt in enumerate(ball_tracks) if 1 not in bt)
        if not all_missing:
            logger.info("SAHI refill: no missing ball frames — skipping")
            return ball_tracks

        # Identify contiguous gaps and keep only those >= min_gap_frames
        sahi_frames: set[int] = set()
        gap_start = all_missing[0]
        prev = all_missing[0]
        for idx in all_missing[1:]:
            if idx != prev + 1:
                if prev - gap_start + 1 >= min_gap_frames:
                    sahi_frames.update(range(gap_start, prev + 1))
                gap_start = idx
            prev = idx
        if prev - gap_start + 1 >= min_gap_frames:
            sahi_frames.update(range(gap_start, prev + 1))

        skipped = len(all_missing) - len(sahi_frames)
        if not sahi_frames:
            logger.info(
                "SAHI refill: all %d missing frames are in short gaps (<=%d) — skipping SAHI",
                len(all_missing), min_gap_frames - 1,
            )
            return ball_tracks

        logger.info(
            "SAHI refill: %d frames in long gaps (skipping %d short-gap frames) — running tiled detection",
            len(sahi_frames), skipped,
        )
        conf = sahi_conf if sahi_conf is not None else max(self.conf * 0.8, 0.2)
        tracks = list(ball_tracks)
        found = 0
        remaining = set(sahi_frames)

        from utils.video_utils import iter_video_frames
        for frame_idx, frame in enumerate(iter_video_frames(video_path, max_height=720)):
            if frame_idx >= len(tracks):
                break
            if frame_idx not in remaining:
                continue
            bbox = self._sahi_detect_frame(frame, tile_size, overlap, conf)
            if bbox is not None:
                tracks[frame_idx] = {1: {"bbox": bbox}}
                found += 1
            remaining.discard(frame_idx)
            if not remaining:
                break

        logger.info("SAHI refill: recovered %d / %d long-gap frames", found, len(sahi_frames))
        return tracks

    def _sahi_detect_frame(
        self,
        frame: np.ndarray,
        tile_size: int,
        overlap: float,
        conf: float,
    ) -> list[float] | None:
        """
        Tile a single frame and batch all tiles into one predict() call.

        All tiles for the frame are collected first, then passed as a single
        batch to the model — much faster than one predict() call per tile.
        """
        h, w = frame.shape[:2]
        if h <= tile_size and w <= tile_size:
            results = self.model.predict(
                frame, conf=conf, iou=self.iou, verbose=False, device=self._device,            )
            return self._best_ball_from_result(results[0] if results else None, 0, 0)

        step = max(1, int(tile_size * (1 - overlap)))
        tiles: list[np.ndarray] = []
        offsets: list[tuple[int, int]] = []

        for y in range(0, h, step):
            for x in range(0, w, step):
                x2, y2 = min(x + tile_size, w), min(y + tile_size, h)
                tiles.append(frame[y:y2, x:x2])
                offsets.append((x, y))

        if not tiles:
            return None

        results = self.model.predict(
            tiles, conf=conf, iou=self.iou, verbose=False, device=self._device,        )

        best_conf = 0.0
        best_bbox: list[float] | None = None
        for det, (ox, oy) in zip(results, offsets):
            bbox, bc = self._best_ball_from_result(det, ox, oy, return_conf=True)
            if bbox is not None and bc > best_conf:
                best_conf = bc
                best_bbox = bbox

        return best_bbox

    def _best_ball_from_result(
        self,
        det,
        offset_x: int,
        offset_y: int,
        return_conf: bool = False,
    ):
        """Extract best ball bbox from a YOLO result, applying tile coordinate offset."""
        if det is None:
            return (None, 0.0) if return_conf else None
        cls_names_inv = {v: k for k, v in det.names.items()}
        best_bbox: list[float] | None = None
        best_conf = 0.0
        for box in det.boxes:
            cls_id = int(box.cls[0])
            bc = float(box.conf[0])
            if (
                any(
                    alias in cls_names_inv and cls_id == cls_names_inv[alias]
                    for alias in _BALL_CLASS_ALIASES
                )
                and bc > best_conf
            ):
                raw = box.xyxy[0].tolist()
                best_bbox = [
                    raw[0] + offset_x, raw[1] + offset_y,
                    raw[2] + offset_x, raw[3] + offset_y,
                ]
                best_conf = bc
        return (best_bbox, best_conf) if return_conf else best_bbox

    def remove_wrong_detections(self,ball_positions):
        """
        Filter out incorrect ball detections based on maximum allowed movement distance.

        Args:
            ball_positions (list): List of detected ball positions across frames.

        Returns:
            list: Filtered ball positions with incorrect detections removed.
        """
        
        maximum_allowed_distance = 25
        last_good_frame_index = -1

        for i in range(len(ball_positions)):
            current_box = ball_positions[i].get(1, {}).get('bbox', [])

            if len(current_box) == 0:
                continue

            if last_good_frame_index == -1:
                # First valid detection
                last_good_frame_index = i
                continue

            last_good_box = ball_positions[last_good_frame_index].get(1, {}).get('bbox', [])
            frame_gap = i - last_good_frame_index
            adjusted_max_distance = maximum_allowed_distance * frame_gap

            if np.linalg.norm(np.array(last_good_box[:2]) - np.array(current_box[:2])) > adjusted_max_distance:
                ball_positions[i] = {}
            else:
                last_good_frame_index = i

        return ball_positions

    def interpolate_ball_positions(self,ball_positions):
        """
        Interpolate missing ball positions to create smooth tracking results.

        Args:
            ball_positions (list): List of ball positions with potential gaps.

        Returns:
            list: List of ball positions with interpolated values filling the gaps.
        """
        ball_positions = [x.get(1,{}).get('bbox',[]) for x in ball_positions]
        df_ball_positions = pd.DataFrame(ball_positions,columns=['x1','y1','x2','y2'])

        # Interpolate missing values
        df_ball_positions = df_ball_positions.interpolate()
        df_ball_positions = df_ball_positions.bfill()

        ball_positions = [{1: {"bbox":x}} for x in df_ball_positions.to_numpy().tolist()]
        return ball_positions