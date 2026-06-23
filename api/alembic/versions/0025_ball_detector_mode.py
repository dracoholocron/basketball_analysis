"""Add games.ball_detector_mode (auto|tracknet|yolo).

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("games")}
    if "ball_detector_mode" not in cols:
        op.add_column(
            "games",
            sa.Column("ball_detector_mode", sa.String(length=20),
                      nullable=False, server_default="auto"),
        )


def downgrade() -> None:
    op.drop_column("games", "ball_detector_mode")
