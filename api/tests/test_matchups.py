"""Matchup CRUD tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.team import Team


@pytest.mark.asyncio
async def test_list_matchups_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/matchups", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_matchup(client: AsyncClient, auth_headers: dict, team: Team):
    resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Test vs Eagles", "own_team_id": str(team.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test vs Eagles"
    assert data["own_team_id"] == str(team.id)
    return data["id"]


@pytest.mark.asyncio
async def test_get_matchup(client: AsyncClient, auth_headers: dict, team: Team):
    create_resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Retrievable Matchup"},
        headers=auth_headers,
    )
    matchup_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/matchups/{matchup_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == matchup_id


@pytest.mark.asyncio
async def test_update_matchup_notes(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Notes Matchup"},
        headers=auth_headers,
    )
    matchup_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/matchups/{matchup_id}/notes",
        json={"notes": {"rotation_plan": "Start 1-3-1", "coach_notes": "Push the pace"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["notes"]["rotation_plan"] == "Start 1-3-1"


@pytest.mark.asyncio
async def test_delete_matchup(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Delete Me"},
        headers=auth_headers,
    )
    matchup_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/matchups/{matchup_id}", headers=auth_headers)
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/matchups/{matchup_id}", headers=auth_headers)
    assert get_resp.status_code == 404
