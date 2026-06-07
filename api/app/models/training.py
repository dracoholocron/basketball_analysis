"""Training session models for pose estimation and shooting form analysis."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.types import JsonB

from ..core.database import Base

if TYPE_CHECKING:
    from .user import User


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    video_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sport_drill: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    keypoints: Mapped[list["PoseKeypoints"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["ShootingFormMetric"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class PoseKeypoints(Base):
    __tablename__ = "pose_keypoints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frame: Mapped[int] = mapped_column(Integer, nullable=False)
    person_id: Mapped[int] = mapped_column(Integer, nullable=False)
    keypoints: Mapped[dict | None] = mapped_column(JsonB, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JsonB, nullable=True)
    hoop_bbox: Mapped[dict | None] = mapped_column(JsonB, nullable=True)
    hoop_conf: Mapped[float | None] = mapped_column(Float, nullable=True)

    session: Mapped["TrainingSession"] = relationship(back_populates="keypoints")


class ShootingFormMetric(Base):
    __tablename__ = "shooting_form_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frame: Mapped[int] = mapped_column(Integer, nullable=False)
    person_id: Mapped[int] = mapped_column(Integer, nullable=False)
    elbow_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    elbow_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    knee_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    knee_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    hip_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    hip_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    torso_lean: Mapped[float | None] = mapped_column(Float, nullable=True)
    back_angle: Mapped[float | None] = mapped_column(Float, nullable=True)
    release_angle: Mapped[float | None] = mapped_column(Float, nullable=True)
    depth: Mapped[float | None] = mapped_column(Float, nullable=True)

    session: Mapped["TrainingSession"] = relationship(back_populates="metrics")
