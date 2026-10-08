"""Booking enhancements wave 1, P7 audit log (docs/product/booking-enhancements.md §4.6): the append-only
``audit_events`` table (UPDATE and DELETE refused by triggers on SQLite and PostgreSQL) and ``audit.view``.

Deploy note: on PostgreSQL the trigger refuses UPDATE/DELETE for every role; a future KVKK retention job (A4)
must drop and recreate the trigger inside its own migration.

Revision ID: 0014_audit_events
Revises: 0013_find_room
Create Date: 2026-10-08 16:32:00

"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0014_audit_events"
down_revision = "0013_find_room"
branch_labels = None
depends_on = None

PERMISSIONS = [("audit.view", "View the audit log of every change")]

APPEND_ONLY_SQLITE = (
    "CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
)
APPEND_ONLY_POSTGRES = (
    "CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS "
    "$$ BEGIN RAISE EXCEPTION 'audit_events is append-only'; END $$",
    "DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events",
    "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
    "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()",
)


def _perm_helpers():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("_m0012", Path(__file__).with_name("0012_room_features.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_label", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("term_id", sa.Integer(), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("diff", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip_hash", sa.String(length=32), nullable=True),
        sa.Column("reversible", sa.Boolean(), nullable=False),
        sa.Column("undo_of", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id", "id"])
    op.create_index("ix_audit_events_actor", "audit_events", ["actor_id", "id"])
    op.create_index("ix_audit_events_ts", "audit_events", ["ts"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_undo_of", "audit_events", ["undo_of"])
    op.create_index("ix_audit_events_parent_id", "audit_events", ["parent_id"])
    dialect = op.get_bind().dialect.name
    for stmt in {"sqlite": APPEND_ONLY_SQLITE, "postgresql": APPEND_ONLY_POSTGRES}.get(dialect, ()):
        op.execute(stmt)
    _perm_helpers().grant(PERMISSIONS)


def downgrade() -> None:
    _perm_helpers().revoke(PERMISSIONS)
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete")
    for ix in ("parent_id", "undo_of", "action", "ts", "actor", "entity"):
        op.drop_index(f"ix_audit_events_{ix}", table_name="audit_events")
    op.drop_table("audit_events")
