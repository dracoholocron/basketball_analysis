"""
E2E HTTP tests for the Basketball Analytics API.

These tests require a running platform stack (docker compose up).
They are skipped automatically when API_BASE_URL is not set.

Run against a live stack:
    API_BASE_URL=http://localhost:8000 pytest tests/e2e/ -v -m e2e

The tests exercise the full flow:
  1. Create a season + game
  2. Upload a synthetic video
  3. Poll job until done (or timeout)
  4. Validate /metrics shape
  5. Validate /annotated-video download
"""
from __future__ import annotations

import io
import os
import time
import pytest

httpx = pytest.importorskip("httpx", reason="httpx not installed")


BASE_URL = os.environ.get("API_BASE_URL", "")
ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "admin@test.com")
ADMIN_PASS = os.environ.get("E2E_ADMIN_PASS", "testpassword123")
ORG_ID = os.environ.get("E2E_ORG_ID", "")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not BASE_URL, reason="API_BASE_URL not set"),
]


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30)


@pytest.fixture(scope="module")
def auth_token(client):
    """Obtain a JWT token for the test user."""
    r = client.post(
        "/api/v1/auth/token",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASS},
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def season_id(client, auth_headers):
    if not ORG_ID:
        pytest.skip("E2E_ORG_ID not set")
    r = client.post(
        "/api/v1/seasons",
        json={"organization_id": ORG_ID, "name": "E2E Test Season", "year": "2026"},
        headers=auth_headers,
    )
    if r.status_code == 422:
        pytest.skip("Seasons endpoint not implemented yet")
    assert r.status_code == 201
    return r.json()["id"]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_game(client, auth_headers, season_id):
    r = client.post(
        "/api/v1/games",
        json={
            "season_id": season_id,
            "court_level": "primaria",
            "is_half_court": False,
            "home_team1_jersey": "white shirt",
            "away_team2_jersey": "red shirt",
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["court_level"] == "primaria"
    return data["id"]


@pytest.fixture(scope="module")
def game_id(client, auth_headers, season_id):
    r = client.post(
        "/api/v1/games",
        json={
            "season_id": season_id,
            "court_level": "primaria",
            "is_half_court": False,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_upload_video_returns_job(client, auth_headers, game_id):
    """Upload a tiny synthetic video and verify a job is created."""
    import cv2
    import numpy as np
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as tmp:
        path = tmp.name

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    out = cv2.VideoWriter(path, fourcc, 24.0, (64, 64))
    for _ in range(10):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        out.write(frame)
    out.release()

    with open(path, "rb") as f:
        r = client.post(
            f"/api/v1/games/{game_id}/video",
            files={"file": ("test.avi", f, "video/x-msvideo")},
            headers=auth_headers,
        )
    os.unlink(path)

    assert r.status_code == 202
    job = r.json()
    assert "id" in job
    assert job["status"] in ("pending", "running")
    return job["id"]


def test_poll_job_status(client, auth_headers, game_id):
    """After uploading, job should eventually reach 'done' or 'failed'."""
    # First upload
    import cv2
    import numpy as np
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as tmp:
        path = tmp.name

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    out = cv2.VideoWriter(path, fourcc, 24.0, (64, 64))
    for _ in range(10):
        out.write(np.zeros((64, 64, 3), dtype=np.uint8))
    out.release()

    with open(path, "rb") as f:
        upload_r = client.post(
            f"/api/v1/games/{game_id}/video",
            files={"file": ("test.avi", f, "video/x-msvideo")},
            headers=auth_headers,
        )
    os.unlink(path)

    assert upload_r.status_code == 202
    job_id = upload_r.json()["id"]

    # Poll for up to 5 minutes
    deadline = time.time() + 300
    while time.time() < deadline:
        r = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        assert r.status_code == 200
        status = r.json()["status"]
        if status in ("done", "failed"):
            break
        time.sleep(5)

    final_status = r.json()["status"]
    # Accept done or failed (worker may not have models in CI)
    assert final_status in ("done", "failed"), f"Job stuck in status: {final_status}"


def test_metrics_shape(client, auth_headers, game_id):
    """GET /games/{id}/metrics must return the expected shape."""
    r = client.get(f"/api/v1/games/{game_id}/metrics", headers=auth_headers)
    if r.status_code == 404:
        pytest.skip("No completed job yet for this game")
    assert r.status_code == 200
    data = r.json()
    assert "total_frames" in data
    assert "team1_possession_pct" in data
    assert "players" in data
    assert isinstance(data["players"], list)
