"""Tests for assist events (2pt_made/3pt_made → assist) with parent_event_id."""
from __future__ import annotations

import uuid
import pytest

from app.models.matchup import Matchup


@pytest.fixture
async def matchup(db_session, admin_user, team, away_team):
    m = Matchup(
        id=uuid.uuid4(), name="Assist Test Matchup",
        own_team_id=team.id, opponent_team_id=away_team.id,
        organization_id=admin_user.organization_id,
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    return m


async def test_assist_after_2pt_made(client, auth_headers, matchup):
    """Assist event persists with parent_event_id linking to the made basket."""
    # Create the made basket event
    r = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "2pt_made", "team": 1, "points": 2,
        "x_pct": 40.0, "y_pct": 50.0, "player_jersey": "23",
        "period": 1, "game_time_seconds": 900,
    }, headers=auth_headers)
    assert r.status_code == 201
    made_id = r.json()["id"]

    # Create the assist event linked to the made basket
    r2 = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "assist", "team": 1, "points": 0,
        "parent_event_id": made_id, "player_jersey": "11",
        "period": 1, "game_time_seconds": 900,
    }, headers=auth_headers)
    assert r2.status_code == 201
    assist = r2.json()
    assert assist["event_type"] == "assist"
    assert assist["parent_event_id"] == made_id
    assert assist["player_jersey"] == "11"
    assert assist["team"] == 1


async def test_assist_after_3pt_made(client, auth_headers, matchup):
    """Assist event persists after a 3-point made basket."""
    r = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "3pt_made", "team": 2, "points": 3,
        "x_pct": 80.0, "y_pct": 20.0, "player_jersey": "5",
        "period": 2, "game_time_seconds": 600,
    }, headers=auth_headers)
    assert r.status_code == 201
    made_id = r.json()["id"]

    r2 = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "assist", "team": 2, "points": 0,
        "parent_event_id": made_id, "player_jersey": "33",
        "period": 2, "game_time_seconds": 600,
    }, headers=auth_headers)
    assert r2.status_code == 201
    assist = r2.json()
    assert assist["event_type"] == "assist"
    assert assist["parent_event_id"] == made_id
    assert assist["player_jersey"] == "33"


async def test_assist_appears_in_event_list(client, auth_headers, matchup):
    """Assist event appears in the matchup event list with correct parent linkage."""
    # Create made basket
    r = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "2pt_made", "team": 1, "points": 2, "player_jersey": "7",
    }, headers=auth_headers)
    assert r.status_code == 201
    made_id = r.json()["id"]

    # Create assist
    await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "assist", "team": 1, "points": 0,
        "parent_event_id": made_id, "player_jersey": "44",
    }, headers=auth_headers)

    # Verify the event list contains both events
    r_list = await client.get(f"/api/v1/matchups/{matchup.id}/events", headers=auth_headers)
    assert r_list.status_code == 200
    events = r_list.json()
    made_events = [e for e in events if e["event_type"] == "2pt_made"]
    assist_events = [e for e in events if e["event_type"] == "assist"]
    assert len(made_events) >= 1
    assert len(assist_events) >= 1
    assert any(e["parent_event_id"] == made_id for e in assist_events)
    assert any(e["player_jersey"] == "44" for e in assist_events)


async def test_assist_no_parent_is_valid(client, auth_headers, matchup):
    """Assist event can be created without a parent_event_id (standalone)."""
    r = await client.post(f"/api/v1/matchups/{matchup.id}/events", json={
        "event_type": "assist", "team": 1, "points": 0, "player_jersey": "10",
    }, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["event_type"] == "assist"
    assert data["parent_event_id"] is None
