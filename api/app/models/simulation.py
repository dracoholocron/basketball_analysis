"""Monte Carlo simulation models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.types import JsonB

if TYPE_CHECKING:
    from .matchup import Matchup

from ..core.database import Base


class GameSimulation(Base):
    __tablename__ = "game_simulations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matchup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matchups.id", ondelete="CASCADE"), index=True
    )
    n_runs: Mapped[int] = mapped_column(Integer, default=1000)
    win_pct_own: Mapped[float] = mapped_column(Float, default=0.5)
    win_pct_opp: Mapped[float] = mapped_column(Float, default=0.5)
    avg_score_own: Mapped[float | None] = mapped_column(Float)
    avg_score_opp: Mapped[float | None] = mapped_column(Float)
    score_range_own_low: Mapped[float | None] = mapped_column(Float)
    score_range_own_high: Mapped[float | None] = mapped_column(Float)
    score_range_opp_low: Mapped[float | None] = mapped_column(Float)
    score_range_opp_high: Mapped[float | None] = mapped_column(Float)
    runs_data: Mapped[list | None] = mapped_column(JsonB, nullable=True)
    key_drivers: Mapped[dict | None] = mapped_column(JsonB, nullable=True)
    base_log_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    matchup: Mapped["Matchup"] = relationship(back_populates="simulations")
    keys: Mapped[list["KeyToVictory"]] = relationship(back_populates="simulation")


class KeyToVictory(Base):
    __tablename__ = "keys_to_victory"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_simulations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_metric: Mapped[str | None] = mapped_column(String(100))
    target_value: Mapped[float | None] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    # Logistic regression fields
    feature_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    coefficient: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Live game tracking
    live_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Priority and per-player metric targets (G8 M1, G2)
    is_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_targets: Mapped[list | None] = mapped_column(JsonB, nullable=True)

    simulation: Mapped["GameSimulation"] = relationship(back_populates="keys")


class SituationalAdjustment(Base):
    __tablename__ = "situational_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    matchup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matchups.id", ondelete="CASCADE"), index=True
    )
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    expected_impact: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default="offensive")
    order: Mapped[int] = mapped_column(Integer, default=0)

    matchup: Mapped["Matchup"] = relationship(back_populates="situational_adjustments")
