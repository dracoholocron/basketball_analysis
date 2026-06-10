import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


class HoopAnnotation(Base):
    """Manual hoop/backboard boxes for a game, to improve shot counting and
    ball-near-rim detection (the YOLO hoop detector is unreliable).

    hoops: [{"frame_t": float, "bbox": [x1, y1, x2, y2], "kind": "rim"|"backboard"}]
    Pixels are in the video's INTRINSIC resolution (rescaled to 720p at use time).
    """

    __tablename__ = "hoop_annotations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, index=True
    )

    hoops: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
