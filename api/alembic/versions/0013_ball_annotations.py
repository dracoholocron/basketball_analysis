"""Add ball_annotations table for manual ball annotation (SAM2 tracking + fine-tune).

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-09

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ball_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        # [{"frame_t": 0.0, "pixel": [x, y], "visible": true}, ...]
        sa.Column("points", postgresql.JSONB(), nullable=True),
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
        "CREATE INDEX IF NOT EXISTS ix_ball_annotations_game_id ON ball_annotations (game_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_ball_annotations_game_id", table_name="ball_annotations")
    op.drop_table("ball_annotations")
