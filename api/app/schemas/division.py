from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class DivisionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    category: str | None = Field(None, max_length=40)   # U12|U14|U15|U18_mixto|...
    season_id: uuid.UUID | None = None


class DivisionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    category: str | None = Field(None, max_length=40)
    season_id: uuid.UUID | None = None


class DivisionRead(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    category: str | None
    season_id: uuid.UUID | None
    player_count: int = 0

    model_config = {"from_attributes": True}
