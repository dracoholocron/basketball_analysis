"""CRUD endpoints for Season."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role
from ..models.season import Season
from ..schemas.season import SeasonCreate, SeasonRead

router = APIRouter(prefix="/seasons", tags=["seasons"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")


@router.get("", response_model=list[SeasonRead])
async def list_seasons(
    organization_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    q = select(Season).order_by(Season.year.desc(), Season.name)
    if organization_id is not None:
        q = q.where(Season.organization_id == organization_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{season_id}", response_model=SeasonRead)
async def get_season(
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    season = await db.get(Season, season_id)
    if season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    return season


@router.post("", response_model=SeasonRead, status_code=status.HTTP_201_CREATED)
async def create_season(
    payload: SeasonCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    season = Season(
        organization_id=payload.organization_id,
        name=payload.name,
        year=payload.year,
    )
    db.add(season)
    await db.commit()
    await db.refresh(season)
    return season
