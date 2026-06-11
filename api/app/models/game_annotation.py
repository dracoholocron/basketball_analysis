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

    # FashionCLIP image exemplars per team for jersey-appearance matching:
    # {"1": [{"frame_t": 2.0, "bbox_norm": [x1,y1,x2,y2]}, ...], "2": [...]}
    # bbox_norm is normalized [0..1] to the video frame (resolution-independent).
    team_exemplars: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
