"""Adaptive scheduling (AS-03, AS-05, AS-13; docs/research/2026-10-17-adaptive-scheduling.md)

* ``season_profiles``: versioned per-season solver weights, booking overlays and peak threshold (draft / active /
  retired, ``parent_id`` for "Geri al"); the built-in ``standard`` and ``exam_week`` profiles live in code.
* ``season_segments``: admin period segments of a term (add/drop, midterm ...), drafts proposed after an import.
* ``demand_events``: the find-room / booking demand ledger. Aggregate only (KVKK): no user id, no free text.
* ``learning_versions`` + ``learned_prior_snapshots``: one row per learning refresh with counts, checksum and diff,
  and the prior set it produced, so an admin can go back to a version.

Plain tables only, so the migration is the same on SQLite and PostgreSQL. No table holds per-person rows, so none
gets a row-level-security policy; the RLS role of 0035 reaches them through the default privileges.

Revision ID: 0041_adaptive
Revises: 0040_welcome_guide
Create Date: 2026-10-17 23:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0041_adaptive"
down_revision = "0040_welcome_guide"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "season_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name_tr", sa.String(length=128), nullable=False),
        sa.Column("name_en", sa.String(length=128), nullable=False),
        sa.Column("applies_to", sa.JSON(), nullable=False),
        sa.Column("solver_weights", sa.JSON(), nullable=False),
        sa.Column("booking_overlays", sa.JSON(), nullable=False),
        sa.Column("peak_threshold_pct", sa.SmallInteger(), nullable=False, server_default="85"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("season_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False, server_default="admin"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", "version", name="uq_season_profiles_key_version"),
    )
    op.create_index("ix_season_profiles_key", "season_profiles", ["key"])
    op.create_index("ix_season_profiles_status", "season_profiles", ["status"])
    op.create_index("ix_season_profiles_parent_id", "season_profiles", ["parent_id"])

    op.create_table(
        "season_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("week_from", sa.Integer(), nullable=True),
        sa.Column("week_to", sa.Integer(), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("label_tr", sa.String(length=128), nullable=False),
        sa.Column("label_en", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_season_segments_term_id", "season_segments", ["term_id"])

    op.create_table(
        "demand_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("weekday", sa.SmallInteger(), nullable=True),
        sa.Column("start_period", sa.SmallInteger(), nullable=True),
        sa.Column("end_period", sa.SmallInteger(), nullable=True),
        sa.Column("period_kind", sa.String(length=16), nullable=True),
        sa.Column("headcount_band", sa.String(length=16), nullable=True),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("building", sa.String(length=16), nullable=True),
        sa.Column("results_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="searched"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="find_room"),
    )
    op.create_index("ix_demand_events_ts", "demand_events", ["ts"])
    op.create_index("ix_demand_events_cell", "demand_events", ["term_id", "weekday", "start_period"])

    op.create_table(
        "learning_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suggestible", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("restored_from", sa.Integer(), nullable=True),
        sa.UniqueConstraint("term_id", "number", name="uq_learning_versions_term_number"),
    )
    op.create_index("ix_learning_versions_term_id", "learning_versions", ["term_id"])

    op.create_table(
        "learned_prior_snapshots",
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("learning_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
    )
    op.create_index("ix_learned_prior_snapshots_term_id", "learned_prior_snapshots", ["term_id"])


def downgrade() -> None:
    op.drop_index("ix_learned_prior_snapshots_term_id", table_name="learned_prior_snapshots")
    op.drop_table("learned_prior_snapshots")
    op.drop_index("ix_learning_versions_term_id", table_name="learning_versions")
    op.drop_table("learning_versions")
    op.drop_index("ix_demand_events_cell", table_name="demand_events")
    op.drop_index("ix_demand_events_ts", table_name="demand_events")
    op.drop_table("demand_events")
    op.drop_index("ix_season_segments_term_id", table_name="season_segments")
    op.drop_table("season_segments")
    op.drop_index("ix_season_profiles_parent_id", table_name="season_profiles")
    op.drop_index("ix_season_profiles_status", table_name="season_profiles")
    op.drop_index("ix_season_profiles_key", table_name="season_profiles")
    op.drop_table("season_profiles")
