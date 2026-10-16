"""Invigilator assignment for exam runs (docs/features.yml "invigilator assignment"; app/services/invigilation.py)

* ``invigilator_pool``: staff / assistants who may invigilate, and per-person rules (unavailability, duty limits,
  load factor) of anyone in the pool, an instructor included; ``term_id`` null = every term;
* ``invigilation_plans``: one solve of an exam run (status, scores, diagnosis, parent plan of a re-run); at most one
  published plan per exam run (partial unique index);
* ``invigilation_duties``: one person at one post (room, date, periods) of a plan; locked duties carry to a re-run.

No existing row changes.

Revision ID: 0031_invigilation
Revises: 0030_booking_conflicts
Create Date: 2026-10-16 14:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0031_invigilation"
down_revision = "0030_booking_conflicts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invigilator_pool",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=True),
        sa.Column("instructor_id", sa.Integer(), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("max_duties", sa.Integer(), nullable=True),
        sa.Column("max_per_day", sa.Integer(), nullable=True),
        sa.Column("load_factor", sa.Integer(), nullable=False),
        sa.Column("unavailable", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invigilator_pool_term_id", "invigilator_pool", ["term_id"])
    op.create_index("ix_invigilator_pool_instructor_id", "invigilator_pool", ["instructor_id"])
    op.create_index("ix_invigilator_pool_term_canonical", "invigilator_pool", ["term_id", "canonical_name"])

    op.create_table(
        "invigilation_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("exam_run_id", sa.Integer(), nullable=False),
        sa.Column("parent_plan_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("diagnosis", sa.JSON(), nullable=False),
        sa.Column("hard_score", sa.Integer(), nullable=True),
        sa.Column("soft_score", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["exam_run_id"], ["schedule_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_plan_id"], ["invigilation_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invigilation_plans_term_id", "invigilation_plans", ["term_id"])
    op.create_index("ix_invigilation_plans_exam_run_id", "invigilation_plans", ["exam_run_id"])
    op.create_index("ix_invigilation_plans_status", "invigilation_plans", ["status"])
    op.create_index(
        "uq_invigilation_plans_active",
        "invigilation_plans",
        ["exam_run_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "invigilation_duties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("post_key", sa.String(length=64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_period", sa.Integer(), nullable=False),
        sa.Column("end_period", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("exam_request_ids", sa.JSON(), nullable=False),
        sa.Column("person_key", sa.String(length=32), nullable=False),
        sa.Column("person_name", sa.String(length=255), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=True),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["invigilation_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["staff_id"], ["invigilator_pool.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invigilation_duties_plan_id", "invigilation_duties", ["plan_id"])
    op.create_index("ix_invigilation_duties_date", "invigilation_duties", ["date"])
    op.create_index("ix_invigilation_duties_person_key", "invigilation_duties", ["person_key"])
    op.create_index("ix_invigilation_duties_instructor_id", "invigilation_duties", ["instructor_id"])
    op.create_index("ix_invigilation_duties_staff_id", "invigilation_duties", ["staff_id"])
    op.create_index("ix_invigilation_duties_plan_post", "invigilation_duties", ["plan_id", "post_key"])


def downgrade() -> None:
    op.drop_table("invigilation_duties")
    op.drop_index("uq_invigilation_plans_active", table_name="invigilation_plans")
    op.drop_table("invigilation_plans")
    op.drop_table("invigilator_pool")
