"""Room owner faculty (owner report 2026-11-02 item 2: Tıp classrooms are reserved for Tıp academicians)

``rooms.owner_faculty_id`` (nullable, ``faculties.id``, ``ON DELETE SET NULL``): a room owned by a faculty can be
booked only by members of that faculty (a user's faculty is their department's faculty: ``users.department_id`` ->
``programs.faculty_id``); administrators keep full access. A room without an owner is open to every faculty. The
room master's ``owner_faculty`` column and the room admin panel set it (app/services/room_faculty.py). Schema only:
no data is moved here. Works on SQLite (batch mode) and PostgreSQL.

Revision ID: 0049_room_owner_faculty
Revises: 0048_helper_feedback
Create Date: 2026-11-02 18:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0049_room_owner_faculty"
down_revision = "0048_helper_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("owner_faculty_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_rooms_owner_faculty_id", "faculties", ["owner_faculty_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_rooms_owner_faculty_id", ["owner_faculty_id"])


def downgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.drop_index("ix_rooms_owner_faculty_id")
        batch.drop_constraint("fk_rooms_owner_faculty_id", type_="foreignkey")
        batch.drop_column("owner_faculty_id")
