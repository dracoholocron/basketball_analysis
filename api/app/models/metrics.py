import uuid
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.database import Base


class PlayerMetric(Base):
    """Aggregated per-player stats for a Job (one row per player per job)."""

    __tablename__ = "player_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    display_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    team_id: Mapped[int | None] = mapped_column(Integer)

    total_distance_m: Mapped[float] = mapped_column(Float, default=0.0)
    avg_speed_kmh: Mapped[float] = mapped_column(Float, default=0.0)
    max_speed_kmh: Mapped[float] = mapped_column(Float, default=0.0)
    possession_frames: Mapped[int] = mapped_column(Integer, default=0)
    passes_made: Mapped[int] = mapped_column(Integer, default=0)
    interceptions_made: Mapped[int] = mapped_column(Integer, default=0)

    job: Mapped["Job"] = relationship(back_populates="player_metrics")
    player: Mapped["Player | None"] = relationship(back_populates="metrics")


class FrameMetric(Base):
    """Lightweight per-frame ball possession record (enables timeline charts)."""

    __tablename__ = "frame_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ball_holder_track_id: Mapped[int | None] = mapped_column(Integer)
    ball_holder_team: Mapped[int | None] = mapped_column(Integer)

    job: Mapped["Job"] = relationship(back_populates="frame_metrics")
