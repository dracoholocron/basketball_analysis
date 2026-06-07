"""Analytics features: box scores, matchups, scouting, simulation, plays

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Alter players table (add position, make team_id nullable, change jersey_number to String) ──
    op.alter_column("players", "team_id", nullable=True)
    op.execute("ALTER TABLE players ALTER COLUMN jersey_number TYPE VARCHAR(10) USING jersey_number::VARCHAR")
    op.add_column("players", sa.Column("position", sa.String(10), nullable=True))

    # ── Box scores ──────────────────────────────────────────────────────────────
    op.create_table(
        "box_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("pts", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fgm", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fga", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fg3m", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fg3a", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("ftm", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fta", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("oreb", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("dreb", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("ast", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("stl", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("blk", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("tov", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("pf", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_box_scores_game_id", "box_scores", ["game_id"])
    op.create_index("ix_box_scores_team_id", "box_scores", ["team_id"])

    op.create_table(
        "player_box_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("box_score_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=True),
        sa.Column("player_name", sa.String(255), nullable=True),
        sa.Column("jersey_number", sa.String(10), nullable=True),
        sa.Column("minutes_played", sa.Float(), nullable=True),
        sa.Column("pts", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fgm", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fga", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fg3m", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fg3a", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("ftm", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("fta", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("oreb", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("dreb", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("ast", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("stl", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("blk", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("tov", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("pf", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("plus_minus", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["box_score_id"], ["box_scores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_box_scores_box_score_id", "player_box_scores", ["box_score_id"])

    # ── Matchups ─────────────────────────────────────────────────────────────────
    op.create_table(
        "matchups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("own_team_id", sa.UUID(), nullable=True),
        sa.Column("opponent_team_id", sa.UUID(), nullable=True),
        sa.Column("season_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=True, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["own_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opponent_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matchups_organization_id", "matchups", ["organization_id"])

    # ── Scouting reports ─────────────────────────────────────────────────────────
    op.create_table(
        "scouting_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("matchup_id", sa.UUID(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("team_identity", sa.Text(), nullable=True),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mvp_players", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("game_keys_offensive", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("game_keys_defensive", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("coach_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["matchup_id"], ["matchups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scouting_reports_matchup_id", "scouting_reports", ["matchup_id"])

    op.create_table(
        "player_scouting_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("report_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=True),
        sa.Column("player_name", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("is_mvp", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("mvp_rank", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["scouting_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_scouting_notes_report_id", "player_scouting_notes", ["report_id"])

    # ── Simulations ──────────────────────────────────────────────────────────────
    op.create_table(
        "game_simulations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("matchup_id", sa.UUID(), nullable=False),
        sa.Column("n_runs", sa.Integer(), nullable=True, server_default="1000"),
        sa.Column("win_pct_own", sa.Float(), nullable=True, server_default="0.5"),
        sa.Column("win_pct_opp", sa.Float(), nullable=True, server_default="0.5"),
        sa.Column("avg_score_own", sa.Float(), nullable=True),
        sa.Column("avg_score_opp", sa.Float(), nullable=True),
        sa.Column("score_range_own_low", sa.Float(), nullable=True),
        sa.Column("score_range_own_high", sa.Float(), nullable=True),
        sa.Column("score_range_opp_low", sa.Float(), nullable=True),
        sa.Column("score_range_opp_high", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["matchup_id"], ["matchups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_game_simulations_matchup_id", "game_simulations", ["matchup_id"])

    op.create_table(
        "keys_to_victory",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("simulation_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_metric", sa.String(100), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("order", sa.Integer(), nullable=True, server_default="0"),
        sa.ForeignKeyConstraint(["simulation_id"], ["game_simulations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_keys_to_victory_simulation_id", "keys_to_victory", ["simulation_id"])

    op.create_table(
        "situational_adjustments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("matchup_id", sa.UUID(), nullable=False),
        sa.Column("scenario", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("expected_impact", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(30), nullable=True, server_default="offensive"),
        sa.Column("order", sa.Integer(), nullable=True, server_default="0"),
        sa.ForeignKeyConstraint(["matchup_id"], ["matchups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_situational_adjustments_matchup_id", "situational_adjustments", ["matchup_id"])

    # ── Plays ────────────────────────────────────────────────────────────────────
    op.create_table(
        "plays",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=True, server_default="quick_hitter"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("svg_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("shared", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plays_organization_id", "plays", ["organization_id"])


def downgrade() -> None:
    op.drop_table("plays")
    op.drop_table("situational_adjustments")
    op.drop_table("keys_to_victory")
    op.drop_table("game_simulations")
    op.drop_table("player_scouting_notes")
    op.drop_table("scouting_reports")
    op.drop_table("matchups")
    op.drop_table("player_box_scores")
    op.drop_table("box_scores")
    op.drop_column("players", "position")
