"""Add job_run_summary (per-analysis detection-quality proxies + timings).

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "job_run_summary" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "job_run_summary",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("job_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("model_versions_used", postgresql.JSONB(), nullable=True),
            sa.Column("ball_detector_source", sa.String(length=20), nullable=True),
            sa.Column("ball_detector_mode", sa.String(length=20), nullable=True),
            sa.Column("ball_raw_detection_rate", sa.Float(), nullable=True),
            sa.Column("ball_coverage_pct", sa.Float(), nullable=True),
            sa.Column("ball_source_counts", postgresql.JSONB(), nullable=True),
            sa.Column("ball_static_fp_dropped", sa.Integer(), nullable=True),
            sa.Column("ball_static_fp_dropped_post_sahi", sa.Integer(), nullable=True),
            sa.Column("ball_review_flags", sa.Integer(), nullable=True),
            sa.Column("raw_tracks", sa.Integer(), nullable=True),
            sa.Column("consolidated_identities", sa.Integer(), nullable=True),
            sa.Column("identities_with_dorsal", sa.Integer(), nullable=True),
            sa.Column("total_frames", sa.Integer(), nullable=True),
            sa.Column("total_seconds", sa.Float(), nullable=True),
            sa.Column("fps_processed", sa.Float(), nullable=True),
            sa.Column("stage_timings", postgresql.JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
        )
        op.create_index("ix_job_run_summary_job_id", "job_run_summary", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_run_summary")
