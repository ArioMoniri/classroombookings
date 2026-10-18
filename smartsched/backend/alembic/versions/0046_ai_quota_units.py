"""AI quota chain and shared reservations (HB-10; docs/research/2026-10-17-ai-helper-architecture.md §5.9)

* ``ai_usage.department_id`` / ``ai_usage.faculty_id`` (integers, nullable, no foreign key): the caller's department
  (programme) and its faculty **at record time**, so a faculty report does not move when a person changes
  department. Indexes ``(created_at, faculty_id)`` and ``(created_at, department_id)`` for the monthly unit totals.
* ``ai_reservations``: the in-flight estimate of every gateway call (``kind = call``, deleted when the call settles,
  ignored after ``expires_at``) and one row per counted request for the per-minute limit (``kind = rate``, swept
  after two minutes). Every API worker reads the same rows, so two workers no longer double the budget, the
  per-minute limit or the concurrency gate. ``reserve`` serialises on ``pg_advisory_xact_lock`` (PostgreSQL).
  The rows are transient counters touched only in the system context, so the table has no row-level security.

Existing rows keep NULL units (they count toward the org budget only). Works on SQLite (batch mode) and PostgreSQL.

Revision ID: 0046_ai_quota_units
Revises: 0045_user_sessions
Create Date: 2026-10-18 13:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0046_ai_quota_units"
down_revision = "0045_user_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage") as batch:
        batch.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("faculty_id", sa.Integer(), nullable=True))
    op.create_index("ix_ai_usage_created_faculty", "ai_usage", ["created_at", "faculty_id"])
    op.create_index("ix_ai_usage_created_department", "ai_usage", ["created_at", "department_id"])
    op.create_table(
        "ai_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=8), nullable=False, server_default="call"),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("feature", sa.String(length=16), nullable=True),
        sa.Column("role_key", sa.String(length=32), nullable=True),
        sa.Column("faculty_id", sa.Integer(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("audio_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_reservations_user_created", "ai_reservations", ["user_id", "created_at"])
    op.create_index("ix_ai_reservations_expires", "ai_reservations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_reservations_expires", table_name="ai_reservations")
    op.drop_index("ix_ai_reservations_user_created", table_name="ai_reservations")
    op.drop_table("ai_reservations")
    op.drop_index("ix_ai_usage_created_department", table_name="ai_usage")
    op.drop_index("ix_ai_usage_created_faculty", table_name="ai_usage")
    with op.batch_alter_table("ai_usage") as batch:
        batch.drop_column("faculty_id")
        batch.drop_column("department_id")
