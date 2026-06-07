"""Matchup model: pairing of two teams for scouting/simulation."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.types import JsonB

from ..core.database import Base


class Matchup(Base):
    __tablename__ = "matchups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    own_team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    opponent_team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    game_date: Mapped[date | None] = mapped_column(Date)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    notes: Mapped[dict | None] = mapped_column(JsonB, nullable=True)
    game_config: Mapped[dict | None] = mapped_column(JsonB, nullable=True)
    clock_state: Mapped[dict | None] = mapped_column(JsonB, nullable=True)
    halftime_adjustments: Mapped[list | None] = mapped_column(JsonB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    own_team: Mapped["Team"] = relationship(foreign_keys=[own_team_id])
    opponent_team: Mapped["Team"] = relationship(foreign_keys=[opponent_team_id])
    scouting_reports: Mapped[list["ScoutingReport"]] = relationship(back_populates="matchup")
    simulations: Mapped[list["GameSimulation"]] = relationship(back_populates="matchup")
    situational_adjustments: Mapped[list["SituationalAdjustment"]] = relationship(back_populates="matchup")
    events: Mapped[list["GameEvent"]] = relationship(back_populates="matchup")
