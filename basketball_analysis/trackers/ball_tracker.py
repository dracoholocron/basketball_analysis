import os

from ultralytics import YOLO
import supervision as sv
import numpy as np
import pandas as pd
from utils import read_stub, save_stub
from configs.settings import settings

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
        self.model = YOLO(model_path)
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
            )
            detections += batch_results
        return detections

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