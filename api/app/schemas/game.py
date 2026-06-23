from __future__ import annotations
import uuid
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class GameCreate(BaseModel):
    season_id: uuid.UUID
    home_team_id: Optional[uuid.UUID] = None
    away_team_id: Optional[uuid.UUID] = None
    game_date: Optional[date] = None
    location: Optional[str] = None
    court_level: str = Field(default="nba", description="nba|fiba_juvenil|primaria|mini_basket")
    court_width_m: Optional[float] = None
    court_height_m: Optional[float] = None
    is_half_court: bool = False
    home_team1_jersey: str = "white shirt"
    away_team2_jersey: str = "dark blue shirt"
    show_poses: bool = True
    ball_detector_mode: str = Field(default="auto", description="auto|tracknet|yolo")


class GameRead(BaseModel):
    id: uuid.UUID
    season_id: uuid.UUID
    home_team_id: Optional[uuid.UUID]
    away_team_id: Optional[uuid.UUID]
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    game_date: Optional[date]
    location: Optional[str]
    court_level: str
    is_half_court: bool
    show_poses: bool
    home_team1_jersey: str
    away_team2_jersey: str
    home_score: Optional[int]
    away_score: Optional[int]
    analysis_start_s: Optional[float] = None
    analysis_end_s: Optional[float] = None
    ball_tracking_quality: Optional[str] = None
    ball_detector_mode: Optional[str] = None

    model_config = {"from_attributes": True}


class GameList(BaseModel):
    items: list[GameRead]
    total: int


class AnalysisOptions(BaseModel):
    """Optional per-analysis parameters sent in the body of POST /games/{id}/analyze."""
    pose_player_filter: Optional[list[int]] = Field(
        default=None,
        description="Track IDs to limit pose drawing to. None = draw all players.",
    )
    use_curated_ball: bool = Field(
        default=False,
        description=(
            "Use the curated ball track from the game's completed interactive "
            "ball-tracking session (skips the SAM2 propagation stage)."
        ),
    )
    ball_detector_mode: Optional[str] = Field(
        default=None,
        description="Override the game's ball detector mode for this run: auto|tracknet|yolo.",
    )
    emit_layers: bool = Field(
        default=False,
        description="Also export toggleable pose/ball overlay layers (canvas player). Adds a JSON output.",
    )
