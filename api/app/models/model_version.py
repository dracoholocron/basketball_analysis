import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ModelVersion(Base):
    """A versioned model file for a pipeline role (player|ball|court|pose).

    Files live in the worker's models_data volume; this table is the registry that
    selects which version is ACTIVE per role. Only the active version is loaded at
    analysis time (no extra VRAM from versioning). Reverting = activate another row.
    """

    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # player|ball|court|pose
    filename: Mapped[str] = mapped_column(String(255), nullable=False)         # path under models/ (e.g. models/ball_detector__ft_...pt)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="builtin")  # builtin|finetune|upload
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
