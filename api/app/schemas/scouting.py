from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PlayerScoutingNoteRead(BaseModel):
    id: uuid.UUID
    player_id: uuid.UUID | None
    player_name: str | None
    summary: str | None
    is_mvp: bool
    mvp_rank: int | None

    model_config = {"from_attributes": True}


class ScoutingReportRead(BaseModel):
    id: uuid.UUID
    matchup_id: uuid.UUID
    generated_at: datetime
    model_used: str | None
    team_identity: str | None
    strengths: list[Any] | None
    weaknesses: list[Any] | None
    mvp_players: list[Any] | None
    game_keys_offensive: list[Any] | None
    game_keys_defensive: list[Any] | None
    coach_notes: str | None
    player_notes: list[PlayerScoutingNoteRead] = []

    model_config = {"from_attributes": True}


class CoachNotesUpdate(BaseModel):
    coach_notes: str
