"""add display_label to player_metrics

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_metrics",
        sa.Column("display_label", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("player_metrics", "display_label")
