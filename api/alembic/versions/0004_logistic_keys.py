"""Add runs_data/key_drivers to simulations, logistic fields to keys, box_scores_hash to scouting, live_status to keys

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-16

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # GameSimulation: persist runs features + logistic key drivers
    op.add_column(
        "game_simulations",
        sa.Column("runs_data", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "game_simulations",
        sa.Column("key_drivers", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "game_simulations",
        sa.Column("base_log_odds", sa.Float(), nullable=True),
    )

    # KeyToVictory: logistic regression fields + live_status
    op.add_column(
        "keys_to_victory",
        sa.Column("feature_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "keys_to_victory",
        sa.Column("coefficient", sa.Float(), nullable=True),
    )
    op.add_column(
        "keys_to_victory",
        sa.Column("feature_mean", sa.Float(), nullable=True),
    )
    op.add_column(
        "keys_to_victory",
        sa.Column("feature_std", sa.Float(), nullable=True),
    )
    op.add_column(
        "keys_to_victory",
        sa.Column("live_status", sa.String(20), nullable=True),
    )

    # ScoutingReport: cache hash
    op.add_column(
        "scouting_reports",
        sa.Column("box_scores_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scouting_reports", "box_scores_hash")
    op.drop_column("keys_to_victory", "live_status")
    op.drop_column("keys_to_victory", "feature_std")
    op.drop_column("keys_to_victory", "feature_mean")
    op.drop_column("keys_to_victory", "coefficient")
    op.drop_column("keys_to_victory", "feature_name")
    op.drop_column("game_simulations", "base_log_odds")
    op.drop_column("game_simulations", "key_drivers")
    op.drop_column("game_simulations", "runs_data")
