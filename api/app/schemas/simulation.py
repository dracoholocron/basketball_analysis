from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class KeyToVictoryRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    target_metric: str | None
    target_value: float | None
    weight: float
    active: bool
    order: int
    feature_name: str | None = None
    coefficient: float | None = None
    feature_mean: float | None = None
    feature_std: float | None = None
    live_status: str | None = None

    model_config = {"from_attributes": True}


class KeyToggle(BaseModel):
    active: bool


class KeysImpactRequest(BaseModel):
    active_key_ids: list[uuid.UUID]


class KeysImpactResponse(BaseModel):
    adjusted_win_pct: float
    delta_log_odds: float


class SituationalAdjustmentRead(BaseModel):
    id: uuid.UUID
    matchup_id: uuid.UUID
    scenario: str
    response: str
    expected_impact: str | None
    kind: str
    order: int

    model_config = {"from_attributes": True}


class SimulationRead(BaseModel):
    id: uuid.UUID
    matchup_id: uuid.UUID
    n_runs: int
    win_pct_own: float
    win_pct_opp: float
    avg_score_own: float | None
    avg_score_opp: float | None
    score_range_own_low: float | None
    score_range_own_high: float | None
    score_range_opp_low: float | None
    score_range_opp_high: float | None
    base_log_odds: float | None = None
    created_at: datetime
    keys: list[KeyToVictoryRead] = []

    model_config = {"from_attributes": True}


class SimulationStatusResponse(BaseModel):
    job_id: str
    status: str
    simulation_id: str | None = None
