"""Booking enhancements wave 1, P1 approval workflows (docs/product/booking-enhancements.md §4.3, user decisions
2026-10-08): designated approvers (``approver_scopes``), ``approval_rules``, ``approval_requests`` with the rule
snapshot, ``approval_decisions``, ``inapp_notifications``; ``bookings.held_until`` (tentative hold); the
permissions ``approvals.decide``, ``book_single.request``, ``book_recur.request`` (Administrator only).

No rule is created: bookings behave exactly like CRBS until an administrator adds one.

Revision ID: 0015_approvals
Revises: 0014_audit_events
Create Date: 2026-10-08 16:33:00

"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0015_approvals"
down_revision = "0014_audit_events"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("approvals.decide", "Approve or reject booking requests (as a designated approver)"),
    ("book_single.request", "Request single bookings that an approver confirms"),
    ("book_recur.request", "Request recurring bookings that an approver confirms"),
]


def _perm_helpers():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("_m0012", Path(__file__).with_name("0012_room_features.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upgrade() -> None:
    op.create_table(
        "approver_scopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("tag", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approver_scopes_scope", "approver_scopes", ["scope_type", "scope_id"])
    op.create_index("ix_approver_scopes_user_id", "approver_scopes", ["user_id"])
    op.create_table(
        "approval_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("tag", sa.String(length=16), nullable=True),
        sa.Column("term_id", sa.Integer(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("hold_minutes", sa.Integer(), nullable=False),
        sa.Column("lead_time_workdays", sa.Integer(), nullable=False),
        sa.Column("expires_before_start_minutes", sa.Integer(), nullable=False),
        sa.Column("allow_self_approve", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_rules_entity", "approval_rules", ["entity_type", "entity_id"])
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=True),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("rule_snapshot", sa.JSON(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("suggestion", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["approval_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["series_id"], ["booking_series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("booking_id", "series_id", "room_id", "status"):
        op.create_index(f"ix_approval_requests_{col}", "approval_requests", [col])
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("approver_user_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("alternative", sa.JSON(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["request_id"], ["approval_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_decisions_request_id", "approval_decisions", ["request_id"])
    op.create_table(
        "inapp_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=255), nullable=True),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inapp_notifications_user_read", "inapp_notifications", ["user_id", "read_at"])
    with op.batch_alter_table("bookings") as batch:
        batch.add_column(sa.Column("held_until", sa.DateTime(), nullable=True))
    _perm_helpers().grant(PERMISSIONS)


def downgrade() -> None:
    conn = op.get_bind()
    # requests that were never approved disappear with the workflow; their bookings become CRBS cancellations
    conn.execute(
        sa.text(
            "update bookings set status = 'CANCELLED' where status in ('PENDING', 'REJECTED', 'EXPIRED', 'WITHDRAWN')"
        )
    )
    conn.execute(
        sa.text(
            "update booking_series set status = 'CANCELLED' where status in ('PENDING', 'REJECTED', 'EXPIRED', 'WITHDRAWN')"
        )
    )
    conn.execute(
        sa.text("delete from booking_slots where booking_id in (select id from bookings where status = 'CANCELLED')")
    )
    _perm_helpers().revoke(PERMISSIONS)
    with op.batch_alter_table("bookings") as batch:
        batch.drop_column("held_until")
    op.drop_index("ix_inapp_notifications_user_read", table_name="inapp_notifications")
    op.drop_table("inapp_notifications")
    op.drop_index("ix_approval_decisions_request_id", table_name="approval_decisions")
    op.drop_table("approval_decisions")
    for col in ("status", "room_id", "series_id", "booking_id"):
        op.drop_index(f"ix_approval_requests_{col}", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index("ix_approval_rules_entity", table_name="approval_rules")
    op.drop_table("approval_rules")
    op.drop_index("ix_approver_scopes_user_id", table_name="approver_scopes")
    op.drop_index("ix_approver_scopes_scope", table_name="approver_scopes")
    op.drop_table("approver_scopes")
