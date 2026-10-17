"""Booking policies and exam-period mode (booking enhancements wave 2, P8; docs/product/booking-enhancements.md §P8)

* ``booking_policies``: one rule per row (scope: every room, a room, a room group or a room type; roles; minimum
  notice in working days, maximum advance, maximum back-to-back duration, maximum active bookings, buffer, quiet
  hours, blackout dates; effect refuse or request). No row is created: bookings behave as before until an
  administrator adds a rule. Exam-period mode is the setting ``policies.exam_period_mode`` (absent = off).

No existing row changes.

Revision ID: 0029_booking_policies
Revises: 0028_p19_gaps
Create Date: 2026-10-16 12:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0029_booking_policies"
down_revision = "0028_p19_gaps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("tag", sa.String(length=32), nullable=True),
        sa.Column("role_codes", sa.JSON(), nullable=False),
        sa.Column("effect", sa.String(length=10), nullable=False),
        sa.Column("min_notice_workdays", sa.Integer(), nullable=True),
        sa.Column("max_advance_days", sa.Integer(), nullable=True),
        sa.Column("max_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("max_active_bookings", sa.Integer(), nullable=True),
        sa.Column("buffer_minutes", sa.Integer(), nullable=True),
        sa.Column("quiet_hours", sa.JSON(), nullable=False),
        sa.Column("blackouts", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("booking_policies")
