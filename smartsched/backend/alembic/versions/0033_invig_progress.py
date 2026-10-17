"""Invigilation plan progress and liveness (backend asks batch 2; app/services/invigilation.py)

* ``invigilation_plans.heartbeat_at``: the job queue's beat while the plan is queued or running (like
  ``schedule_runs.heartbeat_at``), so the startup sweep can tell a plan of a dead process from one another replica
  is still solving;
* ``invigilation_plans.progress_phase`` / ``progress_pct``: the last phase and percentage the queue job reported
  (``queued`` 0, ``loading`` 10, ``solving`` 30, ``persisting`` 90, ``done`` 100, ``failed``).

Existing rows keep NULLs (a finished plan has no progress to show; the brief derives ``done`` / ``failed``).

Revision ID: 0033_invig_progress
Revises: 0032_kvkk
Create Date: 2026-10-16 18:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0033_invig_progress"
down_revision = "0032_kvkk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invigilation_plans") as batch:
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("progress_phase", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("progress_pct", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("invigilation_plans") as batch:
        batch.drop_column("progress_pct")
        batch.drop_column("progress_phase")
        batch.drop_column("heartbeat_at")
