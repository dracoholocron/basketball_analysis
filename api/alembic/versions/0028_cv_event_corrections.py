"""Add cv_event_corrections (manual overrides over a job's cv_events).

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "cv_event_corrections" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "cv_event_corrections",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("job_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_index", sa.Integer(), nullable=False),
            sa.Column("new_type", sa.String(length=40), nullable=True),
            sa.Column("new_player_track_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.UniqueConstraint("job_id", "event_index", name="uq_cv_corr_job_idx"),
        )
        op.create_index("ix_cv_event_corrections_job_id", "cv_event_corrections", ["job_id"])


def downgrade() -> None:
    op.drop_table("cv_event_corrections")
