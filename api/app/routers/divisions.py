"""CRUD for team divisions (age groups) + player↔division assignment (M2M).

Divisions are additive groups within a team; a player can belong to several. The
player's club is still Player.team_id. Routes are split between team-scoped
(`/teams/{id}/divisions`) and division-scoped (`/divisions/...`).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.division import Division, player_divisions
from ..models.player import Player
from ..models.team import Team
from ..schemas.division import DivisionCreate, DivisionRead, DivisionUpdate
from ..schemas.player import PlayerRead

router = APIRouter(tags=["divisions"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")


async def _team_or_404(db: AsyncSession, team_id: uuid.UUID, org_id: uuid.UUID | None) -> Team:
    team = await db.get(Team, team_id)
    if team is None or (org_id is not None and team.organization_id != org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


async def _division_or_404(db: AsyncSession, division_id: uuid.UUID, org_id: uuid.UUID | None) -> Division:
    div = await db.get(Division, division_id)
    if div is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Division not found")
    if org_id is not None:
        team = await db.get(Team, div.team_id)
        if team is None or team.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Division not found")
    return div


def _to_read(div: Division, player_count: int) -> DivisionRead:
    return DivisionRead(
        id=div.id, team_id=div.team_id, name=div.name,
        category=div.category, season_id=div.season_id, player_count=player_count,
    )


@router.get("/teams/{team_id}/divisions", response_model=list[DivisionRead])
async def list_team_divisions(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    await _team_or_404(db, team_id, org_id)
    divs = (await db.execute(
        select(Division).where(Division.team_id == team_id).order_by(Division.name)
    )).scalars().all()
    # player counts per division in one query
    counts = dict((await db.execute(
        select(player_divisions.c.division_id, func.count())
        .where(player_divisions.c.division_id.in_([d.id for d in divs] or [uuid.uuid4()]))
        .group_by(player_divisions.c.division_id)
    )).all())
    return [_to_read(d, int(counts.get(d.id, 0))) for d in divs]


@router.post("/teams/{team_id}/divisions", response_model=DivisionRead,
             status_code=status.HTTP_201_CREATED)
async def create_division(
    team_id: uuid.UUID,
    payload: DivisionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    await _team_or_404(db, team_id, org_id)
    div = Division(
        team_id=team_id, name=payload.name,
        category=payload.category, season_id=payload.season_id,
    )
    db.add(div)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A division with that name already exists for this team")
    await db.refresh(div)
    return _to_read(div, 0)


@router.put("/divisions/{division_id}", response_model=DivisionRead)
async def update_division(
    division_id: uuid.UUID,
    payload: DivisionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    div = await _division_or_404(db, division_id, org_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(div, field, value)
    await db.commit()
    await db.refresh(div)
    count = (await db.execute(
        select(func.count()).where(player_divisions.c.division_id == division_id)
    )).scalar() or 0
    return _to_read(div, int(count))


@router.delete("/divisions/{division_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_division(
    division_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    div = await _division_or_404(db, division_id, org_id)
    await db.delete(div)
    await db.commit()


@router.get("/divisions/{division_id}/players", response_model=list[PlayerRead])
async def list_division_players(
    division_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    await _division_or_404(db, division_id, org_id)
    div = (await db.execute(
        select(Division).where(Division.id == division_id).options(selectinload(Division.players))
    )).scalar_one()
    return sorted(div.players, key=lambda p: p.name)


@router.post("/divisions/{division_id}/players/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_player(
    division_id: uuid.UUID,
    player_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    await _division_or_404(db, division_id, org_id)
    if await db.get(Player, player_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    exists = (await db.execute(
        select(player_divisions).where(
            player_divisions.c.division_id == division_id,
            player_divisions.c.player_id == player_id,
        )
    )).first()
    if not exists:
        await db.execute(player_divisions.insert().values(
            division_id=division_id, player_id=player_id))
        await db.commit()


@router.delete("/divisions/{division_id}/players/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_player(
    division_id: uuid.UUID,
    player_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    await _division_or_404(db, division_id, org_id)
    await db.execute(player_divisions.delete().where(
        player_divisions.c.division_id == division_id,
        player_divisions.c.player_id == player_id,
    ))
    await db.commit()


@router.get("/players/{player_id}/divisions", response_model=list[DivisionRead])
async def list_player_divisions(
    player_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    player = (await db.execute(
        select(Player).where(Player.id == player_id).options(selectinload(Player.divisions))
    )).scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    return [_to_read(d, 0) for d in sorted(player.divisions, key=lambda d: d.name)]
