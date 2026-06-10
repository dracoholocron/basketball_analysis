"""CRUD endpoints for Team."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.box_score import BoxScore
from ..models.game import Game
from ..models.player import Player
from ..models.player_game_stats import PlayerGameStats
from ..models.season import Season
from ..models.team import Team
from ..schemas.box_score import TeamAverages
from ..schemas.team import TeamCreate, TeamRead

router = APIRouter(prefix="/teams", tags=["teams"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")


@router.get("/{team_id}/stats")
async def team_stats(
    team_id: uuid.UUID,
    season_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Per-player season aggregates + team totals from player_game_stats (box-score
    + CV). Optional season filter. Powers the team profile page."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    q = select(PlayerGameStats).where(PlayerGameStats.team_id == team_id)
    if season_id is not None:
        q = q.where(PlayerGameStats.season_id == season_id)
    rows = (await db.execute(q)).scalars().all()

    # Player names for the roster table
    pres = await db.execute(select(Player).where(Player.team_id == team_id))
    name_by_id = {p.id: p for p in pres.scalars().all()}

    by_player: dict[uuid.UUID, list[PlayerGameStats]] = {}
    for r in rows:
        by_player.setdefault(r.player_id, []).append(r)

    def s(attr):
        return sum(getattr(r, attr) or 0 for r in rows)

    players_out = []
    for pid, prows in by_player.items():
        p = name_by_id.get(pid)
        gp = len(prows)
        pts = sum(x.pts or 0 for x in prows)
        fgm = sum(x.fgm or 0 for x in prows); fga = sum(x.fga or 0 for x in prows)
        mcv = sum(x.shots_made_cv or 0 for x in prows); acv = sum(x.shots_attempted_cv or 0 for x in prows)
        players_out.append({
            "player_id": str(pid),
            "name": p.name if p else "—",
            "jersey_number": p.jersey_number if p else None,
            "games": gp,
            "ppg": round(pts / gp, 1) if gp and pts else None,
            "minutes_played": round(sum(x.minutes_played or 0 for x in prows), 1),
            "distance_m": round(sum(x.distance_m or 0 for x in prows), 1),
            "fg_pct": round(fgm / fga, 3) if fga else (round(mcv / acv, 3) if acv else None),
            "shots_made_cv": mcv, "shots_attempted_cv": acv,
            "rebounds_cv": sum(x.rebounds_cv or 0 for x in prows),
            "steals_cv": sum(x.steals_cv or 0 for x in prows),
        })
    players_out.sort(key=lambda x: (-(x["minutes_played"] or 0)))

    games_count = len({r.game_id for r in rows})
    return {
        "team_id": str(team_id), "name": team.name,
        "seasons": sorted({str(r.season_id) for r in rows if r.season_id}),
        "games": games_count,
        "totals": {
            "pts": s("pts"), "fgm": s("fgm"), "fga": s("fga"),
            "distance_m": round(s("distance_m"), 1),
            "shots_made_cv": s("shots_made_cv"), "shots_attempted_cv": s("shots_attempted_cv"),
            "rebounds_cv": s("rebounds_cv"), "steals_cv": s("steals_cv"),
        },
        "players": players_out,
    }


@router.get("", response_model=list[TeamRead])
async def list_teams(
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    q = select(Team).order_by(Team.name)
    if org_id is not None:
        q = q.where(Team.organization_id == org_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    team = await db.get(Team, team_id)
    if team is None or (org_id is not None and team.organization_id != org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    # User's org always takes precedence — prevents cross-org team creation.
    # Fall back to payload.organization_id only for super-admins (org_id is None).
    resolved_org = org_id or payload.organization_id
    if resolved_org is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="organization_id is required",
        )
    team = Team(
        organization_id=resolved_org,
        name=payload.name,
        jersey_description=payload.jersey_description,
        level=payload.level,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


@router.put("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: uuid.UUID,
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    team = await db.get(Team, team_id)
    if team is None or (org_id is not None and team.organization_id != org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(team, field, value)
    await db.commit()
    await db.refresh(team)
    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    team = await db.get(Team, team_id)
    if team is None or (org_id is not None and team.organization_id != org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    await db.delete(team)
    await db.commit()


@router.get("/{team_id}/averages", response_model=TeamAverages)
async def get_team_averages(
    team_id: uuid.UUID,
    season_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Compute season averages from box scores."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    q = select(BoxScore).where(BoxScore.team_id == team_id)

    if season_id is not None:
        q = q.join(Game, BoxScore.game_id == Game.id).where(Game.season_id == season_id)

    result = await db.execute(q)
    scores = result.scalars().all()

    if not scores:
        return TeamAverages(
            team_id=team_id, season_id=season_id, games_played=0,
            avg_pts=0, avg_fgm=0, avg_fga=0, fg_pct=0,
            avg_fg3m=0, avg_fg3a=0, fg3_pct=0,
            avg_ftm=0, avg_fta=0, ft_pct=0,
            avg_reb=0, avg_ast=0, avg_stl=0, avg_blk=0, avg_tov=0,
        )

    n = len(scores)

    def avg(field: str) -> float:
        return sum(getattr(s, field) for s in scores) / n

    total_fga = sum(s.fga for s in scores)
    total_fgm = sum(s.fgm for s in scores)
    total_fg3a = sum(s.fg3a for s in scores)
    total_fg3m = sum(s.fg3m for s in scores)
    total_fta = sum(s.fta for s in scores)
    total_ftm = sum(s.ftm for s in scores)

    return TeamAverages(
        team_id=team_id,
        season_id=season_id,
        games_played=n,
        avg_pts=avg("pts"),
        avg_fgm=avg("fgm"),
        avg_fga=avg("fga"),
        fg_pct=total_fgm / total_fga if total_fga > 0 else 0,
        avg_fg3m=avg("fg3m"),
        avg_fg3a=avg("fg3a"),
        fg3_pct=total_fg3m / total_fg3a if total_fg3a > 0 else 0,
        avg_ftm=avg("ftm"),
        avg_fta=avg("fta"),
        ft_pct=total_ftm / total_fta if total_fta > 0 else 0,
        avg_reb=avg("oreb") + avg("dreb"),
        avg_ast=avg("ast"),
        avg_stl=avg("stl"),
        avg_blk=avg("blk"),
        avg_tov=avg("tov"),
    )
