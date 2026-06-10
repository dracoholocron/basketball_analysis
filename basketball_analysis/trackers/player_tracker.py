"""
Player detection and tracking using YOLO + ByteTrack.

Supports both the legacy single-class player model and the new YOLO11
multi-class model (Ball, Clock, Hoop, Overlay, Player, Ref, Scoreboard).
The class name 'Player' is accepted from both.
"""
from __future__ import annotations

import logging
import os

from ultralytics import YOLO
import supervision as sv
from utils import read_stub, save_stub
from configs.settings import settings

logger = logging.getLogger(__name__)

_PLAYER_CLASS_NAMES: tuple[str, ...] = ("Player",)
_REFEREE_CLASS_NAMES: tuple[str, ...] = ("Ref", "referee", "Referee")


class PlayerTracker:
    """
    Player detection and tracking using YOLO and ByteTrack.

    Works with:
    - Legacy single-class player model (class "Player")
    - New YOLO11 multi-class model (also exposes class "Player")
    """

    def __init__(self, model_path: str, conf: float = 0.5) -> None:
        self._device = settings.resolve_device()
        self.model = YOLO(model_path)
        self.model.to(self._device)
        logger.info("PlayerTracker loaded on device: %s", self._device)
        # Tuned ByteTrack: a larger lost-track buffer keeps identities alive across
        # occlusions/re-entries → far fewer spurious new IDs than the default.
        try:
            self.tracker = sv.ByteTrack(
                lost_track_buffer=getattr(settings, "tracker_lost_buffer", 120),
                minimum_matching_threshold=getattr(settings, "tracker_min_match", 0.85),
                frame_rate=getattr(settings, "tracker_frame_rate", 30),
            )
        except TypeError:
            # Older supervision signature
            self.tracker = sv.ByteTrack()
        self.conf = conf

    def detect_frames(self, frames: list) -> list:
        batch_size = settings.yolo_batch_size
        detections: list = []
        for i in range(0, len(frames), batch_size):
            batch = self.model.predict(
                frames[i : i + batch_size],
                conf=self.conf,
                verbose=False,
                device=self._device,
            )
            detections += batch
        return detections

    def detect_frames_streaming(
        self, video_path: str, chunk_size: int, max_height: int = 720,
        target_height: int = 720,
    ) -> list[sv.Detections]:
        """
        YOLO detection over the full video using frame-by-frame iteration.

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

        # If detecting at a higher resolution than the pipeline's working space,
        # rescale boxes back to target_height (720p) so all downstream stages
        # (tracking, tactical homography, drawing) stay in one coordinate space.
        _scale = (target_height / max_height) if max_height != target_height else 1.0

        _imgsz = getattr(settings, "player_imgsz", 640)

        def _flush(frames: list) -> None:
            for r in self.model.predict(
                frames, conf=self.conf, verbose=False, device=self._device,
                imgsz=_imgsz,
            ):
                if self._cls_names is None:
                    self._cls_names = r.names
                det = sv.Detections.from_ultralytics(r)
                if _scale != 1.0 and len(det) > 0:
                    det.xyxy = det.xyxy * _scale
                all_sv.append(det)

        for frame in iter_video_frames(video_path, max_height=max_height):
            batch.append(frame)
            if len(batch) == batch_size:
                _flush(batch)
                batch = []
        if batch:
            _flush(batch)

        logger.info(
            "PlayerTracker.detect_frames_streaming: %d frames detected (max_h=%d)",
            len(all_sv), max_height,
        )
        return all_sv

    def _botsort_cfg(self) -> str:
        """Absolute path to the tuned BoT-SORT config shipped with the engine."""
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(here, "configs", "trackers", "botsort_smartbasket.yaml")

    def get_tracks_streaming(
        self, video_path: str, max_height: int = 720, target_height: int = 720,
    ) -> tuple[list[dict], list[dict]]:
        """Detect + track players and referees over the full video (streaming).

        Returns ``(player_tracks, referee_tracks)``. Chooses the tracker backend
        from settings: 'botsort' (BoT-SORT + camera-motion compensation — robust on
        panning footage) or 'bytetrack' (legacy supervision path).
        """
        backend = getattr(settings, "tracker", "botsort").lower()
        if backend != "botsort":
            sv_det = self.detect_frames_streaming(video_path, 0, max_height, target_height)
            return (
                self.build_tracks_from_sv_detections(sv_det),
                self.build_referee_tracks_from_sv_detections(sv_det),
            )

        from utils.video_utils import iter_video_frames

        cfg = self._botsort_cfg()
        _scale = (target_height / max_height) if max_height != target_height else 1.0
        _imgsz = getattr(settings, "player_imgsz", 640)
        logger.info("PlayerTracker: BoT-SORT (GMC) tracking, cfg=%s", os.path.basename(cfg))

        player_tracks: list[dict] = []
        referee_tracks: list[dict] = []
        ref_counter = 0
        self._cls_names = None

        for frame in iter_video_frames(video_path, max_height=max_height):
            res = self.model.track(
                frame, persist=True, conf=self.conf, imgsz=_imgsz,
                tracker=cfg, verbose=False, device=self._device,
            )
            r = res[0]
            if self._cls_names is None:
                self._cls_names = r.names
            cls_inv = {v: k for k, v in r.names.items()}
            player_id_set = {cls_inv[n] for n in _PLAYER_CLASS_NAMES if n in cls_inv}
            ref_id_set = {cls_inv[n] for n in _REFEREE_CLASS_NAMES if n in cls_inv}

            pframe: dict = {}
            rframe: dict = {}
            boxes = r.boxes
            if boxes is not None and len(boxes) > 0:
                xyxy = boxes.xyxy.cpu().numpy()
                clss = boxes.cls.cpu().numpy().astype(int)
                ids = (
                    boxes.id.cpu().numpy().astype(int)
                    if boxes.id is not None else [None] * len(clss)
                )
                for box, cls_id, tid in zip(xyxy, clss, ids):
                    bbox = (box * _scale).tolist() if _scale != 1.0 else box.tolist()
                    if cls_id in player_id_set and tid is not None:
                        pframe[int(tid)] = {"bbox": bbox}
                    elif cls_id in ref_id_set:
                        ref_counter += 1
                        rframe[-ref_counter] = {"bbox": bbox}
            player_tracks.append(pframe)
            referee_tracks.append(rframe)

        logger.info(
            "PlayerTracker.get_tracks_streaming (botsort): %d frames, %d player IDs, %d ref dets",
            len(player_tracks),
            len({tid for f in player_tracks for tid in f}),
            sum(len(f) for f in referee_tracks),
        )
        return player_tracks, referee_tracks

    def build_tracks_from_sv_detections(
        self, sv_detections: list[sv.Detections]
    ) -> list[dict]:
        """
        Run ByteTrack on pre-computed sv.Detections (no frame data needed).

        Requires self._cls_names to be set (populated by detect_frames_streaming).
        """
        cls_names = getattr(self, "_cls_names", None) or {}
        cls_names_inv = {v: k for k, v in cls_names.items()}

        tracks: list[dict] = []
        for frame_num, det_sv in enumerate(sv_detections):
            det_with_tracks = self.tracker.update_with_detections(det_sv)
            tracks.append({})
            for frame_detection in det_with_tracks:
                bbox = frame_detection[0].tolist()
                cls_id = frame_detection[3]
                track_id = frame_detection[4]
                if any(
                    name in cls_names_inv and cls_id == cls_names_inv[name]
                    for name in _PLAYER_CLASS_NAMES
                ):
                    tracks[frame_num][track_id] = {"bbox": bbox}

        logger.info(
            "PlayerTracker.build_tracks_from_sv_detections: %d frames tracked",
            len(tracks),
        )
        return tracks

    def build_referee_tracks_from_sv_detections(
        self, sv_detections: list[sv.Detections]
    ) -> list[dict]:
        """
        Extract referee bounding boxes from pre-computed sv.Detections.

        Uses the same detection pass as player tracking (no extra inference).
        Referees are NOT tracked with ByteTrack (no persistent ID needed).
        Returns list[dict] same shape as player_tracks for easy iteration.
        """
        cls_names = getattr(self, "_cls_names", None) or {}
        cls_names_inv = {v: k for k, v in cls_names.items()}
        ref_ids = {
            cls_names_inv[name]
            for name in _REFEREE_CLASS_NAMES
            if name in cls_names_inv
        }

        tracks: list[dict] = []
        ref_counter = 0
        for det_sv in sv_detections:
            frame_refs: dict = {}
            if ref_ids:
                for i in range(len(det_sv)):
                    cls_id = int(det_sv.class_id[i]) if det_sv.class_id is not None else -1
                    if cls_id in ref_ids:
                        bbox = det_sv.xyxy[i].tolist()
                        ref_counter += 1
                        frame_refs[-(ref_counter)] = {"bbox": bbox}
            tracks.append(frame_refs)

        n_refs = sum(len(f) for f in tracks)
        logger.info(
            "PlayerTracker.build_referee_tracks_from_sv_detections: %d referee detections across %d frames",
            n_refs, len(tracks),
        )
        return tracks

    def get_object_tracks(
        self,
        frames: list,
        read_from_stub: bool = False,
        stub_path: str | None = None,
    ) -> list[dict]:
        tracks = read_stub(read_from_stub, stub_path)
        if tracks is not None and len(tracks) == len(frames):
            return tracks

        detections = self.detect_frames(frames)
        tracks = []

        for frame_num, detection in enumerate(detections):
            cls_names = detection.names
            cls_names_inv = {v: k for k, v in cls_names.items()}

            det_sv = sv.Detections.from_ultralytics(detection)
            det_with_tracks = self.tracker.update_with_detections(det_sv)

            tracks.append({})
            for frame_detection in det_with_tracks:
                bbox = frame_detection[0].tolist()
                cls_id = frame_detection[3]
                track_id = frame_detection[4]

                if any(
                    name in cls_names_inv and cls_id == cls_names_inv[name]
                    for name in _PLAYER_CLASS_NAMES
                ):
                    tracks[frame_num][track_id] = {"bbox": bbox}

        save_stub(stub_path, tracks)
        return tracks
