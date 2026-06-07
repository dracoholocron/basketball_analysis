"""Celery application factory."""
from celery import Celery
from ..core.config import settings

celery_app = Celery(
    "basketball_analytics",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks", "app.worker.cpu_tasks", "app.worker.gpu_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.worker.tasks.run_analysis": {"queue": "gpu"},
        "app.worker.cpu_tasks.run_simulation_task": {"queue": "cpu"},
        "app.worker.gpu_tasks.run_pose_analysis_task": {"queue": "gpu"},
    },
)
