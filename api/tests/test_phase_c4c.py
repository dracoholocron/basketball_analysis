"""Phase C4c: shot heatmap endpoint built from CV shot events with court positions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.models.job import Job, JobStatus, JobStage


@pytest.mark.asyncio
async def test_shot_heatmap_from_cv_events(client: AsyncClient, auth_headers, db_session, game):
    job = Job(
        id=uuid.uuid4(), game_id=game.id, status=JobStatus.DONE,
        current_stage=JobStage.COMPLETE,
        created_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
        cv_events_json=[
            {"event_type": "shot_made", "frame": 10, "made": True, "x_pct": 0.12, "y_pct": 0.40},
            {"event_type": "shot_attempt", "frame": 20, "made": False, "x_pct": 0.85, "y_pct": 0.55},
            {"event_type": "shot_attempt", "frame": 30, "made": False},  # no position
            {"event_type": "pass", "frame": 40},  # not a shot
        ],
    )
    db_session.add(job)
    await db_session.commit()

    r = await client.get(f"/api/v1/games/{game.id}/shot-heatmap", headers=auth_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_shots"] == 3 and d["made_shots"] == 1
    assert d["positioned_shots"] == 2
    assert d["fg_pct"] == pytest.approx(1 / 3, abs=0.01)
    # 2 positioned shots → 2 cells with heat
    nonzero = sum(1 for row in d["heat_grid"] for c in row if c > 0)
    assert nonzero == 2


@pytest.mark.asyncio
async def test_shot_heatmap_empty_without_job(client: AsyncClient, auth_headers, game):
    r = await client.get(f"/api/v1/games/{game.id}/shot-heatmap", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total_shots"] == 0
