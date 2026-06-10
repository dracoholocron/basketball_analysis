"""Add hoop_annotations table for manual rim/backboard boxes.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-09

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hoop_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        # [{"frame_t": 0.0, "bbox": [x1,y1,x2,y2], "kind": "rim"}, ...]
        sa.Column("hoops", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_hoop_annotations_game_id ON hoop_annotations (game_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_hoop_annotations_game_id", table_name="hoop_annotations")
    op.drop_table("hoop_annotations")
