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

    # ── Batch sizes ────────────────────────────────────────────────────────────
    yolo_batch_size: int = Field(
        default=16,
        description="Batch size for YOLO inference (increase for higher VRAM GPUs). Env: BA_YOLO_BATCH_SIZE",
    )
    clip_batch_size: int = Field(
        default=8,
        description="Batch size for CLIP team assigner inference. Env: BA_CLIP_BATCH_SIZE",
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

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Python logging level")

    def configure_logging(self) -> None:
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    def get_court_profile(self) -> CourtProfile:
        return CourtProfile.from_level(self.court_level)


# Module-level singleton — callers do `from configs.settings import settings`
settings = EngineSettings()
