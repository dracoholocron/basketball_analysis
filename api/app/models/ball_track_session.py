import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class BallTrackSession(Base):
    """Interactive SAM2 ball-tracking session (pause → correct → resume).

    The GPU worker runs the tracking incrementally; when the model loses the ball /
    drifts, or the user requests a pause, the task checkpoints (partial track to MinIO
    at ``track_key``) and ends, leaving status=waiting_user. The user corrects in the
    annotate-ball UI and resumes — only the remainder is re-tracked. When done, the
    full analysis can consume the curated track (skipping the SAM2 stage entirely).
    """

    __tablename__ = "ball_track_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True
    )

    # queued | running | waiting_user | done | cancelled | error
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    current_frame: Mapped[int] = mapped_column(Integer, default=0)
    total_frames: Mapped[int] = mapped_column(Integer, default=0)
    fps: Mapped[float] = mapped_column(Float, default=25.0)
    coverage_pct: Mapped[float] = mapped_column(Float, default=0.0)

    pause_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)  # lost|drift|user
    pause_frame: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)

    preview_key: Mapped[str | None] = mapped_column(String(255), nullable=True)  # outputs bucket
    track_key: Mapped[str | None] = mapped_column(String(255), nullable=True)    # outputs bucket
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
