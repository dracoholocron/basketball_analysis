from __future__ import annotations
import uuid
from typing import Optional
from pydantic import BaseModel


class PlayerMetricRead(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    track_id: int
    display_label: Optional[str] = None
    team_id: Optional[int]
    total_distance_m: float
    avg_speed_kmh: float
    max_speed_kmh: float
    possession_frames: int
    passes_made: int
    interceptions_made: int

    model_config = {"from_attributes": True}


class GameMetrics(BaseModel):
    game_id: uuid.UUID
    job_id: uuid.UUID
    total_frames: int
    team1_possession_pct: float
    team2_possession_pct: float
    team1_passes: int
    team2_passes: int
    team1_interceptions: int
    team2_interceptions: int
    players: list[PlayerMetricRead]
