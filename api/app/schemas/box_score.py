from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class PlayerBoxScoreCreate(BaseModel):
    player_id: uuid.UUID | None = None
    player_name: str | None = None
    jersey_number: str | None = None
    minutes_played: float | None = None
    pts: int = 0
    fgm: int = 0
    fga: int = 0
    fg3m: int = 0
    fg3a: int = 0
    ftm: int = 0
    fta: int = 0
    oreb: int = 0
    dreb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0
    pf: int = 0
    plus_minus: int | None = None


class PlayerBoxScoreRead(PlayerBoxScoreCreate):
    id: uuid.UUID
    box_score_id: uuid.UUID

    model_config = {"from_attributes": True}


class BoxScoreCreate(BaseModel):
    game_id: uuid.UUID
    team_id: uuid.UUID
    pts: int = 0
    fgm: int = 0
    fga: int = 0
    fg3m: int = 0
    fg3a: int = 0
    ftm: int = 0
    fta: int = 0
    oreb: int = 0
    dreb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0
    pf: int = 0
    players: list[PlayerBoxScoreCreate] = []


class BoxScoreRead(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    team_id: uuid.UUID
    pts: int
    fgm: int
    fga: int
    fg3m: int
    fg3a: int
    ftm: int
    fta: int
    oreb: int
    dreb: int
    ast: int
    stl: int
    blk: int
    tov: int
    pf: int
    created_at: datetime
    player_box_scores: list[PlayerBoxScoreRead] = []

    model_config = {"from_attributes": True}


class TeamAverages(BaseModel):
    team_id: uuid.UUID
    season_id: uuid.UUID | None
    games_played: int
    avg_pts: float
    avg_fgm: float
    avg_fga: float
    fg_pct: float
    avg_fg3m: float
    avg_fg3a: float
    fg3_pct: float
    avg_ftm: float
    avg_fta: float
    ft_pct: float
    avg_reb: float
    avg_ast: float
    avg_stl: float
    avg_blk: float
    avg_tov: float
