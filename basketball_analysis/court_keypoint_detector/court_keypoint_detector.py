import logging

from ultralytics import YOLO
import supervision as sv
from utils import read_stub, save_stub
from configs.settings import settings

logger = logging.getLogger(__name__)


class CourtKeypointDetector:
    """
    The CourtKeypointDetector class uses a YOLO model to detect court keypoints in image frames. 
    It also provides functionality to draw these detected keypoints on the frames.
    """
    def __init__(self, model_path):
        self._device = settings.resolve_device()
        self.model = YOLO(model_path)
        self.model.to(self._device)
        logger.info("CourtKeypointDetector loaded on device: %s", self._device)
    
    def get_court_keypoints(self, frames, read_from_stub=False, stub_path=None):
        """
        Detect court keypoints for a batch of frames using the YOLO model. If requested, 
        attempts to read previously detected keypoints from a stub file before running the model.

        Args:
            frames (list of numpy.ndarray): A list of frames (images) on which to detect keypoints.
            read_from_stub (bool, optional): Indicates whether to read keypoints from a stub file 
                instead of running the detection model. Defaults to False.
            stub_path (str, optional): The file path for the stub file. If None, a default path may be used. 
                Defaults to None.

        Returns:
            list: A list of detected keypoints for each input frame.
        """
        court_keypoints = read_stub(read_from_stub, stub_path)
        if court_keypoints is not None:
            if len(court_keypoints) == len(frames):
                return court_keypoints
        
        batch_size = settings.yolo_batch_size
        court_keypoints = []
        for i in range(0, len(frames), batch_size):
            detections_batch = self.model.predict(
                frames[i:i + batch_size],
                conf=0.5,
                device=self._device,
            )
            for detection in detections_batch:
                court_keypoints.append(detection.keypoints)

        save_stub(stub_path, court_keypoints)

        return court_keypoints

    def get_court_keypoints_streaming(
        self, video_path: str, chunk_size: int, max_height: int = 720
    ) -> list:
        """
        Detect court keypoints over the full video using frame-by-frame iteration.

        Reads frames via iter_video_frames (max_height=720 by default) so that
        keypoint coordinates are always in the same 720p space as the draw pass.
        """
        from utils.video_utils import iter_video_frames_selective

        batch_size = getattr(settings, "court_kp_batch_size", None) or settings.yolo_batch_size
        stride = max(1, getattr(settings, "court_kp_sample_every", 1))
        use_half = bool(getattr(settings, "yolo_half", False)) and str(self._device).startswith("cuda")
        _imgsz = getattr(settings, "court_kp_imgsz", 640)

        sampled: list = []   # one detection per sampled frame (indices 0, stride, 2·stride, …)
        batch: list = []

        def _flush(frames: list) -> None:
            for r in self.model.predict(
                frames, conf=0.5, verbose=False, device=self._device,
                half=use_half, imgsz=_imgsz,
            ):
                sampled.append(r.keypoints)

        # Court geometry changes slowly → infer only every `stride` frames (batched,
        # FP16) and carry the last result forward for the skipped ones. Skipped frames
        # are grab()-skipped (not decoded) for an extra speedup. FP16 + larger batch
        # raise GPU/VRAM use; results unchanged vs decoding every frame.
        total = 0
        for idx, frame in iter_video_frames_selective(
            video_path, lambda i: i % stride == 0, max_height=max_height
        ):
            total = idx + 1
            if frame is not None:
                batch.append(frame)
                if len(batch) == batch_size:
                    _flush(batch)
                    batch = []
        if batch:
            _flush(batch)

        # Expand to one entry per frame (carry the block's detection forward).
        keypoints = [
            sampled[min(i // stride, len(sampled) - 1)] if sampled else None
            for i in range(total)
        ]

        logger.info(
            "CourtKeypointDetector.get_court_keypoints_streaming: %d frames "
            "(%d inferred, max_h=%d, imgsz=%d, stride=%d, half=%s)",
            len(keypoints), len(sampled), max_height, _imgsz, stride, use_half,
        )
        return keypoints