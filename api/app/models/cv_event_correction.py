import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class CvEventCorrection(Base):
    """A manual override applied on top of a job's immutable cv_events_json. Keyed by the
    event index; the cv-events read overlays corrections (change event type / reassign the
    player track) without mutating the analysis output."""

    __tablename__ = "cv_event_corrections"
    __table_args__ = (UniqueConstraint("job_id", "event_index", name="uq_cv_corr_job_idx"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    new_type: Mapped[str | None] = mapped_column(String(40))
    new_player_track_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
