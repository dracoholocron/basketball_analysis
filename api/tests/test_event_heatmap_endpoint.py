"""Tests for the /matchups/{id}/event-heatmap endpoint (G2)."""
from __future__ import annotations

import uuid
import pytest

from app.models.matchup import Matchup
from app.models.game_event import GameEvent


@pytest.fixture
async def matchup_with_events(db_session, admin_user, team, away_team):
    m = Matchup(
        id=uuid.uuid4(), name="Heatmap Test", own_team_id=team.id,
        opponent_team_id=away_team.id, organization_id=admin_user.organization_id,
    )
    db_session.add(m)
    await db_session.flush()

    events = [
        GameEvent(id=uuid.uuid4(), matchup_id=m.id, event_type="2pt_made", team=1, points=2,
                  x_pct=25.0, y_pct=30.0),
        GameEvent(id=uuid.uuid4(), matchup_id=m.id, event_type="3pt_made", team=1, points=3,
                  x_pct=80.0, y_pct=20.0),
        GameEvent(id=uuid.uuid4(), matchup_id=m.id, event_type="missed", team=1, points=0,
                  x_pct=45.0, y_pct=50.0),
        GameEvent(id=uuid.uuid4(), matchup_id=m.id, event_type="block", team=2, points=0),
        GameEvent(id=uuid.uuid4(), matchup_id=m.id, event_type="steal", team=2, points=0),
        GameEvent(id=uuid.uuid4(), matchup_id=m.id, event_type="foul", team=1, points=0),
    ]
    db_session.add_all(events)
    await db_session.commit()
    await db_session.refresh(m)
    return m


async def test_heatmap_returns_grid_and_stats(client, auth_headers, matchup_with_events):
    m = matchup_with_events
    r = await client.get(f"/api/v1/matchups/{m.id}/event-heatmap", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()

    assert "heat_grid" in data
    assert len(data["heat_grid"]) == 10  # 10 rows
    assert all(len(row) == 6 for row in data["heat_grid"])  # 6 cols

    assert data["blocks"] == 1
    assert data["steals"] == 1
    assert data["fouls"] == 1
    assert data["total_shots"] == 3
    assert data["made_shots"] == 2


async def test_heatmap_fg_pct(client, auth_headers, matchup_with_events):
    r = await client.get(
        f"/api/v1/matchups/{matchup_with_events.id}/event-heatmap",
        headers=auth_headers
    )
    data = r.json()
    assert abs(data["fg_pct"] - round(2 / 3, 3)) < 0.01


async def test_heatmap_empty_matchup(client, auth_headers, db_session, admin_user, team, away_team):
    m = Matchup(id=uuid.uuid4(), name="Empty Heatmap", own_team_id=team.id,
                opponent_team_id=away_team.id, organization_id=admin_user.organization_id)
    db_session.add(m)
    await db_session.commit()
    r = await client.get(f"/api/v1/matchups/{m.id}/event-heatmap", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total_shots"] == 0
    assert data["fg_pct"] == 0.0
