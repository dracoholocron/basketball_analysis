"""Phase C2: CV event corrections overlay (change type / reassign player track)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus, JobStage


async def _done_job_with_events(db: AsyncSession, game) -> Job:
    job = Job(
        id=uuid.uuid4(), game_id=game.id, status=JobStatus.DONE,
        current_stage=JobStage.COMPLETE,
        created_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
        cv_events_json=[
            {"event_type": "shot_attempt", "frame": 100, "time_s": 4.0, "team_id": 0, "player_track_id": 5},
            {"event_type": "pass", "frame": 200, "time_s": 8.0, "team_id": 1, "player_track_id": 7},
        ],
    )
    db.add(job)
    await db.commit()
    return job


@pytest.mark.asyncio
async def test_cv_event_correction_overlay(client: AsyncClient, auth_headers, db_session, game):
    await _done_job_with_events(db_session, game)

    # change event 0 type + reassign its player
    r = await client.patch(
        f"/api/v1/games/{game.id}/cv-events/0",
        json={"new_type": "shot_made", "new_player_track_id": 11}, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["event_type"] == "shot_made"
    assert r.json()["player_track_id"] == 11
    assert r.json()["edited"] is True

    # GET reflects the correction (idx 0) but leaves idx 1 untouched
    g = await client.get(f"/api/v1/games/{game.id}/cv-events", headers=auth_headers)
    evs = g.json()
    assert evs[0]["event_type"] == "shot_made" and evs[0]["player_track_id"] == 11 and evs[0]["edited"]
    assert evs[1]["event_type"] == "pass" and evs[1]["edited"] is False
    assert evs[0]["idx"] == 0 and evs[1]["idx"] == 1


@pytest.mark.asyncio
async def test_cv_event_correction_out_of_range(client: AsyncClient, auth_headers, db_session, game):
    await _done_job_with_events(db_session, game)
    r = await client.patch(
        f"/api/v1/games/{game.id}/cv-events/99",
        json={"new_type": "steal"}, headers=auth_headers,
    )
    assert r.status_code == 404
