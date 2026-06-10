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
