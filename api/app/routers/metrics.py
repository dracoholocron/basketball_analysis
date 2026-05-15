from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.metrics import FrameMetric
from ..models.job import Job, JobStatus
from ..models.metrics import PlayerMetric
from ..models.user import User
from ..schemas.metrics import GameMetrics, PlayerMetricRead

router = APIRouter(prefix="/games", tags=["metrics"])


@router.get("/{game_id}/metrics", response_model=GameMetrics)
async def get_game_metrics(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Find the most recent completed job for this game
    result = await db.execute(
        select(Job)
        .where(Job.game_id == game_id, Job.status == JobStatus.DONE)
        .order_by(Job.finished_at.desc())
        .limit(1)
    )
    job: Job | None = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="No completed analysis found for this game")

    pm_result = await db.execute(
        select(PlayerMetric).where(PlayerMetric.job_id == job.id)
    )
    player_metrics = pm_result.scalars().all()

    fm_result = await db.execute(
        select(func.count()).select_from(FrameMetric).where(FrameMetric.job_id == job.id)
    )
    total_frames = fm_result.scalar_one()

    t1_poss = sum(p.possession_frames for p in player_metrics if p.team_id == 1)
    t2_poss = sum(p.possession_frames for p in player_metrics if p.team_id == 2)
    total_poss = t1_poss + t2_poss or 1

    return GameMetrics(
        game_id=game_id,
        job_id=job.id,
        total_frames=total_frames,
        team1_possession_pct=round(100 * t1_poss / total_poss, 1),
        team2_possession_pct=round(100 * t2_poss / total_poss, 1),
        team1_passes=sum(p.passes_made for p in player_metrics if p.team_id == 1),
        team2_passes=sum(p.passes_made for p in player_metrics if p.team_id == 2),
        team1_interceptions=sum(p.interceptions_made for p in player_metrics if p.team_id == 1),
        team2_interceptions=sum(p.interceptions_made for p in player_metrics if p.team_id == 2),
        players=[PlayerMetricRead.model_validate(p) for p in player_metrics],
    )
