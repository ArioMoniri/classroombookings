"""A4 KVKK compliance (docs/product/booking-enhancements.md §A4 and §4.7; Law 6698 Art. 7, 11, 13).

* **Data inventory** (:data:`DATA_CLASSES`): what SmartSched keeps, where, on which legal basis, for how long
  (``GET /admin/kvkk/inventory``, for the VERBİS preparation).
* **Retention** (``retention_policies``): per data class ``retain_days`` and ``delete`` / ``anonymise``; the
  administrator edits them and the code refuses values under the floor (:data:`FLOORS`: audit 365 days). The
  daily job (:func:`start_purge_job`, like ``learning.start_purge_job``) applies every enabled policy that no legal
  hold protects and writes one ``kvkk.retention`` audit event per class with the counts. Every policy ships
  **disabled**: nothing is destroyed until the institution's KVKK officer reviewed the periods.
  Audit rows are deleted through the ``audit_purge_windows`` exception of the append-only triggers (older than the
  cutoff and than 365 days, enforced by the database too).
* **Privacy notices** (aydınlatma metni): versioned per language, published once and never edited; a user who has
  not acknowledged the current version sees it first (``GET /me/privacy`` ``needs_ack``).
* **Consents**: explicit consent only where it is the legal basis (``sms``, ``photo``, ``calendar_sync``,
  ``ai_personal``); withdrawing ``sms`` deletes the linked phone numbers at once.
* **Data-subject requests** (``dsr_requests``): ``export`` is self-service (a zip of JSON + CSV built at download
  time, never stored, for 7 days); ``erase``, ``rectify`` and ``info`` go to the administrators' queue with the
  30-day deadline (Art. 13). Completing an erasure cancels the person's future bookings with a reason, anonymises
  the past ones, deletes their notifications, delivery ledgers, channel links, SSO identities, calendar links and
  tokens, personal settings, consents and learned observations (``learning.erase_person``), pseudonymises their audit
  rows (actor ``Silinmiş kullanıcı #h``; the rows are kept: legal retention) and anonymises the account itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import hmac
import io
import json
import logging
import secrets
import zipfile
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, revoke_tokens
from app.models import (
    ApprovalRequest,
    ApproverScope,
    AuditEvent,
    Booking,
    BookingPeriod,
    BookingSeries,
    BookingSlot,
    CalendarConnection,
    CalendarFeedToken,
    ChannelDelivery,
    ChannelLinkCode,
    InAppNotification,
    Instructor,
    MultiBooking,
    NotificationDelivery,
    NotificationOutbox,
    OAuthState,
    PasswordResetToken,
    RoomAcl,
    Setting,
    SsoAuthState,
    SsoInvite,
    User,
    UserChannel,
    UserConstraint,
    UserIdentity,
)
from app.models.base import utcnow
from app.models.booking import BOOKED, CANCELLED, PENDING
from app.models.catalog import Room
from app.models.kvkk import AuditPurgeWindow, Consent, DsrRequest, NoticeAck, PrivacyNotice, RetentionPolicy
from app.services import audit
from app.services.events import publish_event

log = logging.getLogger(__name__)

DUE_DAYS = 30  # Art. 13: requests are answered within 30 days [verify the exact wording with legal]
DOWNLOAD_DAYS = 7
KINDS = ("export", "erase", "rectify", "info")
OPEN_STATES = ("OPEN", "IN_PROGRESS")
PURPOSES: dict[str, tuple[str, str]] = {
    "sms": ("SMS / WhatsApp ile bildirim (telefon numaram)", "Notifications by SMS / WhatsApp (my phone number)"),
    "photo": ("Profil fotoğrafı", "Profile photo"),
    "calendar_sync": ("Takvimimle eşitleme (Google / Microsoft)", "Sync with my calendar (Google / Microsoft)"),
    "ai_personal": ("Kişisel verimin yapay zekâ ile işlenmesi", "Processing of my data by the AI assistant"),
}
#: the phone-based channels a withdrawn SMS consent removes
PHONE_CHANNELS = ("sms", "whatsapp")
ACTIONS = ("delete", "anonymise")

#: the inventory; ``retention`` = the class has a retention policy the daily job applies
DATA_CLASSES: dict[str, dict[str, Any]] = {
    "account": {
        "tr": "Hesap: ad, kullanıcı adı, e-posta, rol, bölüm, dil, son giriş",
        "en": "Account: name, username, e-mail, role, department, language, last sign-in",
        "tables": ["users", "user_identities", "sso_invites"],
        "legal_basis": "KVKK m.5/2(c) sözleşmenin ifası, (ç) hukuki yükümlülük (kurumun kamu görevi)",
        "retention": None,
        "kept": "hesap silme talebine ya da kurumdan ayrılışa kadar",
    },
    "booking": {
        "tr": "Rezervasyonlar ve seriler: kimin adına, oda, tarih, notlar",
        "en": "Bookings and series: for whom, room, date, notes",
        "tables": ["bookings", "booking_series", "approval_requests", "approval_decisions"],
        "legal_basis": "KVKK m.5/2(c), (f) meşru menfaat (derslik kullanımının planlanması)",
        "retention": {"default_days": 1095, "floor_days": 365, "action": "anonymise"},
    },
    "audit": {
        "tr": "Denetim kaydı: kim neyi ne zaman değiştirdi (ağ adresi yalnızca /24 HMAC)",
        "en": "Audit log: who changed what and when (network only as an HMAC of the /24)",
        "tables": ["audit_events"],
        "legal_basis": "KVKK m.5/2(ç) hukuki yükümlülük, (e) bir hakkın tesisi ve korunması",
        "retention": {"default_days": 730, "floor_days": 365, "action": "delete"},
    },
    "notification": {
        "tr": "Bildirimler ve teslim kayıtları (uygulama içi, e-posta, kanallar)",
        "en": "Notifications and delivery ledgers (in-app, e-mail, channels)",
        "tables": ["inapp_notifications", "notification_deliveries", "notification_outbox", "channel_deliveries"],
        "legal_basis": "KVKK m.5/2(c), (f)",
        "retention": {"default_days": 180, "floor_days": 30, "action": "delete"},
    },
    "phone": {
        "tr": "Bağlı kanallar: telefon (SMS/WhatsApp), Telegram, tarayıcı bildirimi (şifreli)",
        "en": "Linked channels: phone (SMS/WhatsApp), Telegram, browser push (encrypted)",
        "tables": ["user_channels", "channel_link_codes"],
        "legal_basis": "KVKK m.5/1 açık rıza (kişi kendi bağlar; rıza geri alınınca silinir)",
        "retention": None,
        "kept": "kişi bağlantıyı kaldırana ya da rızasını geri alana kadar",
    },
    "calendar": {
        "tr": "Takvim abonelik bağlantıları ve Google / Microsoft bağlantıları",
        "en": "Calendar feed links and Google / Microsoft connections",
        "tables": ["calendar_feed_tokens", "calendar_connections", "calendar_event_links"],
        "legal_basis": "KVKK m.5/1 açık rıza; yurt dışı aktarım m.9 (7499 sayılı Kanun)",
        "retention": None,
        "kept": "kişi bağlantıyı kaldırana kadar",
    },
    "learning": {
        "tr": "Öğrenilen tercihler (geçmiş planlardan çıkarılan kanıt)",
        "en": "Learned preferences (evidence from past timetables)",
        "tables": ["learned_observations", "learned_priors", "suggestion_feedback"],
        "legal_basis": "KVKK m.5/2(f) meşru menfaat",
        "retention": None,
        "kept": "sıfırlama ya da silme talebine kadar (30 gün geri alma süresi)",
    },
    "login_ip": {
        "tr": "Ağ adresi: saklanmaz; yalnızca /24 ağın HMAC özeti denetim kaydında",
        "en": "Network address: not stored; only an HMAC of the /24 network in the audit log",
        "tables": ["audit_events.ip_hash"],
        "legal_basis": "KVKK m.5/2(ç), 5651 sayılı Kanun",
        "retention": None,
        "kept": "denetim kaydıyla birlikte",
    },
    "checkin": {
        "tr": "Yoklama / giriş kaydı: bu sürümde tutulmaz",
        "en": "Check-ins: not stored in this version",
        "tables": [],
        "legal_basis": "-",
        "retention": None,
        "kept": "tutulmaz",
    },
    "availability": {
        "tr": "Uygunluk gerekçeleri: tutulmaz (sağlık bilgisi istenmez, m.6)",
        "en": "Availability reasons: not stored (no health data is asked for, Art. 6)",
        "tables": [],
        "legal_basis": "-",
        "retention": None,
        "kept": "tutulmaz",
    },
    "ai_prompt": {
        "tr": "Yapay zekâ istemleri: yalnızca belirteç sayıları ve model adı günlüğe yazılır",
        "en": "AI prompts: only token counts and the model id are logged",
        "tables": [],
        "legal_basis": "KVKK m.9 (yurt dışı aktarım), yönetici onayı gerekir",
        "retention": None,
        "kept": "tutulmaz",
    },
}
FLOORS = {k: v["retention"]["floor_days"] for k, v in DATA_CLASSES.items() if v["retention"]}


class KvkkError(Exception):
    def __init__(self, status: int, code: str, message: str, message_tr: str, **data: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.message_tr, self.data = status, code, message, message_tr, data

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "message_en": self.message,
            "message_tr": self.message_tr,
            **self.data,
        }


def pseudonym(user_id: int) -> str:
    """``Silinmiş kullanıcı #h``: a stable keyed hash, so counts per (former) person still add up."""
    key = get_settings().app_secret.encode()
    h = hmac.new(key, f"user:{user_id}".encode(), hashlib.sha256).hexdigest()[:8]
    return f"Silinmiş kullanıcı #{h}"


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime | date) else v


