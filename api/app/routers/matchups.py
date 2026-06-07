"""Matchup CRUD endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.box_score import BoxScore
from ..models.game_event import GameEvent
from ..models.matchup import Matchup
from ..models.play import Play
from ..models.simulation import GameSimulation, KeyToVictory
from ..models.team import Team
from ..schemas.matchup import (
    ClockAction, MatchupCreate, MatchupRead, MatchupUpdate, MatchupNotesUpdate,
    PrepStatusRead, PrepStatusStep, TimeoutAction,
)

router = APIRouter(prefix="/matchups", tags=["matchups"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")


@router.get("", response_model=list[MatchupRead])
async def list_matchups(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    q = select(Matchup).order_by(Matchup.created_at.desc()).offset(skip).limit(limit)
    if org_id is not None:
        # Filter matchups by org via own_team join
        q = (
            select(Matchup)
            .join(Team, Matchup.own_team_id == Team.id)
            .where(Team.organization_id == org_id)
            .order_by(Matchup.created_at.desc())
            .offset(skip).limit(limit)
        )
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/upcoming", response_model=list[MatchupRead])
async def get_upcoming_matchups_head(
    limit: int = 3,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    """Return next N matchups by scheduled_at date (registered before /{id} to avoid UUID conflict)."""
    now = datetime.now(timezone.utc)
    q = (
        select(Matchup)
        .where(Matchup.scheduled_at >= now)
        .order_by(Matchup.scheduled_at.asc())
        .limit(limit)
    )
    if org_id is not None:
        q = (
            select(Matchup)
            .join(Team, Matchup.own_team_id == Team.id)
            .where(Team.organization_id == org_id)
            .where(Matchup.scheduled_at >= now)
            .order_by(Matchup.scheduled_at.asc())
            .limit(limit)
        )
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{matchup_id}", response_model=MatchupRead)
async def get_matchup(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matchup not found")
    return m


@router.post("", response_model=MatchupRead, status_code=status.HTTP_201_CREATED)
async def create_matchup(
    payload: MatchupCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    m = Matchup(**payload.model_dump())
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


@router.put("/{matchup_id}", response_model=MatchupRead)
async def update_matchup(
    matchup_id: uuid.UUID,
    payload: MatchupUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matchup not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(m, field, value)
    await db.commit()
    await db.refresh(m)
    return m


@router.patch("/{matchup_id}/notes", response_model=MatchupRead)
async def update_matchup_notes(
    matchup_id: uuid.UUID,
    payload: MatchupNotesUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matchup not found")
    m.notes = payload.notes
    await db.commit()
    await db.refresh(m)
    return m


@router.delete("/{matchup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_matchup(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matchup not found")
    await db.delete(m)
    await db.commit()


@router.patch("/{matchup_id}/clock", response_model=MatchupRead)
async def update_clock(
    matchup_id: uuid.UUID,
    payload: ClockAction,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Manage game clock state: start, pause, reset, advance_period, set_time."""
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    config = m.game_config or {}
    mins = config.get("mins_per_period", 20)
    total_secs = mins * 60

    state = dict(m.clock_state or {})
    if not state:
        state = {
            "period": 1,
            "time_remaining_seconds": total_secs,
            "is_paused": True,
            "started_at": None,
            "timeouts_used_team1": 0,
            "timeouts_used_team2": 0,
        }

    action = payload.action
    now_iso = datetime.now(timezone.utc).isoformat()

    if action == "start":
        state["is_paused"] = False
        state["started_at"] = now_iso
    elif action == "pause":
        state["is_paused"] = True
    elif action == "reset":
        state["is_paused"] = True
        state["time_remaining_seconds"] = total_secs
        state["period"] = 1
    elif action == "advance_period":
        state["period"] = state.get("period", 1) + 1
        state["time_remaining_seconds"] = total_secs
        state["is_paused"] = True
    elif action == "set_time":
        if payload.time_seconds is None:
            raise HTTPException(status_code=422, detail="time_seconds required for set_time")
        state["time_remaining_seconds"] = payload.time_seconds
    else:
        raise HTTPException(status_code=422, detail=f"Unknown clock action: {action}")

    m.clock_state = state
    await db.commit()
    await db.refresh(m)
    return m


