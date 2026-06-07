"""Auth endpoint tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_login_correct(client: AsyncClient, admin_user: User):
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": admin_user.email, "password": "admin123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, admin_user: User):
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": admin_user.email, "password": "wrongpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code in (400, 401, 422)


@pytest.mark.asyncio
async def test_login_wrong_email(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "nobody@nowhere.com", "password": "anything"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code in (400, 401, 422)


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/matchups")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_request(client: AsyncClient, auth_headers: dict):
    """Token is valid → any authenticated endpoint returns 200/non-401."""
    resp = await client.get("/api/v1/matchups", headers=auth_headers)
    assert resp.status_code != 401
