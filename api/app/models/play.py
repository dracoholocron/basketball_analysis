"""Play model for the Play Builder feature."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.types import JsonB

from ..core.database import Base


class Play(Base):
    __tablename__ = "plays"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    linked_matchup_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("matchups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="quick_hitter")
    description: Mapped[str | None] = mapped_column(Text)
    svg_data: Mapped[dict | None] = mapped_column(JsonB)
    svg_data_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tags: Mapped[list | None] = mapped_column(JsonB, nullable=True)
    pace: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
