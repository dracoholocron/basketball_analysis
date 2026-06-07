"""Play Builder CRUD endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.play import Play
from ..schemas.play import PlayCreate, PlayRead, PlayUpdate

router = APIRouter(prefix="/plays", tags=["plays"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")

SEED_PLAYS = [
    {"name": "Pick & Roll", "category": "set_play", "description": "Classic ball-handler pick and roll action", "tags": ["Offensive Set", "P&R"], "pace": "medium-to-fast"},
    {"name": "Horns", "category": "set_play", "description": "Two bigs at the elbows with guards at corners", "tags": ["Offensive Set", "Horns"], "pace": "medium"},
    {"name": "Flex", "category": "set_play", "description": "Continuous flex cuts and down screens", "tags": ["Offensive Set", "Flex"], "pace": "slow-to-medium"},
    {"name": "Princeton", "category": "set_play", "description": "Back-door cuts from the high post", "tags": ["Offensive Set", "Princeton"], "pace": "slow"},
    {"name": "Motion Offense", "category": "system", "description": "5-out motion with spacing principles", "tags": ["System", "5-out"], "pace": "medium"},
    {"name": "Floppy", "category": "set_play", "description": "Off-ball screens to free shooters", "tags": ["Offensive Set", "Shooter"], "pace": "medium"},
    {"name": "Spain Pick & Roll", "category": "set_play", "description": "Pick & roll with back screen on roller", "tags": ["Offensive Set", "P&R"], "pace": "fast"},
    {"name": "Hammer", "category": "set_play", "description": "Corner shooter off baseline cut from DHO", "tags": ["Offensive Set", "Shooter"], "pace": "medium-to-fast"},
    {"name": "Zipper", "category": "set_play", "description": "Guard cuts to ball on wing for action", "tags": ["Offensive Set"], "pace": "medium"},
    {"name": "Pin Down", "category": "set_play", "description": "Big screens for shooter cutting up from corner", "tags": ["Offensive Set", "Shooter"], "pace": "slow-to-medium"},
    {"name": "Blob (Baseline OB)", "category": "inbound", "description": "Baseline out-of-bounds play", "tags": ["Inbound", "Baseline"], "pace": "medium"},
    {"name": "Slob (Sideline OB)", "category": "inbound", "description": "Sideline out-of-bounds play", "tags": ["Inbound", "Sideline"], "pace": "medium"},
    {"name": "Zone Attack", "category": "set_play", "description": "vs 2-3 zone — skip passes and hi-lo", "tags": ["Offensive Set", "vs Zone"], "pace": "slow"},
    {"name": "Press Break", "category": "system", "description": "Full-court press breaker with outlets", "tags": ["System", "Press Break"], "pace": "fast"},
]


async def _seed_plays(db: AsyncSession) -> None:
    """Seed the database with template plays if none exist."""
    result = await db.execute(select(Play).where(Play.is_template == True).limit(1))
    if result.scalar_one_or_none() is None:
        for p in SEED_PLAYS:
            play = Play(
                name=p["name"],
                category=p["category"],
                description=p["description"],
                tags=p.get("tags"),
                pace=p.get("pace"),
                is_template=True,
                shared=True,
                svg_data={"version": 1, "players": [], "arrows": [], "freeform_paths": []},
            )
            db.add(play)
        await db.commit()


@router.get("", response_model=list[PlayRead])
async def list_plays(
    skip: int = 0,
    limit: int = 50,
    matchup_id: uuid.UUID | None = None,
    category: str | None = None,
    pace: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    await _seed_plays(db)
    q = select(Play).order_by(Play.is_template.desc(), Play.name)
    if org_id is not None:
        q = q.where(or_(Play.organization_id == org_id, Play.is_template == True))
    if matchup_id is not None:
        q = q.where(Play.linked_matchup_id == matchup_id)
    if category is not None:
        q = q.where(Play.category == category)
    if pace is not None:
        q = q.where(Play.pace == pace)
    result = await db.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@router.post("/import-pdf", response_model=PlayRead, status_code=status.HTTP_201_CREATED)
async def import_play_pdf(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    """Import a play from a PDF file. Stores the filename as the play name."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="File must be a PDF")
    play_name = file.filename.replace(".pdf", "").replace("_", " ").replace("-", " ")
    play = Play(
        name=play_name,
        category="imported",
        description=f"Imported from PDF: {file.filename}",
        svg_data=None,
        svg_data_version=1,
        organization_id=org_id,
        is_template=False,
        shared=False,
        tags=["Imported"],
    )
    db.add(play)
    await db.commit()
    await db.refresh(play)
    return play


@router.get("/{play_id}", response_model=PlayRead)
async def get_play(
    play_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    play = await db.get(Play, play_id)
    if play is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Play not found")
    return play


@router.post("", response_model=PlayRead, status_code=status.HTTP_201_CREATED)
async def create_play(
    payload: PlayCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    play = Play(**payload.model_dump())
    db.add(play)
    await db.commit()
    await db.refresh(play)
    return play


@router.put("/{play_id}", response_model=PlayRead)
async def update_play(
    play_id: uuid.UUID,
    payload: PlayUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    play = await db.get(Play, play_id)
    if play is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Play not found")
    update_data = payload.model_dump(exclude_unset=True)
    # Auto-set version=2 when frames is present in svg_data
    if "svg_data" in update_data and isinstance(update_data["svg_data"], dict):
        if "frames" in update_data["svg_data"]:
            update_data["svg_data"]["version"] = 2
            update_data["svg_data_version"] = 2
    for field, value in update_data.items():
        setattr(play, field, value)
    await db.commit()
    await db.refresh(play)
    return play


@router.delete("/{play_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_play(
    play_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    play = await db.get(Play, play_id)
    if play is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Play not found")
    if play.is_template:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete template plays")
    await db.delete(play)
    await db.commit()
