import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class JobRunSummary(Base):
    """Per-analysis-run summary: detection-quality proxies, model versions used, and stage
    timings. One row per Job. Feeds the in-game "analysis detail" section and the
    daily/monthly/yearly performance dashboard. Best-effort: absence does not break a job."""

    __tablename__ = "job_run_summary"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, unique=True
    )

    # Models active for this run (player/ball/court/pose/tracknet_ball + ball_detector_mode)
    model_versions_used: Mapped[dict | None] = mapped_column(JSONB)
    ball_detector_source: Mapped[str | None] = mapped_column(String(20))  # tracknet|yolo|curated
    ball_detector_mode: Mapped[str | None] = mapped_column(String(20))    # auto|tracknet|yolo

    # Ball detection-quality proxies
    ball_raw_detection_rate: Mapped[float | None] = mapped_column(Float)  # 0..1
    ball_coverage_pct: Mapped[float | None] = mapped_column(Float)        # 0..100
    ball_source_counts: Mapped[dict | None] = mapped_column(JSONB)
    ball_static_fp_dropped: Mapped[int | None] = mapped_column(Integer)
    ball_static_fp_dropped_post_sahi: Mapped[int | None] = mapped_column(Integer)
    ball_review_flags: Mapped[int | None] = mapped_column(Integer)

    # Identity consolidation
    raw_tracks: Mapped[int | None] = mapped_column(Integer)
    consolidated_identities: Mapped[int | None] = mapped_column(Integer)
    identities_with_dorsal: Mapped[int | None] = mapped_column(Integer)

    # Timing / efficiency
    total_frames: Mapped[int | None] = mapped_column(Integer)
    total_seconds: Mapped[float | None] = mapped_column(Float)
    fps_processed: Mapped[float | None] = mapped_column(Float)  # frames / total_seconds
    stage_timings: Mapped[dict | None] = mapped_column(JSONB)   # {stage: seconds}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
