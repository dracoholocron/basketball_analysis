"""Box score CRUD and import endpoints."""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import require_role
from ..models.box_score import BoxScore, PlayerBoxScore
from ..schemas.box_score import BoxScoreCreate, BoxScoreRead

router = APIRouter(prefix="/box-scores", tags=["box-scores"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")


def _validate_pts_consistency(pts: int, fgm: int, fg3m: int, ftm: int) -> None:
    """Validate that points are consistent with field goals and free throws."""
    expected = 2 * fgm + 3 * fg3m + ftm
    if abs(pts - expected) > 5:
        raise HTTPException(
            status_code=400,
            detail=(
                f"pts={pts} is inconsistent with fgm={fgm}, fg3m={fg3m}, ftm={ftm}. "
                f"Expected ~{expected} (2*fgm + 3*fg3m + ftm)."
            ),
        )


@router.get("", response_model=list[BoxScoreRead])
async def list_box_scores(
    game_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    q = (
        select(BoxScore)
        .options(selectinload(BoxScore.player_box_scores))
        .order_by(BoxScore.created_at.desc())
    )
    if game_id is not None:
        q = q.where(BoxScore.game_id == game_id)
    if team_id is not None:
        q = q.where(BoxScore.team_id == team_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=BoxScoreRead, status_code=status.HTTP_201_CREATED)
async def create_box_score(
    payload: BoxScoreCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    _validate_pts_consistency(payload.pts, payload.fgm, payload.fg3m, payload.ftm)

    box_score = BoxScore(
        game_id=payload.game_id,
        team_id=payload.team_id,
        pts=payload.pts, fgm=payload.fgm, fga=payload.fga,
        fg3m=payload.fg3m, fg3a=payload.fg3a,
        ftm=payload.ftm, fta=payload.fta,
        oreb=payload.oreb, dreb=payload.dreb,
        ast=payload.ast, stl=payload.stl, blk=payload.blk,
        tov=payload.tov, pf=payload.pf,
    )
    db.add(box_score)
    await db.flush()

    for p in payload.players:
        ps = PlayerBoxScore(
            box_score_id=box_score.id,
            player_id=p.player_id,
            player_name=p.player_name,
            jersey_number=p.jersey_number,
            minutes_played=p.minutes_played,
            pts=p.pts, fgm=p.fgm, fga=p.fga,
            fg3m=p.fg3m, fg3a=p.fg3a,
            ftm=p.ftm, fta=p.fta,
            oreb=p.oreb, dreb=p.dreb,
            ast=p.ast, stl=p.stl, blk=p.blk,
            tov=p.tov, pf=p.pf,
            plus_minus=p.plus_minus,
        )
        db.add(ps)

    await db.commit()
    result = await db.execute(
        select(BoxScore)
        .where(BoxScore.id == box_score.id)
        .options(selectinload(BoxScore.player_box_scores))
    )
    return result.scalar_one()


@router.delete("/{box_score_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_box_score(
    box_score_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    bs = await db.get(BoxScore, box_score_id)
    if bs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Box score not found")
    await db.delete(bs)
    await db.commit()


# ── Team Averages ──────────────────────────────────────────────────────────────

class TeamAveragesRead(BaseModel):
    team_id: str
    games_played: int
    avg_pts: float
    avg_fgm: float
    avg_fga: float
    avg_fg3m: float
    avg_fg3a: float
    avg_ftm: float
    avg_fta: float
    avg_oreb: float
    avg_dreb: float
    avg_reb: float
    avg_ast: float
    avg_stl: float
    avg_blk: float
    avg_tov: float
    fg_pct: float
    fg3_pct: float
    ft_pct: float


@router.get("/team-averages", response_model=TeamAveragesRead)
async def get_team_averages(
    team_id: uuid.UUID = Query(...),
    season_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Return aggregated box score averages for a team, optionally filtered by season."""
    q = select(BoxScore).where(BoxScore.team_id == team_id)
    if season_id is not None:
        from ..models.game import Game
        subq = select(Game.id).where(Game.season_id == season_id)
        q = q.where(BoxScore.game_id.in_(subq))
    result = await db.execute(q)
    scores = result.scalars().all()

    if not scores:
        raise HTTPException(status_code=404, detail="No box scores found for this team")

    n = len(scores)
    stat_fields = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "ast", "stl", "blk", "tov"]
    avgs: dict[str, Any] = {"team_id": str(team_id), "games_played": n}
    for f in stat_fields:
        avgs[f"avg_{f}"] = round(sum(getattr(s, f, 0) or 0 for s in scores) / n, 2)

    avgs["avg_reb"] = round(avgs["avg_oreb"] + avgs["avg_dreb"], 2)
    avgs["fg_pct"] = round(avgs["avg_fgm"] / avgs["avg_fga"], 3) if avgs["avg_fga"] > 0 else 0.0
    avgs["fg3_pct"] = round(avgs["avg_fg3m"] / avgs["avg_fg3a"], 3) if avgs["avg_fg3a"] > 0 else 0.0
    avgs["ft_pct"] = round(avgs["avg_ftm"] / avgs["avg_fta"], 3) if avgs["avg_fta"] > 0 else 0.0
    return avgs


# ── CSV Import ─────────────────────────────────────────────────────────────────

class ImportResult(BaseModel):
    message: str
    imported: int
    skipped: int


@router.post("/import", response_model=ImportResult)
async def import_box_scores(
    game_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    """
    Import box scores via game_id. Currently a stub that returns a message
    directing users to use the manual entry form for individual game import.
    Full CSV import requires uploading a file via multipart/form-data.
    """
    # Check game exists
    from ..models.game import Game
    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    # Count existing box scores for this game
    result = await db.execute(select(BoxScore).where(BoxScore.game_id == game_id))
    existing = result.scalars().all()

    return ImportResult(
        message=(
            f"Game {str(game_id)[:8]} has {len(existing)} box score(s). "
            "Upload a CSV via POST /box-scores/import-csv (multipart) or use manual entry."
        ),
        imported=0,
        skipped=len(existing),
    )


_CSV_INT_STAT_FIELDS = (
    "pts",
    "fgm",
    "fga",
    "fg3m",
    "fg3a",
    "ftm",
    "fta",
    "oreb",
    "dreb",
    "ast",
    "stl",
    "blk",
    "tov",
    "pf",
    "plus_minus",
)


def _normalize_csv_row(raw: dict[str, Any]) -> dict[str, str]:
    return {
        (k or "").strip().lower(): ("" if v is None else str(v)).strip()
        for k, v in raw.items()
        if k is not None and str(k).strip()
    }


def _parse_csv_int(value: str, default: int = 0) -> int:
    if not value:
        return default
    return int(float(value))


def _parse_csv_float_optional(value: str) -> float | None:
    if not value:
        return None
    return float(value)


def _parse_player_csv_row(row: dict[str, str]) -> dict[str, Any]:
    name = row.get("player_name", "").strip()
    if not name:
        raise ValueError("player_name is required")

    parsed: dict[str, Any] = {
        "player_name": name,
        "jersey_number": row.get("jersey_number") or None,
        "minutes_played": _parse_csv_float_optional(row.get("minutes_played", "")),
        "player_id": None,
    }
    for field in _CSV_INT_STAT_FIELDS:
        parsed[field] = _parse_csv_int(row.get(field, ""), 0)
    return parsed


@router.post("/import-csv", response_model=ImportResult)
async def import_box_scores_csv(
    game_id: uuid.UUID = Query(...),
    team_id: uuid.UUID = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
):
    """
    Import per-player box score rows from CSV and derive team totals by summing players.

    If a box score already exists for (game_id, team_id), it is replaced (delete + recreate).
    """
    from ..models.game import Game

    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV is empty or missing a header row")

    imported = 0
    skipped = 0
    player_rows: list[dict[str, Any]] = []

    for raw in reader:
        try:
            normalized = _normalize_csv_row(raw)
            if not any(normalized.values()):
                continue
            player_rows.append(_parse_player_csv_row(normalized))
            imported += 1
        except (ValueError, TypeError):
            skipped += 1

    if not player_rows:
        return ImportResult(
            message="No player rows imported. Check CSV headers and player_name column.",
            imported=0,
            skipped=skipped,
        )

    team_totals = {f: 0 for f in _CSV_INT_STAT_FIELDS if f != "plus_minus"}
    for pr in player_rows:
        for f in team_totals:
            team_totals[f] += pr[f]

    _validate_pts_consistency(
        team_totals["pts"],
        team_totals["fgm"],
        team_totals["fg3m"],
        team_totals["ftm"],
    )

    existing_result = await db.execute(
        select(BoxScore).where(BoxScore.game_id == game_id, BoxScore.team_id == team_id)
    )
    existing_scores = existing_result.scalars().all()
    had_existing = bool(existing_scores)
    for existing_bs in existing_scores:
        await db.delete(existing_bs)
    await db.flush()

    box_score = BoxScore(
        game_id=game_id,
        team_id=team_id,
        pts=team_totals["pts"],
        fgm=team_totals["fgm"],
        fga=team_totals["fga"],
        fg3m=team_totals["fg3m"],
        fg3a=team_totals["fg3a"],
        ftm=team_totals["ftm"],
        fta=team_totals["fta"],
        oreb=team_totals["oreb"],
        dreb=team_totals["dreb"],
        ast=team_totals["ast"],
        stl=team_totals["stl"],
        blk=team_totals["blk"],
        tov=team_totals["tov"],
        pf=team_totals["pf"],
    )
    db.add(box_score)
    await db.flush()

    for pr in player_rows:
        db.add(
            PlayerBoxScore(
                box_score_id=box_score.id,
                player_id=pr["player_id"],
                player_name=pr["player_name"],
                jersey_number=pr["jersey_number"],
                minutes_played=pr["minutes_played"],
                pts=pr["pts"],
                fgm=pr["fgm"],
                fga=pr["fga"],
                fg3m=pr["fg3m"],
                fg3a=pr["fg3a"],
                ftm=pr["ftm"],
                fta=pr["fta"],
                oreb=pr["oreb"],
                dreb=pr["dreb"],
                ast=pr["ast"],
                stl=pr["stl"],
                blk=pr["blk"],
                tov=pr["tov"],
                pf=pr["pf"],
                plus_minus=pr["plus_minus"],
            )
        )

    await db.commit()

    replaced_note = " Replaced existing box score for this game/team." if had_existing else ""
    return ImportResult(
        message=(
            f"Imported {imported} player row(s) for game {str(game_id)[:8]} / team {str(team_id)[:8]}."
            f"{replaced_note} Skipped {skipped} row(s)."
        ),
        imported=imported,
        skipped=skipped,
    )
