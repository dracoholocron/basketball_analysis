"""Model version registry — list/activate/scan/delete versioned models per role.

The active version per role is what the pipeline loads at analysis time. Reverting to
a previous model is a one-click activate here (no worker rebuild). Files live in the
worker's models_data volume; registration/scan is done by the worker.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role
from ..models.model_version import ModelVersion
from ..worker.celery_app import celery_app

router = APIRouter(prefix="/models", tags=["models"])
_staff = require_role("admin", "coach")
_admin = require_role("admin")

ROLES = ("player", "ball", "court", "pose")


class ModelVersionRead(BaseModel):
    id: uuid.UUID
    role: str
    filename: str
    label: str | None = None
    source: str
    metrics: dict | None = None
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("")
async def list_model_versions(db: AsyncSession = Depends(get_db), _=Depends(_staff)):
    """All versions grouped by role, with the active one flagged."""
    rows = (await db.execute(select(ModelVersion).order_by(ModelVersion.created_at.desc()))).scalars().all()
    out: dict[str, list] = {r: [] for r in ROLES}
    for v in rows:
        out.setdefault(v.role, []).append(ModelVersionRead.model_validate(v).model_dump())
    return {"roles": out}


@router.post("/{version_id}/activate")
async def activate_model_version(
    version_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    """Activate this version and deactivate all others of the same role."""
    mv = await db.get(ModelVersion, version_id)
    if mv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    others = (await db.execute(
        select(ModelVersion).where(ModelVersion.role == mv.role, ModelVersion.is_active.is_(True))
    )).scalars().all()
    for o in others:
        o.is_active = False
    mv.is_active = True
    await db.commit()
    return {"ok": True, "role": mv.role, "active": mv.filename}


@router.post("/scan")
async def scan_models(_=Depends(_admin)):
    """Ask the worker (which has the models_data volume) to register any model files
    not yet in the registry. Returns the task id."""
    res = celery_app.send_task("app.worker.tasks.scan_models", queue="gpu")
    return {"task_id": res.id, "queued": True}


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_version(
    version_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    mv = await db.get(ModelVersion, version_id)
    if mv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    if mv.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the active version")
    await db.delete(mv)
    await db.commit()
