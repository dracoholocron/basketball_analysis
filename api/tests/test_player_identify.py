"""Player-identify popup backend: correcting a detected identity's dorsal/team via
player-mapping (no re-analysis), and preserving the player link on a number-only fix."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.models.job import Job, JobStatus, JobStage
from app.models.metrics import PlayerMetric
from app.models.player import Player


async def _seed_done_job(db_session, game) -> Job:
    job = Job(
        id=uuid.uuid4(), game_id=game.id, status=JobStatus.DONE,
        current_stage=JobStage.COMPLETE, progress_pct=100,
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.add_all([
        PlayerMetric(job_id=job.id, track_id=7, display_label="#0", jersey_number=None,
                     team_id=1, minutes_played=12.0),
        PlayerMetric(job_id=job.id, track_id=9, display_label="#23", jersey_number="23",
                     team_id=2, minutes_played=8.0),
    ])
    await db_session.commit()
    return job


@pytest.mark.asyncio
async def test_correct_dorsal_and_team(client: AsyncClient, auth_headers, db_session, game):
    await _seed_done_job(db_session, game)

    r = await client.put(
        f"/api/v1/games/{game.id}/player-mapping",
        json={"mappings": [{"track_id": 7, "jersey_number": "11", "team_id": 2}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ident = {i["track_id"]: i for i in r.json()["identities"]}
    assert ident[7]["jersey_number"] == "11"
    assert ident[7]["team_id"] == 2
    assert ident[7]["display_label"] == "#11"


@pytest.mark.asyncio
async def test_number_only_fix_preserves_player_link(client: AsyncClient, auth_headers, db_session, game):
    job = await _seed_done_job(db_session, game)
    # Pre-link track 9 to a real player.
    pl = Player(team_id=game.away_team_id, name="Linked Star", jersey_number="23")
    db_session.add(pl)
    await db_session.commit()
    await db_session.refresh(pl)
    pm = (await db_session.execute(
        PlayerMetric.__table__.select().where(
            (PlayerMetric.job_id == job.id) & (PlayerMetric.track_id == 9))
    )).first()
    # set link directly
    from sqlalchemy import update
    await db_session.execute(
        update(PlayerMetric).where(PlayerMetric.job_id == job.id, PlayerMetric.track_id == 9)
        .values(player_id=pl.id))
    await db_session.commit()

    # Correct only the dorsal, forwarding the existing player_id (as the popup does).
    r = await client.put(
        f"/api/v1/games/{game.id}/player-mapping",
        json={"mappings": [{"track_id": 9, "jersey_number": "24", "player_id": str(pl.id)}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ident = {i["track_id"]: i for i in r.json()["identities"]}
    assert ident[9]["jersey_number"] == "24"
    assert ident[9]["player_id"] == str(pl.id)  # link preserved
