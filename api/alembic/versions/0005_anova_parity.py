"""Anova parity: clock/config on matchups, period/jersey on events, priority/targets on keys,
tags/pace on plays, track_data on jobs, linked_matchup on plays, new training tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-16

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- game_events ---
    op.add_column("game_events", sa.Column("period", sa.Integer(), nullable=True))
    op.add_column("game_events", sa.Column("game_time_seconds", sa.Integer(), nullable=True))
    op.add_column(
        "game_events",
        sa.Column(
            "parent_event_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("game_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("game_events", sa.Column("player_jersey", sa.String(10), nullable=True))

    # --- matchups ---
    op.add_column("matchups", sa.Column("game_config", postgresql.JSONB(), nullable=True))
    op.add_column("matchups", sa.Column("clock_state", postgresql.JSONB(), nullable=True))
    op.add_column("matchups", sa.Column("halftime_adjustments", postgresql.JSONB(), nullable=True))
    op.add_column("matchups", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))

    # --- keys_to_victory ---
    op.add_column("keys_to_victory", sa.Column("metric_targets", postgresql.JSONB(), nullable=True))
    op.add_column(
        "keys_to_victory",
        sa.Column("is_priority", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("keys_to_victory", sa.Column("priority_rank", sa.Integer(), nullable=True))

    # --- plays ---
    op.add_column("plays", sa.Column("tags", postgresql.JSONB(), nullable=True))
    op.add_column("plays", sa.Column("pace", sa.String(30), nullable=True))
    op.add_column("plays", sa.Column("svg_data_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("plays", sa.Column("pdf_url", sa.String(500), nullable=True))
    op.add_column(
        "plays",
        sa.Column(
            "linked_matchup_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("matchups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # --- jobs ---
    op.add_column("jobs", sa.Column("track_data_s3_key", sa.String(500), nullable=True))
    op.add_column("jobs", sa.Column("source_video_s3_key", sa.String(500), nullable=True))

    # --- training_sessions ---
    op.create_table(
        "training_sessions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("video_s3_key", sa.String(500), nullable=True),
        sa.Column("sport_drill", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- pose_keypoints ---
    op.create_table(
        "pose_keypoints",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("training_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("frame", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("keypoints", postgresql.JSONB(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(), nullable=True),
        sa.Column("hoop_bbox", postgresql.JSONB(), nullable=True),
        sa.Column("hoop_conf", sa.Float(), nullable=True),
    )

    # --- shooting_form_metrics ---
    op.create_table(
        "shooting_form_metrics",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("training_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("frame", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("elbow_l", sa.Float(), nullable=True),
        sa.Column("elbow_r", sa.Float(), nullable=True),
        sa.Column("knee_l", sa.Float(), nullable=True),
        sa.Column("knee_r", sa.Float(), nullable=True),
        sa.Column("hip_l", sa.Float(), nullable=True),
        sa.Column("hip_r", sa.Float(), nullable=True),
        sa.Column("torso_lean", sa.Float(), nullable=True),
        sa.Column("back_angle", sa.Float(), nullable=True),
        sa.Column("release_angle", sa.Float(), nullable=True),
        sa.Column("depth", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("shooting_form_metrics")
    op.drop_table("pose_keypoints")
    op.drop_table("training_sessions")

    op.drop_column("jobs", "source_video_s3_key")
    op.drop_column("jobs", "track_data_s3_key")

    op.drop_column("plays", "linked_matchup_id")
    op.drop_column("plays", "pdf_url")
    op.drop_column("plays", "svg_data_version")
    op.drop_column("plays", "pace")
    op.drop_column("plays", "tags")

    op.drop_column("keys_to_victory", "priority_rank")
    op.drop_column("keys_to_victory", "is_priority")
    op.drop_column("keys_to_victory", "metric_targets")

    op.drop_column("matchups", "scheduled_at")
    op.drop_column("matchups", "halftime_adjustments")
    op.drop_column("matchups", "clock_state")
    op.drop_column("matchups", "game_config")

    op.drop_column("game_events", "player_jersey")
    op.drop_column("game_events", "parent_event_id")
    op.drop_column("game_events", "game_time_seconds")
    op.drop_column("game_events", "period")
