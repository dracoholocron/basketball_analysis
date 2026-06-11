"""Add model_versions registry (per-role versioned model selection).

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-10

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "model_versions" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "model_versions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("label", sa.String(length=120), nullable=True),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="builtin"),
            sa.Column("metrics", postgresql.JSONB(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_model_versions_role", "model_versions", ["role"])


def downgrade() -> None:
    op.drop_table("model_versions")