# --------------------------------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------------------------------


async def ensure_policies(session: AsyncSession) -> list[RetentionPolicy]:
    """One row per class with a retention rule; new rows are disabled with the class's default period."""
    rows = {p.data_class: p for p in (await session.execute(select(RetentionPolicy))).scalars()}
    for code, spec in DATA_CLASSES.items():
        if spec["retention"] and code not in rows:
            p = RetentionPolicy(
                data_class=code,
                retain_days=spec["retention"]["default_days"],
                action=spec["retention"]["action"],
                enabled=False,
                legal_hold=False,
            )
            session.add(p)
            rows[code] = p
    await session.flush()
    return [rows[c] for c in DATA_CLASSES if c in rows]


def policy_out(p: RetentionPolicy) -> dict[str, Any]:
    spec = DATA_CLASSES.get(p.data_class, {})
    return {
        "data_class": p.data_class,
        "label_tr": spec.get("tr"),
        "label_en": spec.get("en"),
        "retain_days": p.retain_days,
        "floor_days": FLOORS.get(p.data_class),
        "action": p.action,
        "enabled": p.enabled,
        "legal_hold": p.legal_hold,
        "legal_hold_reason": p.legal_hold_reason,
        "last_run_at": _iso(p.last_run_at),
        "last_result": p.last_result,
        "updated_at": _iso(p.updated_at),
    }


