"""
Player detection and tracking using YOLO + ByteTrack.

Supports both the legacy single-class player model and the new YOLO11
multi-class model (Ball, Clock, Hoop, Overlay, Player, Ref, Scoreboard).
The class name 'Player' is accepted from both.
"""
from __future__ import annotations

import os

from ultralytics import YOLO
import supervision as sv
from utils import read_stub, save_stub

_PLAYER_CLASS_NAMES: tuple[str, ...] = ("Player",)


class PlayerTracker:
    """
    Player detection and tracking using YOLO and ByteTrack.

    Works with:
    - Legacy single-class player model (class "Player")
    - New YOLO11 multi-class model (also exposes class "Player")
    """

    def __init__(self, model_path: str, conf: float = 0.5) -> None:
        self.model = YOLO(model_path)
        self.tracker = sv.ByteTrack()
        self.conf = conf

    def detect_frames(self, frames: list) -> list:
        batch_size = 20
        detections: list = []
        for i in range(0, len(frames), batch_size):
            batch = self.model.predict(frames[i : i + batch_size], conf=self.conf, verbose=False)
            detections += batch
        return detections

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
