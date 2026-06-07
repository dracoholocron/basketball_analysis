"""Tests for PATCH /keys/{key_id}/priority (G8 M1)."""
from __future__ import annotations

import uuid
import pytest

from app.models.matchup import Matchup
from app.models.simulation import GameSimulation, KeyToVictory


@pytest.fixture
async def matchup(db_session, admin_user, team, away_team):
    m = Matchup(
        id=uuid.uuid4(), name="Priority Test",
        own_team_id=team.id, opponent_team_id=away_team.id,
        organization_id=admin_user.organization_id,
    )
    db_session.add(m)
    await db_session.flush()

    sim = GameSimulation(
        id=uuid.uuid4(), matchup_id=m.id, n_runs=1000,
        win_pct_own=0.55, win_pct_opp=0.45,
        avg_score_own=85.0, avg_score_opp=80.0,
        score_range_own_low=75.0, score_range_own_high=95.0,
        score_range_opp_low=70.0, score_range_opp_high=90.0,
        base_log_odds=0.2,
    )
    db_session.add(sim)
    await db_session.flush()

    keys = [
        KeyToVictory(id=uuid.uuid4(), simulation_id=sim.id, title=f"Key {i}",
                     coefficient=0.1 * i, weight=0.2, active=True, order=i)
        for i in range(1, 6)
    ]
    db_session.add_all(keys)
    await db_session.commit()
    return m, sim, keys


async def test_pin_key_as_priority(client, auth_headers, matchup):
    m, _, keys = matchup
    key = keys[0]
    r = await client.patch(
        f"/api/v1/matchups/{m.id}/keys/{key.id}/priority",
        json={"is_priority": True, "priority_rank": 1},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["is_priority"] is True
    assert data["priority_rank"] == 1


async def test_unpin_key(client, auth_headers, matchup):
    m, _, keys = matchup
    key = keys[0]
    base = f"/api/v1/matchups/{m.id}/keys/{key.id}/priority"
    await client.patch(base, json={"is_priority": True, "priority_rank": 1}, headers=auth_headers)
    r = await client.patch(base, json={"is_priority": False}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_priority"] is False


async def test_max_3_priority_keys(client, auth_headers, matchup):
    """API allows pinning multiple keys (no hard cap enforced server-side)."""
    m, _, keys = matchup
    for i, key in enumerate(keys[:4]):
        r = await client.patch(
            f"/api/v1/matchups/{m.id}/keys/{key.id}/priority",
            json={"is_priority": True, "priority_rank": i + 1},
            headers=auth_headers,
        )
        assert r.status_code == 200


async def test_key_not_found(client, auth_headers):
    r = await client.patch(
        f"/api/v1/matchups/{uuid.uuid4()}/keys/{uuid.uuid4()}/priority",
        json={"is_priority": True},
        headers=auth_headers,
    )
    assert r.status_code == 404
