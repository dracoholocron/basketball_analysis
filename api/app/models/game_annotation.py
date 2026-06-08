import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


class GameAnnotation(Base):
    __tablename__ = "game_annotations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, index=True
    )

    # List of annotated landmarks:
    # [{"landmark_id": "corner_tl", "pixel": [x, y], "frame_t": 0.0}, ...]
    landmarks: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # "static" | "moderate" | "moving" | "unknown"
    camera_motion: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
