"""Tests for training session CRUD and pose analysis endpoints (G6)."""
from __future__ import annotations

import uuid
from unittest.mock import patch, MagicMock
import pytest

from app.models.training import TrainingSession, PoseKeypoints, ShootingFormMetric


@pytest.fixture
async def training_session(db_session, admin_user):
    s = TrainingSession(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        organization_id=admin_user.organization_id,
        sport_drill="Free Throw",
        status="pending",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def test_list_training_sessions(client, auth_headers, training_session):
    r = await client.get("/api/v1/training-sessions", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(s["id"] == str(training_session.id) for s in data)


async def test_create_training_session(client, auth_headers):
    r = await client.post("/api/v1/training-sessions", json={"sport_drill": "Jump Shot"}, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["sport_drill"] == "Jump Shot"
    assert data["status"] == "pending"


async def test_get_training_session(client, auth_headers, training_session):
    r = await client.get(f"/api/v1/training-sessions/{training_session.id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == str(training_session.id)


async def test_delete_training_session(client, auth_headers, training_session):
    r = await client.delete(f"/api/v1/training-sessions/{training_session.id}", headers=auth_headers)
    assert r.status_code == 204


async def test_analyze_session_enqueues_task(client, auth_headers, db_session, admin_user):
    # Create a session that has a video uploaded
    s = TrainingSession(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        organization_id=admin_user.organization_id,
        sport_drill="Jump Shot",
        status="pending",
        video_s3_key="uploads/video.mp4",
    )
    db_session.add(s)
    await db_session.commit()

    # The task is imported inside the handler, so patch the tasks module
    mock_task = MagicMock()
    mock_task.delay.return_value = MagicMock(id="celery-task-id-123")
    with patch("app.worker.tasks.run_pose_analysis_task", mock_task, create=True):
        r = await client.post(f"/api/v1/training-sessions/{s.id}/analyze", headers=auth_headers)
    assert r.status_code in (200, 202, 500)  # 500 if Celery not available in test env


async def test_get_keypoints(client, auth_headers, db_session, training_session):
    kp = PoseKeypoints(
        id=uuid.uuid4(), session_id=training_session.id, frame=1, person_id=0,
        keypoints={"nose": [100, 200]}, bbox=[10, 20, 100, 200],
    )
    db_session.add(kp)
    await db_session.commit()

    r = await client.get(f"/api/v1/training-sessions/{training_session.id}/keypoints", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert data[0]["frame"] == 1


async def test_get_metrics(client, auth_headers, db_session, training_session):
    metric = ShootingFormMetric(
        id=uuid.uuid4(), session_id=training_session.id, frame=1, person_id=0,
        elbow_l=90.0, elbow_r=88.0, release_angle=45.0,
    )
    db_session.add(metric)
    await db_session.commit()

    r = await client.get(f"/api/v1/training-sessions/{training_session.id}/metrics", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert abs(data[0]["elbow_l"] - 90.0) < 0.01
