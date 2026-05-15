"""CRUD endpoints for Team."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role
from ..models.team import Team
from ..schemas.team import TeamCreate, TeamRead

router = APIRouter(prefix="/teams", tags=["teams"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")


@router.get("", response_model=list[TeamRead])
async def list_teams(
    organization_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    q = select(Team).order_by(Team.name)
    if organization_id is not None:
        q = q.where(Team.organization_id == organization_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    team = Team(
        organization_id=payload.organization_id,
        name=payload.name,
        jersey_description=payload.jersey_description,
        level=payload.level,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team
