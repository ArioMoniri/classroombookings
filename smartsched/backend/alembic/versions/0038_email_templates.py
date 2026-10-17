"""Themed e-mails (wave 3b W3-MAIL; app/emails, app/services/mail.py): the outbox remembers the button link and the reader's language

* ``notification_outbox.link`` (the panel path or URL of the e-mail's button, e.g. ``/approvals?request=7``) and
  ``notification_outbox.locale`` (``tr`` / ``en``): the HTML part is rendered from the stored subject + plain-text body
  when the message is sent, so a template fix also reaches queued mail and no HTML is stored. Both nullable: rows
  written before this revision render with the kind's default path and the organisation's language.
* Template overrides need no table: they are rows of ``translations`` (set ``email``), the CRBS override mechanism.

Plain nullable columns (batch mode): applies the same way on SQLite and PostgreSQL.

Revision ID: 0038_email_templates
Revises: 0037_identity_providers
Create Date: 2026-10-17 21:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0038_email_templates"
down_revision = "0037_identity_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notification_outbox") as batch:
        batch.add_column(sa.Column("link", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("locale", sa.String(length=8), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notification_outbox") as batch:
        batch.drop_column("locale")
        batch.drop_column("link")
