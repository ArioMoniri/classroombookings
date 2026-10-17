"""Calendar export for academicians (CAL-01, docs/research/2026-10-17-calendar-export.md §3.2)

* ``calendar_feed_tokens`` gains ``scope_kind`` / ``scope_id`` / ``consent_id`` / ``fields``: a link bound to one
  scope (CAL-03). NULL scope = a legacy multi-scope link, which keeps working.
* New ``calendar_class_revisions``: SEQUENCE / LAST-MODIFIED / tombstone per published class occurrence under a
  run-, assignment- and room-independent UID (``app.services.calendar_classes``). No personal data.
* ``calendar_connections`` gains ``export_scopes`` (what is pushed; the existing ``scopes`` is the OAuth grant),
  ``owned_calendar``, ``account_verified``, ``last_reconciled_at`` and ``calendar_recreated_at`` (CAL-06 / CAL-07).
* ``calendar_event_links`` gains ``item_key`` (``booking:<id>`` | ``class:<uid>``), backfilled for the existing
  booking rows and unique per connection; ``booking_id`` becomes nullable (class links have none).
* ``calendar_sync_jobs`` gains ``item_key``; ``oauth_states`` gains ``export_scopes`` (the scopes approved before
  the provider's consent screen).

Batch mode for SQLite; plain columns, one new table and one unique constraint, so it applies the same way on
PostgreSQL. The new table gets the default privileges of the RLS role from 0035 (no policy: not personal data).

Revision ID: 0039_calendar_classes
Revises: 0038_email_templates
Create Date: 2026-10-17 22:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0039_calendar_classes"
down_revision = "0038_email_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("calendar_feed_tokens") as batch:
        batch.add_column(sa.Column("scope_kind", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("scope_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("consent_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("fields", sa.JSON(), nullable=True))

    op.create_table(
        "calendar_class_revisions",
        sa.Column("uid", sa.String(length=160), primary_key=True),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_modified", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("program_ids", sa.JSON(), nullable=False),
        sa.Column("instructor_ids", sa.JSON(), nullable=False),
        sa.Column("room_ids", sa.JSON(), nullable=False),
        sa.Column("seen", sa.JSON(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("location", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("legacy", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_calendar_class_revisions_term_id", "calendar_class_revisions", ["term_id"])
    op.create_index("ix_calendar_class_revisions_term_ended", "calendar_class_revisions", ["term_id", "ended_at"])

    with op.batch_alter_table("calendar_connections") as batch:
        batch.add_column(sa.Column("export_scopes", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("owned_calendar", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("account_verified", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("last_reconciled_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("calendar_recreated_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("calendar_event_links") as batch:
        batch.add_column(sa.Column("item_key", sa.String(length=180), nullable=True))
        batch.alter_column("booking_id", existing_type=sa.Integer(), nullable=True)
    op.execute(
        "UPDATE calendar_event_links SET item_key = 'booking:' || CAST(booking_id AS VARCHAR(20)) "
        "WHERE booking_id IS NOT NULL AND item_key IS NULL"
    )
    with op.batch_alter_table("calendar_event_links") as batch:
        batch.create_unique_constraint("uq_calendar_event_links_conn_item", ["connection_id", "item_key"])

    with op.batch_alter_table("calendar_sync_jobs") as batch:
        batch.add_column(sa.Column("item_key", sa.String(length=180), nullable=True))

    with op.batch_alter_table("oauth_states") as batch:
        batch.add_column(sa.Column("export_scopes", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("oauth_states") as batch:
        batch.drop_column("export_scopes")

    op.execute("DELETE FROM calendar_sync_jobs WHERE kind IN ('classes', 'nightly')")
    with op.batch_alter_table("calendar_sync_jobs") as batch:
        batch.drop_column("item_key")

    op.execute("DELETE FROM calendar_event_links WHERE booking_id IS NULL")
    with op.batch_alter_table("calendar_event_links") as batch:
        batch.drop_constraint("uq_calendar_event_links_conn_item", type_="unique")
    with op.batch_alter_table("calendar_event_links") as batch:
        batch.drop_column("item_key")
        batch.alter_column("booking_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("calendar_connections") as batch:
        batch.drop_column("calendar_recreated_at")
        batch.drop_column("last_reconciled_at")
        batch.drop_column("account_verified")
        batch.drop_column("owned_calendar")
        batch.drop_column("export_scopes")

    op.drop_index("ix_calendar_class_revisions_term_ended", table_name="calendar_class_revisions")
    op.drop_index("ix_calendar_class_revisions_term_id", table_name="calendar_class_revisions")
    op.drop_table("calendar_class_revisions")

    with op.batch_alter_table("calendar_feed_tokens") as batch:
        batch.drop_column("fields")
        batch.drop_column("consent_id")
        batch.drop_column("scope_id")
        batch.drop_column("scope_kind")
