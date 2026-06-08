"""Playbook CRUD endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role, get_current_org_id
from ..models.play import Play
from ..models.playbook import Playbook
from ..schemas.playbook import PlaybookCreate, PlaybookRead, PlaybookUpdate

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

_staff = require_role("admin", "coach")
_admin = require_role("admin")


async def _playbook_with_count(db: AsyncSession, pb: Playbook) -> PlaybookRead:
    count_result = await db.execute(
        select(func.count()).where(Play.playbook_id == pb.id)
    )
    count = count_result.scalar_one()
    data = PlaybookRead.model_validate(pb)
    data.play_count = count
    return data


@router.get("", response_model=list[PlaybookRead])
async def list_playbooks(
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    q = select(Playbook).order_by(Playbook.is_system.desc(), Playbook.name)
    if org_id is not None:
        q = q.where(or_(Playbook.organization_id == org_id, Playbook.is_system == True))
    result = await db.execute(q)
    playbooks = result.scalars().all()
    return [await _playbook_with_count(db, pb) for pb in playbooks]


@router.post("", response_model=PlaybookRead, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    payload: PlaybookCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    pb = Playbook(
        name=payload.name,
        description=payload.description,
        organization_id=org_id,
        is_system=False,
    )
    db.add(pb)
    await db.commit()
    await db.refresh(pb)
    return await _playbook_with_count(db, pb)


@router.get("/{playbook_id}", response_model=PlaybookRead)
async def get_playbook(
    playbook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    pb = await db.get(Playbook, playbook_id)
    if pb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    if not pb.is_system and org_id is not None and pb.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return await _playbook_with_count(db, pb)


@router.put("/{playbook_id}", response_model=PlaybookRead)
async def update_playbook(
    playbook_id: uuid.UUID,
    payload: PlaybookUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    pb = await db.get(Playbook, playbook_id)
    if pb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    if pb.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify system playbooks")
    if org_id is not None and pb.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pb, field, value)
    await db.commit()
    await db.refresh(pb)
    return await _playbook_with_count(db, pb)


@router.delete("/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    playbook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
):
    pb = await db.get(Playbook, playbook_id)
    if pb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    if pb.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete system playbooks")
    if org_id is not None and pb.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    # Plays keep their data — only playbook_id is NULLed via ON DELETE SET NULL
    await db.delete(pb)
    await db.commit()
