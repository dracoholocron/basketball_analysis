"""GameEvent CRUD endpoint tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _create_matchup(client: AsyncClient, headers: dict) -> str:
    resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Event Matchup"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_game_event(client: AsyncClient, auth_headers: dict):
    matchup_id = await _create_matchup(client, auth_headers)
    resp = await client.post(
        f"/api/v1/matchups/{matchup_id}/events",
        json={
            "event_type": "2pt_made",
            "team": 1,
            "points": 2,
            "x_pct": 45.0,
            "y_pct": 55.0,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["event_type"] == "2pt_made"
    assert data["team"] == 1
    assert data["points"] == 2
    assert data["matchup_id"] == matchup_id
    return data["id"], matchup_id


@pytest.mark.asyncio
async def test_list_game_events(client: AsyncClient, auth_headers: dict):
    matchup_id = await _create_matchup(client, auth_headers)
    for i in range(3):
        await client.post(
            f"/api/v1/matchups/{matchup_id}/events",
            json={"event_type": "rebound", "team": 1 + (i % 2), "points": 0},
            headers=auth_headers,
        )

    resp = await client.get(f"/api/v1/matchups/{matchup_id}/events", headers=auth_headers)
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 3


@pytest.mark.asyncio
async def test_delete_game_event(client: AsyncClient, auth_headers: dict):
    matchup_id = await _create_matchup(client, auth_headers)
    create_resp = await client.post(
        f"/api/v1/matchups/{matchup_id}/events",
        json={"event_type": "turnover", "team": 2, "points": 0},
        headers=auth_headers,
    )
    event_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/matchups/{matchup_id}/events/{event_id}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/matchups/{matchup_id}/events", headers=auth_headers)
    events = list_resp.json()
    assert all(e["id"] != event_id for e in events)


@pytest.mark.asyncio
async def test_game_event_wrong_matchup(client: AsyncClient, auth_headers: dict):
    import uuid
    matchup_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/matchups/{matchup_id}/events", headers=auth_headers)
    assert resp.status_code == 404
