"""Add jobs.layers_key (post-hoc overlay layers JSON).

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("jobs")}
    if "layers_key" not in cols:
        op.add_column("jobs", sa.Column("layers_key", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "layers_key")
