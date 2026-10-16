"""A4 KVKK compliance (docs/product/booking-enhancements.md §A4 and §4.7; service: :mod:`app.services.kvkk`).

* ``retention_policies``: how long a data class is kept and what happens after (delete / anonymise); the nightly
  job applies the enabled ones unless a legal hold protects the class. The floors are in the code (audit 365 days).
* ``privacy_notices`` (aydınlatma metni, versioned per language) and ``notice_acks`` (who acknowledged which).
* ``consents``: explicit consent only where it is the legal basis (optional SMS, photo, calendar sync, personal AI).
* ``dsr_requests``: data-subject requests (export, erase, rectify, info) with the 30-day deadline and the admin
  queue.
* ``audit_purge_windows``: the only way past the append-only triggers of ``audit_events``. The retention job opens a
  ``retention`` window with a cutoff (rows older than the cutoff and older than 365 days may be deleted), an erasure
  opens an ``anonymise`` window for one person (their rows may lose actor id, label, network hash and request id).
  Both windows are deleted again in the same transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_class: Mapped[str] = mapped_column(String(32), unique=True)
    retain_days: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(10), default="delete")  # delete | anonymise
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PrivacyNotice(Base):
    __tablename__ = "privacy_notices"
    __table_args__ = (UniqueConstraint("version", "language", name="uq_privacy_notices_version_language"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(8))  # tr | en
    title: Mapped[str] = mapped_column(String(255))
    body_md: Mapped[str] = mapped_column(Text)
    #: None = draft; a published notice is never edited (a new version is)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NoticeAck(Base):
    __tablename__ = "notice_acks"
    __table_args__ = (UniqueConstraint("user_id", "notice_id", name="uq_notice_acks_user_notice"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("privacy_notices.id", ondelete="CASCADE"))
    acked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(32))  # sms | photo | calendar_sync | ai_personal
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notice_id: Mapped[int | None] = mapped_column(
        ForeignKey("privacy_notices.id", ondelete="SET NULL"), nullable=True
    )


class DsrRequest(Base):
    __tablename__ = "dsr_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: SET NULL keeps the request (and its deadline record) after the account is gone
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    #: "Silinmiş kullanıcı #h" once erased; the requester's name never stays here
    subject_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))  # export | erase | rectify | info
    status: Mapped[str] = mapped_column(String(12), default="OPEN", index=True)  # OPEN | IN_PROGRESS | DONE | REFUSED
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditPurgeWindow(Base):
    __tablename__ = "audit_purge_windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # retention | anonymise
    cutoff: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    subject_actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
