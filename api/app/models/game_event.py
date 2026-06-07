"""Game event model for live game tracking (live scorer / shot chart)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base

if TYPE_CHECKING:
    from .matchup import Matchup


class GameEvent(Base):
    __tablename__ = "game_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matchup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matchups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("game_events.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    team: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    x_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    player_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    player_jersey: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    game_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    matchup: Mapped["Matchup"] = relationship(back_populates="events", foreign_keys=[matchup_id])
