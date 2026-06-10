"""Add ball_tracking_quality to games (SAM 2.1 checkpoint selector).

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-10

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("games")}
    if "ball_tracking_quality" not in cols:
        op.add_column(
            "games",
            sa.Column("ball_tracking_quality", sa.String(length=20),
                      nullable=False, server_default="base_plus"),
        )


def downgrade() -> None:
    op.drop_column("games", "ball_tracking_quality")
