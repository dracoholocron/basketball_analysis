from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SeasonCreate(BaseModel):
    organization_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=100)
    year: str | None = Field(None, max_length=20)


class SeasonRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    year: str | None

    model_config = {"from_attributes": True}
