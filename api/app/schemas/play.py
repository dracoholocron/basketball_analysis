from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlayCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = "quick_hitter"
    description: str | None = None
    svg_data: dict[str, Any] | None = None
    organization_id: uuid.UUID | None = None
    linked_matchup_id: uuid.UUID | None = None
    tags: list[str] | None = None
    pace: str | None = None
    shared: bool = False


class PlayUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    category: str | None = None
    description: str | None = None
    svg_data: dict[str, Any] | None = None
    svg_data_version: int | None = None
    linked_matchup_id: uuid.UUID | None = None
    tags: list[str] | None = None
    pace: str | None = None
    shared: bool | None = None


class PlayRead(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    description: str | None
    svg_data: dict[str, Any] | None
    svg_data_version: int
    tags: list[str] | None
    pace: str | None
    pdf_url: str | None
    is_template: bool
    shared: bool
    organization_id: uuid.UUID | None
    linked_matchup_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
