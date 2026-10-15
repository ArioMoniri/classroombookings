"""Approval-first bookings (owner requirement 2026-10-15; docs/ROADMAP.md "Approval-first bookings"):

* ``approval_requests.reason_code`` (structured rejection reason) and ``decided_by`` (who closed the request; the
  requester may see it), ``approval_decisions.reason_code`` (per period in group decisions);
* ``inapp_notifications.data``: the structured payload (room, dates, periods, decision, reason, decided_by);
* ``notification_deliveries``: the dispatcher's ledger, unique per (occurrence, recipient, channel);
* the permission ``bookings.skip_approval`` (Administrator only): book directly when ``bookings.approval_mode`` is
  ``all``.

No setting is written: ``bookings.approval_mode`` defaults to ``rules`` (CRBS + P1 rules) until an administrator
sets ``all`` (``PUT /api/v1/org/settings {"approval_mode": "all"}``).

Revision ID: 0025_approval_first
Revises: 0024_moderation_indexes
Create Date: 2026-10-15 23:00:00

"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0025_approval_first"
down_revision = "0024_moderation_indexes"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("bookings.skip_approval", "Book directly when every booking request needs approval (bookings.approval_mode)"),
]


def _perm_helpers():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("_m0012", Path(__file__).with_name("0012_room_features.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch:
        batch.add_column(sa.Column("decided_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("reason_code", sa.String(length=32), nullable=True))
        batch.create_foreign_key(
            "fk_approval_requests_decided_by_users", "users", ["decided_by"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("approval_decisions") as batch:
        batch.add_column(sa.Column("reason_code", sa.String(length=32), nullable=True))
    with op.batch_alter_table("inapp_notifications") as batch:
        batch.add_column(sa.Column("data", sa.JSON(), nullable=True))
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", "user_id", "channel", name="uq_notification_deliveries_key"),
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
    _perm_helpers().grant(PERMISSIONS)


def downgrade() -> None:
    _perm_helpers().revoke(PERMISSIONS)
    op.drop_index("ix_notification_deliveries_user_id", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    with op.batch_alter_table("inapp_notifications") as batch:
        batch.drop_column("data")
    with op.batch_alter_table("approval_decisions") as batch:
        batch.drop_column("reason_code")
    with op.batch_alter_table("approval_requests") as batch:
        batch.drop_constraint("fk_approval_requests_decided_by_users", type_="foreignkey")
        batch.drop_column("reason_code")
        batch.drop_column("decided_by")
