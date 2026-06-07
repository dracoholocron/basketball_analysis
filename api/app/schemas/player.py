from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PlayerCreate(BaseModel):
    team_id: uuid.UUID | None = None
    name: str = Field(..., min_length=1, max_length=255)
    jersey_number: str | None = Field(None, max_length=10)
    position: str | None = Field(None, max_length=10)
    track_id: int | None = None


class PlayerUpdate(BaseModel):
    team_id: uuid.UUID | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    jersey_number: str | None = Field(None, max_length=10)
    position: str | None = Field(None, max_length=10)
    track_id: int | None = None


class PlayerRead(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID | None
    name: str
    jersey_number: str | None
    position: str | None
    track_id: int | None

    model_config = {"from_attributes": True}
