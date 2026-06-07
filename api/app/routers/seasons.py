"""CRUD endpoints for Season + CSV box-score import."""
from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.box_score import BoxScore, PlayerBoxScore
from ..models.game import Game
from ..models.season import Season
from ..schemas.season import SeasonCreate, SeasonRead

router = APIRouter(prefix="/seasons", tags=["seasons"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")


@router.get("", response_model=list[SeasonRead])
async def list_seasons(
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    q = select(Season).order_by(Season.year.desc(), Season.name)
    if org_id is not None:
        q = q.where(Season.organization_id == org_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{season_id}", response_model=SeasonRead)
async def get_season(
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    season = await db.get(Season, season_id)
    if season is None or (org_id is not None and season.organization_id != org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    return season


@router.post("", response_model=SeasonRead, status_code=status.HTTP_201_CREATED)
async def create_season(
    payload: SeasonCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    resolved_org = payload.organization_id or org_id
    season = Season(
        organization_id=resolved_org,
        name=payload.name,
        year=payload.year,
    )
    db.add(season)
    await db.commit()
    await db.refresh(season)
    return season


@router.put("/{season_id}", response_model=SeasonRead)
async def update_season(
    season_id: uuid.UUID,
    payload: SeasonCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    season = await db.get(Season, season_id)
    if season is None or (org_id is not None and season.organization_id != org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(season, field, value)
    await db.commit()
    await db.refresh(season)
    return season


@router.delete("/{season_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_season(
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    season = await db.get(Season, season_id)
    if season is None or (org_id is not None and season.organization_id != org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    await db.delete(season)
    await db.commit()


@router.post("/{season_id}/import-box-scores", status_code=status.HTTP_201_CREATED)
async def import_box_scores_csv(
    season_id: uuid.UUID,
    game_id: uuid.UUID = Form(...),
    team_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    """
    Import a box score from a CSV file (HUDL/MaxPreps-compatible format).

    Expected CSV columns (case-insensitive, extra columns ignored):
    player_name, jersey_number, minutes_played, pts, fgm, fga, fg3m, fg3a,
    ftm, fta, oreb, dreb, ast, stl, blk, tov, pf, plus_minus

    Also accepts a TEAM row for game totals (player_name == "TEAM" or "Total").
    """
    # Verify season and game exist
    season = await db.get(Season, season_id)
    if season is None:
        raise HTTPException(status_code=404, detail="Season not found")

    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.season_id != season_id:
        raise HTTPException(status_code=400, detail="Game does not belong to this season")

    contents = await file.read()
    try:
        text = contents.decode("utf-8-sig")  # handles BOM from Excel exports
    except UnicodeDecodeError:
        text = contents.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    # Normalize header names
    rows = [{k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items()} for row in reader]

    if not rows:
        raise HTTPException(status_code=400, detail="CSV is empty")

    def _int(val: str, default: int = 0) -> int:
        try:
            return int(float(val)) if val else default
        except (ValueError, TypeError):
            return default

    def _float(val: str, default: float | None = None):
        try:
            return float(val) if val else default
        except (ValueError, TypeError):
            return default

    # Separate team totals row from player rows
    team_row = None
    player_rows = []
    for row in rows:
        name = row.get("player_name", row.get("name", "")).lower()
        if name in ("team", "total", "totals"):
            team_row = row
        else:
            player_rows.append(row)

    # Compute team totals from player rows if no explicit TEAM row
    def _sum_col(col: str) -> int:
        return sum(_int(r.get(col, "0")) for r in player_rows)

    if team_row:
        pts = _int(team_row.get("pts", "0"))
        fgm = _int(team_row.get("fgm", "0"))
        fga = _int(team_row.get("fga", "0"))
        fg3m = _int(team_row.get("fg3m", "0"))
        fg3a = _int(team_row.get("fg3a", "0"))
        ftm = _int(team_row.get("ftm", "0"))
        fta = _int(team_row.get("fta", "0"))
        oreb = _int(team_row.get("oreb", "0"))
        dreb = _int(team_row.get("dreb", "0"))
        ast = _int(team_row.get("ast", "0"))
        stl = _int(team_row.get("stl", "0"))
        blk = _int(team_row.get("blk", "0"))
        tov = _int(team_row.get("tov", "0"))
        pf = _int(team_row.get("pf", "0"))
    else:
        pts = _sum_col("pts")
        fgm = _sum_col("fgm")
        fga = _sum_col("fga")
        fg3m = _sum_col("fg3m")
        fg3a = _sum_col("fg3a")
        ftm = _sum_col("ftm")
        fta = _sum_col("fta")
        oreb = _sum_col("oreb")
        dreb = _sum_col("dreb")
        ast = _sum_col("ast")
        stl = _sum_col("stl")
        blk = _sum_col("blk")
        tov = _sum_col("tov")
        pf = _sum_col("pf")

    # Server-side consistency validation
    expected_pts = 2 * fgm + 3 * fg3m + ftm
    if pts > 0 and abs(pts - expected_pts) > 5:
        raise HTTPException(
            status_code=400,
            detail=(
                f"pts={pts} is inconsistent with fgm={fgm}, fg3m={fg3m}, ftm={ftm}. "
                f"Expected ~{expected_pts} (2*fgm + 3*fg3m + ftm)."
            ),
        )

    box_score = BoxScore(
        game_id=game_id,
        team_id=team_id,
        pts=pts, fgm=fgm, fga=fga,
        fg3m=fg3m, fg3a=fg3a,
        ftm=ftm, fta=fta,
        oreb=oreb, dreb=dreb,
        ast=ast, stl=stl, blk=blk,
        tov=tov, pf=pf,
    )
    db.add(box_score)
    await db.flush()

    for row in player_rows:
        name = row.get("player_name", row.get("name", ""))
        if not name:
            continue
        ps = PlayerBoxScore(
            box_score_id=box_score.id,
            player_name=name,
            jersey_number=row.get("jersey_number", row.get("jersey", row.get("#", None))),
            minutes_played=_float(row.get("minutes_played", row.get("min", ""))),
            pts=_int(row.get("pts", "0")),
            fgm=_int(row.get("fgm", "0")),
            fga=_int(row.get("fga", "0")),
            fg3m=_int(row.get("fg3m", "0")),
            fg3a=_int(row.get("fg3a", "0")),
            ftm=_int(row.get("ftm", "0")),
            fta=_int(row.get("fta", "0")),
            oreb=_int(row.get("oreb", "0")),
            dreb=_int(row.get("dreb", "0")),
            ast=_int(row.get("ast", "0")),
            stl=_int(row.get("stl", "0")),
            blk=_int(row.get("blk", "0")),
            tov=_int(row.get("tov", "0")),
            pf=_int(row.get("pf", "0")),
            plus_minus=_int(row.get("plus_minus", row.get("+/-", ""))) if row.get("plus_minus") or row.get("+/-") else None,
        )
        db.add(ps)

    await db.commit()
    await db.refresh(box_score)
    return {
        "box_score_id": str(box_score.id),
        "players_imported": len(player_rows),
        "pts": pts,
        "message": f"Imported {len(player_rows)} player rows for game {game_id}",
    }
