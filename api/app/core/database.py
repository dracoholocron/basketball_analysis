"""SQLAlchemy async engine and session factory."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from .config import settings

# Engine and session factory are created lazily to avoid errors when this
# module is imported by the Celery worker (which uses a sync psycopg2 URL).
_engine: "AsyncEngine | None" = None
AsyncSessionLocal = None


def _get_engine() -> "AsyncEngine":
    global _engine, AsyncSessionLocal
    if _engine is None:
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        AsyncSessionLocal = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _engine


# Backward-compat alias used by existing code that does `from .database import engine`
class _LazyEngine:
    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    def begin(self):
        return _get_engine().begin()

    def connect(self):
        return _get_engine().connect()


engine = _LazyEngine()


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator["AsyncSession", None]:
    from sqlalchemy.ext.asyncio import AsyncSession
    _get_engine()  # ensure session factory is initialised
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
