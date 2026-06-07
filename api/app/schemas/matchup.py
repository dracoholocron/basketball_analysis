from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class MatchupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    own_team_id: uuid.UUID | None = None
    opponent_team_id: uuid.UUID | None = None
    season_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    game_date: date | None = None
    scheduled_at: datetime | None = None
    game_config: dict | None = None


class MatchupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    game_date: date | None = None
    scheduled_at: datetime | None = None
    status: str | None = None
    notes: dict | None = None
    game_config: dict | None = None


class MatchupRead(BaseModel):
    id: uuid.UUID
    name: str
    own_team_id: uuid.UUID | None
    opponent_team_id: uuid.UUID | None
    season_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    game_date: date | None
    scheduled_at: datetime | None
    status: str
    notes: dict | None
    game_config: dict | None
    clock_state: dict | None
    halftime_adjustments: list | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchupNotesUpdate(BaseModel):
    notes: dict


class ClockAction(BaseModel):
    action: str  # "start" | "pause" | "reset" | "advance_period" | "set_time"
    time_seconds: int | None = None


class TimeoutAction(BaseModel):
    team: int  # 1 or 2
    delta: int = 1  # +1 or -1


class PrepStatusStep(BaseModel):
    id: str
    name: str
    complete: bool
    link: str


class PrepStatusRead(BaseModel):
    matchup_id: uuid.UUID
    matchup_name: str
    steps: list[PrepStatusStep]
    win_probability_us: float | None
    progress_pct: int
