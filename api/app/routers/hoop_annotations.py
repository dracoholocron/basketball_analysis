"""Hoop annotations router — manual rim/backboard boxes to improve shot counting."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, require_role
from ..models.game import Game
from ..models.hoop_annotation import HoopAnnotation
from ..models.user import User

router = APIRouter(tags=["hoop-annotations"])


class HoopBox(BaseModel):
    frame_t: float = 0.0
    bbox: list[float]            # [x1, y1, x2, y2] intrinsic video resolution
    kind: str = "rim"           # "rim" | "backboard"
    hoop_id: int = 0            # which physical hoop this box belongs to (0, 1, …)

    @field_validator("bbox")
    @classmethod
    def _validate_bbox(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError("bbox must be [x1, y1, x2, y2]")
        return v


class HoopAnnotationUpdate(BaseModel):
    hoops: list[HoopBox]


class HoopAnnotationRead(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    hoops: Optional[list] = None

    model_config = {"from_attributes": True}


@router.get("/games/{game_id}/hoop-annotation", response_model=HoopAnnotationRead | None)
async def get_hoop_annotation(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HoopAnnotation).where(HoopAnnotation.game_id == game_id)
    )
    return result.scalar_one_or_none()


@router.put("/games/{game_id}/hoop-annotation", response_model=HoopAnnotationRead)
async def upsert_hoop_annotation(
    game_id: uuid.UUID,
    payload: HoopAnnotationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin", "coach")),
):
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    result = await db.execute(
        select(HoopAnnotation).where(HoopAnnotation.game_id == game_id)
    )
    ann = result.scalar_one_or_none()
    hoops_data = [h.model_dump() for h in payload.hoops]

    if ann is None:
        ann = HoopAnnotation(game_id=game_id, hoops=hoops_data)
        db.add(ann)
    else:
        ann.hoops = hoops_data

    await db.commit()
    await db.refresh(ann)
    return ann
