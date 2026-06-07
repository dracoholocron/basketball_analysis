"""Add game_events table and matchup notes column

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-16

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notes JSONB column to matchups
    op.add_column(
        "matchups",
        sa.Column("notes", postgresql.JSONB(), nullable=True),
    )

    # Create game_events table
    op.create_table(
        "game_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("matchup_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("team", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("x_pct", sa.Float(), nullable=True),
        sa.Column("y_pct", sa.Float(), nullable=True),
        sa.Column("player_name", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["matchup_id"], ["matchups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_game_events_matchup_id", "game_events", ["matchup_id"])


def downgrade() -> None:
    op.drop_index("ix_game_events_matchup_id", "game_events")
    op.drop_table("game_events")
    op.drop_column("matchups", "notes")
