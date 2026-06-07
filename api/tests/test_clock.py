"""Tests for matchup clock management (G1)."""
from __future__ import annotations

import uuid
import pytest

from app.models.matchup import Matchup


@pytest.fixture
async def matchup(db_session, admin_user, team, away_team):
    m = Matchup(
        id=uuid.uuid4(),
        name="Clock Test Matchup",
        own_team_id=team.id,
        opponent_team_id=away_team.id,
        organization_id=admin_user.organization_id,
        clock_state={"period": 1, "time_remaining_seconds": 1200, "is_paused": True,
                     "timeouts_used_team1": 0, "timeouts_used_team2": 0},
        game_config={"sport": "Basketball", "halves": 2, "mins_per_period": 20, "timeouts_per_team": 4},
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    return m


async def test_clock_start(client, auth_headers, matchup):
    r = await client.patch(f"/api/v1/matchups/{matchup.id}/clock", json={"action": "start"}, headers=auth_headers)
    assert r.status_code == 200
    clock = r.json()["clock_state"]
    assert clock["is_paused"] is False


async def test_clock_pause(client, auth_headers, matchup):
    await client.patch(f"/api/v1/matchups/{matchup.id}/clock", json={"action": "start"}, headers=auth_headers)
    r = await client.patch(f"/api/v1/matchups/{matchup.id}/clock", json={"action": "pause"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["clock_state"]["is_paused"] is True


async def test_clock_advance_period(client, auth_headers, matchup):
    r = await client.patch(f"/api/v1/matchups/{matchup.id}/clock", json={"action": "advance_period"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["clock_state"]["period"] == 2


async def test_clock_reset(client, auth_headers, matchup):
    await client.patch(f"/api/v1/matchups/{matchup.id}/clock", json={"action": "advance_period"}, headers=auth_headers)
    r = await client.patch(f"/api/v1/matchups/{matchup.id}/clock", json={"action": "reset"}, headers=auth_headers)
    assert r.status_code == 200
    clock = r.json()["clock_state"]
    assert clock["period"] == 1
    assert clock["is_paused"] is True


async def test_clock_set_time(client, auth_headers, matchup):
    r = await client.patch(
        f"/api/v1/matchups/{matchup.id}/clock",
        json={"action": "set_time", "time_seconds": 300},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["clock_state"]["time_remaining_seconds"] == 300


async def test_clock_invalid_action(client, auth_headers, matchup):
    r = await client.patch(f"/api/v1/matchups/{matchup.id}/clock", json={"action": "fly_away"}, headers=auth_headers)
    # Server returns 422 (FastAPI validation) for unknown action
    assert r.status_code in (400, 422)
