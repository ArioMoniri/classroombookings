"""Helper feedback and unanswered queries (HB-14; docs/research/2026-10-17-ai-helper-architecture.md §5.7)

Three nullable columns on ``helper_events``:

* ``reason`` (≤ 48): why a turn fell back to index mode (``rate_limited``, ``provider_error`` ...) or the reason a
  person picked with a thumbs-down (``wrong_page``, ``not_helpful`` ...);
* ``query`` (≤ 64): an index miss only, Turkish-folded, without digits or e-mail-like words. The admin summary shows
  it only after at least 5 different people typed it (k-anonymity); nothing else typed is ever stored;
* ``note`` (≤ 300): the person's own thumbs-down note, only when the institution allows notes. It is never shown
  to admins, goes into the DSR export, and is deleted on erasure and by the 90-day purge.

The 0044 owner-only row-level-security policy covers the new columns. Works on SQLite (batch mode) and PostgreSQL.

Revision ID: 0048_helper_feedback
Revises: 0047_rf_import_safety
Create Date: 2026-10-18 15:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0048_helper_feedback"
down_revision = "0047_rf_import_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("helper_events") as batch:
        batch.add_column(sa.Column("reason", sa.String(length=48), nullable=True))
        batch.add_column(sa.Column("query", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("note", sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("helper_events") as batch:
        batch.drop_column("note")
        batch.drop_column("query")
        batch.drop_column("reason")
