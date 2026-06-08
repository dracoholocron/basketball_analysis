"""Shared test fixtures using SQLite in-memory database."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.models.season import Season
from app.models.team import Team
from app.models.game import Game

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DB_URL, echo=False, connect_args={"check_same_thread": False})
TestSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, org: Organization) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
        hashed_password=hash_password("admin123"),
        role=UserRole.ADMIN,
        is_active=True,
        full_name="Test Admin",
        organization_id=org.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def coach_user(db_session: AsyncSession, org: Organization) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"coach_{uuid.uuid4().hex[:6]}@test.com",
        hashed_password=hash_password("coach123"),
        role=UserRole.COACH,
        is_active=True,
        full_name="Test Coach",
        organization_id=org.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user: User) -> str:
    return create_access_token({"sub": str(admin_user.id)})


@pytest_asyncio.fixture
async def coach_token(coach_user: User) -> str:
    return create_access_token({"sub": str(coach_user.id)})


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def auth_client(db_session: AsyncSession, admin_token: str) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated AsyncClient for admin user — convenience fixture."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_headers(coach_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {coach_token}"}


@pytest_asyncio.fixture
async def org(db_session: AsyncSession) -> Organization:
    uid = uuid.uuid4().hex[:8]
    org = Organization(id=uuid.uuid4(), name=f"Test Org {uid}", slug=f"test-org-{uid}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def season(db_session: AsyncSession, org: Organization) -> Season:
    s = Season(
        id=uuid.uuid4(),
        name="2024-25",
        organization_id=org.id,
        year="2024",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest_asyncio.fixture
async def team(db_session: AsyncSession, org: Organization) -> Team:
    t = Team(id=uuid.uuid4(), name="Home Team", organization_id=org.id)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def away_team(db_session: AsyncSession, org: Organization) -> Team:
    t = Team(id=uuid.uuid4(), name="Away Team", organization_id=org.id)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def game(db_session: AsyncSession, season: Season, team: Team, away_team: Team) -> Game:
    from datetime import date
    g = Game(
        id=uuid.uuid4(),
        season_id=season.id,
        home_team_id=team.id,
        away_team_id=away_team.id,
        game_date=date(2024, 12, 15),
        location="Test Arena",
    )
    db_session.add(g)
    await db_session.commit()
    await db_session.refresh(g)
    return g
