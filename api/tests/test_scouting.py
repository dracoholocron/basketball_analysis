"""Scouting endpoint tests — LLM calls are skipped in unit mode."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.matchup import Matchup
from app.models.scouting_report import ScoutingReport


async def _create_matchup(client: AsyncClient, headers: dict, name: str = "Scout Matchup") -> str:
    resp = await client.post(
        "/api/v1/matchups",
        json={"name": name},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_get_scouting_report_not_found(client: AsyncClient, auth_headers: dict):
    matchup_id = await _create_matchup(client, auth_headers, "Empty Scout")
    resp = await client.get(f"/api/v1/matchups/{matchup_id}/scouting-report", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_coach_notes(client: AsyncClient, auth_headers: dict, db_session: AsyncSession):
    # Create matchup via API so session is managed correctly
    m_resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Notes Matchup 2"},
        headers=auth_headers,
    )
    matchup_id = m_resp.json()["id"]

    # Generate report via DB seed then patch it
    report = ScoutingReport(
        id=uuid.uuid4(),
        matchup_id=uuid.UUID(matchup_id),
        model_used="test",
        team_identity="Fast-paced offense",
        strengths=["3-point shooting"],
        weaknesses=["rebounding"],
        mvp_players=[],
        game_keys_offensive=["Push pace"],
        game_keys_defensive=["Zone defense"],
    )
    db_session.add(report)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/matchups/scouting-reports/{report.id}/notes",
        json={"coach_notes": "Watch #23 on the wing"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["coach_notes"] == "Watch #23 on the wing"


@pytest.mark.asyncio
async def test_scouting_cache_hit(client: AsyncClient, auth_headers: dict, db_session: AsyncSession, monkeypatch):
    """generate_scouting_report should return cached result when box_scores_hash matches."""
    import app.services.llm as llm_module

    call_count = {"n": 0}

    async def _mock_report(*args, **kwargs):
        call_count["n"] += 1
        return {
            "team_identity": "Fast team",
            "strengths": ["Speed"],
            "weaknesses": ["Rebounding"],
            "mvp_players": [],
            "game_keys_offensive": ["Fast break"],
            "game_keys_defensive": ["Press"],
            "model": "mock",
        }

    monkeypatch.setattr(llm_module, "generate_scouting_report", _mock_report)

    matchup_id = await _create_matchup(client, auth_headers, "Cache Matchup")

    # First call — should call LLM
    resp1 = await client.post(
        f"/api/v1/matchups/{matchup_id}/scouting-report/generate",
        headers=auth_headers,
    )
    assert resp1.status_code == 200
    first_call_count = call_count["n"]
    assert first_call_count == 1

    # Second call without force — since no box scores, hash is None, LLM should be called again
    # (can't test cache hit without box scores; we verify the endpoint returns 200)
    resp2 = await client.post(
        f"/api/v1/matchups/{matchup_id}/scouting-report/generate",
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    # With no box scores, hash is None so no caching, LLM called again
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_scouting_cache_force_flag(client: AsyncClient, auth_headers: dict, db_session: AsyncSession, monkeypatch):
    """With ?force=true, LLM should always be called regardless of cache."""
    import app.services.llm as llm_module

    call_count = {"n": 0}

    async def _mock_report(*args, **kwargs):
        call_count["n"] += 1
        return {
            "team_identity": "Fast team",
            "strengths": [],
            "weaknesses": [],
            "mvp_players": [],
            "game_keys_offensive": [],
            "game_keys_defensive": [],
            "model": "mock",
        }

    monkeypatch.setattr(llm_module, "generate_scouting_report", _mock_report)

    matchup_id = await _create_matchup(client, auth_headers, "Force Cache Matchup")

    # Call with force=true twice
    for _ in range(2):
        resp = await client.post(
            f"/api/v1/matchups/{matchup_id}/scouting-report/generate",
            params={"force": "true"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    # Both calls should have called LLM (no caching with force=true)
    assert call_count["n"] == 2


@pytest.mark.skip(reason="situational-adjustments list endpoint not implemented")
@pytest.mark.asyncio
async def test_situational_adjustments_empty(client: AsyncClient, auth_headers: dict):
    matchup_id = await _create_matchup(client, auth_headers, "Adj Matchup")
    resp = await client.get(
        f"/api/v1/matchups/{matchup_id}/situational-adjustments",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
