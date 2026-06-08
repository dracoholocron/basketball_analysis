"""CSV import for box scores."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.box_score import BoxScore
from app.models.game import Game
from app.models.team import Team

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_box_scores.csv"
EXPECTED_PLAYER_ROWS = 3
EXPECTED_TEAM_PTS = 66  # 30 + 24 + 12
EXPECTED_TEAM_FGM = 23  # 10 + 8 + 5


@pytest.mark.asyncio
async def test_import_box_scores_csv(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    game: Game,
    team: Team,
):
    csv_bytes = FIXTURE_CSV.read_bytes()
    resp = await client.post(
        f"/api/v1/box-scores/import-csv?game_id={game.id}&team_id={team.id}",
        files={"file": ("sample_box_scores.csv", csv_bytes, "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == EXPECTED_PLAYER_ROWS
    assert body["skipped"] == 0
    assert "message" in body

    result = await db_session.execute(
        select(BoxScore)
        .where(BoxScore.game_id == game.id, BoxScore.team_id == team.id)
        .options(selectinload(BoxScore.player_box_scores))
    )
    box_score = result.scalar_one()
    assert box_score.pts == EXPECTED_TEAM_PTS
    assert box_score.fgm == EXPECTED_TEAM_FGM
    assert len(box_score.player_box_scores) == EXPECTED_PLAYER_ROWS

    names = {p.player_name for p in box_score.player_box_scores}
    assert names == {"Alex Johnson", "Sam Rivera", "Jordan Lee"}
