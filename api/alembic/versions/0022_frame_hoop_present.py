"""Add frame_metrics.hoop_present (hoop detected per frame → "aros detectados").

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("frame_metrics")]
    if "hoop_present" not in cols:
        op.add_column("frame_metrics", sa.Column("hoop_present", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("frame_metrics", "hoop_present")
