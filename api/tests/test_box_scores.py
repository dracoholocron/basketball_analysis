"""Box score CRUD and validation tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.game import Game
from app.models.team import Team


async def _create_matchup(client: AsyncClient, headers: dict) -> str:
    resp = await client.post("/api/v1/matchups", json={"name": "BoxScore Matchup"}, headers=headers)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_box_score_valid(
    client: AsyncClient, auth_headers: dict, game: Game, team: Team
):
    # pts = 2*fgm + 3*fg3m + ftm = 2*25 + 3*5 + 15 = 50+15+15 = 80
    payload = {
        "game_id": str(game.id),
        "team_id": str(team.id),
        "pts": 80,
        "fgm": 25,
        "fga": 60,
        "fg3m": 5,
        "fg3a": 18,
        "ftm": 15,
        "fta": 18,
        "oreb": 8,
        "dreb": 25,
        "ast": 18,
        "stl": 6,
        "blk": 3,
        "tov": 12,
        "pf": 18,
        "players": [],
    }
    resp = await client.post("/api/v1/box-scores", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["pts"] == 80


@pytest.mark.asyncio
async def test_create_box_score_inconsistent_pts(
    client: AsyncClient, auth_headers: dict, game: Game, team: Team
):
    """pts=100 but fgm=10, fg3m=0, ftm=0 → expected 20 → diff > 5 → 400."""
    payload = {
        "game_id": str(game.id),
        "team_id": str(team.id),
        "pts": 100,
        "fgm": 10,
        "fga": 30,
        "fg3m": 0,
        "fg3a": 5,
        "ftm": 0,
        "fta": 5,
        "oreb": 5,
        "dreb": 15,
        "ast": 10,
        "stl": 3,
        "blk": 2,
        "tov": 8,
        "pf": 12,
        "players": [],
    }
    resp = await client.post("/api/v1/box-scores", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "inconsistent" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_box_scores(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/box-scores", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
