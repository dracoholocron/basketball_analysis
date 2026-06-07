"""Game event CRUD endpoints for live game tracking."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import require_role
from ..models.game_event import GameEvent
from ..models.matchup import Matchup
from ..models.simulation import GameSimulation, KeyToVictory
from ..services import simulation as sim_engine

router = APIRouter(tags=["game_events"])

_staff = require_role("admin", "coach")


class GameEventCreate(BaseModel):
    event_type: str
    team: int
    points: int = 0
    x_pct: float | None = None
    y_pct: float | None = None
    player_name: str | None = None
    player_jersey: str | None = None
    period: int | None = None
    game_time_seconds: int | None = None
    parent_event_id: uuid.UUID | None = None
    game_id: uuid.UUID | None = None


class GameEventRead(BaseModel):
    id: uuid.UUID
    matchup_id: uuid.UUID
    game_id: uuid.UUID | None
    parent_event_id: uuid.UUID | None
    event_type: str
    team: int
    points: int
    x_pct: float | None
    y_pct: float | None
    player_name: str | None
    player_jersey: str | None
    period: int | None
    game_time_seconds: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LiveKeyStatus(BaseModel):
    key_id: str
    title: str
    live_status: str
    description: str | None = None


@router.post(
    "/matchups/{matchup_id}/events",
    response_model=GameEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_event(
    matchup_id: uuid.UUID,
    payload: GameEventCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    matchup = await db.get(Matchup, matchup_id)
    if matchup is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    event = GameEvent(
        matchup_id=matchup_id,
        game_id=payload.game_id,
        parent_event_id=payload.parent_event_id,
        event_type=payload.event_type,
        team=payload.team,
        points=payload.points,
        x_pct=payload.x_pct,
        y_pct=payload.y_pct,
        player_name=payload.player_name,
        player_jersey=payload.player_jersey,
        period=payload.period,
        game_time_seconds=payload.game_time_seconds,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("/matchups/{matchup_id}/events", response_model=List[GameEventRead])
async def list_events(
    matchup_id: uuid.UUID,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    matchup = await db.get(Matchup, matchup_id)
    if matchup is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    result = await db.execute(
        select(GameEvent)
        .where(GameEvent.matchup_id == matchup_id)
        .order_by(GameEvent.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.delete(
    "/matchups/{matchup_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_event(
    matchup_id: uuid.UUID,
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    event = await db.get(GameEvent, event_id)
    if event is None or event.matchup_id != matchup_id:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)
    await db.commit()


@router.get("/matchups/{matchup_id}/live-keys-status", response_model=List[LiveKeyStatus])
async def get_live_keys_status(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Return live status of Keys to Victory based on current game events."""
    # Get latest simulation keys
    sim_result = await db.execute(
        select(GameSimulation)
        .where(GameSimulation.matchup_id == matchup_id)
        .options(selectinload(GameSimulation.keys))
        .order_by(GameSimulation.created_at.desc())
        .limit(1)
    )
    sim = sim_result.scalar_one_or_none()
    if sim is None:
        return []

    # Get current game events
    events_result = await db.execute(
        select(GameEvent)
        .where(GameEvent.matchup_id == matchup_id)
        .order_by(GameEvent.created_at.asc())
    )
    events = events_result.scalars().all()

    # Compute live stats from events for team 1 (our team)
    own_events = [e for e in events if e.team == 1]
    made_shots = sum(1 for e in own_events if e.event_type in ("2pt_made", "3pt_made"))
    made_3s = sum(1 for e in own_events if e.event_type == "3pt_made")
    total_shot_attempts = sum(1 for e in own_events if e.event_type in ("2pt_made", "3pt_made", "missed"))
    turnovers = sum(1 for e in own_events if e.event_type == "turnover")
    rebounds = sum(1 for e in own_events if e.event_type == "rebound")
    total_possessions = max(1, total_shot_attempts + turnovers)

    live_fg_pct = made_shots / total_shot_attempts if total_shot_attempts > 0 else None
    live_fg3_pct = made_3s / max(1, round(total_shot_attempts * 0.35)) if total_shot_attempts > 0 else None
    live_tov_rate = turnovers / total_possessions if total_possessions > 0 else None
    live_oreb_rate = rebounds / total_possessions if total_possessions > 0 else None

    live_stats = {
        "own_fg_pct": live_fg_pct,
        "own_fg3_pct": live_fg3_pct,
        "own_tov_rate": live_tov_rate,
        "own_oreb_rate": live_oreb_rate,
    }

    statuses = []
    for key in sim.keys:
        if not key.feature_name or key.coefficient is None:
            # No logistic data — use generic on_track
            statuses.append(LiveKeyStatus(
                key_id=str(key.id),
                title=key.title,
                live_status=key.live_status or "on_track",
                description=key.description,
            ))
            continue

        live_val = live_stats.get(key.feature_name)
        if live_val is None or len(events) < 5:
            live_status = "on_track"
        else:
            mean = key.feature_mean or 0.0
            std = key.feature_std or 1.0
            coef = key.coefficient

            # Compute z-score of current live performance vs expected mean
            z = (live_val - mean) / std
            # If coef is positive, higher is better; if negative, lower is better
            z_weighted = z * (1 if coef > 0 else -1)

            if z_weighted > 0.5:
                live_status = "good"
            elif z_weighted > -0.5:
                live_status = "on_track"
            else:
                live_status = "at_risk"

        # Persist live_status to DB
        key.live_status = live_status
        statuses.append(LiveKeyStatus(
            key_id=str(key.id),
            title=key.title,
            live_status=live_status,
            description=key.description,
        ))

    await db.commit()
    return statuses


