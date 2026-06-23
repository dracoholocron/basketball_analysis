"""Phase C3: simulation generates diagrammed suggested plays (sim_suggested) for the matchup."""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_simulation_generates_suggested_plays(
    client: AsyncClient, auth_headers, monkeypatch, team, away_team, db_session
):
    # Force the LLM keys call to no-op so the sim uses driver-based keys (fast, offline).
    import app.routers.matchups as mm
    async def _no_keys(*a, **k):
        return []
    monkeypatch.setattr(mm, "generate_keys_to_victory", _no_keys, raising=False)
    # generate_keys_to_victory is imported inside the endpoint from services.llm:
    import app.services.llm as llm
    monkeypatch.setattr(llm, "generate_keys_to_victory", _no_keys)

    m = await client.post("/api/v1/matchups", json={
        "name": "C3 sim", "own_team_id": str(team.id), "opponent_team_id": str(away_team.id),
    }, headers=auth_headers)
    assert m.status_code == 201, m.text
    mid = m.json()["id"]

    r = await client.post(f"/api/v1/matchups/{mid}/simulate", headers=auth_headers)
    assert r.status_code in (200, 201), r.text

    # Suggested plays should now be linked to the matchup, with valid v2 svg_data.
    from app.models.play import Play
    from sqlalchemy import select as _select
    rows = (await db_session.execute(
        _select(Play).where(Play.linked_matchup_id == uuid.UUID(mid),
                            Play.category == "sim_suggested")
    )).scalars().all()
    assert len(rows) >= 1
    p0 = rows[0]
    assert p0.svg_data_version == 2
    assert p0.svg_data and len(p0.svg_data["frames"]) >= 10


@pytest.mark.asyncio
async def test_suggested_play_specs_mapping():
    from app.routers.matchups import _suggested_play_specs
    specs = _suggested_play_specs(
        [{"feature_name": "own_fg3_pct"}, {"feature_name": "own_oreb_rate"}], pace_fast=True)
    names = [s[0] for s in specs]
    assert "Floppy" in names and "Hi-Lo Zone Series" in names
    assert "Press Break" in names  # pace_fast adds transition
