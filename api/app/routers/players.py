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
from ..models.metrics import PlayerMetric
from ..models.player_game_stats import PlayerGameStats
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


@router.get("/{player_id}/aggregate-metrics")
async def aggregate_player_metrics(
    player_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Career aggregates for an athlete across all analyzed jobs/games.

    Sums PlayerMetric rows mapped to this player (via jersey OCR consolidation),
    feeding historical analysis and future simulations. Counting stats are summed;
    speed is averaged over games where the player appears.
    """
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")

    result = await db.execute(
        select(PlayerMetric).where(PlayerMetric.player_id == player_id)
    )
    rows = result.scalars().all()
    games = len(rows)
    avg_speeds = [r.avg_speed_kmh for r in rows if r.avg_speed_kmh and r.avg_speed_kmh > 0]
    return {
        "player_id": str(player_id),
        "name": player.name,
        "jersey_number": player.jersey_number,
        "games_analyzed": games,
        "minutes_played": round(sum(r.minutes_played or 0.0 for r in rows), 1),
        "total_distance_m": round(sum(r.total_distance_m or 0.0 for r in rows), 1),
        "avg_speed_kmh": round(sum(avg_speeds) / len(avg_speeds), 2) if avg_speeds else 0.0,
        "max_speed_kmh": round(max((r.max_speed_kmh or 0.0 for r in rows), default=0.0), 2),
        "possession_frames": sum(r.possession_frames or 0 for r in rows),
        "passes_made": sum(r.passes_made or 0 for r in rows),
        "interceptions_made": sum(r.interceptions_made or 0 for r in rows),
        "shots_attempted": sum(r.shots_attempted or 0 for r in rows),
        "rebounds": sum(r.rebounds or 0 for r in rows),
        "steals_cv": sum(r.steals_cv or 0 for r in rows),
        "per_game": {
            "shots_attempted": round(sum(r.shots_attempted or 0 for r in rows) / games, 2) if games else 0.0,
            "rebounds": round(sum(r.rebounds or 0 for r in rows) / games, 2) if games else 0.0,
            "distance_m": round(sum(r.total_distance_m or 0.0 for r in rows) / games, 1) if games else 0.0,
        },
    }


def _aggregate_pgs(rows: list[PlayerGameStats]) -> dict:
    """Aggregate a list of player_game_stats rows into season totals + per-game (derived
    FG% prefers box-score; falls back to CV makes/attempts)."""
    g = len(rows)
    def s(attr):
        return sum(getattr(r, attr) or 0 for r in rows)
    fgm, fga = s("fgm"), s("fga")
    fg3m, fg3a = s("fg3m"), s("fg3a")
    made_cv, att_cv = s("shots_made_cv"), s("shots_attempted_cv")
    pts = s("pts")
    avg_speeds = [r.avg_speed_kmh for r in rows if r.avg_speed_kmh and r.avg_speed_kmh > 0]
    return {
        "games": g,
        # box-score family (None-safe sums; 0 when no box scores imported)
        "pts": pts, "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a,
        "ftm": s("ftm"), "fta": s("fta"), "ast": s("ast"), "stl": s("stl"),
        "blk": s("blk"), "tov": s("tov"), "oreb": s("oreb"), "dreb": s("dreb"),
        "fg_pct": round(fgm / fga, 3) if fga else (round(made_cv / att_cv, 3) if att_cv else None),
        "fg3_pct": round(fg3m / fg3a, 3) if fg3a else None,
        "ppg": round(pts / g, 1) if g and pts else None,
        # cv/tracking family
        "minutes_played": round(s("minutes_played"), 1),
        "distance_m": round(s("distance_m"), 1),
        "avg_speed_kmh": round(sum(avg_speeds) / len(avg_speeds), 2) if avg_speeds else 0.0,
        "max_speed_kmh": round(max((r.max_speed_kmh or 0.0 for r in rows), default=0.0), 2),
        "shots_attempted_cv": att_cv, "shots_made_cv": made_cv,
        "shots_missed_cv": s("shots_missed_cv"),
        "fg_pct_cv": round(made_cv / att_cv, 3) if att_cv else None,
        "rebounds_cv": s("rebounds_cv"), "steals_cv": s("steals_cv"), "passes_cv": s("passes_cv"),
    }


@router.get("/{player_id}/stats")
async def player_stats(
    player_id: uuid.UUID,
    season_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Unified per-game stats + season aggregate for an athlete (box-score + CV).

    Reads player_game_stats. Optional season filter. Returns the seasons present,
    the aggregate for the (optionally filtered) set, and a per-game log.
    """
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")

    q = select(PlayerGameStats).where(PlayerGameStats.player_id == player_id)
    if season_id is not None:
        q = q.where(PlayerGameStats.season_id == season_id)
    rows = (await db.execute(q)).scalars().all()

    seasons = sorted({str(r.season_id) for r in rows if r.season_id})
    games = [
        {
            "game_id": str(r.game_id), "season_id": str(r.season_id) if r.season_id else None,
            "source": r.source, "minutes_played": round(r.minutes_played, 1),
            "pts": r.pts, "fgm": r.fgm, "fga": r.fga, "fg3m": r.fg3m, "fg3a": r.fg3a,
            "reb": (r.oreb or 0) + (r.dreb or 0) if (r.oreb is not None or r.dreb is not None) else None,
            "ast": r.ast, "stl": r.stl, "tov": r.tov,
            "distance_m": round(r.distance_m, 1), "max_speed_kmh": round(r.max_speed_kmh, 2),
            "shots_attempted_cv": r.shots_attempted_cv, "shots_made_cv": r.shots_made_cv,
            "rebounds_cv": r.rebounds_cv, "steals_cv": r.steals_cv,
        }
        for r in rows
    ]
    return {
        "player_id": str(player_id), "name": player.name,
        "jersey_number": player.jersey_number, "team_id": str(player.team_id) if player.team_id else None,
        "seasons": seasons,
        "aggregate": _aggregate_pgs(rows),
        "games": games,
    }


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
