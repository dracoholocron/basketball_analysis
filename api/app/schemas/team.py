from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    organization_id: uuid.UUID | None = None
    name: str = Field(..., min_length=1, max_length=255)
    jersey_description: str | None = Field(None, max_length=255)
    level: str | None = Field(None, max_length=50)


class TeamRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    jersey_description: str | None
    level: str | None
    logo_url: str | None = None   # presigned URL, populated from logo_s3_key

    model_config = {"from_attributes": True}
