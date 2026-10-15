"""Publish guard + per-term write lock (review 2026-10-15 D4 / D8).

* ``uq_schedule_runs_active``: at most one active (published) run per term + kind -- a partial unique index
  ``(term_id, kind) WHERE is_active``. Terms that already carry several active runs of one kind (the old
  activation raced) keep the newest one active.
* ``term_locks``: one row per locked scope (``term:2026-BAHAR``) while an import or a commit writes it.

Revision ID: 0019_publish_guard_term_locks
Revises: 0018_ai_proposal_decisions
Create Date: 2026-10-15 17:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_publish_guard_term_locks"
down_revision = "0018_ai_proposal_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    true = sa.true()
    runs = sa.table(
        "schedule_runs",
        sa.column("id", sa.Integer),
        sa.column("term_id", sa.Integer),
        sa.column("kind", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    newest = (
        sa.select(runs.c.term_id, runs.c.kind, sa.func.max(runs.c.id).label("keep"))
        .where(runs.c.is_active == true)
        .group_by(runs.c.term_id, runs.c.kind)
        .having(sa.func.count() > 1)
    )
    for term_id, kind, keep in bind.execute(newest).all():
        bind.execute(
            runs.update()
            .where(runs.c.term_id == term_id, runs.c.kind == kind, runs.c.is_active == true, runs.c.id != keep)
            .values(is_active=False)
        )
    op.create_index(
        "uq_schedule_runs_active",
        "schedule_runs",
        ["term_id", "kind"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "term_locks",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("holder", sa.String(255), nullable=False),
        sa.Column("token", sa.String(36), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("term_locks")
    op.drop_index("uq_schedule_runs_active", table_name="schedule_runs")
