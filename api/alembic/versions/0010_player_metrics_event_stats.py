"""add shots_attempted, rebounds, steals_cv to player_metrics

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("player_metrics", sa.Column("shots_attempted", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("player_metrics", sa.Column("rebounds", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("player_metrics", sa.Column("steals_cv", sa.Integer(), nullable=True, server_default="0"))


def downgrade() -> None:
    op.drop_column("player_metrics", "shots_attempted")
    op.drop_column("player_metrics", "rebounds")
    op.drop_column("player_metrics", "steals_cv")
