import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


class BallAnnotation(Base):
    """Manual ball annotations for a game, used to seed SAM2 ball tracking and to
    generate auto-labels for fine-tuning the ball detector.

    points: [{"frame_t": float, "pixel": [x, y], "visible": bool}, ...]
      - visible=true  → the ball is at pixel [x,y] at time frame_t
      - visible=false → the ball is NOT present in that frame (negative example)
    Pixels are stored in the video's INTRINSIC resolution (same convention as
    court landmarks), and rescaled to the 720p pipeline space at use time.
    """

    __tablename__ = "ball_annotations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, index=True
    )

    points: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
