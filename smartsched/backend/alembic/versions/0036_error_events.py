"""Grouped error events for the operations panel (W3-OPS; app/models/error_event.py, app/core/observability.py)

* ``error_events``: one row per fingerprint (backend exceptions / 5xx and browser error reports), with first/last
  seen, count, a PII-scrubbed sample stack, route, user role, release sha and the admin's status
  (open / acknowledged / resolved / ignored); rows unseen for 90 days are purged (``app.core.observability``).

Plain table + indexes: applies the same way on SQLite and PostgreSQL.

Revision ID: 0036_error_events
Revises: 0035_rls_policies
Create Date: 2026-10-17 19:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0036_error_events"
down_revision = "0035_rls_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=128), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("route", sa.String(length=255), nullable=True),
        sa.Column("method", sa.String(length=8), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("user_role", sa.String(length=32), nullable=True),
        sa.Column("release", sa.String(length=64), nullable=True),
        sa.Column("sample_stack", sa.Text(), nullable=True),
        sa.Column("last_request_id", sa.String(length=64), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("reopened", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_error_events_fingerprint", "error_events", ["fingerprint"], unique=True)
    op.create_index("ix_error_events_source", "error_events", ["source"])
    op.create_index("ix_error_events_status", "error_events", ["status"])
    op.create_index("ix_error_events_last_seen", "error_events", ["last_seen"])


def downgrade() -> None:
    op.drop_index("ix_error_events_last_seen", table_name="error_events")
    op.drop_index("ix_error_events_status", table_name="error_events")
    op.drop_index("ix_error_events_source", table_name="error_events")
    op.drop_index("ix_error_events_fingerprint", table_name="error_events")
    op.drop_table("error_events")
