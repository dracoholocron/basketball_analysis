"""add jersey columns to games

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column(
            "home_team1_jersey",
            sa.String(120),
            nullable=False,
            server_default="white shirt",
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "away_team2_jersey",
            sa.String(120),
            nullable=False,
            server_default="dark blue shirt",
        ),
    )


def downgrade() -> None:
    op.drop_column("games", "away_team2_jersey")
    op.drop_column("games", "home_team1_jersey")
