"""Add game_annotations table for manual court homography calibration.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "game_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        # [{"landmark_id": "corner_tl", "pixel": [x,y], "frame_t": 0.0}, ...]
        sa.Column("landmarks", postgresql.JSONB(), nullable=True),
        # "static" | "moderate" | "moving" | "unknown"
        sa.Column("camera_motion", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_game_annotations_game_id ON game_annotations (game_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_game_annotations_game_id", table_name="game_annotations")
    op.drop_table("game_annotations")
