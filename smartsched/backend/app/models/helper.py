"""AI helper tables (HB-04, alembic 0044_helper; docs/research/2026-10-17-ai-helper-architecture.md §5.4, §5.7).

* ``helper_action_invocations``: one row per **confirmed** helper write. The row is created when the person presses
  the card's button: its unique ``nonce`` is the once-only claim of the signed confirm token (a replay or a double
  click hits the unique key). Previews write nothing. ``audit_id`` points at the ``helper.action.<name>`` event,
  ``undo_of`` at the invocation an undo reversed.
* ``helper_threads`` / ``helper_messages``: conversation history (kept ``ai.helper.history_days``, default 30).
* ``helper_notes``: memory the person chose to keep ("Bunu hatırla"): ≤ 20 per person, ≤ 200 characters, purged
  180 days after last use.
* ``helper_events``: product telemetry without prompt text; ``user_id`` (and a feedback ``note``) is nulled after 90
  days. HB-14 writes it (``app.ai.helper.telemetry``); ``reason`` / ``query`` / ``note`` come from 0048_helper_feedback.

Every per-person table cascades with the account and has an owner-only row-level-security policy on PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

INVOCATION_STATUSES = ("confirmed", "done", "failed", "undone")
NOTE_SOURCES = ("user_button", "user_confirmed")


class HelperActionInvocation(Base):
    __tablename__ = "helper_action_invocations"
    __table_args__ = (Index("ix_helper_invocations_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(64))
    args_hash: Mapped[str] = mapped_column(String(64))
    preview_hash: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(32), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="confirmed")
    #: the booking / approval request the write produced or touched
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: the audit event of the write (``helper.action.<name>``)
    audit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: the service's reversible audit event (``booking.create`` / ``booking.cancel``) that ``bookings_undo`` reverses
    undo_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    undo_of: Mapped[int | None] = mapped_column(
        ForeignKey("helper_action_invocations.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HelperThread(Base):
    __tablename__ = "helper_threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class HelperMessage(Base):
    __tablename__ = "helper_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("helper_threads.id", ondelete="CASCADE"), index=True)
    #: the thread's owner again, so the row-level-security policy needs no join
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text, default="")
    cards: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HelperNote(Base):
    __tablename__ = "helper_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class HelperEvent(Base):
    __tablename__ = "helper_events"
    __table_args__ = (Index("ix_helper_events_ts_kind", "ts", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    #: nulled after 90 days by the daily purge (aggregates only from then on)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    turn_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))
    feature_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: the fallback code of a turn, or the reason picked with a thumbs-down
    reason: Mapped[str | None] = mapped_column(String(48), nullable=True)
    #: an index miss only: Turkish-folded words, no digits, no e-mail; shown after ≥ 5 different people (k-anonymity)
    query: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: the person's own thumbs-down note (≤ 300); never shown to admins, deleted on erasure and after 90 days
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)


__all__ = [
    "INVOCATION_STATUSES",
    "NOTE_SOURCES",
    "HelperActionInvocation",
    "HelperEvent",
    "HelperMessage",
    "HelperNote",
    "HelperThread",
]
