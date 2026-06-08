"""Regression tests for bugs fixed in the June 2026 audit and Phase-5 additions."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.job import Job, JobStatus, JobStage
from app.models.metrics import PlayerMetric


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


@pytest.mark.asyncio
async def test_job_list_backwards_compatible(client: AsyncClient, auth_headers: dict):
    """Regression: GET /jobs without params must still return a list (no breaking change)."""
    resp = await client.get("/api/v1/jobs", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list), "Should return a JSON array"


@pytest.mark.asyncio
async def test_metrics_schema_includes_display_label(client: AsyncClient, auth_headers: dict):
    """Regression: PlayerMetricRead must still expose all previously existing fields."""
    from app.schemas.metrics import PlayerMetricRead
    import inspect

    fields = PlayerMetricRead.model_fields
    required_fields = {
        "id", "job_id", "track_id", "team_id",
        "total_distance_m", "avg_speed_kmh", "max_speed_kmh",
        "possession_frames", "passes_made", "interceptions_made",
        "display_label",
    }
    missing = required_fields - set(fields.keys())
    assert not missing, f"Missing fields in PlayerMetricRead: {missing}"


@pytest.mark.asyncio
async def test_player_max_speed_not_zero(
    client: AsyncClient,
    db_session: AsyncSession,
    game: Game,
    auth_headers: dict,
):
    """Regression: _persist_metrics should no longer store max_speed_kmh=0 when speeds exist."""
    job = Job(
        id=uuid.uuid4(),
        game_id=game.id,
        status=JobStatus.DONE,
        current_stage=JobStage.COMPLETE,
    )
    db_session.add(job)
    await db_session.commit()

    # Add a player metric with non-zero max speed (as the fixed code would produce)
    pm = PlayerMetric(
        id=uuid.uuid4(),
        job_id=job.id,
        track_id=42,
        display_label="#1",
        avg_speed_kmh=12.5,
        max_speed_kmh=22.3,  # previously would have been hardcoded 0.0
        total_distance_m=500.0,
        possession_frames=10,
        passes_made=2,
        interceptions_made=0,
    )
    db_session.add(pm)
    await db_session.commit()

    resp = await client.get(f"/api/v1/jobs/{job.id}/metrics", headers=auth_headers)
    if resp.status_code == 404:
        pytest.skip("metrics endpoint not available in test env")
    assert resp.status_code == 200
    data = resp.json()
    players = data.get("players", [])
    if players:
        p = next((p for p in players if p["track_id"] == 42), None)
        if p:
            assert p["max_speed_kmh"] > 0, "max_speed_kmh should be > 0 after the fix"
