"""Add team divisions (age groups) + player_divisions M2M.

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()

    if "divisions" not in tables:
        op.create_table(
            "divisions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("team_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("category", sa.String(length=40), nullable=True),
            sa.Column("season_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.UniqueConstraint("team_id", "name", name="uq_division_team_name"),
        )
        op.create_index("ix_divisions_team_id", "divisions", ["team_id"])
        op.create_index("ix_divisions_season_id", "divisions", ["season_id"])

    if "player_divisions" not in tables:
        op.create_table(
            "player_divisions",
            sa.Column("player_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("division_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True),
        )


def downgrade() -> None:
    op.drop_table("player_divisions")
    op.drop_table("divisions")
