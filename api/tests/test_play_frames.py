"""Tests for play SVG data versioning (v1→v2 multi-frame) (G3, G4)."""
from __future__ import annotations

import uuid
import pytest

from app.models.matchup import Matchup


@pytest.fixture
async def matchup(db_session, admin_user, team, away_team):
    m = Matchup(
        id=uuid.uuid4(), name="Play Frame Test", own_team_id=team.id,
        opponent_team_id=away_team.id, organization_id=admin_user.organization_id,
    )
    db_session.add(m)
    await db_session.commit()
    return m


async def test_create_play_v1(client, auth_headers):
    """Basic play creation returns svg_data_version=1 by default."""
    payload = {
        "name": "Test Play V1",
        "category": "Offense",
        "svg_data": {"players": [], "arrows": []},
    }
    r = await client.post("/api/v1/plays", json=payload, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["svg_data_version"] == 1


async def test_update_play_to_v2_with_frames(client, auth_headers):
    """Updating a play with svg_data containing 'frames' key should set version=2."""
    r = await client.post("/api/v1/plays", json={"name": "Multi-frame Play", "category": "Offense"}, headers=auth_headers)
    assert r.status_code == 201
    play_id = r.json()["id"]

    r2 = await client.put(f"/api/v1/plays/{play_id}", json={
        "name": "Multi-frame Play",
        "category": "Offense",
        "svg_data": {"frames": [{"players": []}, {"players": []}]},
    }, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["svg_data_version"] == 2


async def test_play_with_tags_and_pace(client, auth_headers):
    payload = {
        "name": "Tagged Play",
        "category": "Offense",
        "tags": ["vs Zone", "BLOB"],
        "pace": "half-court",
    }
    r = await client.post("/api/v1/plays", json=payload, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert "vs Zone" in (data.get("tags") or [])
    assert data.get("pace") == "half-court"


async def test_play_linked_to_matchup(client, auth_headers, matchup):
    payload = {
        "name": "Linked Play",
        "category": "Offense",
        "linked_matchup_id": str(matchup.id),
    }
    r = await client.post("/api/v1/plays", json=payload, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data.get("linked_matchup_id") == str(matchup.id)
