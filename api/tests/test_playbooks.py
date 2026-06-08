"""API tests for playbook CRUD and scoping."""
import pytest
import uuid

from httpx import AsyncClient


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_playbook(client: AsyncClient, name: str = "Test PB", description: str | None = None) -> dict:
    r = await client.post("/api/v1/playbooks", json={"name": name, "description": description})
    assert r.status_code == 201, r.text
    return r.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_playbook(auth_client: AsyncClient):
    pb = await _create_playbook(auth_client, "My Playbook", "desc")
    assert pb["name"] == "My Playbook"
    assert pb["description"] == "desc"
    assert pb["is_system"] is False
    assert pb["play_count"] == 0


@pytest.mark.asyncio
async def test_list_playbooks_includes_created(auth_client: AsyncClient):
    await _create_playbook(auth_client, "Listed PB")
    r = await auth_client.get("/api/v1/playbooks")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Listed PB" in names


@pytest.mark.asyncio
async def test_get_playbook(auth_client: AsyncClient):
    pb = await _create_playbook(auth_client, "Get Me")
    r = await auth_client.get(f"/api/v1/playbooks/{pb['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Get Me"


@pytest.mark.asyncio
async def test_update_playbook(auth_client: AsyncClient):
    pb = await _create_playbook(auth_client, "Old Name")
    r = await auth_client.put(f"/api/v1/playbooks/{pb['id']}", json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_playbook_leaves_plays(auth_client: AsyncClient):
    pb = await _create_playbook(auth_client, "To Delete")
    # Create a play in the playbook
    r_play = await auth_client.post("/api/v1/plays", json={
        "name": "PB Play", "category": "set_play",
        "playbook_id": pb["id"],
    })
    assert r_play.status_code == 201
    play_id = r_play.json()["id"]

    # Delete playbook
    r_del = await auth_client.delete(f"/api/v1/playbooks/{pb['id']}")
    assert r_del.status_code == 204

    # Play still exists but without playbook_id
    r_get_play = await auth_client.get(f"/api/v1/plays/{play_id}")
    assert r_get_play.status_code == 200
    assert r_get_play.json()["playbook_id"] is None


@pytest.mark.asyncio
async def test_cannot_delete_system_playbook(auth_client: AsyncClient):
    # System playbooks are seeded; list and try to delete one
    r_list = await auth_client.get("/api/v1/playbooks")
    system_pbs = [p for p in r_list.json() if p["is_system"]]
    if not system_pbs:
        pytest.skip("No system playbooks seeded yet")
    r_del = await auth_client.delete(f"/api/v1/playbooks/{system_pbs[0]['id']}")
    assert r_del.status_code == 400


# ── Filtering plays by playbook ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_plays_by_playbook_id(auth_client: AsyncClient):
    pb = await _create_playbook(auth_client, "Filter PB")
    # Create play in playbook
    await auth_client.post("/api/v1/plays", json={
        "name": "PB-only Play", "category": "set_play",
        "playbook_id": pb["id"],
    })
    # Create play NOT in playbook
    await auth_client.post("/api/v1/plays", json={"name": "Unassigned Play", "category": "set_play"})

    r = await auth_client.get(f"/api/v1/plays?playbook_id={pb['id']}")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "PB-only Play" in names
    # Unassigned play should not appear when filtering
    assert "Unassigned Play" not in names


# ── Play visibility bug regression ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_created_play_visible_in_list(auth_client: AsyncClient):
    """Regression: plays created by the user must appear in GET /plays."""
    r_create = await auth_client.post("/api/v1/plays", json={
        "name": "Visibility Test Play", "category": "quick_hitter",
    })
    assert r_create.status_code == 201
    play_id = r_create.json()["id"]

    r_list = await auth_client.get("/api/v1/plays")
    assert r_list.status_code == 200
    ids = [p["id"] for p in r_list.json()]
    assert play_id in ids, "Newly created play is not visible in /plays list"
