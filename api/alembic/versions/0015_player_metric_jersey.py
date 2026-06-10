"""Add jersey_number column to player_metrics (jersey OCR identity).

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-09

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("player_metrics")}
    if "jersey_number" not in cols:
        op.add_column(
            "player_metrics",
            sa.Column("jersey_number", sa.String(length=10), nullable=True),
        )
    if "minutes_played" not in cols:
        op.add_column(
            "player_metrics",
            sa.Column("minutes_played", sa.Float(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("player_metrics", "minutes_played")
    op.drop_column("player_metrics", "jersey_number")
