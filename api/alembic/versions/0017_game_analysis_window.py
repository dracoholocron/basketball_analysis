"""Add analysis_start_s / analysis_end_s to games (live-play window).

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-10

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("games")}
    if "analysis_start_s" not in cols:
        op.add_column("games", sa.Column("analysis_start_s", sa.Float(), nullable=True))
    if "analysis_end_s" not in cols:
        op.add_column("games", sa.Column("analysis_end_s", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("games", "analysis_end_s")
    op.drop_column("games", "analysis_start_s")