async def update_policy(session: AsyncSession, actor: User, data_class: str, data: dict[str, Any]) -> RetentionPolicy:
    rows = {p.data_class: p for p in await ensure_policies(session)}
    p = rows.get(data_class)
    if p is None:
        raise KvkkError(404, "data_class", f"no retention policy for {data_class!r}", "bu veri sınıfı için kural yok")
    before = policy_out(p)
    if data.get("retain_days") is not None:
        days = int(data["retain_days"])
        floor = FLOORS[data_class]
        if days < floor:
            raise KvkkError(
                422,
                "below_floor",
                f"{data_class} must be kept at least {floor} days",
                f"{data_class} verisi en az {floor} gün saklanmalı",
                floor_days=floor,
            )
        p.retain_days = days
    if data.get("action") is not None:
        if data["action"] not in ACTIONS:
            raise KvkkError(422, "action", "action: delete or anonymise", "işlem: delete (sil) ya da anonymise")
        if data_class == "booking" and data["action"] == "delete":
            raise KvkkError(
                422,
                "action",
                "bookings are anonymised, not deleted (room usage statistics stay)",
                "rezervasyonlar silinmez, anonimleştirilir (kullanım istatistikleri korunur)",
            )
        p.action = data["action"]
    for key in ("enabled", "legal_hold"):
        if data.get(key) is not None:
            setattr(p, key, bool(data[key]))
    if "legal_hold_reason" in data:
        p.legal_hold_reason = (data.get("legal_hold_reason") or "").strip() or None
    if p.legal_hold and not p.legal_hold_reason:
        raise KvkkError(422, "legal_hold_reason", "a legal hold needs a reason", "yasal saklama için gerekçe yazın")
    p.updated_by, p.updated_at = actor.id, utcnow()
    await session.flush()
    await audit.record(
        session, "kvkk.retention_policy", "retention_policy", data_class, before=before, after=policy_out(p), actor=actor
    )
    return p


async def _count_delete(session: AsyncSession, stmt: Any) -> int:
    res = await session.execute(stmt.execution_options(synchronize_session=False))
    return int(getattr(res, "rowcount", 0) or 0)


async def _purge_class(session: AsyncSession, p: RetentionPolicy, now: datetime) -> dict[str, int]:
    cutoff = now - timedelta(days=max(p.retain_days, FLOORS[p.data_class]))
    out: dict[str, int] = {}
    if p.data_class == "audit":
        window = AuditPurgeWindow(kind="retention", cutoff=cutoff, created_at=now)
        session.add(window)
        await session.flush()
        out["audit_events"] = await _count_delete(session, delete(AuditEvent).where(AuditEvent.ts < cutoff))
        await session.delete(window)
        await session.flush()
    elif p.data_class == "notification":
        out["inapp_notifications"] = await _count_delete(
            session, delete(InAppNotification).where(InAppNotification.created_at < cutoff)
        )
        out["notification_deliveries"] = await _count_delete(
            session, delete(NotificationDelivery).where(NotificationDelivery.created_at < cutoff)
        )
        out["notification_outbox"] = await _count_delete(
            session,
            delete(NotificationOutbox).where(
                NotificationOutbox.created_at < cutoff, NotificationOutbox.status.in_(("SENT", "FAILED", "UNSENT"))
            ),
        )
        out["channel_deliveries"] = await _count_delete(
            session,
            delete(ChannelDelivery).where(
                ChannelDelivery.created_at < cutoff, ChannelDelivery.status.in_(("SENT", "FAILED", "SKIPPED"))
            ),
        )
    elif p.data_class == "booking":
        day = cutoff.date()
        q = (
            update(Booking)
            .where(Booking.date < day, or_(Booking.user_id.is_not(None), Booking.notes.is_not(None)))
            .values(user_id=None, notes=None, created_by=None, updated_by=None, cancelled_by=None)
        )
        out["bookings"] = await _count_delete(session, q)
        last = (
            select(BookingSeries.id)
            .join(Booking, Booking.series_id == BookingSeries.id)
            .group_by(BookingSeries.id)
            .having(func.max(Booking.date) < day)
        )
        out["booking_series"] = await _count_delete(
            session,
            update(BookingSeries)
            .where(BookingSeries.id.in_(last), BookingSeries.user_id.is_not(None))
            .values(user_id=None, notes=None, created_by=None, updated_by=None, cancelled_by=None),
        )
    return out


