"""Add ball_track_sessions (interactive pause→correct→resume SAM2 ball tracking).

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-12

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "ball_track_sessions" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "ball_track_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("game_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
            sa.Column("current_frame", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_frames", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fps", sa.Float(), nullable=False, server_default="25"),
            sa.Column("coverage_pct", sa.Float(), nullable=False, server_default="0"),
            sa.Column("pause_reason", sa.String(length=20), nullable=True),
            sa.Column("pause_frame", sa.Integer(), nullable=True),
            sa.Column("pause_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("preview_key", sa.String(length=255), nullable=True),
            sa.Column("track_key", sa.String(length=255), nullable=True),
            sa.Column("error_message", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
        )
        op.create_index("ix_ball_track_sessions_game_id", "ball_track_sessions", ["game_id"])


def downgrade() -> None:
    op.drop_table("ball_track_sessions")
