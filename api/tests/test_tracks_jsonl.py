"""Tests for /jobs/{id}/tracks and /jobs/{id}/source-video endpoints."""
from __future__ import annotations

import uuid
from unittest.mock import patch, MagicMock
import pytest

from app.models.job import Job


@pytest.fixture
async def job_with_tracks(db_session, game):
    j = Job(
        id=uuid.uuid4(),
        game_id=game.id,
        status="done",
        track_data_s3_key="outputs/tracks/test.jsonl",
        source_video_s3_key="uploads/test.mp4",
        output_s3_key=None,
    )
    db_session.add(j)
    await db_session.commit()
    await db_session.refresh(j)
    return j


@pytest.fixture
async def job_no_tracks(db_session, game):
    j = Job(
        id=uuid.uuid4(),
        game_id=game.id,
        status="pending",
        track_data_s3_key=None,
        source_video_s3_key=None,
        output_s3_key=None,
    )
    db_session.add(j)
    await db_session.commit()
    await db_session.refresh(j)
    return j


async def test_get_tracks_url(client, auth_headers, job_with_tracks):
    mock_url = "https://minio.local/bucket/tracks.jsonl?X-Amz-Signature=test"
    mock_storage = MagicMock()
    mock_storage.get_presigned_url.return_value = mock_url
    with patch("app.routers.jobs.get_storage", return_value=mock_storage):
        r = await client.get(f"/api/v1/jobs/{job_with_tracks.id}/tracks", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["tracks_url"] == mock_url
    assert data["job_id"] == str(job_with_tracks.id)


async def test_get_tracks_no_s3_key(client, auth_headers, job_no_tracks):
    r = await client.get(f"/api/v1/jobs/{job_no_tracks.id}/tracks", headers=auth_headers)
    assert r.status_code == 404


async def test_get_source_video_url(client, auth_headers, job_with_tracks):
    mock_url = "https://minio.local/bucket/video.mp4?X-Amz-Signature=test"
    mock_storage = MagicMock()
    mock_storage.get_presigned_url.return_value = mock_url
    with patch("app.routers.jobs.get_storage", return_value=mock_storage):
        r = await client.get(f"/api/v1/jobs/{job_with_tracks.id}/source-video", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["source_video_url"] == mock_url
