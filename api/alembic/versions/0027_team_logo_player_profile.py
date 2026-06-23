"""Add team logo + player photo/general-info columns.

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(bind, table) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tcols = _cols(bind, "teams")
    if "logo_s3_key" not in tcols:
        op.add_column("teams", sa.Column("logo_s3_key", sa.String(length=512), nullable=True))
    pcols = _cols(bind, "players")
    if "photo_s3_key" not in pcols:
        op.add_column("players", sa.Column("photo_s3_key", sa.String(length=512), nullable=True))
    if "height_cm" not in pcols:
        op.add_column("players", sa.Column("height_cm", sa.Integer(), nullable=True))
    if "weight_kg" not in pcols:
        op.add_column("players", sa.Column("weight_kg", sa.Integer(), nullable=True))
    if "birth_date" not in pcols:
        op.add_column("players", sa.Column("birth_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "birth_date")
    op.drop_column("players", "weight_kg")
    op.drop_column("players", "height_cm")
    op.drop_column("players", "photo_s3_key")
    op.drop_column("teams", "logo_s3_key")
