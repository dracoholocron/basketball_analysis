import uuid
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    jersey_description: Mapped[str | None] = mapped_column(String(255))
    level: Mapped[str | None] = mapped_column(String(50))  # mini_basket|primaria|secundaria
    logo_s3_key: Mapped[str | None] = mapped_column(String(512))  # team logo image (outputs bucket)

    organization: Mapped["Organization"] = relationship(back_populates="teams")
    players: Mapped[list["Player"]] = relationship(back_populates="team")
    divisions: Mapped[list["Division"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
