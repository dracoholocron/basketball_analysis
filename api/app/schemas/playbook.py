from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PlaybookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class PlaybookUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None


class PlaybookRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    name: str
    description: str | None
    is_system: bool
    created_at: datetime
    play_count: int = 0

    model_config = {"from_attributes": True}
