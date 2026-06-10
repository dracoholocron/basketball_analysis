from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, require_role
from ..models.metrics import FrameMetric
from ..models.job import Job, JobStatus
from ..models.metrics import PlayerMetric
from ..models.game import Game
from ..models.team import Team
from ..models.player import Player
from ..models.player_game_stats import PlayerGameStats
from ..models.user import User
from ..schemas.metrics import GameMetrics, PlayerMetricRead

router = APIRouter(prefix="/games", tags=["metrics"])


async def _latest_done_job(db: AsyncSession, game_id: uuid.UUID) -> Job | None:
    result = await db.execute(
        select(Job)
        .where(Job.game_id == game_id, Job.status == JobStatus.DONE)
        .order_by(Job.finished_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


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

    t1 = [p for p in player_metrics if p.team_id == 1]
    t2 = [p for p in player_metrics if p.team_id == 2]

    # Resolve real team names (team_id 1 = home, 2 = away)
    home_name = away_name = None
    game = await db.get(Game, game_id)
    if game is not None:
        if game.home_team_id:
            ht = await db.get(Team, game.home_team_id)
            home_name = ht.name if ht else None
        if game.away_team_id:
            at = await db.get(Team, game.away_team_id)
            away_name = at.name if at else None

    return GameMetrics(
        game_id=game_id,
        job_id=job.id,
        home_team_name=home_name,
        away_team_name=away_name,
        total_frames=total_frames,
        team1_possession_pct=round(100 * t1_poss / total_poss, 1),
        team2_possession_pct=round(100 * t2_poss / total_poss, 1),
        team1_passes=sum(p.passes_made for p in t1),
        team2_passes=sum(p.passes_made for p in t2),
        team1_interceptions=sum(p.interceptions_made for p in t1),
        team2_interceptions=sum(p.interceptions_made for p in t2),
        team1_shots_attempted=sum(p.shots_attempted for p in t1),
        team2_shots_attempted=sum(p.shots_attempted for p in t2),
        team1_rebounds=sum(p.rebounds for p in t1),
        team2_rebounds=sum(p.rebounds for p in t2),
        team1_steals_cv=sum(p.steals_cv for p in t1),
        team2_steals_cv=sum(p.steals_cv for p in t2),
        players=[PlayerMetricRead.model_validate(p) for p in player_metrics],
    )


# ── Roster mapping: link detected (team, dorsal) identities → real players ──────

class RosterPlayer(BaseModel):
    id: uuid.UUID
    name: str
    jersey_number: str | None = None


class MappingIdentity(BaseModel):
    track_id: int
    display_label: str | None = None
    jersey_number: str | None = None
    team_id: int | None = None          # 1 = home, 2 = away
    minutes_played: float = 0.0
    player_id: uuid.UUID | None = None   # currently linked player


class PlayerMappingRead(BaseModel):
    game_id: uuid.UUID
    job_id: uuid.UUID
    home_team: RosterPlayer | None = None  # reuse: id+name (jersey unused)
    away_team: RosterPlayer | None = None
    home_roster: list[RosterPlayer] = []
    away_roster: list[RosterPlayer] = []
    identities: list[MappingIdentity] = []


class PlayerMapItem(BaseModel):
    track_id: int
    player_id: uuid.UUID | None = None      # link to an existing player
    new_player_name: str | None = None      # or create a player with this name
    team_id: int | None = None              # 1/2 → home/away (for creation)
    jersey_number: str | None = None        # for creation / info


class PlayerMappingUpdate(BaseModel):
    mappings: list[PlayerMapItem]


@router.get("/{game_id}/player-mapping", response_model=PlayerMappingRead)
async def get_player_mapping(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    job = await _latest_done_job(db, game_id)
    if not job:
        raise HTTPException(status_code=404, detail="No completed analysis found for this game")
    game = await db.get(Game, game_id)

    async def _roster(team_uuid):
        if not team_uuid:
            return None, []
        team = await db.get(Team, team_uuid)
        res = await db.execute(select(Player).where(Player.team_id == team_uuid).order_by(Player.name))
        players = [RosterPlayer(id=p.id, name=p.name, jersey_number=p.jersey_number) for p in res.scalars().all()]
        return (RosterPlayer(id=team.id, name=team.name) if team else None), players

    home_team, home_roster = await _roster(game.home_team_id if game else None)
    away_team, away_roster = await _roster(game.away_team_id if game else None)

    res = await db.execute(select(PlayerMetric).where(PlayerMetric.job_id == job.id))
    identities = [
        MappingIdentity(
            track_id=pm.track_id, display_label=pm.display_label,
            jersey_number=pm.jersey_number, team_id=pm.team_id,
            minutes_played=pm.minutes_played or 0.0, player_id=pm.player_id,
        )
        for pm in res.scalars().all()
    ]
    # Surface the most relevant first: identified (dorsal) then by minutes
    identities.sort(key=lambda i: (i.jersey_number is None, -i.minutes_played))
    return PlayerMappingRead(
        game_id=game_id, job_id=job.id,
        home_team=home_team, away_team=away_team,
        home_roster=home_roster, away_roster=away_roster,
        identities=identities,
    )


@router.put("/{game_id}/player-mapping", response_model=PlayerMappingRead)
async def put_player_mapping(
    game_id: uuid.UUID,
    payload: PlayerMappingUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin", "coach")),
):
    """Link detected identities (by track_id) to real players, or create players from
    detected dorsales — WITHOUT re-running the analysis. Updates PlayerMetric.player_id."""
    job = await _latest_done_job(db, game_id)
    if not job:
        raise HTTPException(status_code=404, detail="No completed analysis found for this game")
    game = await db.get(Game, game_id)
    team_uuid_by_no = {1: game.home_team_id if game else None, 2: game.away_team_id if game else None}

    # Index this job's PlayerMetric rows by track_id
    res = await db.execute(select(PlayerMetric).where(PlayerMetric.job_id == job.id))
    pm_by_track = {pm.track_id: pm for pm in res.scalars().all()}

    for item in payload.mappings:
        pm = pm_by_track.get(item.track_id)
        if pm is None:
            continue
        player_id = item.player_id
        if player_id is None and item.new_player_name:
            team_uuid = team_uuid_by_no.get(item.team_id or pm.team_id)
            new_player = Player(
                team_id=team_uuid, name=item.new_player_name.strip(),
                jersey_number=item.jersey_number or pm.jersey_number,
            )
            db.add(new_player)
            await db.flush()  # get id
            player_id = new_player.id
        pm.player_id = player_id  # may be None to unlink
    await db.commit()

    # Populate the unified player_game_stats (CV family) for the just-mapped players,
    # so profiles/season aggregates fill in WITHOUT re-running the analysis.
    await _upsert_pgs_from_mapping(db, game, job.id)
    return await get_player_mapping(game_id, db, _)  # type: ignore[arg-type]


async def _upsert_pgs_from_mapping(db: AsyncSession, game: Game | None, job_id: uuid.UUID) -> None:
    if game is None:
        return
    team_uuid_by_no = {1: game.home_team_id, 2: game.away_team_id}
    res = await db.execute(
        select(PlayerMetric).where(PlayerMetric.job_id == job_id, PlayerMetric.player_id.isnot(None))
    )
    for pm in res.scalars().all():
        ex = await db.execute(
            select(PlayerGameStats).where(
                PlayerGameStats.player_id == pm.player_id,
                PlayerGameStats.game_id == game.id,
            )
        )
        pgs = ex.scalar_one_or_none()
        is_new = pgs is None
        if is_new:
            pgs = PlayerGameStats(player_id=pm.player_id, game_id=game.id)
        pgs.season_id = game.season_id
        pgs.team_id = team_uuid_by_no.get(pm.team_id)
        pgs.job_id = job_id
        pgs.minutes_played = pm.minutes_played or 0.0
        pgs.distance_m = pm.total_distance_m or 0.0
        pgs.avg_speed_kmh = pm.avg_speed_kmh or 0.0
        pgs.max_speed_kmh = pm.max_speed_kmh or 0.0
        pgs.possession_frames = pm.possession_frames or 0
        pgs.shots_attempted_cv = pm.shots_attempted or 0
        pgs.shots_made_cv = pm.shots_made or 0
        pgs.shots_missed_cv = pm.shots_missed or 0
        pgs.rebounds_cv = pm.rebounds or 0
        pgs.steals_cv = pm.steals_cv or 0
        pgs.passes_cv = pm.passes_made or 0
        if pgs.source != "both":
            pgs.source = "both" if pgs.pts is not None else "cv"
        if is_new:
            db.add(pgs)
    await db.commit()
