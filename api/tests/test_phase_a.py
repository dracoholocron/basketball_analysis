"""Phase A integration tests: games season/team filter + team-name enrichment,
and scouting-report LLM-failure surfacing (502)."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.season import Season
from app.models.game import Game


@pytest.mark.asyncio
async def test_games_filtered_by_season(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, season: Season, game: Game, org
):
    # A second season + game that must NOT appear when filtering by `season`.
    other = Season(id=uuid.uuid4(), name="Otra", organization_id=org.id, year="2023")
    db_session.add(other)
    await db_session.commit()
    db_session.add(Game(id=uuid.uuid4(), season_id=other.id))
    await db_session.commit()

    r = await client.get("/api/v1/games", params={"season_id": str(season.id)}, headers=auth_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    ids = {g["id"] for g in items}
    assert str(game.id) in ids
    assert all(g["season_id"] == str(season.id) for g in items)


@pytest.mark.asyncio
async def test_games_filtered_by_team_and_enriched_names(
    client: AsyncClient, auth_headers: dict, season: Season, team, away_team, game: Game
):
    r = await client.get(
        "/api/v1/games",
        params={"season_id": str(season.id), "team_id": str(team.id)},
        headers=auth_headers,
    )
    assert r.status_code == 200
    items = r.json()["items"]
    row = next(it for it in items if it["id"] == str(game.id))
    # Team names are enriched so the box-score filter shows readable labels.
    assert row["home_team_name"] == "Home Team"
    assert row["away_team_name"] == "Away Team"


@pytest.mark.asyncio
async def test_scouting_generate_502_on_llm_failure(client: AsyncClient, auth_headers: dict, monkeypatch):
    """When the LLM is unreachable/invalid, the endpoint surfaces a 502 (not a silent
    degraded 200) so the UI can show a real error."""
    import app.services.llm as llm_module

    async def _boom(*args, **kwargs):
        raise RuntimeError("LLM unreachable")

    monkeypatch.setattr(llm_module, "generate_scouting_report", _boom)

    m = await client.post("/api/v1/matchups", json={"name": "LLM down"}, headers=auth_headers)
    matchup_id = m.json()["id"]
    r = await client.post(
        f"/api/v1/matchups/{matchup_id}/scouting-report/generate", headers=auth_headers
    )
    assert r.status_code == 502
    assert "IA" in r.json()["detail"] or "LLM" in r.json()["detail"]
