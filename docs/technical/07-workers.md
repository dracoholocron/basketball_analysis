# Celery Workers

## Overview

The platform uses two Celery workers:

| Worker | Queue | Tasks | Hardware |
|--------|-------|-------|----------|
| CPU Worker | `default` | Scouting reports, situational adjustments | Any CPU |
| GPU Worker | `gpu` | Video tracking, pose analysis | NVIDIA GPU |

## Configuration

`api/app/worker/celery_app.py`:

```python
celery_app = Celery(
    "basketball_iq",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks", "app.worker.gpu_tasks"],
)

celery_app.conf.task_routes = {
    "app.worker.gpu_tasks.run_pose_analysis_task": {"queue": "gpu"},
}
```

## Starting Workers

```bash
# CPU worker (inside api/ container or virtualenv)
celery -A app.worker.celery_app worker -Q default --concurrency 2 --loglevel=info

# GPU worker (1 concurrent task to avoid GPU OOM)
celery -A app.worker.celery_app worker -Q gpu --concurrency 1 --loglevel=info
```

In Docker:
```bash
docker compose up cpu-worker gpu-worker -d
```

## Task Reference

### CPU Tasks (`app.worker.tasks`)

- No named tasks currently; LLM calls are made directly from the API router (async, not via Celery)
- Future: `generate_scouting_report_task`, `run_simulation_task` can be moved here for async processing

### GPU Tasks (`app.worker.gpu_tasks`)

**`run_pose_analysis_task(session_id: str)`**

1. Fetches `TrainingSession` from DB
2. Downloads video from MinIO
3. Runs YOLOv8-pose on each frame
4. Inserts `PoseKeypoints` and `ShootingFormMetric` rows
5. Updates session status to `done` or `failed`

## Monitoring

Check worker status:
```bash
docker exec basketball-cpu-worker celery -A app.worker.celery_app inspect active
```

Check queued tasks:
```bash
docker exec basketball-cpu-worker celery -A app.worker.celery_app inspect reserved
```

## Retry Policy

Tasks that fail due to transient errors (network, DB timeout) are retried up to 3 times with exponential backoff. Video tasks that fail update the session status to `failed` with an error message.

## Redis Broker Configuration

- Broker URL: `redis://<host>:6379/0`
- Result backend: `redis://<host>:6379/0`
- Task serializer: `json`
- Result expiry: 86400 seconds (24 hours)
