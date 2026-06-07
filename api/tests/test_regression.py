"""Regression tests for bugs fixed in the June 2026 audit."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_import_box_scores_requires_query_param(client: AsyncClient, auth_headers: dict):
    """Bug #1 regression: game_id must be a query param, not body."""
    resp = await client.post("/api/v1/box-scores/import", json={"game_id": "fake"}, headers=auth_headers)
    assert resp.status_code != 500

    resp2 = await client.post(
        "/api/v1/box-scores/import?game_id=00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp2.status_code in (200, 401, 404, 422)


@pytest.mark.asyncio
async def test_simulation_endpoint_exists(client: AsyncClient, auth_headers: dict):
    """Bug #2 regression: GET /matchups/{id}/simulation should return 404, not 500, when no sim exists."""
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/matchups/{fake_id}/simulation",
        headers=auth_headers,
    )
    assert resp.status_code in (200, 404)
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_scouting_report_generate_path(client: AsyncClient, auth_headers: dict):
    """Bug from audit: generate endpoint is /scouting-report/generate not /scouting-report POST."""
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/matchups/{fake_id}/scouting-report/generate",
        headers=auth_headers,
    )
    assert resp.status_code in (200, 404, 422)
    assert resp.status_code != 405

    resp2 = await client.patch(
        f"/api/v1/scouting-reports/{fake_id}/notes",
        headers=auth_headers,
    )
    assert resp2.status_code in (404, 422)
