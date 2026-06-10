"""Matchup CRUD endpoints."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.box_score import BoxScore
from ..models.game_event import GameEvent
from ..models.matchup import Matchup
from ..models.play import Play
from ..models.player_game_stats import PlayerGameStats
from ..models.scouting_report import ScoutingReport
from ..models.simulation import GameSimulation, KeyToVictory, SituationalAdjustment
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


# ── Pydantic schemas for new endpoints ────────────────────────────────────────

class ScoutingReportRead(BaseModel):
    id: uuid.UUID
    matchup_id: uuid.UUID
    generated_at: datetime
    model_used: str | None = None
    team_identity: str | None = None
    strengths: list | None = None
    weaknesses: list | None = None
    mvp_players: list | None = None
    game_keys_offensive: list | None = None
    game_keys_defensive: list | None = None
    coach_notes: str | None = None

    model_config = {"from_attributes": True}


class ScoutingNotesUpdate(BaseModel):
    coach_notes: str


class KeyToVictoryRead(BaseModel):
    id: uuid.UUID
    simulation_id: uuid.UUID
    title: str
    description: str | None = None
    target_metric: str | None = None
    target_value: float | None = None
    weight: float = 1.0
    coefficient: float | None = None
    feature_name: str | None = None
    is_priority: bool = False
    priority_rank: int | None = None
    live_status: str | None = None

    model_config = {"from_attributes": True}


class SimulationRead(BaseModel):
    id: uuid.UUID
    matchup_id: uuid.UUID
    n_runs: int
    win_pct_own: float
    win_pct_opp: float
    avg_score_own: float | None = None
    avg_score_opp: float | None = None
    score_range_own_low: float | None = None
    score_range_own_high: float | None = None
    score_range_opp_low: float | None = None
    score_range_opp_high: float | None = None
    key_drivers: dict | None = None
    base_log_odds: float | None = None
    created_at: datetime
    keys: list[KeyToVictoryRead] = []

    model_config = {"from_attributes": True}


class PriorityKeyUpdate(BaseModel):
    is_priority: bool
    priority_rank: int | None = None


# ── Helper: aggregate box scores for a team ───────────────────────────────────

async def _get_team_stats(db: AsyncSession, team_id: uuid.UUID) -> dict[str, Any]:
    """Return team stats for simulation: box-score shooting rates (authoritative)
    MERGED with CV-derived tempo/defense from player_game_stats. ``data_sources``
    records what fed the numbers (box_score / cv / both)."""
    result = await db.execute(
        select(BoxScore).where(BoxScore.team_id == team_id).order_by(BoxScore.created_at.desc()).limit(10)
    )
    scores = result.scalars().all()
    avgs: dict[str, Any] = {}
    if scores:
        n = len(scores)
        fields = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "ast", "stl", "blk", "tov"]
        for f in fields:
            total = sum(getattr(s, f, 0) or 0 for s in scores)
            avgs[f"avg_{f}"] = round(total / n, 2)
        avgs["games_played"] = n
        avgs["fg_pct"] = round(avgs["avg_fgm"] / avgs["avg_fga"], 3) if avgs.get("avg_fga", 0) > 0 else 0.0
        avgs["fg3_pct"] = round(avgs["avg_fg3m"] / avgs["avg_fg3a"], 3) if avgs.get("avg_fg3a", 0) > 0 else 0.0
        avgs["ft_pct"] = round(avgs["avg_ftm"] / avgs["avg_fta"], 3) if avgs.get("avg_fta", 0) > 0 else 0.0
        avgs["avg_reb"] = round(avgs.get("avg_oreb", 0) + avgs.get("avg_dreb", 0), 2)

    # ── CV/tracking aggregates from analyzed games (tempo + defensive pressure) ──
    cv_res = await db.execute(
        select(PlayerGameStats).where(PlayerGameStats.team_id == team_id)
    )
    cv_rows = cv_res.scalars().all()
    cv_game_ids = {r.game_id for r in cv_rows}
    if cv_game_ids:
        ng = len(cv_game_ids)
        team_steals = sum(r.steals_cv or 0 for r in cv_rows)
        team_shots = sum(r.shots_attempted_cv or 0 for r in cv_rows)
        team_made = sum(r.shots_made_cv or 0 for r in cv_rows)
        avgs["cv_games"] = ng
        avgs["cv_steals_pg"] = round(team_steals / ng, 2)
        avgs["cv_shots_pg"] = round(team_shots / ng, 2)
        # Defensive pressure → extra turnover probability inflicted on the OPPONENT.
        # Scaled & capped so CV defense nudges, not dominates, the box-score model.
        avgs["cv_def_pressure"] = round(min(0.06, (team_steals / ng) / 200.0), 4)
        # CV shooting (rim makes/attempts) — only used as fallback when no box score.
        if team_shots > 0:
            avgs["cv_fg_pct"] = round(team_made / team_shots, 3)
        # Pace proxy: shot attempts per game → possessions estimate when no box score.
        avgs["cv_possessions"] = round(team_shots / ng, 1) if ng else None

    avgs["data_sources"] = (
        "both" if (scores and cv_game_ids) else "box_score" if scores
        else "cv" if cv_game_ids else "none"
    )
    return avgs


# ── Scouting Report endpoints ──────────────────────────────────────────────────

@router.get("/{matchup_id}/scouting-report", response_model=ScoutingReportRead)
async def get_scouting_report(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Return the latest scouting report for a matchup."""
    result = await db.execute(
        select(ScoutingReport)
        .where(ScoutingReport.matchup_id == matchup_id)
        .order_by(ScoutingReport.generated_at.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="No scouting report found for this matchup")
    return report


@router.post("/{matchup_id}/scouting-report/generate", response_model=ScoutingReportRead)
async def generate_scouting_report(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Generate a new scouting report using LLM + team box score stats."""
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    # Fetch team names
    own_team = await db.get(Team, m.own_team_id) if m.own_team_id else None
    opp_team = await db.get(Team, m.opponent_team_id) if m.opponent_team_id else None

    own_stats = await _get_team_stats(db, m.own_team_id) if m.own_team_id else {}
    opp_stats = await _get_team_stats(db, m.opponent_team_id) if m.opponent_team_id else {}

    # Build a hash to detect if stats have changed
    stats_hash = hashlib.md5(json.dumps(opp_stats, sort_keys=True).encode()).hexdigest()

    from ..services.llm import generate_scouting_report as llm_generate
    content = await llm_generate(
        matchup_name=m.name,
        own_team_name=own_team.name if own_team else "Our Team",
        opponent_team_name=opp_team.name if opp_team else "Opponent",
        opponent_stats=opp_stats,
    )

    report = ScoutingReport(
        matchup_id=matchup_id,
        model_used=content.get("model_used", "llm"),
        team_identity=content.get("team_identity"),
        strengths=content.get("strengths", []),
        weaknesses=content.get("weaknesses", []),
        mvp_players=content.get("mvp_players", []),
        game_keys_offensive=content.get("game_keys_offensive", []),
        game_keys_defensive=content.get("game_keys_defensive", []),
        box_scores_hash=stats_hash,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


@router.patch("/scouting-reports/{report_id}/notes", response_model=ScoutingReportRead)
async def update_scouting_notes(
    report_id: uuid.UUID,
    payload: ScoutingNotesUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Update coach notes on a scouting report."""
    report = await db.get(ScoutingReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Scouting report not found")
    report.coach_notes = payload.coach_notes
    await db.commit()
    await db.refresh(report)
    return report


# ── Video Insights endpoint ────────────────────────────────────────────────────

@router.get("/{matchup_id}/video-insights", response_model=dict)
async def get_video_insights(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Return player-level video analysis metrics for both teams in a matchup."""
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    teams = [
        {"team_id": str(m.own_team_id), "team_role": "own"},
        {"team_id": str(m.opponent_team_id), "team_role": "opponent"},
    ] if m.own_team_id and m.opponent_team_id else []

    insights = []
    for t in teams:
        team_id = uuid.UUID(t["team_id"])
        # Use box score player data as proxy for video metrics
        bs_result = await db.execute(
            select(BoxScore)
            .options(selectinload(BoxScore.player_box_scores))
            .where(BoxScore.team_id == team_id)
            .order_by(BoxScore.created_at.desc())
            .limit(5)
        )
        box_scores = bs_result.scalars().all()

        # Aggregate player stats across games
        player_agg: dict[str, Any] = {}
        for bs in box_scores:
            for pbs in (bs.player_box_scores or []):
                name = pbs.player_name or "Unknown"
                if name not in player_agg:
                    player_agg[name] = {
                        "player_name": name,
                        "jersey_number": pbs.jersey_number,
                        "pts": 0, "ast": 0, "reb": 0, "stl": 0, "blk": 0,
                        "fgm": 0, "fga": 0, "games": 0,
                    }
                agg = player_agg[name]
                agg["pts"] += pbs.pts or 0
                agg["ast"] += pbs.ast or 0
                agg["reb"] += (pbs.oreb or 0) + (pbs.dreb or 0)
                agg["stl"] += pbs.stl or 0
                agg["blk"] += pbs.blk or 0
                agg["fgm"] += pbs.fgm or 0
                agg["fga"] += pbs.fga or 0
                agg["games"] += 1

        players = []
        for p in player_agg.values():
            g = p["games"] or 1
            players.append({
                "player_name": p["player_name"],
                "jersey_number": p.get("jersey_number"),
                "avg_pts": round(p["pts"] / g, 1),
                "avg_ast": round(p["ast"] / g, 1),
                "avg_reb": round(p["reb"] / g, 1),
                "avg_stl": round(p["stl"] / g, 1),
                "avg_blk": round(p["blk"] / g, 1),
                "fg_pct": round(p["fgm"] / p["fga"], 3) if p["fga"] > 0 else 0.0,
                "games": g,
            })
        players.sort(key=lambda x: x["avg_pts"], reverse=True)

        insights.append({"team_id": t["team_id"], "team_role": t["team_role"], "players": players})

    return {"insights": insights, "note": "Derived from box score data"}


# ── Simulation endpoint ────────────────────────────────────────────────────────

@router.get("/{matchup_id}/simulation", response_model=SimulationRead)
async def get_latest_simulation(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
) -> SimulationRead:
    """Return the most recent simulation for a matchup."""
    stmt = (
        select(GameSimulation)
        .where(GameSimulation.matchup_id == matchup_id)
        .options(selectinload(GameSimulation.keys))
        .order_by(GameSimulation.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="No simulation found for this matchup")
    return sim


@router.post("/{matchup_id}/simulate", response_model=SimulationRead)
async def run_simulation(
    matchup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Run Monte Carlo simulation for a matchup using team box score averages."""
    m = await db.get(Matchup, matchup_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Matchup not found")

    own_stats = await _get_team_stats(db, m.own_team_id) if m.own_team_id else {}
    opp_stats = await _get_team_stats(db, m.opponent_team_id) if m.opponent_team_id else {}

    from ..services.simulation import run_monte_carlo
    from ..services.llm import generate_keys_to_victory

    sim_result = run_monte_carlo(own_stats, opp_stats, n_runs=1000)

    sim = GameSimulation(
        matchup_id=matchup_id,
        n_runs=sim_result["n_runs"],
        win_pct_own=sim_result["win_pct_own"],
        win_pct_opp=sim_result["win_pct_opp"],
        avg_score_own=sim_result["avg_score_own"],
        avg_score_opp=sim_result["avg_score_opp"],
        score_range_own_low=sim_result["score_range_own_low"],
        score_range_own_high=sim_result["score_range_own_high"],
        score_range_opp_low=sim_result["score_range_opp_low"],
        score_range_opp_high=sim_result["score_range_opp_high"],
        key_drivers={"drivers": sim_result.get("key_drivers", [])},
        base_log_odds=sim_result.get("base_log_odds"),
        runs_data=sim_result.get("runs_data", [])[:100],  # Store first 100 for space
    )
    db.add(sim)
    await db.flush()

    # Generate keys to victory from LLM
    summary = {
        "win_pct_own": round(sim_result["win_pct_own"], 3),
        "avg_score_own": round(sim_result.get("avg_score_own", 0), 1),
        "avg_score_opp": round(sim_result.get("avg_score_opp", 0), 1),
        "key_drivers": sim_result.get("key_drivers", []),
        "own_team_stats": {k: v for k, v in own_stats.items() if k.startswith("avg_") or k in ("fg_pct", "fg3_pct", "ft_pct")},
        "opp_team_stats": {k: v for k, v in opp_stats.items() if k.startswith("avg_") or k in ("fg_pct", "fg3_pct", "ft_pct")},
    }

    try:
        keys_data = await generate_keys_to_victory(summary, m.name)
    except Exception:
        keys_data = []

    # Fallback: use driver-based keys if LLM fails
    if not keys_data:
        driver_labels = {
            "own_fg_pct": ("Shoot efficiently", "Maintain high field goal percentage", "fg_pct"),
            "own_fg3_pct": ("3-point shooting", "Capitalize on three-point opportunities", "fg3_pct"),
            "own_tov_rate": ("Protect the ball", "Minimize turnovers to preserve possessions", "tov"),
            "own_oreb_rate": ("Win the boards", "Dominate offensive rebounding for second chances", "reb"),
            "opp_fg_pct": ("Defend the paint", "Limit opponent field goal percentage", "fg_pct"),
        }
        for d in (sim_result.get("key_drivers") or [])[:5]:
            fn = d.get("feature_name", "")
            label_info = driver_labels.get(fn, (fn.replace("_", " ").title(), "", fn))
            keys_data.append({
                "title": label_info[0],
                "description": label_info[1],
                "target_metric": label_info[2],
                "target_value": None,
                "weight": min(1.0, abs(d.get("coefficient", 0.5))),
            })

    for i, kd in enumerate(keys_data[:6]):
        key = KeyToVictory(
            simulation_id=sim.id,
            title=kd.get("title", f"Key {i+1}"),
            description=kd.get("description"),
            target_metric=kd.get("target_metric"),
            target_value=kd.get("target_value"),
            weight=kd.get("weight", 1.0),
            order=i,
            feature_name=(sim_result.get("key_drivers") or [{}])[i % len(sim_result.get("key_drivers") or [{}])].get("feature_name") if sim_result.get("key_drivers") else None,
            coefficient=(sim_result.get("key_drivers") or [{}])[i % len(sim_result.get("key_drivers") or [{}])].get("coefficient") if sim_result.get("key_drivers") else None,
        )
        db.add(key)

    await db.commit()

    final = await db.execute(
        select(GameSimulation)
        .where(GameSimulation.id == sim.id)
        .options(selectinload(GameSimulation.keys))
    )
    return final.scalar_one()


# ── Priority Keys endpoint ─────────────────────────────────────────────────────

@router.patch("/{matchup_id}/keys/{key_id}/priority", response_model=KeyToVictoryRead)
async def set_key_priority(
    matchup_id: uuid.UUID,
    key_id: uuid.UUID,
    payload: PriorityKeyUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Toggle priority flag and rank on a Key to Victory."""
    key = await db.get(KeyToVictory, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Key not found")

    # Verify the key belongs to a simulation of this matchup
    sim = await db.get(GameSimulation, key.simulation_id)
    if sim is None or sim.matchup_id != matchup_id:
        raise HTTPException(status_code=403, detail="Key does not belong to this matchup")

    key.is_priority = payload.is_priority
    key.priority_rank = payload.priority_rank
    await db.commit()
    await db.refresh(key)
    return key
