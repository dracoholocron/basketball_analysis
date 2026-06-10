"""Add shots_made/missed to player_metrics + unified player_game_stats table.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-10

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("player_metrics")}
    if "shots_made" not in cols:
        op.add_column("player_metrics", sa.Column("shots_made", sa.Integer(), nullable=False, server_default="0"))
    if "shots_missed" not in cols:
        op.add_column("player_metrics", sa.Column("shots_missed", sa.Integer(), nullable=False, server_default="0"))

    if "player_game_stats" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "player_game_stats",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("season_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("source", sa.String(length=12), nullable=False, server_default="cv"),
            # box-score family
            sa.Column("pts", sa.Integer(), nullable=True),
            sa.Column("fgm", sa.Integer(), nullable=True),
            sa.Column("fga", sa.Integer(), nullable=True),
            sa.Column("fg3m", sa.Integer(), nullable=True),
            sa.Column("fg3a", sa.Integer(), nullable=True),
            sa.Column("ftm", sa.Integer(), nullable=True),
            sa.Column("fta", sa.Integer(), nullable=True),
            sa.Column("ast", sa.Integer(), nullable=True),
            sa.Column("stl", sa.Integer(), nullable=True),
            sa.Column("blk", sa.Integer(), nullable=True),
            sa.Column("tov", sa.Integer(), nullable=True),
            sa.Column("oreb", sa.Integer(), nullable=True),
            sa.Column("dreb", sa.Integer(), nullable=True),
            # cv/tracking family
            sa.Column("minutes_played", sa.Float(), nullable=False, server_default="0"),
            sa.Column("distance_m", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_speed_kmh", sa.Float(), nullable=False, server_default="0"),
            sa.Column("max_speed_kmh", sa.Float(), nullable=False, server_default="0"),
            sa.Column("possession_frames", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("shots_attempted_cv", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("shots_made_cv", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("shots_missed_cv", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rebounds_cv", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("steals_cv", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("passes_cv", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("player_id", "game_id", name="uq_pgs_player_game"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "player_game_stats" in sa.inspect(bind).get_table_names():
        op.drop_table("player_game_stats")
    cols = {c["name"] for c in sa.inspect(bind).get_columns("player_metrics")}
    if "shots_missed" in cols:
        op.drop_column("player_metrics", "shots_missed")
    if "shots_made" in cols:
        op.drop_column("player_metrics", "shots_made")
