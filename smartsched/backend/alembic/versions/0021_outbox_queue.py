"""E-mail outbox on the integrations queue (ROADMAP Phase 11): ``notification_outbox`` gains ``next_attempt_at``
(when the worker tries next; indexed) and ``locked_until`` (the lease of a running send). Existing rows keep their
status (UNSENT / SENT / FAILED) and are not re-sent.

Revision ID: 0021_outbox_queue
Revises: 0020_council
Create Date: 2026-10-15 19:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_outbox_queue"
down_revision = "0020_council"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notification_outbox") as batch:
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))
        batch.create_index("ix_notification_outbox_next_attempt_at", ["next_attempt_at"])


def downgrade() -> None:
    with op.batch_alter_table("notification_outbox") as batch:
        batch.drop_index("ix_notification_outbox_next_attempt_at")
        batch.drop_column("locked_until")
        batch.drop_column("next_attempt_at")
