"""Notification channels ("Bildirim kanalları"; owner decision 2026-10-15, docs/product/2026-10-15-integrations-options.md).

The institution owns one sender per service (a Telegram bot, a WhatsApp Business number, an SMS account, VAPID keys,
department webhooks in Teams / Slack); a user links only an **address**. SmartSched never holds a user's OAuth token
or password.

* ``notify_channel_configs``: one row per channel kind: the administrator's switch, the institution's sender
  credentials (Fernet with APP_SECRET, never returned), non-secret options, the content mode (``full`` /
  ``link_only``) and the KVKK sign-off (who, when, legal basis). A channel without a real sign-off stays off.
* ``user_channels``: a user's linked address (chat id, phone number, push subscription), encrypted at rest because
  phone numbers are personal data; ``address_hash`` (HMAC) finds a row without decrypting. Unlinking deletes the row.
* ``channel_link_codes``: one-time codes (Telegram deep-link nonce, phone verification code), stored as an HMAC
  only, 10 minutes, single use, limited attempts.
* ``channel_department_targets``: department -> Teams Workflows / Slack incoming-webhook URL (a bearer secret, so
  encrypted; the host passed the SSRF guard and the vendor allowlist).
* ``channel_deliveries``: the outbox of the integrations worker for these channels (retries, backoff, delivery log),
  unique per (occurrence, recipient, target): a retried job never sends twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class NotifyChannelConfig(Base):
    __tablename__ = "notify_channel_configs"

    #: webpush | telegram | whatsapp | whatsapp_web | sms | teams | slack
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    content_mode: Mapped[str] = mapped_column(String(10), default="link_only")  # full | link_only
    #: Fernet (APP_SECRET) of a JSON object {name: value}; never returned, never logged
    secrets_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    #: {"enabled": true, "by": .., "by_user_id": .., "at": .., "legal_basis": .., "officer": ..} (kvkk_signed)
    kvkk_signoff: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: WhatsApp Web bridge only: the administrator acknowledged the terms-of-service / ban risk (who, when)
    risk_ack: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UserChannel(Base):
    __tablename__ = "user_channels"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "address_hash", name="uq_user_channels_address"),
        Index("ix_user_channels_lookup", "kind", "address_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # webpush | telegram | whatsapp | sms
    address_enc: Mapped[str] = mapped_column(Text)  # Fernet: chat id, E.164 phone, push subscription JSON
    address_hash: Mapped[str] = mapped_column(String(64))  # HMAC-SHA256 (APP_SECRET) of the address
    display_hint: Mapped[str] = mapped_column(String(64), default="")  # masked, e.g. "+90 5•• ••• •• 33"
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)  # "Telefonum", "İş bilgisayarı"
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | blocked | failed
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ChannelLinkCode(Base):
    __tablename__ = "channel_link_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)  # HMAC-SHA256 (APP_SECRET); the code is not kept
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # telegram | whatsapp | sms
    #: the phone number waiting for its code (Fernet); null for the Telegram nonce
    address_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChannelDepartmentTarget(Base):
    __tablename__ = "channel_department_targets"
    __table_args__ = (UniqueConstraint("kind", "department_id", name="uq_channel_department_targets"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # teams | slack
    department_id: Mapped[int] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), index=True)
    url_enc: Mapped[str] = mapped_column(Text)  # Fernet: the webhook URL is a bearer secret
    host: Mapped[str] = mapped_column(String(255))  # shown instead of the URL
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChannelDelivery(Base):
    __tablename__ = "channel_deliveries"
    __table_args__ = (Index("ix_channel_deliveries_due", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    event: Mapped[str] = mapped_column(String(40))  # approval.rejected | channel.verify | channel.test | ...
    #: occurrence x recipient x target: a second queueing of the same notice is a no-op
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    #: unlinking deletes the address and, with it, whatever was still waiting for it
    user_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_channels.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_department_targets.id", ondelete="CASCADE"), nullable=True
    )
    link_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_link_codes.id", ondelete="CASCADE"), nullable=True
    )
    #: minimised content (link_only: the link and the language only); verification codes are Fernet-encrypted
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="PENDING")  # PENDING RUNNING SENT FAILED SKIPPED
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
