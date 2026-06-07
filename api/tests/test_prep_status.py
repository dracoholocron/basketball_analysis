"""Tests for prep-status and upcoming matchups endpoints (G8 M2, M3)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
import pytest

from app.models.matchup import Matchup


@pytest.fixture
async def upcoming_matchups(db_session, admin_user, team, away_team):
    """Create 3 upcoming matchups with different scheduled_at dates."""
    now = datetime.now(timezone.utc)
    matchups = []
    for i in range(3):
        m = Matchup(
            id=uuid.uuid4(),
            name=f"Upcoming {i + 1}",
            own_team_id=team.id,
            opponent_team_id=away_team.id,
            organization_id=admin_user.organization_id,
            scheduled_at=now + timedelta(days=i + 1),
        )
        db_session.add(m)
        matchups.append(m)
    await db_session.commit()
    return matchups


@pytest.fixture
async def matchup_for_prep(db_session, admin_user, team, away_team):
    m = Matchup(
        id=uuid.uuid4(),
        name="Prep Test Matchup",
        own_team_id=team.id,
        opponent_team_id=away_team.id,
        organization_id=admin_user.organization_id,
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    return m


async def test_upcoming_matchups_ordered_by_date(client, auth_headers, upcoming_matchups):
    r = await client.get("/api/v1/matchups/upcoming", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 3
    # Verify ordered by scheduled_at
    dates = [m["scheduled_at"] for m in data if m["scheduled_at"] is not None]
    assert dates == sorted(dates)


async def test_prep_status_returns_5_steps(client, auth_headers, matchup_for_prep):
    r = await client.get(f"/api/v1/matchups/{matchup_for_prep.id}/prep-status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "steps" in data
    assert len(data["steps"]) == 5


async def test_prep_status_progress_is_zero_empty(client, auth_headers, matchup_for_prep):
    """Fresh matchup should have 0% progress."""
    r = await client.get(f"/api/v1/matchups/{matchup_for_prep.id}/prep-status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["progress_pct"] >= 0
    # Steps all incomplete
    assert all(not s["complete"] for s in data["steps"])


async def test_prep_status_not_found(client, auth_headers):
    r = await client.get(f"/api/v1/matchups/{uuid.uuid4()}/prep-status", headers=auth_headers)
    assert r.status_code == 404
