"""Add team_exemplars to game_annotations (FashionCLIP image exemplars per team).

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("game_annotations")]
    if "team_exemplars" not in cols:
        op.add_column(
            "game_annotations",
            sa.Column("team_exemplars", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("game_annotations", "team_exemplars")
