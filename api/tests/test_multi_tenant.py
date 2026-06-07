"""Multi-tenant isolation tests — org A cannot see or modify org B resources."""
from __future__ import annotations

import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.team import Team
from app.models.season import Season


async def _make_org_and_admin(db_session: AsyncSession, suffix: str):
    """Helper: create org + admin user, return (org, user, headers)."""
    org = Organization(
        id=uuid.uuid4(),
        name=f"Org {suffix}",
        slug=f"org-{suffix}-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(org)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        email=f"admin-{suffix}-{uuid.uuid4().hex[:6]}@test.com",
        hashed_password=hash_password("test123"),
        role=UserRole.ADMIN,
        is_active=True,
        organization_id=org.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    return org, user, headers


@pytest.mark.asyncio
async def test_team_isolation(client: AsyncClient, db_session: AsyncSession):
    """User from org A should NOT see team from org B."""
    org_a, _, headers_a = await _make_org_and_admin(db_session, "A")
    org_b, _, headers_b = await _make_org_and_admin(db_session, "B")

    # Create team in org B via direct DB
    team_b = Team(id=uuid.uuid4(), name="Team B Secret", organization_id=org_b.id)
    db_session.add(team_b)
    await db_session.commit()

    # User A should not see team B in list
    resp_a = await client.get("/api/v1/teams", headers=headers_a)
    assert resp_a.status_code == 200
    team_ids = [t["id"] for t in resp_a.json()]
    assert str(team_b.id) not in team_ids


@pytest.mark.asyncio
async def test_team_get_isolation(client: AsyncClient, db_session: AsyncSession):
    """User from org A should get 404 when accessing team from org B directly."""
    _, _, headers_a = await _make_org_and_admin(db_session, "A-get")
    org_b, _, _ = await _make_org_and_admin(db_session, "B-get")

    team_b = Team(id=uuid.uuid4(), name="Team B Private", organization_id=org_b.id)
    db_session.add(team_b)
    await db_session.commit()

    # Accessing org B's team with org A's credentials
    resp = await client.get(f"/api/v1/teams/{team_b.id}", headers=headers_a)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_season_isolation(client: AsyncClient, db_session: AsyncSession):
    """User from org A should NOT see seasons from org B."""
    org_a, _, headers_a = await _make_org_and_admin(db_session, "A-season")
    org_b, _, _ = await _make_org_and_admin(db_session, "B-season")

    season_b = Season(
        id=uuid.uuid4(),
        name="Season B",
        organization_id=org_b.id,
        year="2025",
    )
    db_session.add(season_b)
    await db_session.commit()

    resp = await client.get("/api/v1/seasons", headers=headers_a)
    assert resp.status_code == 200
    season_ids = [s["id"] for s in resp.json()]
    assert str(season_b.id) not in season_ids


@pytest.mark.asyncio
async def test_same_org_visible(client: AsyncClient, db_session: AsyncSession):
    """User can see resources within their own org."""
    org, _, headers = await _make_org_and_admin(db_session, "same-org")

    team = Team(id=uuid.uuid4(), name="Own Team", organization_id=org.id)
    db_session.add(team)
    await db_session.commit()

    resp = await client.get("/api/v1/teams", headers=headers)
    assert resp.status_code == 200
    team_ids = [t["id"] for t in resp.json()]
    assert str(team.id) in team_ids


@pytest.mark.asyncio
async def test_delete_cross_org_forbidden(client: AsyncClient, db_session: AsyncSession):
    """User from org A cannot delete team from org B (should get 404)."""
    _, _, headers_a = await _make_org_and_admin(db_session, "A-del")
    org_b, _, _ = await _make_org_and_admin(db_session, "B-del")

    team_b = Team(id=uuid.uuid4(), name="Protected Team", organization_id=org_b.id)
    db_session.add(team_b)
    await db_session.commit()

    resp = await client.delete(f"/api/v1/teams/{team_b.id}", headers=headers_a)
    assert resp.status_code == 404
