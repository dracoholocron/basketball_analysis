"""Phase B: team logo + player photo upload (storage mocked) and enriched player profile."""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient


class _FakeStorage:
    def __init__(self): self.uploaded = []
    def upload_bytes(self, data, bucket, key, content_type="application/octet-stream"):
        self.uploaded.append((bucket, key, content_type)); return key
    def get_presigned_url(self, bucket, key, expiry=3600, public=False):
        return f"https://example.test/{bucket}/{key}"


@pytest.fixture
def _mock_storage(monkeypatch):
    fake = _FakeStorage()
    import app.routers.teams as teams_mod
    import app.routers.players as players_mod
    monkeypatch.setattr(teams_mod, "get_storage", lambda: fake)
    monkeypatch.setattr(players_mod, "get_storage", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_team_logo_upload(client: AsyncClient, auth_headers, team, _mock_storage):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    r = await client.post(
        f"/api/v1/teams/{team.id}/logo",
        files={"file": ("logo.png", png, "image/png")}, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["logo_url"] and "logo.png" in body["logo_url"]
    # list_teams also exposes the logo_url
    lst = await client.get("/api/v1/teams", headers=auth_headers)
    assert any(t["id"] == str(team.id) and t.get("logo_url") for t in lst.json())


@pytest.mark.asyncio
async def test_team_logo_rejects_non_image(client: AsyncClient, auth_headers, team, _mock_storage):
    r = await client.post(
        f"/api/v1/teams/{team.id}/logo",
        files={"file": ("x.txt", b"hello", "text/plain")}, headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_player_photo_and_profile(client: AsyncClient, auth_headers, team, _mock_storage):
    # create a player with general info
    pc = await client.post("/api/v1/players", json={
        "name": "Mateo", "jersey_number": "10", "position": "PG",
        "team_id": str(team.id), "height_cm": 178, "weight_kg": 72,
    }, headers=auth_headers)
    assert pc.status_code == 201, pc.text
    pid = pc.json()["id"]
    assert pc.json()["team_name"] == team.name
    assert pc.json()["height_cm"] == 178

    r = await client.post(
        f"/api/v1/players/{pid}/photo",
        files={"file": ("p.jpg", b"\xff\xd8\xff" + b"0" * 20, "image/jpeg")}, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["photo_url"]

    # profile stats endpoint exposes the ficha fields
    st = await client.get(f"/api/v1/players/{pid}/stats", headers=auth_headers)
    assert st.status_code == 200
    sd = st.json()
    assert sd["team_name"] == team.name and sd["position"] == "PG"
    assert sd["height_cm"] == 178 and sd["photo_url"]
