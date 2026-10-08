"""Calendar sync and outgoing webhooks (docs/product/calendar-sync-api.md): hashed feed tokens, event revisions,
Google / Microsoft push connectors with a durable outbox, OAuth states, webhook endpoints and deliveries.

``users.calendar_token`` (plaintext) moves to ``calendar_feed_tokens.token_hash`` (SHA-256), so existing
subscription links keep working while the database no longer holds a usable token.

Revision ID: 0011_integrations
Revises: 0006_token_version
Create Date: 2026-10-08 16:00:00

"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "0011_integrations"
down_revision = "0006_token_version"
branch_labels = None
depends_on = None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def upgrade() -> None:
    op.create_table(
        "calendar_feed_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("hint", sa.String(length=8), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_calendar_feed_tokens_user_id", "calendar_feed_tokens", ["user_id"])
    op.create_table(
        "calendar_event_revisions",
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("last_modified", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("booking_id"),
    )
    op.create_table(
        "calendar_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_email", sa.String(length=255), nullable=True),
        sa.Column("account_subject", sa.String(length=255), nullable=True),
        sa.Column("calendar_id", sa.String(length=1024), nullable=True),
        sa.Column("calendar_name", sa.String(length=255), nullable=True),
        sa.Column("access_token_enc", sa.Text(), nullable=True),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_calendar_connections_user_provider"),
    )
    op.create_index("ix_calendar_connections_user_id", "calendar_connections", ["user_id"])
    op.create_table(
        "calendar_event_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("calendar_id", sa.String(length=1024), nullable=False),
        sa.Column("external_id", sa.String(length=1024), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["calendar_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "booking_id", name="uq_calendar_event_links_conn_booking"),
    )
    op.create_index("ix_calendar_event_links_booking_id", "calendar_event_links", ["booking_id"])
    op.create_table(
        "calendar_sync_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["calendar_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_sync_jobs_connection_id", "calendar_sync_jobs", ["connection_id"])
    op.create_index("ix_calendar_sync_jobs_due", "calendar_sync_jobs", ["status", "next_attempt_at"])
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("code_verifier_enc", sa.Text(), nullable=False),
        sa.Column("return_path", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(length=8), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("endpoint_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"])
    op.create_index("ix_webhook_deliveries_event_id", "webhook_deliveries", ["event_id"])
    op.create_index("ix_webhook_deliveries_due", "webhook_deliveries", ["status", "next_attempt_at"])

    # existing plaintext subscription tokens -> hashes (the links keep working), then drop the column
    conn = op.get_bind()
    tokens = sa.table(
        "calendar_feed_tokens",
        sa.column("user_id", sa.Integer),
        sa.column("token_hash", sa.String),
        sa.column("hint", sa.String),
        sa.column("label", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    rows = conn.execute(sa.text("SELECT id, calendar_token FROM users WHERE calendar_token IS NOT NULL")).fetchall()
    if rows:
        op.bulk_insert(
            tokens,
            [
                {
                    "user_id": uid,
                    "token_hash": hashlib.sha256(str(tok).encode("utf-8")).hexdigest(),
                    "hint": str(tok)[-4:],
                    "label": None,
                    "created_at": _now(),
                }
                for uid, tok in rows
                if tok
            ],
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_calendar_token", type_="unique")
        batch_op.drop_column("calendar_token")


def downgrade() -> None:
    # the plaintext tokens cannot be recovered from their hashes: subscription links must be created again
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("calendar_token", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint("uq_users_calendar_token", ["calendar_token"])
    op.drop_index("ix_webhook_deliveries_due", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_event_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_endpoint_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_index("ix_oauth_states_user_id", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_index("ix_calendar_sync_jobs_due", table_name="calendar_sync_jobs")
    op.drop_index("ix_calendar_sync_jobs_connection_id", table_name="calendar_sync_jobs")
    op.drop_table("calendar_sync_jobs")
    op.drop_index("ix_calendar_event_links_booking_id", table_name="calendar_event_links")
    op.drop_table("calendar_event_links")
    op.drop_index("ix_calendar_connections_user_id", table_name="calendar_connections")
    op.drop_table("calendar_connections")
    op.drop_table("calendar_event_revisions")
    op.drop_index("ix_calendar_feed_tokens_user_id", table_name="calendar_feed_tokens")
    op.drop_table("calendar_feed_tokens")
