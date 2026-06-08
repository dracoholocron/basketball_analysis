"""
Integration tests for GET /jobs filtering by game_id and status.

Verifies the new query parameters added in Phase 2.2 of the plan.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.job import Job, JobStatus, JobStage


async def _create_job(
    db: AsyncSession,
    game_id: uuid.UUID,
    status: JobStatus = JobStatus.DONE,
) -> Job:
    j = Job(
        id=uuid.uuid4(),
        game_id=game_id,
        status=status,
        current_stage=JobStage.COMPLETE if status == JobStatus.DONE else JobStage.QUEUED,
    )
    db.add(j)
    await db.commit()
    await db.refresh(j)
    return j


@pytest.mark.asyncio
async def test_list_jobs_no_filter_returns_all(
    client: AsyncClient,
    db_session: AsyncSession,
    game: Game,
    auth_headers: dict,
):
    """GET /jobs without filters returns jobs (backwards compatible)."""
    await _create_job(db_session, game.id, JobStatus.DONE)
    resp = await client.get("/api/v1/jobs", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_jobs_filter_by_game_id(
    client: AsyncClient,
    db_session: AsyncSession,
    season,
    team,
    away_team,
    auth_headers: dict,
):
    """GET /jobs?game_id=X returns only jobs for that game."""
    from datetime import date

    game_a = Game(
        id=uuid.uuid4(),
        season_id=season.id,
        home_team_id=team.id,
        away_team_id=away_team.id,
        game_date=date(2024, 11, 1),
        location="Arena A",
    )
    game_b = Game(
        id=uuid.uuid4(),
        season_id=season.id,
        home_team_id=team.id,
        away_team_id=away_team.id,
        game_date=date(2024, 11, 2),
        location="Arena B",
    )
    db_session.add_all([game_a, game_b])
    await db_session.commit()

    job_a = await _create_job(db_session, game_a.id, JobStatus.DONE)
    await _create_job(db_session, game_b.id, JobStatus.DONE)

    resp = await client.get(
        "/api/v1/jobs",
        params={"game_id": str(game_a.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [j["id"] for j in data]
    assert str(job_a.id) in ids, "Job for game_a should be in results"
    for j in data:
        assert j["game_id"] == str(game_a.id), f"Unexpected game_id {j['game_id']}"


@pytest.mark.asyncio
async def test_list_jobs_filter_by_status(
    client: AsyncClient,
    db_session: AsyncSession,
    game: Game,
    auth_headers: dict,
):
    """GET /jobs?status=done returns only done jobs."""
    done_job = await _create_job(db_session, game.id, JobStatus.DONE)
    running_job = await _create_job(db_session, game.id, JobStatus.RUNNING)

    resp = await client.get(
        "/api/v1/jobs",
        params={"game_id": str(game.id), "status": "done"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = [j["id"] for j in data]
    assert str(done_job.id) in ids
    assert str(running_job.id) not in ids, "Running job should not appear when filtering done"

    resp2 = await client.get(
        "/api/v1/jobs",
        params={"game_id": str(game.id), "status": "running"},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    ids2 = [j["id"] for j in resp2.json()]
    assert str(running_job.id) in ids2
    assert str(done_job.id) not in ids2


@pytest.mark.asyncio
async def test_list_jobs_combined_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    season,
    team,
    away_team,
    auth_headers: dict,
):
    """GET /jobs?game_id=X&status=done returns only done jobs for that game."""
    from datetime import date

    game_x = Game(
        id=uuid.uuid4(),
        season_id=season.id,
        home_team_id=team.id,
        away_team_id=away_team.id,
        game_date=date(2024, 12, 1),
        location="Arena X",
    )
    game_y = Game(
        id=uuid.uuid4(),
        season_id=season.id,
        home_team_id=team.id,
        away_team_id=away_team.id,
        game_date=date(2024, 12, 2),
        location="Arena Y",
    )
    db_session.add_all([game_x, game_y])
    await db_session.commit()

    done_x = await _create_job(db_session, game_x.id, JobStatus.DONE)
    running_x = await _create_job(db_session, game_x.id, JobStatus.RUNNING)
    done_y = await _create_job(db_session, game_y.id, JobStatus.DONE)

    resp = await client.get(
        "/api/v1/jobs",
        params={"game_id": str(game_x.id), "status": "done"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = [j["id"] for j in data]
    assert str(done_x.id) in ids
    assert str(running_x.id) not in ids, "Running job must be excluded"
    assert str(done_y.id) not in ids, "Job from another game must be excluded"