async def purge_expired(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    """Apply every enabled policy without a legal hold; one ``kvkk.retention`` audit event per class."""
    now = now or utcnow()
    out: dict[str, Any] = {}
    for p in await ensure_policies(session):
        if not p.enabled:
            continue
        if p.legal_hold:
            out[p.data_class] = {"skipped": "legal_hold"}
            continue
        counts = await _purge_class(session, p, now)
        p.last_run_at, p.last_result = now, counts
        out[p.data_class] = counts
        await audit.record(
            session,
            "kvkk.retention",
            "retention_policy",
            p.data_class,
            after={"retain_days": p.retain_days, "action": p.action, "counts": counts},
        )
    await session.flush()
    return out


PURGE_INTERVAL_S = 24 * 3600.0
_task: asyncio.Task[None] | None = None


async def purge_once() -> dict[str, Any]:
    from app.core.db import get_session_factory

    async with get_session_factory()() as session:
        out = await purge_expired(session)
        await session.commit()
    return out


async def _loop(interval: float) -> None:
    while True:
        try:
            out = await purge_once()
            if out:
                log.info("kvkk retention: %s", out)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failing purge never stops the loop or the app
            log.exception("kvkk retention failed")
        await asyncio.sleep(interval)


def start_purge_job(interval: float = PURGE_INTERVAL_S) -> None:
    """Started from ``app.main`` lifespan next to ``learning.start_purge_job()`` (not in the test environment)."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(interval), name="kvkk-retention")


async def stop_purge_job() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None


async def inventory(session: AsyncSession) -> dict[str, Any]:
    policies = {p.data_class: p for p in await ensure_policies(session)}
    from sqlalchemy import text

    classes = []
    for code, spec in DATA_CLASSES.items():
        counts: dict[str, int] = {}
        for t in spec["tables"]:
            if "." in t:
                continue
            try:
                counts[t] = int((await session.execute(text(f"select count(*) from {t}"))).scalar_one())  # noqa: S608
            except Exception:  # noqa: BLE001 - a table of an optional feature may not exist on an old database
                counts[t] = 0
        p = policies.get(code)
        classes.append(
            {
                "code": code,
                "label_tr": spec["tr"],
                "label_en": spec["en"],
                "tables": spec["tables"],
                "rows": counts,
                "legal_basis": spec["legal_basis"],
                "retention": policy_out(p) if p else None,
                "kept": spec.get("kept"),
            }
        )
    return {"generated_at": utcnow().isoformat(timespec="seconds") + "Z", "classes": classes}


# --------------------------------------------------------------------------------------------------
# Privacy notices and consents
# --------------------------------------------------------------------------------------------------


def notice_out(n: PrivacyNotice) -> dict[str, Any]:
    return {
        "id": n.id,
        "version": n.version,
        "language": n.language,
        "title": n.title,
        "body_md": n.body_md,
        "published_at": _iso(n.published_at),
        "created_at": _iso(n.created_at),
    }


async def current_notice(session: AsyncSession, language: str | None) -> PrivacyNotice | None:
    """The latest published notice in ``language``, else in Turkish, else any."""
    q = select(PrivacyNotice).where(PrivacyNotice.published_at.is_not(None)).order_by(PrivacyNotice.version.desc())
    rows = list((await session.execute(q)).scalars())
    if not rows:
        return None
    top = rows[0].version
    latest = [r for r in rows if r.version == top]
    for lang in (language, "tr"):
        hit = next((r for r in latest if r.language == lang), None)
        if hit is not None:
            return hit
    return latest[0]


async def needs_ack(session: AsyncSession, user: User) -> bool:
    n = await current_notice(session, user.language)
    if n is None:
        return False
    same_version = select(PrivacyNotice.id).where(PrivacyNotice.version == n.version)
    q = select(NoticeAck.id).where(NoticeAck.user_id == user.id, NoticeAck.notice_id.in_(same_version))
    return (await session.execute(q)).first() is None


async def ack(session: AsyncSession, user: User, notice_id: int) -> NoticeAck:
    n = await session.get(PrivacyNotice, notice_id)
    if n is None or n.published_at is None:
        raise KvkkError(404, "notice", "notice not found", "aydınlatma metni bulunamadı")
    existing = (
        await session.execute(select(NoticeAck).where(NoticeAck.user_id == user.id, NoticeAck.notice_id == n.id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = NoticeAck(user_id=user.id, notice_id=n.id, acked_at=utcnow())
    session.add(row)
    await session.flush()
    await audit.record(session, "kvkk.notice_ack", "privacy_notice", n.id, after={"version": n.version}, actor=user)
    return row


async def consents_of(session: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    rows = list(
        (
            await session.execute(select(Consent).where(Consent.user_id == user_id).order_by(Consent.id))
        ).scalars()
    )
    out = []
    for code, (tr, en) in PURPOSES.items():
        last = next((r for r in reversed(rows) if r.purpose == code), None)
        out.append(
            {
                "purpose": code,
                "label_tr": tr,
                "label_en": en,
                "granted": last is not None and last.withdrawn_at is None,
                "granted_at": _iso(last.granted_at) if last else None,
                "withdrawn_at": _iso(last.withdrawn_at) if last else None,
            }
        )
    return out


async def grant(session: AsyncSession, user: User, purpose: str) -> None:
    if purpose not in PURPOSES:
        raise KvkkError(404, "purpose", "unknown consent purpose", "bilinmeyen rıza amacı")
    active = (
        await session.execute(
            select(Consent).where(Consent.user_id == user.id, Consent.purpose == purpose, Consent.withdrawn_at.is_(None))
        )
    ).scalar_one_or_none()
    if active is not None:
        return
    n = await current_notice(session, user.language)
    session.add(Consent(user_id=user.id, purpose=purpose, granted_at=utcnow(), notice_id=n.id if n else None))
    await session.flush()
    await audit.record(session, "kvkk.consent_grant", "consent", purpose, after={"user_id": user.id}, actor=user)


async def withdraw(session: AsyncSession, user: User, purpose: str) -> dict[str, int]:
    if purpose not in PURPOSES:
        raise KvkkError(404, "purpose", "unknown consent purpose", "bilinmeyen rıza amacı")
    now = utcnow()
    rows = (
        await session.execute(
            select(Consent).where(Consent.user_id == user.id, Consent.purpose == purpose, Consent.withdrawn_at.is_(None))
        )
    ).scalars()
    for r in rows:
        r.withdrawn_at = now
    removed = 0
    if purpose == "sms":  # the phone number goes at once (spec §4.7 edge case)
        removed = await _count_delete(
            session, delete(UserChannel).where(UserChannel.user_id == user.id, UserChannel.kind.in_(PHONE_CHANNELS))
        )
        await _count_delete(
            session,
            delete(ChannelLinkCode).where(ChannelLinkCode.user_id == user.id, ChannelLinkCode.kind.in_(PHONE_CHANNELS)),
        )
    await session.flush()
    await audit.record(
        session, "kvkk.consent_withdraw", "consent", purpose, after={"user_id": user.id, "removed": removed}, actor=user
    )
    return {"removed_channels": removed}


# --------------------------------------------------------------------------------------------------
# Data-subject requests
# --------------------------------------------------------------------------------------------------


def dsr_out(r: DsrRequest, now: datetime | None = None, *, admin: bool = False) -> dict[str, Any]:
    now = now or utcnow()
    out = {
        "id": r.id,
        "kind": r.kind,
        "status": r.status,
        "note": r.note,
        "created_at": _iso(r.created_at),
        "due_at": _iso(r.due_at),
        "overdue": r.status in OPEN_STATES and r.due_at < now,
        "days_left": (r.due_at.date() - now.date()).days if r.status in OPEN_STATES else None,
        "handled_at": _iso(r.handled_at),
        "result": r.result,
        "refusal_reason": r.refusal_reason,
        "download_expires_at": _iso(r.download_expires_at),
        "downloadable": r.kind == "export"
        and r.status == "DONE"
        and r.download_expires_at is not None
        and r.download_expires_at > now,
    }
    if admin:
        out["user_id"] = r.user_id
        out["subject"] = r.subject_label
    return out


async def create_request(session: AsyncSession, user: User, kind: str, note: str | None) -> DsrRequest:
    if kind not in KINDS:
        raise KvkkError(422, "kind", "kind: export, erase, rectify or info", "talep türü: export, erase, rectify, info")
    now = utcnow()
    if kind != "export":
        dup = (
            await session.execute(
                select(DsrRequest).where(
                    DsrRequest.user_id == user.id, DsrRequest.kind == kind, DsrRequest.status.in_(OPEN_STATES)
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise KvkkError(
                409, "duplicate", "you have an open request of this kind", "bu türde açık bir talebiniz var", id=dup.id
            )
    r = DsrRequest(
        user_id=user.id,
        subject_label=audit.user_label(user),
        kind=kind,
        status="OPEN",
        note=(note or "").strip() or None,
        created_at=now,
        due_at=now + timedelta(days=DUE_DAYS),
    )
    if kind == "export":  # self-service: the zip is built at download time and never stored
        r.status, r.handled_at = "DONE", now
        r.download_expires_at = now + timedelta(days=DOWNLOAD_DAYS)
    session.add(r)
    await session.flush()
    await audit.record(session, f"kvkk.dsr_{kind}", "dsr_request", r.id, after={"kind": kind, "status": r.status},
                       actor=user)
    return r


async def mine(session: AsyncSession, user: User) -> list[DsrRequest]:
    q = select(DsrRequest).where(DsrRequest.user_id == user.id).order_by(DsrRequest.id.desc())
    return list((await session.execute(q)).scalars())


def _csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    if not rows:
        return ""
    keys = list(dict.fromkeys(k for r in rows for k in r))
    w = csv.DictWriter(buf, fieldnames=keys)
    w.writeheader()
    for r in rows:
        w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else _iso(v) for k, v in r.items()})
    return buf.getvalue()


async def export_data(session: AsyncSession, user: User) -> dict[str, list[dict[str, Any]]]:
    """The person's own records. Other people on shared items (approvers, the one who booked for them) appear as
    their role ("Onaycı", "Yönetici"), never by name or e-mail."""
    uid = user.id
    rooms = {r.id: r.display_name for r in (await session.execute(select(Room))).scalars()}
    periods = {p.id: p.name for p in (await session.execute(select(BookingPeriod))).scalars()}
    data: dict[str, list[dict[str, Any]]] = {}
    data["profile"] = [
        {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "firstname": user.firstname,
            "lastname": user.lastname,
            "role": user.role,
            "department_id": user.department_id,
            "language": user.language,
            "auth_source": user.auth_source,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
        }
    ]
    bookings = list((await session.execute(select(Booking).where(Booking.user_id == uid).order_by(Booking.date))).scalars())
    data["bookings"] = [
        {
            "id": b.id,
            "date": b.date,
            "room": rooms.get(b.room_id),
            "period": periods.get(b.period_id),
            "status": b.status,
            "notes": b.notes,
            "cancel_reason": b.cancel_reason,
            "series_id": b.series_id,
            "booked_by": "kendim / myself" if b.created_by == uid else "başka bir kullanıcı / another user",
            "created_at": b.created_at,
        }
        for b in bookings
    ]
    series = (await session.execute(select(BookingSeries).where(BookingSeries.user_id == uid))).scalars()
    data["series"] = [
        {"id": s.id, "room": rooms.get(s.room_id), "weekday": s.weekday, "status": s.status, "notes": s.notes}
        for s in series
    ]
    reqs = (await session.execute(select(ApprovalRequest).where(ApprovalRequest.requested_by == uid))).scalars()
    data["approvals"] = [
        {
            "id": r.id,
            "room": rooms.get(r.room_id),
            "status": r.status,
            "requested_at": r.requested_at,
            "decided_at": r.decided_at,
            "decided_by": ("Onaycı / approver" if r.decided_by not in (None, uid) else ("kendim" if r.decided_by else None)),
            "note": r.note,
            "reason_code": r.reason_code,
        }
        for r in reqs
    ]
    notes = (await session.execute(select(InAppNotification).where(InAppNotification.user_id == uid))).scalars()
    data["notifications"] = [
        {"kind": x.kind, "title": x.title, "body": x.body, "created_at": x.created_at, "read_at": x.read_at}
        for x in notes
    ]
    dels = (await session.execute(select(NotificationDelivery).where(NotificationDelivery.user_id == uid))).scalars()
    data["deliveries"] = [
        {"event": d.event, "channel": d.channel, "status": d.status, "created_at": d.created_at} for d in dels
    ]
    cdel = (await session.execute(select(ChannelDelivery).where(ChannelDelivery.user_id == uid))).scalars()
    data["channel_deliveries"] = [
        {"channel": d.kind, "event": d.event, "status": d.status, "created_at": d.created_at} for d in cdel
    ]
    chans = (await session.execute(select(UserChannel).where(UserChannel.user_id == uid))).scalars()
    data["channels"] = [
        {"kind": c.kind, "address": c.display_hint, "label": c.label, "status": c.status, "verified_at": c.verified_at}
        for c in chans
    ]
    ids = (await session.execute(select(UserIdentity).where(UserIdentity.user_id == uid))).scalars()
    data["sso_identities"] = [
        {"provider": i.provider, "email_at_login": i.email_at_login, "display_name": i.display_name,
         "origin": i.origin, "created_at": i.created_at, "last_login_at": i.last_login_at}
        for i in ids
    ]
    data["consents"] = await consents_of(session, uid)
    acks = (await session.execute(select(NoticeAck).where(NoticeAck.user_id == uid))).scalars()
    data["notice_acks"] = [{"notice_id": a.notice_id, "acked_at": a.acked_at} for a in acks]
    evs = (
        await session.execute(select(AuditEvent).where(AuditEvent.actor_id == uid).order_by(AuditEvent.id))
    ).scalars()
    data["audit_as_actor"] = [
        {"ts": e.ts, "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id, "reason": e.reason}
        for e in evs
    ]
    from app.models import LearnedObservation

    ins = (await session.execute(select(Instructor).where(Instructor.user_id == uid))).scalars().first()
    keys = [("user", str(uid))] + ([("instructor", str(ins.id))] if ins else [])
    obs = (
        await session.execute(
            select(LearnedObservation).where(
                or_(*((LearnedObservation.subject_type == st) & (LearnedObservation.subject_key == sk) for st, sk in keys))
            )
        )
    ).scalars()
    data["learning_observations"] = [
        {"kind": o.kind, "attribute": o.attribute, "value": o.value, "weight": o.weight, "ts": o.ts} for o in obs
    ]
    data["data_requests"] = [dsr_out(r) for r in await mine(session, user)]
    return data


async def export_zip(session: AsyncSession, user: User, request_id: int) -> bytes:
    r = await session.get(DsrRequest, request_id)
    now = utcnow()
    if r is None or r.user_id != user.id or r.kind != "export":
        raise KvkkError(404, "not_found", "request not found", "talep bulunamadı")
    if r.status != "DONE" or r.download_expires_at is None or r.download_expires_at <= now:
        raise KvkkError(410, "expired", "the download expired; make a new request", "indirme süresi doldu; yeni talep")
    data = await export_data(session, user)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2, default=_iso))
        for name, rows in data.items():
            z.writestr(f"{name}.csv", _csv(rows))
        z.writestr(
            "README.txt",
            "SmartSched kişisel veri dökümü / personal data export (KVKK m.11)\n"
            f"Oluşturma / generated: {now.isoformat(timespec='seconds')}Z\n"
            "Başka kişiler yalnızca rolleriyle gösterilir / other people appear only by their role.\n",
        )
    await audit.record(session, "kvkk.dsr_download", "dsr_request", r.id, after={"sections": len(data)}, actor=user)
    return buf.getvalue()


async def queue(session: AsyncSession, status: str | None) -> list[DsrRequest]:
    q = select(DsrRequest).where(DsrRequest.kind != "export")
    if status == "open":
        q = q.where(DsrRequest.status.in_(OPEN_STATES))
    elif status:
        q = q.where(DsrRequest.status == status.upper())
    return list((await session.execute(q.order_by(DsrRequest.due_at, DsrRequest.id))).scalars())


async def _load_open(session: AsyncSession, request_id: int) -> DsrRequest:
    r = await session.get(DsrRequest, request_id)
    if r is None or r.kind == "export":
        raise KvkkError(404, "not_found", "request not found", "talep bulunamadı")
    if r.status not in OPEN_STATES:
        raise KvkkError(409, "closed", f"the request is already {r.status}", f"talep zaten {r.status}")
    return r


async def refuse(session: AsyncSession, admin: User, request_id: int, reason: str) -> DsrRequest:
    r = await _load_open(session, request_id)
    if len((reason or "").strip()) < 3:
        raise KvkkError(422, "reason", "a refusal needs a written reason", "ret için gerekçe yazın")
    r.status, r.refusal_reason = "REFUSED", reason.strip()
    r.handled_by, r.handled_at = admin.id, utcnow()
    await session.flush()
    await audit.record(session, "kvkk.dsr_refuse", "dsr_request", r.id, after={"kind": r.kind}, reason=r.refusal_reason,
                       actor=admin)
    await _tell(session, r, refused=True)
    return r


async def complete(session: AsyncSession, admin: User, request_id: int, note: str | None) -> DsrRequest:
    r = await _load_open(session, request_id)
    now = utcnow()
    result: dict[str, Any] = {"note": (note or "").strip() or None}
    if r.kind == "erase":
        if r.user_id is None:
            raise KvkkError(409, "gone", "the account is gone already", "hesap zaten yok")
        if r.user_id == admin.id:
            raise KvkkError(
                409, "own_request", "another administrator completes your own erasure", "kendi silme talebinizi başka "
                "bir yönetici tamamlar"
            )
        subject = await session.get(User, r.user_id)
        if subject is None:
            raise KvkkError(409, "gone", "the account is gone already", "hesap zaten yok")
        if subject.role == "ADMIN" and subject.is_active:
            others = (
                await session.execute(
                    select(func.count()).where(User.role == "ADMIN", User.is_active.is_(True), User.id != subject.id)
                )
            ).scalar_one()
            if not others:
                raise KvkkError(409, "last_admin", "the last active administrator cannot be erased",
                                "son etkin yönetici silinemez")
        await _tell(session, r, refused=False)  # before the account loses its address
        result.update(await erase_user(session, admin, subject))
        r.subject_label = pseudonym(subject.id)
        r.user_id = None
    else:
        await _tell(session, r, refused=False)
    r.status, r.handled_by, r.handled_at, r.result = "DONE", admin.id, now, result
    await session.flush()
    await audit.record(session, f"kvkk.dsr_complete", "dsr_request", r.id,
                       after={"kind": r.kind, "counts": result.get("counts")}, actor=admin)
    return r


async def _tell(session: AsyncSession, r: DsrRequest, *, refused: bool) -> None:
    """The requester's in-app note (and e-mail through the outbox) of the decision."""
    from app.services.bookings_notify import _language

    if r.user_id is None:
        return
    user = await session.get(User, r.user_id)
    if user is None:
        return
    tr = (await _language(session, user)) == "tr"
    kind_tr = {"erase": "silme", "rectify": "düzeltme", "info": "bilgi"}.get(r.kind, r.kind)
    if refused:
        title = f"Kişisel veri ({kind_tr}) talebiniz reddedildi" if tr else f"Your data request ({r.kind}) was refused"
        body = r.refusal_reason or ""
    else:
        title = f"Kişisel veri ({kind_tr}) talebiniz tamamlandı" if tr else f"Your data request ({r.kind}) is done"
        body = "Hesabınız ve kişisel verileriniz silindi; denetim kayıtları anonim olarak saklanır." if (
            tr and r.kind == "erase"
        ) else ("Your account and personal data were erased; audit records are kept anonymised." if r.kind == "erase"
                else "")
    session.add(InAppNotification(user_id=user.id, kind="kvkk.request", title=title[:255], body=body,
                                  link="/profile/privacy", data={"request_id": r.id, "status": "REFUSED" if refused
                                                                 else "DONE"}))
    if user.email:
        from app.services import bookings_notify as mail

        await mail.notify(session, kind="kvkk_request", to_email=user.email, subject=title[:255], body=body,
                          user_id=user.id)
    await session.flush()


async def erase_user(session: AsyncSession, admin: User, subject: User) -> dict[str, Any]:
    """Erase / anonymise everything of ``subject`` (see the module docstring). Returns counts per table."""
    from app.services import bookings as bsvc
    from app.services import learning

    uid = subject.id
    label = pseudonym(uid)
    counts: dict[str, int] = {}
    today = await bsvc.today(session)
    now = utcnow()
    reason = "KVKK silme talebi / erasure request"
    # 1. future bookings and open requests are cancelled with a reason (the room is free again)
    future = list(
        (
            await session.execute(
                select(Booking).where(
                    Booking.user_id == uid, Booking.status.in_((BOOKED, PENDING)), Booking.date >= today
                )
            )
        ).scalars()
    )
    items = []
    for b in future:
        before = bsvc.snap(b)
        b.status, b.cancelled_at, b.cancelled_by, b.cancel_reason = CANCELLED, now, admin.id, reason
        b.held_until = None
        items.append((b.id, before, bsvc.snap(b)))
    if future:
        await session.execute(delete(BookingSlot).where(BookingSlot.booking_id.in_([b.id for b in future])))
        for req in (
            await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.requested_by == uid, ApprovalRequest.status == PENDING)
            )
        ).scalars():
            req.status, req.decided_at, req.decided_by, req.note = "WITHDRAWN", now, admin.id, reason
        await session.flush()
        await publish_event(session, "booking.cancel", "booking", future[0].id, items=items, actor=admin,
                            reason=reason, payload={"booking_ids": [b.id for b in future], "actor_id": admin.id})
    counts["bookings_cancelled"] = len(future)
    # 2. past bookings and series: no link to the person, no notes
    counts["bookings_anonymised"] = await _count_delete(
        session, update(Booking).where(Booking.user_id == uid).values(user_id=None, notes=None)
    )
    for col in ("created_by", "updated_by", "cancelled_by"):
        await session.execute(update(Booking).where(getattr(Booking, col) == uid).values({col: None}))
        await session.execute(update(BookingSeries).where(getattr(BookingSeries, col) == uid).values({col: None}))
    counts["series_anonymised"] = await _count_delete(
        session, update(BookingSeries).where(BookingSeries.user_id == uid).values(user_id=None, notes=None)
    )
    await session.execute(update(ApprovalRequest).where(ApprovalRequest.requested_by == uid).values(requested_by=None))
    # 3. notifications, delivery ledgers, channel links, identities, calendar links, tokens, personal settings
    for name, stmt in (
        ("inapp_notifications", delete(InAppNotification).where(InAppNotification.user_id == uid)),
        ("notification_deliveries", delete(NotificationDelivery).where(NotificationDelivery.user_id == uid)),
        (
            "notification_outbox",
            delete(NotificationOutbox).where(
                or_(NotificationOutbox.user_id == uid, NotificationOutbox.to_email == subject.email)
                if subject.email
                else NotificationOutbox.user_id == uid
            ),
        ),
        ("channel_deliveries", delete(ChannelDelivery).where(ChannelDelivery.user_id == uid)),
        ("user_channels", delete(UserChannel).where(UserChannel.user_id == uid)),
        ("channel_link_codes", delete(ChannelLinkCode).where(ChannelLinkCode.user_id == uid)),
        ("user_identities", delete(UserIdentity).where(UserIdentity.user_id == uid)),
        ("sso_invites", delete(SsoInvite).where(SsoInvite.user_id == uid)),
        ("sso_auth_states", delete(SsoAuthState).where(SsoAuthState.user_id == uid)),
        ("calendar_feed_tokens", delete(CalendarFeedToken).where(CalendarFeedToken.user_id == uid)),
        ("calendar_connections", delete(CalendarConnection).where(CalendarConnection.user_id == uid)),
        ("oauth_states", delete(OAuthState).where(OAuthState.user_id == uid)),
        ("password_reset_tokens", delete(PasswordResetToken).where(PasswordResetToken.user_id == uid)),
        ("multi_bookings", delete(MultiBooking).where(MultiBooking.user_id == uid)),
        ("settings", delete(Setting).where(Setting.key.like(f"user.{uid}.%"))),
        ("consents", delete(Consent).where(Consent.user_id == uid)),
        ("notice_acks", delete(NoticeAck).where(NoticeAck.user_id == uid)),
        ("approver_scopes", delete(ApproverScope).where(ApproverScope.user_id == uid)),
        ("user_constraints", delete(UserConstraint).where(UserConstraint.user_id == uid)),
        ("room_acl", delete(RoomAcl).where(RoomAcl.context_type == "user", RoomAcl.context_id == uid)),
    ):
        counts[name] = await _count_delete(session, stmt)
    await session.execute(update(Room).where(Room.owner_user_id == uid).values(owner_user_id=None))
    # 4. learned observations of the person (and of their instructor record), then the link
    ins = (await session.execute(select(Instructor).where(Instructor.user_id == uid))).scalars().first()
    if ins is not None:
        res = await learning.erase_person(session, admin, instructor_id=ins.id, reason=reason)
        counts["learning"] = int(sum((res.get("counts") or {}).values()))
        ins.user_id = None
    from app.models import LearnedObservation

    counts["learning_user"] = await _count_delete(
        session,
        delete(LearnedObservation).where(
            LearnedObservation.subject_type == "user", LearnedObservation.subject_key == str(uid)
        ),
    )
    await session.execute(
        update(LearnedObservation).where(LearnedObservation.actor_id == uid).values(actor_id=None)
    )
    # 5. audit rows: kept (legal retention) but pseudonymised, through the trigger's anonymise window
    await session.flush()
    window = AuditPurgeWindow(kind="anonymise", subject_actor_id=uid, created_at=now)
    session.add(window)
    await session.flush()
    counts["audit_pseudonymised"] = await _count_delete(
        session,
        update(AuditEvent)
        .where(AuditEvent.actor_id == uid)
        .values(actor_id=None, actor_label=label, ip_hash=None, request_id=None),
    )
    counts["audit_account_rows"] = await _count_delete(
        session,
        update(AuditEvent)
        .where(AuditEvent.entity_type == "user", AuditEvent.entity_id == str(uid))
        .values(before=None, after={"anonymised": True}, diff=None),
    )
    await session.delete(window)
    await session.flush()
    # 6. the account itself: no name, no address, cannot sign in
    subject.email = None
    subject.username = f"silinmis-{label.rsplit('#', 1)[-1]}"
    subject.full_name = subject.firstname = subject.lastname = subject.ext = None
    subject.password_hash = hash_password(secrets.token_urlsafe(32))
    subject.is_active = False
    subject.department_id = None
    subject.language = None
    subject.last_login_at = None
    subject.legacy_crbs_user_id = None
    revoke_tokens(subject)
    await session.flush()
    return {"counts": counts, "partial": True,
            "partial_reason": "denetim kayıtları anonim olarak saklanır (yasal saklama) / audit records kept anonymised"}