@router.get("/matchups/{matchup_id}/event-heatmap", response_model=dict)
async def get_event_heatmap(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Return heat-grid (10x6 zones) and aggregate stats from game events."""
    matchup = await db.get(Matchup, matchup_id)
    if matchup is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    events_result = await db.execute(
        select(GameEvent)
        .where(GameEvent.matchup_id == matchup_id)
        .order_by(GameEvent.created_at.asc())
    )
    events = events_result.scalars().all()

    # Build 10 rows × 6 cols heat grid (counts of shots in zone)
    grid: list[list[int]] = [[0] * 6 for _ in range(10)]
    blocks = steals = fouls = total_shots = made_shots = 0

    for ev in events:
        et = ev.event_type
        if et == "block":
            blocks += 1
        elif et == "steal":
            steals += 1
        elif et == "foul":
            fouls += 1

        if et in ("2pt_made", "3pt_made", "missed") and ev.x_pct is not None and ev.y_pct is not None:
            total_shots += 1
            if et in ("2pt_made", "3pt_made"):
                made_shots += 1
            col = min(5, int(ev.x_pct * 6))
            row = min(9, int(ev.y_pct * 10))
            grid[row][col] += 1

    return {
        "heat_grid": grid,
        "blocks": blocks,
        "steals": steals,
        "fouls": fouls,
        "total_shots": total_shots,
        "made_shots": made_shots,
        "fg_pct": round(made_shots / total_shots, 3) if total_shots > 0 else 0.0,
        "event_count": len(events),
    }


@router.post("/matchups/{matchup_id}/halftime-resim", response_model=dict)
async def halftime_resim(
    matchup_id: uuid.UUID,
    coach_mode: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Re-run Monte Carlo simulation using first-half real stats.

    Fetches game events from the current session, derives team stats,
    and runs a fresh 500-game simulation for the second half.
    Updates KeyToVictory live_status based on new probabilities.
    """
    matchup = await db.get(Matchup, matchup_id)
    if matchup is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    # Get all events so far
    events_result = await db.execute(
        select(GameEvent)
        .where(GameEvent.matchup_id == matchup_id)
        .order_by(GameEvent.created_at.asc())
    )
    events = events_result.scalars().all()

    if not events:
        raise HTTPException(status_code=400, detail="No game events yet — play some events before halftime resim")

    # Build stats from events for each team
    def _team_stats_from_events(evs: list[GameEvent]) -> dict:
        made_2 = sum(1 for e in evs if e.event_type == "2pt_made")
        made_3 = sum(1 for e in evs if e.event_type == "3pt_made")
        ft_made = sum(1 for e in evs if e.event_type == "ft_made")
        missed = sum(1 for e in evs if e.event_type == "missed")
        tov = sum(1 for e in evs if e.event_type == "turnover")
        reb = sum(1 for e in evs if e.event_type == "rebound")
        total_fga = made_2 + made_3 + missed
        # Project to full-game (× 2 for halftime data)
        return {
            "avg_fgm": (made_2 + made_3) * 2,
            "avg_fga": total_fga * 2 or 40,
            "avg_fg3m": made_3 * 2,
            "avg_fg3a": max(1, round(total_fga * 0.35)) * 2,
            "avg_ftm": ft_made * 2,
            "avg_fta": max(1, round(ft_made * 1.1)) * 2,
            "avg_tov": tov * 2,
            "avg_reb": reb * 2,
        }

    own_evs = [e for e in events if e.team == 1]
    opp_evs = [e for e in events if e.team == 2]
    own_stats = _team_stats_from_events(own_evs)
    opp_stats = _team_stats_from_events(opp_evs)

    # Run smaller sim for halftime
    results = sim_engine.run_monte_carlo(own_stats, opp_stats, n_runs=500)

    # Get latest simulation and update its win pct
    sim_result = await db.execute(
        select(GameSimulation)
        .where(GameSimulation.matchup_id == matchup_id)
        .options(selectinload(GameSimulation.keys))
        .order_by(GameSimulation.created_at.desc())
        .limit(1)
    )
    sim = sim_result.scalar_one_or_none()

    old_win_pct = sim.win_pct_own if sim else 0.5
    if sim:
        sim.win_pct_own = results["win_pct_own"]
        sim.win_pct_opp = results["win_pct_opp"]
        sim.base_log_odds = results["base_log_odds"]
        await db.commit()

    # Generate LLM halftime adjustments
    win_pct_change = results["win_pct_own"] - old_win_pct
    pre_game_keys = [{"title": k.title, "description": k.description} for k in (sim.keys if sim else [])]
    try:
        from ..services.llm import generate_halftime_adjustments as llm_halftime
        adjustments = await llm_halftime(
            pre_game_keys=pre_game_keys,
            h1_stats=own_stats,
            h2_projected=own_stats,  # reuse as projection
            win_pct_change=win_pct_change,
            coach_mode=coach_mode,
        )
    except Exception:
        adjustments = []

    # Persist halftime adjustments to matchup
    if adjustments:
        matchup.halftime_adjustments = adjustments
        await db.commit()

    return {
        "win_pct_own": round(results["win_pct_own"], 4),
        "win_pct_opp": round(results["win_pct_opp"], 4),
        "avg_score_own": round(results["avg_score_own"], 1),
        "avg_score_opp": round(results["avg_score_opp"], 1),
        "n_runs": results["n_runs"],
        "adjustments": adjustments,
        "message": "Halftime simulation complete — win probability updated",
    }
