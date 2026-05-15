from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class JobStatus(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    status: str
    current_stage: str
    progress_pct: int
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    output_s3_key: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# Alias for import compatibility
JobRead = JobStatus
