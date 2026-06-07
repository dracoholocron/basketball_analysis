"""Box score models for team and player game statistics."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class BoxScore(Base):
    """Team-level box score for a single game."""

    __tablename__ = "box_scores"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    # Scoring
    pts: Mapped[int] = mapped_column(Integer, default=0)
    fgm: Mapped[int] = mapped_column(Integer, default=0)
    fga: Mapped[int] = mapped_column(Integer, default=0)
    fg3m: Mapped[int] = mapped_column(Integer, default=0)
    fg3a: Mapped[int] = mapped_column(Integer, default=0)
    ftm: Mapped[int] = mapped_column(Integer, default=0)
    fta: Mapped[int] = mapped_column(Integer, default=0)
    # Boards
    oreb: Mapped[int] = mapped_column(Integer, default=0)
    dreb: Mapped[int] = mapped_column(Integer, default=0)
    # Other
    ast: Mapped[int] = mapped_column(Integer, default=0)
    stl: Mapped[int] = mapped_column(Integer, default=0)
    blk: Mapped[int] = mapped_column(Integer, default=0)
    tov: Mapped[int] = mapped_column(Integer, default=0)
    pf: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    game: Mapped["Game"] = relationship()
    team: Mapped["Team"] = relationship()
    player_box_scores: Mapped[list["PlayerBoxScore"]] = relationship(back_populates="box_score")


class PlayerBoxScore(Base):
    """Per-player box score for a single game."""

    __tablename__ = "player_box_scores"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    box_score_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("box_scores.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    player_name: Mapped[str | None] = mapped_column(String(255))
    jersey_number: Mapped[str | None] = mapped_column(String(10))
    minutes_played: Mapped[float | None] = mapped_column(Float)
    # Scoring
    pts: Mapped[int] = mapped_column(Integer, default=0)
    fgm: Mapped[int] = mapped_column(Integer, default=0)
    fga: Mapped[int] = mapped_column(Integer, default=0)
    fg3m: Mapped[int] = mapped_column(Integer, default=0)
    fg3a: Mapped[int] = mapped_column(Integer, default=0)
    ftm: Mapped[int] = mapped_column(Integer, default=0)
    fta: Mapped[int] = mapped_column(Integer, default=0)
    # Boards
    oreb: Mapped[int] = mapped_column(Integer, default=0)
    dreb: Mapped[int] = mapped_column(Integer, default=0)
    # Other
    ast: Mapped[int] = mapped_column(Integer, default=0)
    stl: Mapped[int] = mapped_column(Integer, default=0)
    blk: Mapped[int] = mapped_column(Integer, default=0)
    tov: Mapped[int] = mapped_column(Integer, default=0)
    pf: Mapped[int] = mapped_column(Integer, default=0)
    plus_minus: Mapped[int | None] = mapped_column(Integer)

    box_score: Mapped["BoxScore"] = relationship(back_populates="player_box_scores")
