"""Notification channels ("Bildirim kanalları"; owner decision 2026-10-15, docs/product/2026-10-15-integrations-options.md):

* ``notify_channel_configs``: per channel kind the administrator's switch, the institution's sender credentials
  (Fernet, APP_SECRET), options, the content mode and the KVKK sign-off;
* ``user_channels``: a user's linked address (encrypted) with an HMAC for lookups;
* ``channel_link_codes``: one-time Telegram nonces and phone verification codes (HMAC only);
* ``channel_department_targets``: department -> Teams Workflows / Slack webhook (encrypted URL, host shown);
* ``channel_deliveries``: the channels outbox of the integrations worker (unique per occurrence x recipient x target).

No row is written: every channel stays off until an administrator configures it and the KVKK officer signs it off.

Revision ID: 0028_notify_channels
Revises: 0027_p19_gaps
Create Date: 2026-10-16 00:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0028_notify_channels"
down_revision = "0027_p19_gaps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notify_channel_configs",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("content_mode", sa.String(length=10), nullable=False),
        sa.Column("secrets_enc", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("kvkk_signoff", sa.JSON(), nullable=True),
        sa.Column("risk_ack", sa.JSON(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("kind"),
    )
    op.create_table(
        "user_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("address_enc", sa.Text(), nullable=False),
        sa.Column("address_hash", sa.String(length=64), nullable=False),
        sa.Column("display_hint", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "address_hash", name="uq_user_channels_address"),
    )
    op.create_index("ix_user_channels_user_id", "user_channels", ["user_id"])
    op.create_index("ix_user_channels_lookup", "user_channels", ["kind", "address_hash"])
    op.create_table(
        "channel_link_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("address_enc", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_channel_link_codes_user_id", "channel_link_codes", ["user_id"])
    op.create_table(
        "channel_department_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("url_enc", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["department_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "department_id", name="uq_channel_department_targets"),
    )
    op.create_index("ix_channel_department_targets_department_id", "channel_department_targets", ["department_id"])
    op.create_table(
        "channel_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_channel_id", sa.Integer(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("link_code_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_channel_id"], ["user_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["channel_department_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["link_code_id"], ["channel_link_codes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("ix_channel_deliveries_due", "channel_deliveries", ["status", "next_attempt_at"])
    op.create_index("ix_channel_deliveries_user_id", "channel_deliveries", ["user_id"])
    op.create_index("ix_channel_deliveries_user_channel_id", "channel_deliveries", ["user_channel_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_deliveries_user_channel_id", table_name="channel_deliveries")
    op.drop_index("ix_channel_deliveries_user_id", table_name="channel_deliveries")
    op.drop_index("ix_channel_deliveries_due", table_name="channel_deliveries")
    op.drop_table("channel_deliveries")
    op.drop_index("ix_channel_department_targets_department_id", table_name="channel_department_targets")
    op.drop_table("channel_department_targets")
    op.drop_index("ix_channel_link_codes_user_id", table_name="channel_link_codes")
    op.drop_table("channel_link_codes")
    op.drop_index("ix_user_channels_lookup", table_name="user_channels")
    op.drop_index("ix_user_channels_user_id", table_name="user_channels")
    op.drop_table("user_channels")
    op.drop_table("notify_channel_configs")
