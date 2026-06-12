"""Add ball_annotations.flagged (auto-flagged SAM2 drift segments for review).

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-12

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("ball_annotations")]
    if "flagged" not in cols:
        op.add_column("ball_annotations", sa.Column("flagged", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("ball_annotations", "flagged")
