import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.database import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"), index=True
    )
    home_team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id"), nullable=True
    )
    away_team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id"), nullable=True
    )
    game_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(255))
    court_level: Mapped[str] = mapped_column(
        String(30), nullable=False, default="nba"
    )
    court_width_m: Mapped[float | None] = mapped_column(Float)
    court_height_m: Mapped[float | None] = mapped_column(Float)
    is_half_court: Mapped[bool] = mapped_column(default=False)
    show_poses: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    home_team1_jersey: Mapped[str] = mapped_column(String(120), nullable=False, default="white shirt")
    away_team2_jersey: Mapped[str] = mapped_column(String(120), nullable=False, default="dark blue shirt")
    home_score: Mapped[int | None] = mapped_column()
    away_score: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    season: Mapped["Season"] = relationship(back_populates="games")
    video_assets: Mapped[list["VideoAsset"]] = relationship(back_populates="game")
    jobs: Mapped[list["Job"]] = relationship(back_populates="game")
