"""generator studio: drafts, presets, imported snapshots, constraints.source_ref

Revision ID: 0002_studio
Revises: 0001
Create Date: 2026-10-08 07:40:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_studio"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("constraints") as batch:
        batch.add_column(sa.Column("source_ref", sa.JSON(), nullable=True))

    op.create_table(
        "studio_presets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("disabled_builtin_kinds", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "studio_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("horizon", sa.String(length=8), nullable=False),
        sa.Column("horizon_params", sa.JSON(), nullable=False),
        sa.Column("excluded_event_ids", sa.JSON(), nullable=False),
        sa.Column("pins", sa.JSON(), nullable=False),
        sa.Column("disabled_rule_ids", sa.JSON(), nullable=False),
        sa.Column("rule_overrides", sa.JSON(), nullable=False),
        sa.Column("preset_id", sa.Integer(), nullable=True),
        sa.Column("last_step", sa.String(length=16), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("last_precheck", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preset_id"], ["studio_presets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "user_id", "kind", name="uq_studio_drafts_term_user_kind"),
    )
    op.create_index("ix_studio_drafts_term_id", "studio_drafts", ["term_id"])
    op.create_index("ix_studio_drafts_user_id", "studio_drafts", ["user_id"])
    op.create_table(
        "imported_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity", "entity_id", name="uq_imported_snapshots_entity"),
    )
    op.create_index("ix_imported_snapshots_entity_id", "imported_snapshots", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_imported_snapshots_entity_id", table_name="imported_snapshots")
    op.drop_table("imported_snapshots")
    op.drop_index("ix_studio_drafts_user_id", table_name="studio_drafts")
    op.drop_index("ix_studio_drafts_term_id", table_name="studio_drafts")
    op.drop_table("studio_drafts")
    op.drop_table("studio_presets")
    with op.batch_alter_table("constraints") as batch:
        batch.drop_column("source_ref")
