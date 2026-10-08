"""Calendar sync and outgoing webhooks (docs/product/calendar-sync-api.md; booking-enhancements T6 / A2).

* ``calendar_feed_tokens``: per-user secrets for the ``.ics`` subscription links. Only the SHA-256 of a token is
  stored; the token is shown once.
* ``calendar_event_revisions``: ``SEQUENCE`` / ``LAST-MODIFIED`` per booking, bumped when the booking's calendar
  content (fingerprint) changes, so feeds and pushed events carry RFC 5545 update semantics.
* ``calendar_connections`` / ``calendar_event_links`` / ``calendar_sync_jobs`` / ``oauth_states``: the Google
  Calendar and Microsoft Graph push connectors (encrypted OAuth tokens, external event ids, a durable outbox).
* ``webhook_endpoints`` / ``webhook_deliveries``: signed outgoing webhooks with a delivery log.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

# outbox states (calendar_sync_jobs, webhook_deliveries)
PENDING = "PENDING"
RUNNING = "RUNNING"
DONE = "DONE"
SENT = "SENT"
FAILED = "FAILED"
SKIPPED = "SKIPPED"


class CalendarFeedToken(Base):
    __tablename__ = "calendar_feed_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex; the token is never stored
    hint: Mapped[str] = mapped_column(String(8), default="")  # last 4 characters, to tell links apart
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CalendarEventRevision(Base):
    __tablename__ = "calendar_event_revisions"

    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CalendarConnection(Base):
    __tablename__ = "calendar_connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_calendar_connections_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))  # google | microsoft
    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calendar_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    calendar_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet (APP_SECRET)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")  # ACTIVE | REAUTH | ERROR
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CalendarEventLink(Base):
    """The external event a booking was written to. No foreign key to ``bookings``: a deleted booking must still
    be removable from the external calendar."""

    __tablename__ = "calendar_event_links"
    __table_args__ = (UniqueConstraint("connection_id", "booking_id", name="uq_calendar_event_links_conn_booking"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("calendar_connections.id", ondelete="CASCADE"))
    booking_id: Mapped[int] = mapped_column(Integer, index=True)
    calendar_id: Mapped[str] = mapped_column(String(1024))
    external_id: Mapped[str] = mapped_column(String(1024))
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CalendarSyncJob(Base):
    """Durable outbox of the push connectors: ``booking`` = make the external calendar match this booking now,
    ``full`` = queue every relevant booking of the connection."""

    __tablename__ = "calendar_sync_jobs"
    __table_args__ = (Index("ix_calendar_sync_jobs_due", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("calendar_connections.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(12), default="booking")  # booking | full
    status: Mapped[str] = mapped_column(String(10), default=PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OAuthState(Base):
    """One pending authorisation (PKCE): the ``state`` is stored hashed, the code verifier encrypted."""

    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    code_verifier_enc: Mapped[str] = mapped_column(Text)
    return_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    events: Mapped[list[Any]] = mapped_column(JSON, default=list)
    secret_enc: Mapped[str] = mapped_column(Text)  # Fernet (APP_SECRET): needed in clear to sign
    secret_hint: Mapped[str] = mapped_column(String(8), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_deliveries_due", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default=PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
