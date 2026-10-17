"""Conflict resolver after publishing (booking enhancements wave 2, P2; docs/product/booking-enhancements.md §4.4)

* ``booking_conflicts``: one row per (published run, booking) whose slot the run's timetable holds, written when a
  run is activated; status OPEN, RESOLVED or IGNORED with the resolution (unique per run and booking).

No existing row changes.

Revision ID: 0030_booking_conflicts
Revises: 0029_booking_policies
Create Date: 2026-10-16 13:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0030_booking_conflicts"
down_revision = "0029_booking_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_conflicts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_period", sa.Integer(), nullable=False),
        sa.Column("end_period", sa.Integer(), nullable=False),
        sa.Column("held", sa.JSON(), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "booking_id", name="uq_booking_conflicts_run_booking"),
    )
    op.create_index("ix_booking_conflicts_run_status", "booking_conflicts", ["run_id", "status"])
    op.create_index("ix_booking_conflicts_term_id", "booking_conflicts", ["term_id"])
    op.create_index("ix_booking_conflicts_booking_id", "booking_conflicts", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_conflicts_booking_id", table_name="booking_conflicts")
    op.drop_index("ix_booking_conflicts_term_id", table_name="booking_conflicts")
    op.drop_index("ix_booking_conflicts_run_status", table_name="booking_conflicts")
    op.drop_table("booking_conflicts")
