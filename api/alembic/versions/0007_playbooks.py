"""Add playbooks table and plays.playbook_id FK.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_playbooks_organization_id ON playbooks (organization_id)")

    # Add playbook_id column only if it doesn't already exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='plays' AND column_name='playbook_id'
            ) THEN
                ALTER TABLE plays ADD COLUMN playbook_id UUID REFERENCES playbooks(id) ON DELETE SET NULL;
            END IF;
        END
        $$
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_plays_playbook_id ON plays (playbook_id)")


def downgrade() -> None:
    op.drop_index("ix_plays_playbook_id", table_name="plays")
    op.drop_column("plays", "playbook_id")
    op.drop_index("ix_playbooks_organization_id", table_name="playbooks")
    op.drop_table("playbooks")
