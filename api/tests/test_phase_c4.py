"""Phase C4: CV team stats from player_metrics (no roster), box-vs-CV comparison,
and CV per-player video-insights. Builds a minimal analyzed-game fixture in SQLite."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.job import Job, JobStatus, JobStage
from app.models.metrics import PlayerMetric
from app.models.box_score import BoxScore
from app.routers.matchups import _get_team_stats, _cv_player_rows


async def _analyzed_game_with_cv(db: AsyncSession, season, team, away_team):
    """A done job for a game (team=home → CV team_no 1) with a few player_metrics."""
    g = Game(id=uuid.uuid4(), season_id=season.id, home_team_id=team.id, away_team_id=away_team.id)
    db.add(g); await db.flush()
    job = Job(id=uuid.uuid4(), game_id=g.id, status=JobStatus.DONE,
              current_stage=JobStage.COMPLETE, created_at=datetime.now(timezone.utc))
    db.add(job); await db.flush()
    # team_no 1 (home) players with dorsals: 10 made of 25 attempts → cv_fg_pct 0.40
    rows = [
        ("10", 6, 12, 4, 3), ("7", 4, 13, 2, 2),  # made, att, reb, stl
    ]
    for jn, made, att, reb, stl in rows:
        db.add(PlayerMetric(
            id=uuid.uuid4(), job_id=job.id, track_id=int(jn), team_id=1,
            jersey_number=jn, display_label=f"#{jn}",
            shots_made=made, shots_attempted=att, rebounds=reb, steals_cv=stl,
            max_speed_kmh=14.0, total_distance_m=900.0,
        ))
    await db.commit()
    return g


@pytest.mark.asyncio
async def test_team_stats_cv_only_from_metrics(db_session, season, team, away_team):
    await _analyzed_game_with_cv(db_session, season, team, away_team)
    stats = await _get_team_stats(db_session, team.id)
    assert stats["data_sources"] == "cv"
    assert stats["cv_games"] == 1
    # 10 made / 25 attempts = 0.40
    assert stats["cv_fg_pct"] == pytest.approx(0.40, abs=0.001)
    assert "comparison" not in stats  # no box score yet


@pytest.mark.asyncio
async def test_team_stats_both_has_comparison(db_session, season, team, away_team):
    g = await _analyzed_game_with_cv(db_session, season, team, away_team)
    # add a team-level box score → data_sources should become "both" with a comparison
    db_session.add(BoxScore(id=uuid.uuid4(), game_id=g.id, team_id=team.id,
                            pts=50, fgm=20, fga=50))  # box fg_pct 0.40
    await db_session.commit()
    stats = await _get_team_stats(db_session, team.id)
    assert stats["data_sources"] == "both"
    assert "comparison" in stats and "fg_pct" in stats["comparison"]
    assert "fg_pct_blended" in stats


@pytest.mark.asyncio
async def test_cv_player_rows(db_session, season, team, away_team):
    await _analyzed_game_with_cv(db_session, season, team, away_team)
    rows = await _cv_player_rows(db_session, team.id)
    jerseys = {r["jersey_number"] for r in rows}
    assert {"10", "7"} <= jerseys
    top = rows[0]
    assert top["jersey_number"] == "10"  # most made → highest avg_pts
    assert top["fg_pct"] == pytest.approx(0.5, abs=0.001)  # 6/12
