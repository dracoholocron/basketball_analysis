import uuid
from datetime import date
from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    jersey_number: Mapped[str | None] = mapped_column(String(10))
    position: Mapped[str | None] = mapped_column(String(10))
    track_id: Mapped[int | None] = mapped_column(Integer, comment="YOLO tracker ID in video")
    # General info (player profile)
    photo_s3_key: Mapped[str | None] = mapped_column(String(512))  # player photo (outputs bucket)
    height_cm: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[int | None] = mapped_column(Integer)
    birth_date: Mapped[date | None] = mapped_column(Date)

    team: Mapped["Team"] = relationship(back_populates="players")
    metrics: Mapped[list["PlayerMetric"]] = relationship(back_populates="player")
    divisions: Mapped[list["Division"]] = relationship(
        secondary="player_divisions", back_populates="players"
    )
