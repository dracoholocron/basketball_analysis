"""CRUD endpoints for Player."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.player import Player
from ..models.team import Team
from ..schemas.player import PlayerCreate, PlayerRead, PlayerUpdate

router = APIRouter(prefix="/players", tags=["players"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")


@router.get("", response_model=list[PlayerRead])
async def list_players(
    team_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    q = select(Player).order_by(Player.name)
    if team_id is not None:
        q = q.where(Player.team_id == team_id)
    elif org_id is not None:
        # Filter players by org via team join
        q = q.join(Team, Player.team_id == Team.id).where(Team.organization_id == org_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{player_id}", response_model=PlayerRead)
async def get_player(
    player_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    return player


@router.post("", response_model=PlayerRead, status_code=status.HTTP_201_CREATED)
async def create_player(
    payload: PlayerCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    player = Player(
        team_id=payload.team_id,
        name=payload.name,
        jersey_number=payload.jersey_number,
        position=payload.position,
        track_id=payload.track_id,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@router.put("/{player_id}", response_model=PlayerRead)
async def update_player(
    player_id: uuid.UUID,
    payload: PlayerUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(player, field, value)
    await db.commit()
    await db.refresh(player)
    return player


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(
    player_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    await db.delete(player)
    await db.commit()
