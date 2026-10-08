"""Booking enhancements wave 1, T1 find a room (docs/product/booking-enhancements.md §4.2): bookings remember
what they were searched for (``headcount``, ``required_features``) so that the conflict resolver (P2) can rank
alternatives later. No new tables.

Revision ID: 0013_find_room
Revises: 0012_room_features
Create Date: 2026-10-08 16:31:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_find_room"
down_revision = "0012_room_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bookings") as batch:
        batch.add_column(sa.Column("headcount", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("required_features", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bookings") as batch:
        batch.drop_column("required_features")
        batch.drop_column("headcount")