@router.patch("/{matchup_id}/timeouts", response_model=MatchupRead)
async def update_timeouts(
    matchup_id: uuid.UUID,
    payload: TimeoutAction,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Increment or decrement timeout usage for a team."""
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    state = dict(m.clock_state or {})
    if not state:
        state = {"timeouts_used_team1": 0, "timeouts_used_team2": 0}

    key = f"timeouts_used_team{payload.team}"
    if key not in state:
        state[key] = 0
    state[key] = max(0, state[key] + payload.delta)

    m.clock_state = state
    await db.commit()
    await db.refresh(m)
    return m



@router.get("/{matchup_id}/prep-status", response_model=PrepStatusRead)
async def get_prep_status(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Return the 5-step weekly rhythm prep status for a matchup."""
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    mid = str(matchup_id)

    # Step 1: Stats uploaded — any BoxScore linked to teams in this matchup
    stats_complete = False
    if m.own_team_id or m.opponent_team_id:
        team_ids = [tid for tid in [m.own_team_id, m.opponent_team_id] if tid]
        bs_result = await db.execute(
            select(BoxScore).where(BoxScore.team_id.in_(team_ids)).limit(1)
        )
        stats_complete = bs_result.scalar_one_or_none() is not None

    # Step 2: Simulation run
    sim_result = await db.execute(
        select(GameSimulation)
        .where(GameSimulation.matchup_id == matchup_id)
        .order_by(GameSimulation.created_at.desc())
        .limit(1)
    )
    sim = sim_result.scalar_one_or_none()
    sim_complete = sim is not None

    # Step 3: Top 3 keys identified
    priorities_complete = False
    win_prob: float | None = None
    if sim:
        win_prob = sim.win_pct_own
        keys_result = await db.execute(
            select(KeyToVictory)
            .where(KeyToVictory.simulation_id == sim.id)
            .where(KeyToVictory.is_priority == True)  # noqa: E712
        )
        priority_keys = keys_result.scalars().all()
        priorities_complete = len(priority_keys) >= 3

    # Step 4: Plays linked to matchup
    plays_result = await db.execute(
        select(Play).where(Play.linked_matchup_id == matchup_id).limit(1)
    )
    plays_complete = plays_result.scalar_one_or_none() is not None

    # Step 5: Tracker ready (has events OR clock initialized)
    events_result = await db.execute(
        select(GameEvent).where(GameEvent.matchup_id == matchup_id).limit(1)
    )
    has_events = events_result.scalar_one_or_none() is not None
    clock_initialized = bool(m.clock_state)
    tracker_complete = has_events or clock_initialized

    steps = [
        PrepStatusStep(
            id="stats", name="Stats Uploaded", complete=stats_complete,
            link=f"/admin/box-scores?team={m.own_team_id}"
        ),
        PrepStatusStep(
            id="sim", name="Simulation Run", complete=sim_complete,
            link=f"/game-day?matchup={mid}"
        ),
        PrepStatusStep(
            id="priorities", name="Top 3 Keys Identified", complete=priorities_complete,
            link=f"/game-day?matchup={mid}"
        ),
        PrepStatusStep(
            id="plays", name="Plays Linked", complete=plays_complete,
            link=f"/play-builder?matchup={mid}"
        ),
        PrepStatusStep(
            id="tracker", name="Game Tracker Ready", complete=tracker_complete,
            link=f"/game-tracker?matchup={mid}"
        ),
    ]

    completed_count = sum(1 for s in steps if s.complete)
    progress_pct = (completed_count * 100) // len(steps)

    return PrepStatusRead(
        matchup_id=matchup_id,
        matchup_name=m.name,
        steps=steps,
        win_probability_us=win_prob,
        progress_pct=progress_pct,
    )
