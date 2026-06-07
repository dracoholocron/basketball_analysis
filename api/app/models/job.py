import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.types import JsonB

from ..core.database import Base


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobStage(str, Enum):
    QUEUED = "queued"
    READING_VIDEO = "reading_video"
    PLAYER_TRACKING = "player_tracking"
    BALL_TRACKING = "ball_tracking"
    KEYPOINT_DETECTION = "keypoint_detection"
    TEAM_ASSIGNMENT = "team_assignment"
    BALL_ACQUISITION = "ball_acquisition"
    PASS_DETECTION = "pass_detection"
    TACTICAL_VIEW = "tactical_view"
    SPEED_DISTANCE = "speed_distance"
    DRAWING = "drawing"
    SAVING_OUTPUT = "saving_output"
    PERSISTING_METRICS = "persisting_metrics"
    COMPLETE = "complete"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    video_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("video_assets.id"), nullable=True
    )
    status: Mapped[JobStatus] = mapped_column(
        String(20), nullable=False, default=JobStatus.PENDING
    )
    current_stage: Mapped[JobStage] = mapped_column(
        String(40), nullable=False, default=JobStage.QUEUED
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    output_s3_key: Mapped[str | None] = mapped_column(String(500))
    track_data_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_video_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cv_events_json: Mapped[list | None] = mapped_column(JsonB, nullable=True)
    highlights_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    highlights_manifest_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    game: Mapped["Game"] = relationship(back_populates="jobs")
    player_metrics: Mapped[list["PlayerMetric"]] = relationship(back_populates="job")
    frame_metrics: Mapped[list["FrameMetric"]] = relationship(back_populates="job")
