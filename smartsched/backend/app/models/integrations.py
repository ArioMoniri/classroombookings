"""Calendar sync and outgoing webhooks (docs/product/calendar-sync-api.md; booking-enhancements T6 / A2).

* ``calendar_feed_tokens``: per-user secrets for the ``.ics`` subscription links. Only the SHA-256 of a token is
  stored; the token is shown once.
* ``calendar_event_revisions``: ``SEQUENCE`` / ``LAST-MODIFIED`` per booking, bumped when the booking's calendar
  content (fingerprint) changes, so feeds and pushed events carry RFC 5545 update semantics.
* ``calendar_connections`` / ``calendar_event_links`` / ``calendar_sync_jobs`` / ``oauth_states``: the Google
  Calendar and Microsoft Graph push connectors (encrypted OAuth tokens, external event ids, a durable outbox).
* ``webhook_endpoints`` / ``webhook_deliveries``: signed outgoing webhooks with a delivery log.
* ``calendar_class_revisions`` (CAL-01, alembic 0039): ``SEQUENCE`` / ``LAST-MODIFIED`` / tombstone per published
  class occurrence, keyed by a run-, assignment- and room-independent UID (``app.services.calendar_classes``). Not
  personal data: course codes, rooms, times and the ids used to find a scope's occurrences.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
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
    #: CAL-03: the one scope this link serves (``my_classes`` | ``department_classes`` | ``my_bookings`` | ``room`` |
    #: ``room_group``) and its id; NULL = a legacy multi-scope link (mine / room / room-group / department feeds)
    scope_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: the ``calendar_sync`` consent the person gave when approving this scope (``consents.id``)
    consent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: the event fields approved for this link (the admin's allow-list at approval time)
    fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CalendarEventRevision(Base):
    __tablename__ = "calendar_event_revisions"

    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CalendarClassRevision(Base):
    """One published class occurrence (CAL-01). ``room_ids`` / ``program_ids`` / ``instructor_ids`` are the current
    (or, once ended, the last) values; ``seen`` keeps every room / department / instructor the occurrence ever had, so
    a feed that showed it can send a CANCELLED tombstone when it leaves (a room move, a teacher change). ``legacy``
    rows are the pre-0039 UIDs ``class-{assignment}-{room}-{date}``, cancelled once in room / department feeds."""

    __tablename__ = "calendar_class_revisions"
    __table_args__ = (Index("ix_calendar_class_revisions_term_ended", "term_id", "ended_at"),)

    uid: Mapped[str] = mapped_column(String(160), primary_key=True)
    term_id: Mapped[int] = mapped_column(Integer, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    #: set when the occurrence left the published plan (tombstone until ``ended_at + feed_cancelled_grace_days``)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    program_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    program_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    instructor_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    room_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    seen: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    starts_at: Mapped[datetime] = mapped_column(DateTime)  # local, naive (the organisation's zone)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    summary: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    legacy: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


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
    #: CAL-06: what is pushed (``my_bookings``, ``my_classes``, ``department_classes:<id>``); NULL = ["my_bookings"]
    #: (``scopes`` above is the OAuth grant the provider returned, a different thing)
    export_scopes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    #: SmartSched created the target calendar ("SmartSched – Derslerim") and may delete it on disconnect
    owned_calendar: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    #: CAL-07: why the provider account counts as the person's (sso_identity | email | domain | tenant | none)
    account_verified: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: the nightly repair recreated a calendar the user deleted (only once; then the connection asks the user)
    calendar_recreated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CalendarEventLink(Base):
    """The external event a booking was written to. No foreign key to ``bookings``: a deleted booking must still
    be removable from the external calendar."""

    __tablename__ = "calendar_event_links"
    __table_args__ = (
        UniqueConstraint("connection_id", "booking_id", name="uq_calendar_event_links_conn_booking"),
        UniqueConstraint("connection_id", "item_key", name="uq_calendar_event_links_conn_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("calendar_connections.id", ondelete="CASCADE"))
    #: NULL for a class event (CAL-06)
    booking_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    #: ``booking:<id>`` | ``class:<uid>`` (alembic 0039 backfilled the booking rows)
    item_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
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
    #: booking | full | classes (CAL-06: diff the class scopes) | nightly (CAL-06: repair the owned calendar)
    kind: Mapped[str] = mapped_column(String(12), default="booking")
    item_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
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
    #: CAL-06: the export scopes approved before the consent screen (NULL: a legacy bookings-only connect)
    export_scopes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)


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
