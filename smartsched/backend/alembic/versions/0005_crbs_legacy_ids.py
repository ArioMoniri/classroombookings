"""CRBS parity audit B4: ``legacy_crbs_id`` on the parity tables, so that importing a CRBS database twice
updates the rows it created the first time (roles, room groups, custom fields, ACL entries, schedules,
periods, timetable weeks, holidays, booking series and bookings).

Revision ID: 0005_crbs_legacy_ids
Revises: 0004_review_fixes
Create Date: 2026-10-08 13:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_crbs_legacy_ids"
down_revision = "0004_review_fixes"
branch_labels = None
depends_on = None

TABLES = (
    "roles",
    "room_groups",
    "room_custom_fields",
    "room_acl",
    "booking_schedules",
    "booking_periods",
    "timetable_weeks",
    "holidays",
    "booking_series",
    "bookings",
)


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("legacy_crbs_id", sa.Integer(), nullable=True))
            batch.create_index(f"ix_{table}_legacy_crbs_id", ["legacy_crbs_id"])


def downgrade() -> None:
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_legacy_crbs_id")
            batch.drop_column("legacy_crbs_id")
