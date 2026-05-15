from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PlayerCreate(BaseModel):
    team_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    jersey_number: int | None = None
    track_id: int | None = None


class PlayerRead(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    jersey_number: int | None
    track_id: int | None

    model_config = {"from_attributes": True}
