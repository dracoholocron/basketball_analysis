from __future__ import annotations
import uuid
from typing import Optional
from pydantic import BaseModel


class PlayerMetricRead(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    track_id: int
    display_label: Optional[str] = None
    jersey_number: Optional[str] = None
    player_id: Optional[uuid.UUID] = None
    team_id: Optional[int]
    minutes_played: float = 0.0
    total_distance_m: float
    avg_speed_kmh: float
    max_speed_kmh: float
    possession_frames: int
    passes_made: int
    interceptions_made: int
    shots_attempted: int = 0
    shots_made: int = 0
    shots_missed: int = 0
    rebounds: int = 0
    steals_cv: int = 0

    model_config = {"from_attributes": True}


class GameMetrics(BaseModel):
    game_id: uuid.UUID
    job_id: uuid.UUID
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    total_frames: int
    team1_possession_pct: float
    team2_possession_pct: float
    team1_passes: int
    team2_passes: int
    team1_interceptions: int
    team2_interceptions: int
    team1_shots_attempted: int = 0
    team2_shots_attempted: int = 0
    team1_rebounds: int = 0
    team2_rebounds: int = 0
    team1_steals_cv: int = 0
    team2_steals_cv: int = 0
    players: list[PlayerMetricRead]
