"""Play Builder CRUD endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.play import Play
from ..models.playbook import Playbook
from ..schemas.play import PlayCreate, PlayRead, PlayUpdate
from ..services.play_library import build_template_seed_data, build_master_playbook_data

router = APIRouter(prefix="/plays", tags=["plays"])

_admin = require_role("admin")
_staff = require_role("admin", "coach")

# Seed version — bump to force re-seed when content changes
_SEED_VERSION = 2


async def _seed_plays(db: AsyncSession) -> None:
    """Idempotent seed: upsert 12 multi-frame templates + Master Playbook 2026.

    Uses svg_data_version==2 as the marker. Templates already at v2 are skipped.
    On first run or after a version bump the full frame data is written.
    """
    # ── 1. System Templates playbook ────────────────────────────────────────
    tmpl_pb_result = await db.execute(
        select(Playbook).where(Playbook.is_system == True, Playbook.name == "Plantillas del Sistema")
    )
    tmpl_pb = tmpl_pb_result.scalar_one_or_none()
    if tmpl_pb is None:
        tmpl_pb = Playbook(name="Plantillas del Sistema", is_system=True,
                           description="Official play templates with full multi-frame diagrams")
        db.add(tmpl_pb)
        await db.flush()

    # ── 2. Upsert 12 templates ────────────────────────────────────────────
    for seed in build_template_seed_data():
        result = await db.execute(
            select(Play).where(Play.name == seed["name"], Play.is_template == True)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            play = Play(**seed, playbook_id=tmpl_pb.id)
            db.add(play)
        elif existing.svg_data_version < _SEED_VERSION:
            existing.svg_data = seed["svg_data"]
            existing.svg_data_version = 2
            existing.description = seed["description"]
            existing.tags = seed["tags"]
            existing.pace = seed["pace"]
            if existing.playbook_id is None:
                existing.playbook_id = tmpl_pb.id

    # ── 3. Master Playbook 2026 ──────────────────────────────────────────
    master_pb_result = await db.execute(
        select(Playbook).where(Playbook.name == "Master Playbook 2026")
    )
    master_pb = master_pb_result.scalar_one_or_none()
    if master_pb is None:
        playbook_meta, plays_data = build_master_playbook_data()
        master_pb = Playbook(**playbook_meta)
        db.add(master_pb)
        await db.flush()
        for pd in plays_data:
            play = Play(**pd, playbook_id=master_pb.id)
            db.add(play)

    await db.commit()


@router.get("", response_model=list[PlayRead])
async def list_plays(
    skip: int = 0,
    limit: int = 100,
    matchup_id: uuid.UUID | None = None,
    playbook_id: uuid.UUID | None = None,
    category: str | None = None,
    pace: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    await _seed_plays(db)
    q = select(Play).order_by(Play.is_template.desc(), Play.name)
    if org_id is not None:
        # When filtering by playbook, also allow plays inside that playbook
        # regardless of organization (handles system playbooks like Master Playbook 2026)
        if playbook_id is not None:
            q = q.where(
                or_(Play.organization_id == org_id, Play.is_template == True, Play.playbook_id == playbook_id)
            )
        else:
            q = q.where(or_(Play.organization_id == org_id, Play.is_template == True))
    if matchup_id is not None:
        q = q.where(Play.linked_matchup_id == matchup_id)
    if playbook_id is not None:
        q = q.where(Play.playbook_id == playbook_id)
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
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    data = payload.model_dump()
    # User's org always takes precedence so the play is visible in list_plays
    data["organization_id"] = org_id or data.get("organization_id")
    play = Play(**data)
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
