"""FastAPI dependency injection helpers."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .security import decode_token
from ..models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_role(*roles: str):
    """Return a dependency that enforces at least one of the given roles."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role!r} not permitted. Required: {roles}",
            )
        return current_user
    return _check


async def get_current_org_id(
    user: User = Depends(get_current_user),
) -> uuid.UUID | None:
    """Return the org_id from JWT user.

    Returns None for admin users without an org (acts as super-admin, sees all).
    Raises 403 if a non-admin user has no org.
    """
    if user.organization_id is not None:
        return user.organization_id
    if user.role == "admin":
        return None  # Super-admin bypass
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User has no organization assigned",
    )
