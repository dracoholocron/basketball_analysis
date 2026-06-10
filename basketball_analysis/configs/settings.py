"""
Central application settings managed via pydantic-settings.

Values are loaded from environment variables (uppercase) or a .env file.
All hard-coded magic numbers from the original scripts have been moved here.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CourtLevel(str, Enum):
    NBA = "nba"
    FIBA_JUVENIL = "fiba_juvenil"   # FIBA youth / secondary school
    PRIMARIA = "primaria"           # Primary school
    MINI_BASKET = "mini_basket"     # Mini-basket


class CourtProfile:
    """Immutable court dimensions and calibration for a given level."""

    _PRESETS = {
        CourtLevel.NBA: dict(
            width_m=28.65,
            height_m=15.24,
            half_court=False,
            calibration_factor=1.0,
            display_w_px=300,
            display_h_px=161,
        ),
        CourtLevel.FIBA_JUVENIL: dict(
            width_m=26.0,
            height_m=14.0,
            half_court=False,
            calibration_factor=1.0,
            display_w_px=280,
            display_h_px=152,
        ),
        CourtLevel.PRIMARIA: dict(
            width_m=24.0,
            height_m=13.0,
            half_court=False,
            calibration_factor=1.0,
            display_w_px=260,
            display_h_px=141,
        ),
        CourtLevel.MINI_BASKET: dict(
            width_m=22.0,
            height_m=12.0,
            half_court=True,
            calibration_factor=1.0,
            display_w_px=240,
            display_h_px=130,
        ),
    }

    def __init__(
        self,
        level: CourtLevel = CourtLevel.NBA,
        *,
        width_m: Optional[float] = None,
        height_m: Optional[float] = None,
        half_court: Optional[bool] = None,
        calibration_factor: Optional[float] = None,
        display_w_px: Optional[int] = None,
        display_h_px: Optional[int] = None,
    ) -> None:
        preset = self._PRESETS[level].copy()
        self.level = level
        self.width_m: float = width_m if width_m is not None else preset["width_m"]
        self.height_m: float = height_m if height_m is not None else preset["height_m"]
        self.half_court: bool = half_court if half_court is not None else preset["half_court"]
        self.calibration_factor: float = (
            calibration_factor if calibration_factor is not None else preset["calibration_factor"]
        )
        self.display_w_px: int = (
            display_w_px if display_w_px is not None else preset["display_w_px"]
        )
        self.display_h_px: int = (
            display_h_px if display_h_px is not None else preset["display_h_px"]
        )

    @classmethod
    def from_level(cls, level: CourtLevel) -> "CourtProfile":
        return cls(level=level)

    def __repr__(self) -> str:
        return (
            f"CourtProfile(level={self.level}, {self.width_m}m×{self.height_m}m, "
            f"half_court={self.half_court})"
        )


class EngineSettings(BaseSettings):
    """Settings for the basketball analysis engine."""

    model_config = SettingsConfigDict(
        env_prefix="BA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Model paths ────────────────────────────────────────────────────────────
    # YOLO11 multi-class model (Ball, Clock, Hoop, Overlay, Player, Ref, Scoreboard).
    # When set, both PlayerTracker and BallTracker share this single model file,
    # each filtering their respective class.  Falls back to the legacy separate models
    # when the file does not exist.
    multiclass_detector_path: str = Field(
        default="models/yolo11_multiclass.pt",
        description="Path to the YOLO11 multi-class detector (players + ball + hoop)",
    )
    player_detector_path: str = Field(
        default="models/player_detector.pt",
        description="Path to the legacy YOLO player detection model (fallback)",
    )
    ball_detector_path: str = Field(
        default="models/ball_detector.pt",
        description="Path to the legacy YOLO ball detection model (fallback)",
    )
    court_keypoint_detector_path: str = Field(
        default="models/court_keypoint_detector.pt",
        description="Path to the YOLOv8/YOLO11-pose court keypoint model",
    )
    court_image_path: str = Field(
        default="images/basketball_court.png",
        description="Path to the top-down court diagram image",
    )
    stubs_default_path: str = Field(
        default="stubs/",
        description="Default directory for stub (cache) files",
    )
    output_video_path: str = Field(
        default="output_videos/output.avi",
        description="Default output video path",
    )

    # ── Ball acquisition ───────────────────────────────────────────────────────
    containment_threshold: float = Field(
        default=0.8,
        description="Minimum bbox containment ratio to consider a player holding the ball",
    )
    possession_threshold: float = Field(
        default=50.0,
        description="Max pixel distance from ball center to player for possession (fallback)",
    )
    min_possession_frames: int = Field(
        default=6,
        description="Minimum consecutive frames before possession is confirmed (~0.25s at 24fps)",
    )

    # ── Ball detector tuning ───────────────────────────────────────────────────
    ball_detector_conf: float = Field(
        default=0.35,
        description="Detection confidence threshold for ball detector",
    )
    ball_detector_nms: float = Field(
        default=0.4,
        description="NMS IoU threshold for ball detector",
    )
    ball_sahi_tile: int = Field(
        default=640,
        description="SAHI tile size (px) for ball gap-refill; smaller helps tiny balls",
    )
    ball_sahi_overlap: float = Field(
        default=0.25,
        description="SAHI tile overlap fraction for ball gap-refill",
    )
    ball_max_interp_gap: int = Field(
        default=15,
        description=(
            "Max consecutive missing frames to linear-interpolate the ball across "
            "(~0.5s at 30fps). Longer gaps are left empty instead of drawing a "
            "false straight line."
        ),
    )
    ball_kalman: bool = Field(
        default=True,
        description="Apply a constant-velocity Kalman filter to smooth/predict the ball",
    )
    ball_visual_track: bool = Field(
        default=False,
        description=(
            "Bridge detector gaps with a color-agnostic visual tracker (CSRT) seeded "
            "from confident detections — helps off-domain balls (e.g. gray). Off by "
            "default: try lower conf + Kalman first; enable only if coverage is still low."
        ),
    )
    ball_sam2: bool = Field(
        default=True,
        description=(
            "When manual ball annotations exist, propagate them across the video with "
            "SAM2 (color-agnostic) and fuse with the YOLO detector. Degrades to the "
            "YOLO path if sam2 is unavailable."
        ),
    )
    sam2_checkpoint: str = Field(
        default="models/sam2.1_hiera_small.pt",
        description="Path to the SAM2 checkpoint (.pt)",
    )
    sam2_config: str = Field(
        default="configs/sam2.1/sam2.1_hiera_s.yaml",
        description="SAM2 hydra config name (ships with the sam2 package)",
    )
    sam2_stride: int = Field(
        default=1,
        description=(
            "Process 1 of every N frames with SAM2 (rest filled by Kalman/interp). "
            "Raise (2-3) on very long videos to cut SAM2 time."
        ),
    )

    # ── Player detection resolution ──────────────────────────────────────────────
    player_max_h: int = Field(
        default=720,
        description=(
            "Frame read height for player detection. Raise (e.g. 1080) to feed the "
            "detector native-resolution frames; boxes are rescaled back to 720p."
        ),
    )
    player_imgsz: int = Field(
        default=640,
        description=(
            "YOLO inference imgsz for player detection. Raise (e.g. 1280) together "
            "with player_max_h so small/distant players aren't lost to the default "
            "640 internal resize."
        ),
    )
    tracker: str = Field(
        default="botsort",
        description=(
            "Player tracker backend: 'botsort' (BoT-SORT + camera-motion "
            "compensation — best for panning video) or 'bytetrack'."
        ),
    )
    tracker_lost_buffer: int = Field(
        default=120,
        description=(
            "ByteTrack lost_track_buffer (frames). Higher keeps a lost track alive "
            "longer through occlusions → fewer new IDs (~4s at 30fps)."
        ),
    )
    tracker_min_match: float = Field(
        default=0.85,
        description="ByteTrack minimum_matching_threshold (higher = looser re-match)",
    )
    tracker_frame_rate: int = Field(
        default=30,
        description="ByteTrack frame_rate (scales the lost-track buffer window)",
    )
    track_stitch: bool = Field(
        default=True,
        description="Link track fragments by spatio-temporal continuity (tracklet stitching)",
    )
    track_stitch_max_gap_s: float = Field(
        default=1.0,
        description="Max time gap (s) between one track ending and another starting to stitch them",
    )
    track_stitch_max_dist_frac: float = Field(
        default=0.10,
        description="Max center distance to stitch, as fraction of frame width, per second of gap",
    )
    min_track_seconds: float = Field(
        default=0.5,
        description="Drop provisional (no-dorsal) identities seen less than this (noise/false tracks)",
    )

    # ── Jersey number OCR (player identity) ──────────────────────────────────────
    jersey_ocr: bool = Field(
        default=True,
        description="Read jersey numbers (OCR) per track and consolidate identities by (team, number)",
    )
    jersey_ocr_sample_every: int = Field(
        default=5,
        description="Run jersey OCR every N frames per track (cost control; lower = more coverage)",
    )
    jersey_ocr_min_votes: int = Field(
        default=2,
        description="Min OCR readings agreeing before a track is assigned a jersey number",
    )
    ball_export_dataset: bool = Field(
        default=False,
        description="Export SAM2-propagated ball boxes as a YOLO dataset during analysis (fine-tune corpus)",
    )

    # ── Pose estimation ──────────────────────────────────────────────────────────
    pose_conf_threshold: float = Field(
        default=0.05,
        description=(
            "Min keypoint confidence to DRAW a pose joint/bone. RTMPose SimCC "
            "raw-max scores sit around ~0.05-0.17 for real joints, so it is well "
            "below 1.0."
        ),
    )
    pose_topdown: bool = Field(
        default=True,
        description=(
            "YOLO-pose top-down: run pose on each tracked player's crop (upscaled) "
            "instead of the full frame, so small/distant players still get a skeleton."
        ),
    )
    event_pose_conf_threshold: float = Field(
        default=0.12,
        description=(
            "Stricter keypoint confidence used by the event detectors (shots/steals) "
            "so noisy low-confidence joints don't trigger false events. Higher than "
            "the draw threshold."
        ),
    )

    # ── Team assignment ────────────────────────────────────────────────────────
    team_1_jersey: str = Field(
        default="white shirt",
        description="Zero-shot text label for Team 1 jersey",
    )
    team_2_jersey: str = Field(
        default="dark blue shirt",
        description="Zero-shot text label for Team 2 jersey",
    )
    team_assigner_vote_window: int = Field(
        default=30,
        description="Rolling window (frames) for majority-vote team assignment per track_id",
    )

    # ── Speed / distance ───────────────────────────────────────────────────────
    speed_window_frames: int = Field(
        default=25,
        description="Window size (frames) used to compute speed rolling average (~1s at 24fps)",
    )
    speed_max_kmh: float = Field(
        default=40.0,
        description="Hard cap on per-frame speed (km/h) to filter homography noise",
    )
    speed_deadband_m: float = Field(
        default=0.08,
        description=(
            "Per-frame tactical displacement (m) below which movement is treated as "
            "jitter and counted as 0 — stops a stationary player accruing fake distance."
        ),
    )
    speed_smooth_alpha: float = Field(
        default=0.4,
        description=(
            "EMA factor (0-1) to smooth per-player tactical positions before measuring "
            "distance. Lower = smoother. 1.0 disables smoothing."
        ),
    )

    # ── Device / hardware ───────────────────────────────────────────────────────
    device: str = Field(
        default="auto",
        description=(
            "Inference device for YOLO models. "
            "'auto' selects CUDA when available, else CPU. "
            "Can also be set to 'cuda', 'cuda:0', or 'cpu'. Env: BA_DEVICE"
        ),
    )

    # ── Batch sizes ────────────────────────────────────────────────────────────
    yolo_batch_size: int = Field(
        default=16,
        description="Batch size for YOLO inference (increase for higher VRAM GPUs). Env: BA_YOLO_BATCH_SIZE",
    )
    clip_batch_size: int = Field(
        default=8,
        description="Batch size for CLIP team assigner inference. Env: BA_CLIP_BATCH_SIZE",
    )
    clip_sample_every: int = Field(
        default=30,
        description="Run CLIP inference every N frames per player; intermediate frames reuse last vote. Env: BA_CLIP_SAMPLE_EVERY",
    )
    fps: float = Field(
        default=24.0,
        description="Video frame rate — overridden by actual video FPS when available",
    )

    # ── Court / tactical view ──────────────────────────────────────────────────
    court_level: CourtLevel = Field(
        default=CourtLevel.NBA,
        description="Court profile level (nba|fiba_juvenil|primaria|mini_basket)",
    )

    # ── Streaming / chunked inference ─────────────────────────────────────────
    chunk_size: int = Field(
        default=500,
        description=(
            "Number of frames loaded into RAM at once during inference. "
            "Keeps peak RAM at ~chunk_size × 2.76 MB instead of all_frames × 2.76 MB. "
            "Set to 0 to disable chunking (legacy read_video path). Env: BA_CHUNK_SIZE"
        ),
    )

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Python logging level")

    def resolve_device(self) -> str:
        """Resolve 'auto' to 'cuda' or 'cpu' based on torch availability."""
        if self.device.lower() != "auto":
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def configure_logging(self) -> None:
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    def get_court_profile(self) -> CourtProfile:
        return CourtProfile.from_level(self.court_level)


# Module-level singleton — callers do `from configs.settings import settings`
settings = EngineSettings()
