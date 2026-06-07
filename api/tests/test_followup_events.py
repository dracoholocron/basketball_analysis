"""Tests for follow-up events (missed → rebound) with parent_event_id and player_jersey."""
from __future__ import annotations

import uuid
import pytest

from app.models.matchup import Matchup


@pytest.fixture
async def matchup(db_session, admin_user, team, away_team):
    m = Matchup(
        id=uuid.uuid4(), name="Followup Test", own_team_id=team.id,
        opponent_team_id=away_team.id, organization_id=admin_user.organization_id,
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    return m


async def test_create_missed_event_and_rebound(client, auth_headers, matchup):
    # Create missed shot
    r = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "missed", "team": 1, "points": 0, "x_pct": 50.0, "y_pct": 30.0,
        "player_jersey": "23", "period": 1, "game_time_seconds": 600,
    }, headers=auth_headers)
    assert r.status_code == 201
    missed_id = r.json()["id"]

    # Create offensive rebound with parent_event_id
    r2 = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "off_reb", "team": 1, "points": 0,
        "parent_event_id": missed_id, "player_jersey": "5",
    }, headers=auth_headers)
    assert r2.status_code == 201
    rebound = r2.json()
    assert rebound["parent_event_id"] == missed_id
    assert rebound["player_jersey"] == "5"


async def test_defensive_rebound(client, auth_headers, matchup):
    r1 = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "missed", "team": 1, "points": 0,
    }, headers=auth_headers)
    assert r1.status_code == 201
    missed_id = r1.json()["id"]

    r2 = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "def_reb", "team": 2, "points": 0,
        "parent_event_id": missed_id, "player_jersey": "11",
        "period": 2, "game_time_seconds": 400,
    }, headers=auth_headers)
    assert r2.status_code == 201
    rb = r2.json()
    assert rb["parent_event_id"] == missed_id
    assert rb["player_jersey"] == "11"
    assert rb["period"] == 2


async def test_jersey_attribution_in_event_list(client, auth_headers, matchup):
    await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "2pt_made", "team": 1, "points": 2,
        "player_jersey": "33", "period": 1, "game_time_seconds": 900,
    }, headers=auth_headers)
    r = await client.get(f"/api/v1/matchups/{matchup.id}/events", headers=auth_headers)
    assert r.status_code == 200
    events = r.json()
    assert any(e.get("player_jersey") == "33" for e in events)
