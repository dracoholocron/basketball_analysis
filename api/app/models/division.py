import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


# M2M: a player can belong to several divisions (age groups), and a division has
# many players. The club is still Player.team_id; divisions are additive groups.
player_divisions = Table(
    "player_divisions",
    Base.metadata,
    Column("player_id", ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
    Column("division_id", ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True),
)


class Division(Base):
    """An age/category group within a team (e.g. U12, U14, U15, U18 mixto).

    A team can have many divisions; a player can be in several. `team_id` on Player
    remains the primary club; divisions don't replace it.
    """

    __tablename__ = "divisions"
    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_division_team_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)          # display, e.g. "U14 A"
    category: Mapped[str | None] = mapped_column(String(40))                # U12|U14|U15|U18_mixto|...
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    team: Mapped["Team"] = relationship(back_populates="divisions")
    players: Mapped[list["Player"]] = relationship(
        secondary=player_divisions, back_populates="divisions"
    )
