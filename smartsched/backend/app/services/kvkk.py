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
  ``ai_personal``); a withdrawal takes effect at once (:func:`withdraw`): ``sms`` deletes the linked phone numbers,
  ``photo`` the stored profile photo, ``calendar_sync`` revokes the feed links and disconnects the push calendars,
  ``ai_personal`` keeps the person out of every later AI request (``app/ai/personal.py``).
* **Data-subject requests** (``dsr_requests``): ``export`` is self-service (a zip of JSON + CSV built at download
  time, never stored, for 7 days); ``erase``, ``rectify`` and ``info`` go to the administrators' queue with the
  30-day deadline (Art. 13). Completing an erasure cancels the person's future bookings with a reason, anonymises
  the past ones, disconnects their push calendars first (``calendar_connectors.disconnect``: the pushed events are
  removed and the grant revoked at the provider; a provider failure is listed in the result's ``failures``, TR/EN, and
  never blocks the erasure), deletes their notifications, delivery ledgers, channel links, SSO identities, calendar
  links and tokens, personal settings, consents and learned observations (``learning.erase_person``), pseudonymises
  their audit rows (actor ``Silinmiş kullanıcı #h``; the rows are kept: legal retention) and anonymises the account.
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
import re
import secrets
import shutil
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rls
from app.core.config import get_settings
from app.core.export_safety import safe_writer
from app.core.security import hash_password, revoke_tokens
from app.importers import normalize as tr_norm
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
    InAppNotification,
    Instructor,
    MultiBooking,
    NotificationDelivery,
    NotificationOutbox,
    OAuthState,
    PasswordResetToken,
    RoomAcl,
    Setting,
    User,
    UserConstraint,
)
from app.models.base import utcnow
from app.models.booking import BOOKED, CANCELLED, PENDING
from app.models.catalog import Room
from app.models.channels import ChannelDelivery, ChannelLinkCode, UserChannel
from app.models.kvkk import AuditPurgeWindow, Consent, DsrRequest, NoticeAck, PrivacyNotice, RetentionPolicy
from app.models.sso import SsoAuthState, SsoInvite, UserIdentity
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
    #: VO-03: speech to text through the admins' cloud speech provider; the audio is never stored
    "voice": ("Sesimin yazıya dökülmesi (sesli giriş)", "Transcribing my voice (voice input)"),
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
    # welcome guide per role (WG-03, app/services/welcome.py): show / hide the guide; no content, clicks or timings
    "welcome": {
        "tr": "Karşılama rehberi durumu: gösterildi mi, ertelendi mi, turun adımı, tamamlanan maddeler",
        "en": "Welcome guide state: whether the guide was shown, snoozed or finished, the tour step, items done",
        "tables": ["welcome_progress"],
        "legal_basis": "KVKK m.5/2(f) meşru menfaat (rehberi doğru kişiye bir kez göstermek)",
        "retention": None,
        "kept": "hesapla birlikte; silme talebinde silinir",
    },
    # AU-B two-step sign-in (app/services/mfa.py): secrets encrypted, codes and device tokens only as hashes
    "sign_in_security": {
        "tr": "Giriş güvenliği: doğrulama uygulaması (şifreli), kurtarma kodları (özet), geçiş anahtarları (açık "
        "anahtar), güvenilir cihazlar (özet), giriş adımları",
        "en": "Sign-in security: authenticator app (encrypted), recovery codes (hashed), passkeys (public keys), "
        "trusted devices (hashed), sign-in steps",
        "tables": ["user_mfa", "mfa_recovery_codes", "webauthn_credentials", "trusted_devices", "auth_challenges"],
        "legal_basis": "KVKK m.12 veri güvenliği tedbiri; m.5/2(c) sözleşmenin ifası (hesaba güvenli giriş)",
        "retention": None,
        "kept": "hesapla birlikte; silme talebinde silinir",
    },
    # RF-11 new-device sign-in mail (app/services/mail_senders.py): browser + system family and network, as an HMAC
    "known_devices": {
        "tr": "Bilinen giriş cihazları: tarayıcı ve sistem türü ile ağın (/24) özeti, ilk ve son görülme zamanı",
        "en": "Known sign-in devices: a hash of the browser and system family and the network (/24), first and last "
        "seen",
        "tables": ["settings (user.<id>.known_devices)"],
        "legal_basis": "KVKK m.12 veri güvenliği tedbiri (tanınmayan cihazdan girişi bildirmek)",
        "retention": None,
        "kept": "son 20 cihaz, hesapla birlikte; silme talebinde silinir",
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


#: the most a retention period may be (100 years): anything above is a typing mistake
MAX_RETAIN_DAYS = 36_500
_ACTION_WORDS = {
    "delete": "delete",
    "sil": "delete",
    "silme": "delete",
    "anonymise": "anonymise",
    "anonymize": "anonymise",
    "anonimleştir": "anonymise",
    "anonimlestir": "anonymise",
    "anonimleştirme": "anonymise",
}
_YES = {"true", "1", "evet", "e", "açık", "acik", "on", "yes"}
_NO = {"false", "0", "hayır", "hayir", "h", "kapalı", "kapali", "off", "no"}
_DAYS_RX = re.compile(r"^(\d{1,3}(?:[. ]\d{3})+|\d+)(?:\s*(?:gün|gun|days?))?$")


def _field_error(code: str, field: str, message: str, message_tr: str, **data: Any) -> dict[str, Any]:
    return {"code": code, "field": field, "message": message, "message_en": message, "message_tr": message_tr, **data}


def _days(value: Any) -> int | None:
    """``365``, ``"365"``, ``"1.095"`` (Turkish thousands dot), ``"365 gün"``, NBSP -> days; else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        m = _DAYS_RX.match(tr_norm.tr_casefold(tr_norm.clean_text(value) or ""))
        if m:
            return int(re.sub(r"[. ]", "", m.group(1)))
    return None


def _switch(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        word = tr_norm.tr_casefold(tr_norm.clean_text(value) or "")
        if word in _YES:
            return True
        if word in _NO:
            return False
    return None


def _check_policy_input(data_class: str, data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read ``PUT /admin/retention/{data_class}`` (Turkish forms too) -> (clean values, field errors in field order).
    Every error has a stable ``code`` and the input ``field`` (backend asks batch 3 item 3)."""
    errors: list[dict[str, Any]] = []
    clean: dict[str, Any] = {}
    if data.get("retain_days") is not None:
        days = _days(data["retain_days"])
        floor = FLOORS[data_class]
        if days is None or days > MAX_RETAIN_DAYS:
            errors.append(
                _field_error(
                    "retain_days",
                    "retain_days",
                    f"retain_days: a whole number of days between {floor} and {MAX_RETAIN_DAYS}",
                    f"saklama süresi: {floor} ile {MAX_RETAIN_DAYS} arasında tam gün sayısı",
                    floor_days=floor,
                    max_days=MAX_RETAIN_DAYS,
                )
            )
        elif days < floor:
            errors.append(
                _field_error(
                    "below_floor",
                    "retain_days",
                    f"{data_class} must be kept at least {floor} days",
                    f"{data_class} verisi en az {floor} gün saklanmalı",
                    floor_days=floor,
                )
            )
        else:
            clean["retain_days"] = days
    if data.get("action") is not None:
        raw = data["action"]
        action = _ACTION_WORDS.get(tr_norm.tr_casefold(tr_norm.clean_text(raw) or "")) if isinstance(raw, str) else None
        allowed = ["anonymise"] if data_class == "booking" else list(ACTIONS)
        if action is None:
            errors.append(
                _field_error(
                    "action",
                    "action",
                    "action: delete or anonymise",
                    "işlem: delete (sil) ya da anonymise (anonimleştir)",
                    allowed=allowed,
                )
            )
        elif action not in allowed:
            errors.append(
                _field_error(
                    "action",
                    "action",
                    "bookings are anonymised, not deleted (room usage statistics stay)",
                    "rezervasyonlar silinmez, anonimleştirilir (kullanım istatistikleri korunur)",
                    allowed=allowed,
                )
            )
        else:
            clean["action"] = action
    labels = {"enabled": ("enabled", "açık / kapalı"), "legal_hold": ("legal_hold", "yasal saklama")}
    for key, (en, tr) in labels.items():
        if data.get(key) is not None:
            on = _switch(data[key])
            if on is None:
                errors.append(_field_error(key, key, f"{en}: true or false", f"{tr}: evet ya da hayır"))
            else:
                clean[key] = on
    if "legal_hold_reason" in data:
        reason = data.get("legal_hold_reason")
        if reason is not None and not isinstance(reason, str):
            errors.append(
                _field_error(
                    "legal_hold_reason",
                    "legal_hold_reason",
                    "legal_hold_reason: the reason as text",
                    "yasal saklama gerekçesi metin olmalı",
                )
            )
        else:
            clean["legal_hold_reason"] = tr_norm.clean_text(reason) if reason else None
    return clean, errors


def _raise_field_errors(errors: list[dict[str, Any]]) -> None:
    if errors:
        first = errors[0]
        raise KvkkError(
            422,
            first["code"],
            first["message"],
            first["message_tr"],
            **{k: v for k, v in first.items() if k not in ("code", "message", "message_en", "message_tr")},
            errors=errors,
        )


async def update_policy(session: AsyncSession, actor: User, data_class: str, data: dict[str, Any]) -> RetentionPolicy:
    rows = {p.data_class: p for p in await ensure_policies(session)}
    p = rows.get(data_class)
    if p is None:
        allowed = [c for c in DATA_CLASSES if c in FLOORS]
        _raise_field_errors(
            [
                _field_error(
                    "unknown_class",
                    "data_class",
                    f"{data_class!r} has no retention policy; one of {', '.join(allowed)}",
                    f"{data_class!r} için saklama kuralı yok; şunlardan biri: {', '.join(allowed)}",
                    allowed=allowed,
                )
            ]
        )
    assert p is not None
    clean, errors = _check_policy_input(data_class, data)
    hold = clean.get("legal_hold", p.legal_hold)
    reason = clean["legal_hold_reason"] if "legal_hold_reason" in clean else p.legal_hold_reason
    if hold and not reason and not any(e["field"] in ("legal_hold", "legal_hold_reason") for e in errors):
        errors.append(
            _field_error(
                "legal_hold_reason",
                "legal_hold_reason",
                "a legal hold needs a reason",
                "yasal saklama için gerekçe yazın",
            )
        )
    _raise_field_errors(errors)
    before = policy_out(p)
    for key, value in clean.items():
        setattr(p, key, value)
    p.updated_by, p.updated_at = actor.id, utcnow()
    await session.flush()
    await audit.record(
        session,
        "kvkk.retention_policy",
        "retention_policy",
        data_class,
        before=before,
        after=policy_out(p),
        actor=actor,
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
    # AS-05: the aggregate find-room / booking demand ledger keeps demand.retention_days (default 400)
    from app.services import demand

    out["demand"] = await demand.purge(session, now)
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
        # an org-wide count: on PostgreSQL the owner-only tables (welcome_progress, MFA, helper) would show the admin
        # only their own rows, so the counts run as system (the route checks setup.settings)
        async with rls.system_scope(session):
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
    """The latest published notice in the reader's ``language``; only when that language has no published notice at
    all, the latest Turkish one, else the latest in any language. A newer version written in another language
    never replaces the reader's own (round-1 R1-A-26: a Turkish reader was shown an English-only v2)."""
    q = (
        select(PrivacyNotice)
        .where(PrivacyNotice.published_at.is_not(None))
        .order_by(PrivacyNotice.version.desc(), PrivacyNotice.published_at.desc(), PrivacyNotice.id.desc())
    )
    rows = list((await session.execute(q)).scalars())
    if not rows:
        return None
    for lang in (language, "tr"):
        hit = next((r for r in rows if lang and r.language == lang), None)
        if hit is not None:
            return hit
    return rows[0]


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
        (await session.execute(select(Consent).where(Consent.user_id == user_id).order_by(Consent.id))).scalars()
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
            select(Consent).where(
                Consent.user_id == user.id, Consent.purpose == purpose, Consent.withdrawn_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        return
    n = await current_notice(session, user.language)
    row = Consent(user_id=user.id, purpose=purpose, granted_at=utcnow(), notice_id=n.id if n else None)
    session.add(row)
    await session.flush()
    await audit.record(session, "kvkk.consent_grant", "consent", purpose, after={"user_id": user.id}, actor=user)
    if purpose == "calendar_sync":  # RF-11: the person's own record of the consent (e-mail + bell, preferences apply)
        from app.services import mail_senders

        await mail_senders.calendar_consent(session, user, granted=True, consent_id=row.id)


#: what a never-given ``ai_personal`` consent means (ROADMAP batch 3; owner decision 2026-10-17, R1-M-07 / R1-A-24):
#: ``excluded`` (default: silence is not consent for a cross-border transfer, not granted = excluded) or ``included``
#: (an admin's explicit choice in Admin > KVKK: the institution's AI sign-off is the basis until the person withdraws)
AI_PERSONAL_DEFAULT_KEY = "kvkk.ai_personal_default"
AI_PERSONAL_DEFAULTS = ("included", "excluded")
_AI_PERSONAL_WORDS = {
    "included": "included",
    "include": "included",
    "dahil": "included",  # "dahil", "DÂHİL", "Dâhil"
    "excluded": "excluded",
    "exclude": "excluded",
    "haric": "excluded",  # "hariç", "HARİÇ", "HARIC"
}


def parse_ai_personal_default(value: Any) -> str | None:
    """``included`` / ``excluded`` from an admin's input (English or Turkish, any case, dotted / dotless i,
    circumflex, NBSP); ``None`` if neither."""
    if not isinstance(value, str):
        return None
    return _AI_PERSONAL_WORDS.get(tr_norm.fold(value))


async def ai_personal_default(session: AsyncSession) -> str:
    """The stored ``kvkk.ai_personal_default`` (``excluded`` when unset or unreadable: owner decision 2026-10-17)."""
    from app.services import settings_service

    return parse_ai_personal_default(await settings_service.get_value(session, AI_PERSONAL_DEFAULT_KEY)) or "excluded"


#: where a person grants a consent: Profil › Gizlilik (the ``#privacy`` section of the profile page)
GRANT_PATH = "/profile#privacy"


async def has_consent(session: AsyncSession, user_id: int, purpose: str) -> bool:
    """``user_id`` holds an active (granted, not withdrawn) consent for ``purpose``."""
    q = select(Consent.id).where(Consent.user_id == user_id, Consent.purpose == purpose, Consent.withdrawn_at.is_(None))
    return (await session.execute(q.limit(1))).first() is not None


def consent_required_error(purpose: str) -> KvkkError:
    tr, en = PURPOSES[purpose]
    return KvkkError(
        409,
        "consent_required",
        f'This needs your consent "{en}". You can give it under Profile › Privacy.',
        f'Bunun için "{tr}" rızanız gerekir. Rızanızı Profil › Gizlilik bölümünden verebilirsiniz.',
        purpose=purpose,
        label_tr=tr,
        label_en=en,
        grant_path=GRANT_PATH,
        grant_api=f"POST /api/v1/me/consents/{purpose}",
    )


async def require_consent(session: AsyncSession, user: User, purpose: str) -> None:
    """The consent gate (consent gates 2026-10-16): raise a 409 ``consent_required`` :class:`KvkkError` (TR/EN text
    naming the consent and Profil › Gizlilik, ``purpose``, ``label_tr`` / ``label_en``, ``grant_path``, ``grant_api``)
    unless ``user`` holds an active consent for ``purpose``. Called before anything that relies on explicit consent
    as its legal basis is created: a calendar feed link or push connection (``calendar_sync``, while the institution's
    calendar-sync sign-off is on) and any upload path that stores a person's photo (``photo``; route dependency
    :func:`app.api.deps.consent_gate`). ``ValueError`` for an unknown purpose (a programming error, not a 4xx)."""
    if purpose not in PURPOSES:
        raise ValueError(f"unknown consent purpose {purpose!r}")
    if not await has_consent(session, user.id, purpose):
        raise consent_required_error(purpose)


def profile_photo_dir() -> Path:
    """Where a person's profile photo lives (``<upload_dir>/users/<user_id>.<ext>`` or ``<user_id>/``). SmartSched has
    no profile-photo upload yet; anything that adds one stores the file here, gated by the ``photo`` consent, and
    serves it only through an authenticated route (the public ``/uploads`` mount serves room photos only)."""
    return Path(get_settings().upload_dir) / "users"


def delete_profile_photo(user_id: int) -> int:
    """Delete every stored profile-photo file of ``user_id``; the number of files removed."""
    base = profile_photo_dir()
    if not base.is_dir():
        return 0
    removed = 0
    for path in [*base.glob(f"{int(user_id)}.*"), base / str(int(user_id))]:
        if path.is_file():
            path.unlink(missing_ok=True)
            removed += 1
        elif path.is_dir():
            files = [f for f in path.rglob("*") if f.is_file()]
            removed += len(files)
            shutil.rmtree(path, ignore_errors=True)
    return removed


def _effect(code: str, count: int | None, en: str, tr: str) -> dict[str, Any]:
    return {"code": code, "count": count, "message_en": en, "message_tr": tr}


async def _withdraw_calendar_sync(session: AsyncSession, user: User) -> tuple[int, int]:
    """Revoke every calendar feed link of ``user`` and disconnect every Google / Microsoft push connection (the
    events SmartSched put into that calendar are removed and the grant is revoked at the provider, in the
    background; ``calendar_connectors.disconnect``). Pending OAuth starts are dropped too."""
    from app.services import calendar_connectors as conn_svc

    feeds = await _count_delete(session, delete(CalendarFeedToken).where(CalendarFeedToken.user_id == user.id))
    conns = list(
        (
            await session.execute(
                select(CalendarConnection).where(CalendarConnection.user_id == user.id).order_by(CalendarConnection.id)
            )
        ).scalars()
    )
    for conn in conns:
        await conn_svc.disconnect(session, conn)
    await _count_delete(session, delete(OAuthState).where(OAuthState.user_id == user.id))
    return feeds, len(conns)


async def withdraw(session: AsyncSession, user: User, purpose: str) -> dict[str, Any]:
    """Withdraw a consent and apply what it means at once (backend asks batch 3 item 5):

    * ``sms`` -- the linked phone numbers (SMS / WhatsApp) and pending link codes are deleted;
    * ``photo`` -- the stored profile photo files are deleted (:func:`delete_profile_photo`);
    * ``calendar_sync`` -- every calendar feed link is revoked and every push connection disconnected;
    * ``ai_personal`` -- the person is kept out of every later AI request (``app/ai/personal.py``).

    Answers the counts (``removed_channels``, ``removed_photo``, ``revoked_feeds``, ``disconnected_calendars``, all
    present, 0 when not concerned), ``ai_excluded`` and ``effects`` (one TR/EN sentence per consequence); one
    ``kvkk.consent_withdraw`` audit event carries the same counts. Withdrawing twice is harmless."""
    if purpose not in PURPOSES:
        raise KvkkError(404, "purpose", "unknown consent purpose", "bilinmeyen rıza amacı")
    now = utcnow()
    rows = (
        await session.execute(
            select(Consent).where(
                Consent.user_id == user.id, Consent.purpose == purpose, Consent.withdrawn_at.is_(None)
            )
        )
    ).scalars()
    was_granted = False
    withdrawn_ids: list[int] = []
    for r in rows:
        r.withdrawn_at, was_granted = now, True
        withdrawn_ids.append(r.id)
    if not was_granted and purpose == "ai_personal":
        # the per-person switch is the latest consent row: record the withdrawal even without an earlier grant
        session.add(Consent(user_id=user.id, purpose=purpose, granted_at=now, withdrawn_at=now))
    counts = {"removed_channels": 0, "removed_photo": 0, "revoked_feeds": 0, "disconnected_calendars": 0}
    effects: list[dict[str, Any]] = []
    if purpose == "sms":  # the phone number goes at once (spec §4.7 edge case)
        counts["removed_channels"] = await _count_delete(
            session, delete(UserChannel).where(UserChannel.user_id == user.id, UserChannel.kind.in_(PHONE_CHANNELS))
        )
        await _count_delete(
            session,
            delete(ChannelLinkCode).where(ChannelLinkCode.user_id == user.id, ChannelLinkCode.kind.in_(PHONE_CHANNELS)),
        )
        k = counts["removed_channels"]
        effects.append(
            _effect("phones_deleted", k, f"{k} linked phone number(s) deleted", f"bağlı {k} telefon numarası silindi")
            if k
            else _effect("phones_none", 0, "no phone number was linked", "bağlı telefon numarası yoktu")
        )
    elif purpose == "photo":
        k = counts["removed_photo"] = delete_profile_photo(user.id)
        effects.append(
            _effect("photo_deleted", k, "your profile photo was deleted", "profil fotoğrafınız silindi")
            if k
            else _effect("photo_none", 0, "no profile photo was stored", "kayıtlı profil fotoğrafı yoktu")
        )
    elif purpose == "calendar_sync":
        feeds, conns = await _withdraw_calendar_sync(session, user)
        if withdrawn_ids:  # RF-11: only a consent that was in force is announced (withdrawing twice sends nothing)
            from app.services import mail_senders

            await mail_senders.calendar_consent(session, user, granted=False, consent_id=max(withdrawn_ids))
        counts["revoked_feeds"], counts["disconnected_calendars"] = feeds, conns
        if feeds:
            effects.append(
                _effect(
                    "feeds_revoked",
                    feeds,
                    f"{feeds} calendar subscription link(s) revoked; calendars using them stop updating",
                    f"{feeds} takvim abonelik bağlantısı iptal edildi; bunları kullanan takvimler artık güncellenmez",
                )
            )
        if conns:
            effects.append(
                _effect(
                    "calendars_disconnected",
                    conns,
                    f"{conns} Google / Microsoft calendar connection(s) removed; the bookings SmartSched added there "
                    "are being deleted",
                    f"{conns} Google / Microsoft takvim bağlantısı kaldırıldı; SmartSched'in oraya eklediği "
                    "rezervasyonlar siliniyor",
                )
            )
        if not effects:
            effects.append(
                _effect("calendar_none", 0, "no calendar link or connection existed", "takvim bağlantısı yoktu")
            )
    elif purpose == "ai_personal":
        effects.append(
            _effect(
                "ai_excluded",
                None,
                "from now on your name and e-mail are replaced by a placeholder before anything is sent to the AI "
                "assistant",
                "bundan sonra yapay zekâ asistanına gönderilen her şeyde adınız ve e-postanız yer tutucuyla "
                "değiştirilir",
            )
        )
    ai_excluded = purpose == "ai_personal"
    await session.flush()
    await audit.record(
        session,
        "kvkk.consent_withdraw",
        "consent",
        purpose,
        after={"user_id": user.id, "removed": counts["removed_channels"], **counts, "ai_excluded": ai_excluded},
        actor=user,
    )
    return {**counts, "ai_excluded": ai_excluded, "effects": effects}


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
    await audit.record(
        session, f"kvkk.dsr_{kind}", "dsr_request", r.id, after={"kind": kind, "status": r.status}, actor=user
    )
    return r


async def mine(session: AsyncSession, user: User) -> list[DsrRequest]:
    q = select(DsrRequest).where(DsrRequest.user_id == user.id).order_by(DsrRequest.id.desc())
    return list((await session.execute(q)).scalars())


def _csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    if not rows:
        return ""
    keys = list(dict.fromkeys(k for r in rows for k in r))
    w = safe_writer(csv.DictWriter(buf, fieldnames=keys))  # formula injection (W3-SEC)
    w.writeheader()
    for r in rows:
        w.writerow(
            {k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else _iso(v) for k, v in r.items()}
        )
    return buf.getvalue()


async def export_data(session: AsyncSession, user: User) -> dict[str, Any]:
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
    bookings = list(
        (await session.execute(select(Booking).where(Booking.user_id == uid).order_by(Booking.date))).scalars()
    )
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
            "decided_by": (
                "Onaycı / approver" if r.decided_by not in (None, uid) else ("kendim" if r.decided_by else None)
            ),
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
        {
            "provider": i.provider,
            "email_at_login": i.email_at_login,
            "display_name": i.display_name,
            "origin": i.origin,
            "created_at": i.created_at,
            "last_login_at": i.last_login_at,
        }
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
                or_(
                    *(
                        (LearnedObservation.subject_type == st) & (LearnedObservation.subject_key == sk)
                        for st, sk in keys
                    )
                )
            )
        )
    ).scalars()
    data["learning_observations"] = [
        {"kind": o.kind, "attribute": o.attribute, "value": o.value, "weight": o.weight, "ts": o.ts} for o in obs
    ]
    data["data_requests"] = [dsr_out(r) for r in await mine(session, user)]
    from app.services import welcome as welcome_svc  # WG-03: the welcome guide's per-person state

    data["welcome_guide"] = await welcome_svc.dsr_rows(session, uid)
    from app.services import mfa as mfa_svc  # AU-B: what is on and when; never a secret, a code or a key

    data["sign_in_security"] = await mfa_svc.dsr_rows(session, uid)
    from app.services import mail_senders  # RF-11: the new-device check's hashed devices

    data["known_devices"] = await mail_senders.dsr_rows(session, uid)
    data.update(await _person_records(session, user, rooms))
    return await _scrub_others(session, user, data)


ROLE_EN = {"ADMIN": "administrator", "PLANNER": "planner", "TEACHER": "instructor", "VIEWER": "viewer"}
#: audit ``before`` / ``after`` keys that never leave the server, not even to their own person
_SECRET_KEY = re.compile(r"password|token|secret|_enc$|_hash$|^hash$|totp|otp_", re.IGNORECASE)


def _no_secrets(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _no_secrets(x) for k, x in v.items() if not _SECRET_KEY.search(str(k))}
    if isinstance(v, list):
        return [_no_secrets(x) for x in v]
    return v


def _tr_text(v: Any) -> Any:
    """``{tr, en}`` texts of the read models as one "tr / en" string (the CSV stays one column)."""
    if isinstance(v, dict) and set(v) == {"tr", "en"}:
        return v["tr"] if v["tr"] == v["en"] else f"{v['tr']} / {v['en']}"
    return v


async def _person_records(session: AsyncSession, user: User, rooms: dict[int, str]) -> dict[str, list[dict[str, Any]]]:
    """KVKK m.11 beyond the account (round-1 T-R1-27, R1-A-25): the linked instructor record(s) and what the
    planning side keeps about that person: the sections they teach, the planning requests as Taleplerim shows them
    (``moderation.history``: the same rows, verdicts and accessibility rule), the exam requests of their sections,
    their wishes with the coordinator's decision, the coordinators' priority notes about them, approval decisions
    received and made, approver scopes, learned priors and dismissals, invigilation, calendar links, booking limits
    and the audit rows whose subject they are. Other people appear by their role (:func:`_who`); names left in free
    text are replaced by :func:`_scrub_others`."""
    from sqlalchemy.orm import selectinload

    from app.models import (
        ApprovalDecision,
        ConstraintRow,
        ExamRequest,
        InvigilationDuty,
        InvigilatorPoolMember,
        LearnedPrior,
        PriorityOverride,
        Section,
        SectionInstructor,
        SuggestionFeedback,
        Term,
    )
    from app.services import moderation as mod
    from app.services import teacher_preferences as tp

    uid = user.id
    roles = {int(i): r for i, r in (await session.execute(select(User.id, User.role))).all()}

    def who(other: int | None, *, system: bool = False) -> str | None:
        if other is None:
            return "sistem / system" if system else None
        if other == uid:
            return "kendim / myself"
        role = roles.get(other)
        if role is None:
            return "silinmiş kullanıcı / deleted user"
        return f"{ROLE_TR.get(role, 'Kullanıcı')} / {ROLE_EN.get(role, 'user')}"

    terms = {t.id: t.code for t in (await session.execute(select(Term))).scalars()}
    linked = list(
        (await session.execute(select(Instructor).where(Instructor.user_id == uid).order_by(Instructor.id))).scalars()
    )
    iids = [i.id for i in linked]
    out: dict[str, list[dict[str, Any]]] = {}
    out["instructor"] = [
        {
            "id": i.id,
            "full_name": i.full_name,
            "title": i.title,
            "email": i.email,
            "canonical_name": i.canonical_name,
            "archived": i.archived,
            "source": i.source_key,
        }
        for i in linked
    ]

    # the sections they teach (co-instructors by their role only)
    links = (
        list(
            (
                await session.execute(
                    select(SectionInstructor)
                    .where(SectionInstructor.instructor_id.in_(iids))
                    .options(
                        selectinload(SectionInstructor.section).selectinload(Section.course),
                        selectinload(SectionInstructor.section).selectinload(Section.program),
                        selectinload(SectionInstructor.section).selectinload(Section.instructors),
                    )
                )
            ).scalars()
        )
        if iids
        else []
    )
    section_ids = sorted({si.section_id for si in links})
    out["instructor_sections"] = [
        {
            "section_id": si.section_id,
            "term_code": terms.get(si.section.term_id),
            "course_code": si.section.course.display_code if si.section.course else None,
            "course_name": si.section.course.name if si.section.course else None,
            "section": si.section.label,
            "program": si.section.program.name if si.section.program else None,
            "class_year": si.section.class_year,
            "enrolment": si.section.enrolment,
            "mode": si.section.mode,
            "role": si.role,
            "priority": si.section.priority,
            "notes": None if mod.mentions_accessibility(si.section.notes) else si.section.notes,
            "other_instructors": [
                f"[{ROLE_TR['TEACHER']}] ({o.role})" for o in si.section.instructors if o.instructor_id not in iids
            ],
            "archived": si.section.archived,
        }
        for si in sorted(links, key=lambda x: (terms.get(x.section.term_id) or "", x.section_id))
    ]

    # the planning requests: Taleplerim's rows (every term), each with what was asked, what was given and why
    planning: list[dict[str, Any]] = []
    scope = mod.Scope(False, frozenset(iids), "own")
    for ins in linked:
        try:
            hist = await mod.history(session, ins.id, scope)
        except mod.ModerationError:
            continue
        for g in hist["terms"]:
            for it in g["items"]:
                reason = it.get("reason") or None
                planning.append(
                    {
                        "term_code": g["term_code"],
                        "term_name": g["term_name"],
                        "request_id": it["request_id"],
                        "section_id": it["section_id"],
                        "course_code": it["course_code"],
                        "course_name": it["course_name"],
                        "section": it["section"],
                        "label": it["label"],
                        "program": it["program"],
                        "role": it.get("role"),
                        "instructors": [
                            {"role": i["role"], "self": i["id"] in iids, "name": None} for i in it["instructors"]
                        ],
                        "request_text": it["raw"]["room_text"],
                        "notes": it["raw"]["notes"],
                        "requested": it["requested"],
                        "definitive": it["definitive"],
                        "assigned": it["assigned"],
                        "verdict": it["verdict"],
                        "verdict_text": _tr_text(it["verdict_text"]),
                        "reason": (
                            {
                                "code": reason.get("code"),
                                "text": _tr_text(reason.get("text")),
                                "policy_step": reason.get("policy_step"),
                            }
                            if reason
                            else None
                        ),
                        "priority": it.get("priority"),
                        "source": it.get("source"),
                        "run": g["run"]["label"] if g.get("run") else None,
                        "source_row": it["raw"]["row"],
                        "planning_list_cells": it["raw"]["source_row"],
                        "planner_edits": [
                            {k: v for k, v in e.items() if k not in ("id", "actor")} for e in it["planner_edits"]
                        ],
                    }
                )
    out["planning_requests"] = planning

    exams = (
        list(
            (
                await session.execute(
                    select(ExamRequest).where(ExamRequest.section_id.in_(section_ids)).order_by(ExamRequest.id)
                )
            ).scalars()
        )
        if section_ids
        else []
    )
    out["exam_requests"] = [
        {
            "id": e.id,
            "term_code": terms.get(e.term_id),
            "course_code": e.course_code,
            "course_name": e.course_name,
            "date": e.date,
            "date_end": e.date_end,
            "start_time": e.start_time.isoformat() if e.start_time else None,
            "end_time": e.end_time.isoformat() if e.end_time else None,
            "start_period": e.start_period,
            "end_period": e.end_period,
            "requested_venue_text": e.requested_venue_text,
            "definitive_room_text": e.definitive_room_text,
            "invigilators_requested": e.invigilators_requested,
            "no_exam": e.no_exam,
            "instructor_text": e.instructor_text,
            "notes": None if mod.mentions_accessibility(e.notes) else e.notes,
            "status": e.status,
        }
        for e in exams
    ]

    # the wishes ("Tercih ekle") with the coordinator's decision and reason; the coordinator by role
    wish_rows = [
        r
        for r in (
            await session.execute(
                select(ConstraintRow).where(ConstraintRow.source == tp.SOURCE).order_by(ConstraintRow.id)
            )
        ).scalars()
        if r.created_by == uid
        or (isinstance(r.source_ref, dict) and int(r.source_ref.get("instructor_id") or 0) in iids)
    ]
    out["teacher_preferences"] = [
        {
            "id": w["id"],
            "term_code": terms.get(w["term_id"] or 0),
            "kind": w["kind"],
            "kind_label": _tr_text(w["kind_label"]),
            "classes": w["labels"],
            "text": _tr_text(w["text"]),
            "wish": w["wish"],
            "department_asked": w["department"],
            "note": w["note"],
            "status": w["status"],
            "in_effect": w["enabled"],
            "submitted_at": w["submitted_at"],
            "decided_at": w["decided_at"],
            "decided_by": who(w["decided_by"]),
            "reason": w["reason"],
            "reason_code": w["reason_code"],
        }
        for w in await tp.items_out(session, wish_rows)
    ]

    pos = (
        list(
            (
                await session.execute(
                    select(PriorityOverride).where(
                        PriorityOverride.subject_type == "person", PriorityOverride.subject_id.in_(iids)
                    )
                )
            ).scalars()
        )
        if iids
        else []
    )
    out["priority_notes"] = [
        {
            "term_code": terms.get(p.term_id),
            "priority": p.priority,
            "note": p.note,
            "updated_by": who(p.updated_by),
            "updated_at": p.updated_at,
        }
        for p in pos
    ]

    # approval decisions on the person's requests (received) and the ones they made as an approver
    received = (
        await session.execute(
            select(ApprovalDecision, ApprovalRequest)
            .join(ApprovalRequest, ApprovalRequest.id == ApprovalDecision.request_id)
            .where(or_(ApprovalRequest.requested_by == uid, ApprovalDecision.approver_user_id == uid))
            .order_by(ApprovalDecision.id)
        )
    ).all()
    out["approval_decisions"] = [
        {
            "direction": "received / alınan" if req.requested_by == uid else "made / verilen",
            "request_id": req.id,
            "room": rooms.get(req.room_id),
            "step": d.step,
            "decision": d.decision,
            "approver": who(d.approver_user_id),
            "requester": who(req.requested_by),
            "note": d.note,
            "reason_code": d.reason_code,
            "alternative": d.alternative,
            "decided_at": d.decided_at,
        }
        for d, req in received
    ]
    scopes = (await session.execute(select(ApproverScope).where(ApproverScope.user_id == uid))).scalars()
    out["approver_scopes"] = [
        {
            "scope_type": a.scope_type,
            "scope_id": a.scope_id,
            "room": rooms.get(a.scope_id or 0) if a.scope_type == "room" else None,
            "tag": a.tag,
            "created_at": a.created_at,
            "created_by": who(a.created_by),
        }
        for a in scopes
    ]

    keys = [("user", str(uid))] + [("instructor", str(i)) for i in iids]

    def subject(model: Any) -> Any:
        return or_(*((model.subject_type == st) & (model.subject_key == sk) for st, sk in keys))

    out["learned_priors"] = [
        {
            "term_code": terms.get(p.term_id),
            "attribute": p.attribute,
            "value": p.value,
            "score": p.score,
            "support": p.support,
            "total": p.total,
            "terms_count": p.terms_count,
            "confidence": p.confidence,
            "suggestible": p.suggestible,
            "active": p.active,
            "explanation": _tr_text({k: v for k, v in (p.explanation or {}).items() if k in ("tr", "en")} or None),
            "computed_at": p.computed_at,
        }
        for p in (await session.execute(select(LearnedPrior).where(subject(LearnedPrior)))).scalars()
    ]
    out["suggestion_feedback"] = [
        {
            "term_code": terms.get(f.term_id),
            "attribute": f.attribute,
            "value": f.value,
            "action": f.action,
            "scope": f.scope,
            "reason": f.reason,
            "snoozed_until": f.snoozed_until,
            "by": who(f.actor_id),
            "created_at": f.created_at,
        }
        for f in (await session.execute(select(SuggestionFeedback).where(subject(SuggestionFeedback)))).scalars()
    ]

    invig: list[dict[str, Any]] = []
    if iids:
        for m in (
            await session.execute(select(InvigilatorPoolMember).where(InvigilatorPoolMember.instructor_id.in_(iids)))
        ).scalars():
            invig.append(
                {
                    "record": "pool / gözetmen havuzu",
                    "term_code": terms.get(m.term_id or 0),
                    "pool_kind": m.kind,
                    "max_duties": m.max_duties,
                    "max_per_day": m.max_per_day,
                    "load_factor": m.load_factor,
                    "unavailable": m.unavailable,
                    "active": m.active,
                    "notes": m.notes,
                }
            )
        for d in (
            await session.execute(
                select(InvigilationDuty)
                .where(InvigilationDuty.instructor_id.in_(iids))
                .order_by(InvigilationDuty.date, InvigilationDuty.start_period)
            )
        ).scalars():
            invig.append(
                {
                    "record": "duty / gözetmenlik",
                    "plan_id": d.plan_id,
                    "date": d.date,
                    "start_period": d.start_period,
                    "end_period": d.end_period,
                    "room": rooms.get(d.room_id or 0),
                    "origin": d.origin,
                    "locked": d.is_locked,
                }
            )
    out["invigilation"] = invig

    cal: list[dict[str, Any]] = [
        {
            "record": "push calendar / takvim bağlantısı",
            "provider": c.provider,
            "account_email": c.account_email,
            "calendar_name": c.calendar_name,
            "scopes": c.scopes,
            # CAL-06: what SmartSched pushes into that calendar (my_classes, department_classes:<id>, my_bookings)
            "export_scopes": c.export_scopes or ["my_bookings"],
            "account_verified": c.account_verified,
            "status": c.status,
            "last_synced_at": c.last_synced_at,
            "created_at": c.created_at,
        }
        for c in (await session.execute(select(CalendarConnection).where(CalendarConnection.user_id == uid))).scalars()
    ]
    cal += [
        {
            "record": "feed link / takvim bağlantı adresi",
            "hint": f"…{t.hint}" if t.hint else None,
            "label": t.label,
            # CAL-03: the one scope a link serves (none = a legacy link for every feed) and the consent it rests on
            "scope_kind": t.scope_kind,
            "scope_id": t.scope_id,
            "consent_id": t.consent_id,
            "created_at": t.created_at,
            "last_used_at": t.last_used_at,
        }
        for t in (await session.execute(select(CalendarFeedToken).where(CalendarFeedToken.user_id == uid))).scalars()
    ]
    out["calendar_links"] = cal
    lim = await session.get(UserConstraint, uid)
    out["booking_limits"] = (
        [
            {
                "max_active_bookings": f"{lim.max_active_bookings_type}:{lim.max_active_bookings_value}",
                "range_min": f"{lim.range_min_type}:{lim.range_min_value}",
                "range_max": f"{lim.range_max_type}:{lim.range_max_value}",
                "recur_max_instances": f"{lim.recur_max_instances_type}:{lim.recur_max_instances_value}",
            }
        ]
        if lim is not None
        else []
    )

    # the audit rows about the person (their account, their instructor record, their wishes, their requests)
    ents = [
        ("user", [str(uid)]),
        ("instructor", [str(i) for i in iids]),
        ("constraint", [str(r.id) for r in wish_rows]),
    ]
    ents.append(("dsr_request", [str(r.id) for r in await mine(session, user)]))
    conds = [(AuditEvent.entity_type == et) & AuditEvent.entity_id.in_(ids) for et, ids in ents if ids]
    evs = (await session.execute(select(AuditEvent).where(or_(*conds)).order_by(AuditEvent.id))).scalars()
    out["audit_as_subject"] = [
        {
            "ts": e.ts,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "actor": who(e.actor_id, system=e.actor_type != "user"),
            "reason": e.reason,
            "before": _no_secrets(e.before),
            "after": _no_secrets(e.after),
        }
        for e in evs
    ]
    return out


ROLE_TR = {"ADMIN": "Yönetici", "PLANNER": "Planlamacı", "TEACHER": "Öğretim elemanı", "VIEWER": "Görüntüleyici"}


_I_VARIANTS = "iIİı"


def _fold_key(v: str) -> str:
    """Turkish-tolerant match key: dotted / dotless i alike, any case, runs of spaces as one."""
    for ch in _I_VARIANTS:
        v = v.replace(ch, "i")
    return re.sub(r"\s+", " ", v.lower()).strip()


def _needle_rx(v: str) -> str:
    parts: list[str] = []
    for ch in re.sub(r"\s+", " ", v.strip()):
        parts.append(f"[{_I_VARIANTS}]" if ch in _I_VARIANTS else r"\s+" if ch == " " else re.escape(ch))
    return "".join(parts)


_WORD = re.compile(r"\w+")
#: a first name with a Turkish form of address ("Ahmet Bey", "Elif Hanım", "Ali Hoca"), e.g. in a planning-list
#: column header ("... Derslik Planlama Birimi-<ad> Bey tarafından doldurulmalıdır")
_HONORIFIC = re.compile(r"(?<!\w)([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})\s+(?:Bey|Hanım|Hanim|Hoca|Hocam)(?!\w)")
_HONORIFIC_HINT = re.compile(r"(?:Bey|Hanım|Hanim|Hoca|Hocam)(?!\w)")
#: the export's own role labels: never treated as someone's name
_ROLE_WORDS = frozenset(
    _fold_key(w)
    for w in (
        *ROLE_TR.values(),
        *ROLE_EN.values(),
        "kendim",
        "myself",
        "sistem",
        "system",
        "Kullanıcı",
        "user",
        "Onaycı",
        "approver",
        "admin",
    )
)


async def _scrub_others(session: AsyncSession, user: User, data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Other people named in the person's own records (a notification "Ahmet Bey booked for you", an approver's
    note, a coordinator's reason, a co-instructor in a planning-list row) appear by their role, never by name,
    username or e-mail (spec §4.7; round-1 T-R1-27 added the instructor records). Whole words only, Turkish
    dotted / dotless i and case alike, one pass per text (a replacement is never matched again)."""
    marks: dict[str, tuple[str, str]] = {}  # match key -> (pattern, replacement)

    def mark(v: str | None, repl: str) -> None:
        # a role word is no one's name ("Administrator", the seeded admin's name, is also the export's role label)
        if v and len(v.strip()) >= 3 and _WORD.search(v) and _fold_key(v) not in _ROLE_WORDS:
            marks.setdefault(_fold_key(v), (_needle_rx(v), repl))

    linked = list((await session.execute(select(Instructor).where(Instructor.user_id == user.id))).scalars())
    own = {_fold_key(v) for v in (user.email, user.full_name, user.username) if v}
    named_self = " ".join(x for x in (user.firstname, user.lastname) if x)
    if named_self:
        own.add(_fold_key(named_self))
    own |= {_fold_key(v) for i in linked for v in (i.full_name, i.email, i.canonical_name) if v}
    for u in (await session.execute(select(User).where(User.id != user.id))).scalars():
        role = f"[{ROLE_TR.get(u.role, 'Kullanıcı')}]"
        named = " ".join(x for x in (u.firstname, u.lastname) if x)
        for v in (u.email, u.full_name, named, u.username):
            mark(v, role)
    teacher = f"[{ROLE_TR['TEACHER']}]"
    linked_ids = {i.id for i in linked}
    for i in (await session.execute(select(Instructor))).scalars():
        if i.id not in linked_ids:
            for v in (i.full_name, i.email):
                mark(v, teacher)
    for k in own:
        marks.pop(k, None)
    by_word: dict[str, list[str]] = {}
    for k in marks:
        first = _WORD.search(k)
        if first:
            by_word.setdefault(first.group(0), []).append(k)
    compiled: dict[frozenset[str], tuple[re.Pattern[str], list[str]]] = {}

    own_words = {w for k in own for w in _WORD.findall(k)}

    def by_title(m: re.Match[str]) -> str:
        return m.group(0) if _fold_key(m.group(1)) in own_words else "[Kişi]"

    def clean_text(v: str) -> str:
        if _HONORIFIC_HINT.search(v):  # "Ahmet Bey", "Elif Hanım": a person named in a header or a note
            v = _HONORIFIC.sub(by_title, v)
        words = {_fold_key(w) for w in _WORD.findall(v)}
        cands = frozenset(k for w in words for k in by_word.get(w, ()))
        if not cands:
            return v
        hit = compiled.get(cands)
        if hit is None:
            alts = sorted(cands, key=len, reverse=True)  # the longest name first ("Ali Can Öz" before "Ali Can")
            rx = re.compile(r"(?<!\w)(?:" + "|".join(f"({marks[k][0]})" for k in alts) + r")(?!\w)", re.IGNORECASE)
            hit = compiled[cands] = (rx, alts)
        rx, alts = hit
        return rx.sub(lambda m: marks[alts[(m.lastindex or 1) - 1]][1], v)

    def clean(v: Any) -> Any:
        if isinstance(v, str):
            return clean_text(v)
        if isinstance(v, dict):  # keys too: a planning-list column header may name a person
            return {clean_text(k) if isinstance(k, str) else k: clean(x) for k, x in v.items()}
        if isinstance(v, list):
            return [clean(x) for x in v]
        return v

    return {k: clean(rows) for k, rows in data.items()}


#: every file of the export zip, explained in the README (Turkish, English); a section missing here is listed with
#: its name only (``tests/test_loop_r1_lane_d.py`` asks for an explanation of every file)
EXPORT_FILES: dict[str, tuple[str, str]] = {
    "profile": (
        "Hesap bilgileriniz (ad, e-posta, rol, dil, giriş zamanları).",
        "Your account (name, e-mail, role, language, sign-in times).",
    ),
    "bookings": (
        "Sizin adınıza yapılmış rezervasyonlar, notları ve iptal nedenleri.",
        "Bookings in your name, with their notes and cancellation reasons.",
    ),
    "series": ("Yinelenen rezervasyonlarınız.", "Your recurring bookings."),
    "approvals": (
        "Onaya gönderdiğiniz rezervasyon talepleri ve sonuçları.",
        "Booking requests you sent for approval and their outcome.",
    ),
    "approval_decisions": (
        "Taleplerinize verilen kararlar (alınan) ve onaycı olarak verdikleriniz (verilen); karşı taraf rolüyle.",
        "Decisions on your requests (received) and the ones you made as an approver (made); others by role.",
    ),
    "approver_scopes": (
        "Onaycı olduğunuz salon / grup / etiket kapsamları.",
        "The rooms, groups or tags you approve for.",
    ),
    "notifications": ("Uygulama içi bildirimleriniz.", "Your in-app notifications."),
    "deliveries": ("E-posta ve uygulama içi bildirim gönderim kayıtları.", "E-mail and in-app delivery records."),
    "channel_deliveries": (
        "SMS / Telegram gibi kanallara gönderim kayıtları.",
        "Deliveries to channels such as SMS or Telegram.",
    ),
    "channels": (
        "Bağladığınız bildirim kanalları (adresler maskeli).",
        "The notification channels you linked (addresses masked).",
    ),
    "sso_identities": ("Kurumsal oturum açma (SSO) kimlikleriniz.", "Your single sign-on (SSO) identities."),
    "consents": (
        "Açık rızalarınız: verildiği ve geri alındığı zamanlar.",
        "Your explicit consents: when given and withdrawn.",
    ),
    "notice_acks": (
        "Okuduğunuzu onayladığınız aydınlatma metni sürümleri.",
        "The privacy notice versions you acknowledged.",
    ),
    "audit_as_actor": ("Sizin yaptığınız işlemlerin denetim kayıtları.", "Audit records of the actions you took."),
    "audit_as_subject": (
        "Konusu siz olan denetim kayıtları (hesap, öğretim elemanı kaydı, tercihler, başvurular); yapan rolüyle.",
        "Audit records about you (account, instructor record, wishes, requests); who did it by role.",
    ),
    "learning_observations": (
        "Öğrenme modülünün sizinle ilgili gözlemleri.",
        "What the learning module observed about you.",
    ),
    "learned_priors": (
        "Bu gözlemlerden çıkarılan eğilimler (ör. sık istenen salon) ve güven düzeyleri.",
        "Tendencies learned from those observations (e.g. a room often asked for) with their confidence.",
    ),
    "suggestion_feedback": (
        "Bu eğilimlerden doğan önerilere verilen kararlar (kabul, ret, erteleme).",
        "Decisions on the suggestions made from those tendencies (accept, reject, snooze).",
    ),
    "data_requests": (
        "KVKK başvurularınız (indirme, silme, düzeltme, bilgi) ve sonuçları.",
        "Your KVKK requests (export, erase, rectify, info) and their outcome.",
    ),
    "instructor": (
        "Hesabınıza bağlı öğretim elemanı kaydı (ad, unvan, e-posta).",
        "The instructor record linked to your account (name, title, e-mail).",
    ),
    "instructor_sections": (
        "Verdiğiniz dersler ve şubeler; diğer öğretim elemanları yalnızca rolleriyle.",
        "The courses and sections you teach; other instructors by role only.",
    ),
    "planning_requests": (
        "Taleplerim: derslerinizin talepleri (talep metni, istenen → atanan, sonuç, nedeni, planlamacı düzenlemesi).",
        "My requests: your classes' requests (request text, requested -> assigned, verdict, reason, planner edits).",
    ),
    "exam_requests": ("Derslerinizin sınav talepleri.", "The exam requests of your classes."),
    "teacher_preferences": (
        "Tercihleriniz (Tercih ekle): durum, koordinatörün kararı ve gerekçesi; koordinatör rolüyle.",
        "Your wishes (Add a preference): status, the coordinator's decision and reason; the coordinator by role.",
    ),
    "priority_notes": (
        "Koordinatörlerin sizin için belirlediği öncelik ve notu.",
        "The priority and note coordinators set for you.",
    ),
    "invigilation": (
        "Gözetmen havuzu kaydınız ve gözetmenlik görevleriniz.",
        "Your invigilator pool record and invigilation duties.",
    ),
    "calendar_links": (
        "Takvim aktarımı bağlantılarınız (Google / Microsoft) ve takvim adresleriniz (anahtarlar hariç).",
        "Your calendar sync connections (Google / Microsoft) and feed links (without the keys).",
    ),
    "booking_limits": (
        "Size özel rezervasyon sınırları (R: rolün değeri, U: size özel, X: sınırsız).",
        "Booking limits set for you (R: the role's value, U: your own, X: unlimited).",
    ),
    "welcome_guide": (
        "Karşılama rehberinin sizin için durumu (gösterildi, ertelendi, tur adımı, tamamlanan maddeler).",
        "The welcome guide's state for you (shown, snoozed, tour step, items done).",
    ),
    "sign_in_security": (
        "Giriş güvenliğiniz: doğrulama uygulaması açık mı, kalan kurtarma kodu sayısı, geçiş anahtarlarınızın adları "
        "ve tarihleri, güvenilir cihazlar (gizli anahtarlar ve kodlar dışa aktarılmaz).",
        "Your sign-in security: whether the authenticator app is on, recovery codes left, your passkeys' names and "
        "dates, trusted devices (secrets and codes are never exported).",
    ),
    "known_devices": (
        "Hesabınıza giriş yapılan cihazların özeti (ilk ve son görülme); tarayıcı, sistem ve adres saklanmaz.",
        "A hash of each device that signed in to your account (first and last seen); the browser, system and "
        "address are not stored.",
    ),
}


def export_readme(data: dict[str, Any], now: datetime) -> str:
    lines = [
        "SmartSched kişisel veri dökümü / personal data export (KVKK m.11)",
        f"Oluşturma / generated: {now.isoformat(timespec='seconds')}Z",
        "",
        "Başka kişiler yalnızca rolleriyle gösterilir ([Planlamacı], [Öğretim elemanı] ...).",
        "Other people appear only by their role ([Planlamacı] = planner, [Öğretim elemanı] = instructor ...).",
        "Erişilebilirlik ihtiyacı yazan notlar Taleplerim'deki gibi gösterilmez (öğrencilerin sağlık verisi).",
        "Notes that describe an accessibility need are left out, as in My requests (students' health data).",
        "",
        "data.json: bütün bölümler tek dosyada / every section in one file.",
        "Her bölüm ayrıca bir JSON ve bir CSV dosyasıdır / every section is also a JSON and a CSV file:",
        "",
    ]
    for name in data:
        tr, en = EXPORT_FILES.get(name, ("", ""))
        rows = len(data[name]) if isinstance(data[name], list) else 0
        lines.append(f"{name}.json, {name}.csv ({rows} satır / rows)")
        if tr:
            lines += [f"  {tr}", f"  {en}"]
    return "\n".join(lines) + "\n"


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
            z.writestr(f"{name}.json", json.dumps(rows, ensure_ascii=False, indent=2, default=_iso))
        z.writestr("README.txt", export_readme(data, now))
    await audit.record(session, "kvkk.dsr_download", "dsr_request", r.id, after={"sections": len(data)}, actor=user)
    return buf.getvalue()


#: ``GET /admin/dsr?status=``: ``open`` (default: OPEN + IN_PROGRESS), ``all`` (every queued request), or one status
DSR_STATUSES = ("OPEN", "IN_PROGRESS", "DONE", "REFUSED")
QUEUE_FILTERS = ("open", "all", *DSR_STATUSES)


def queue_filter(status: str | None) -> str:
    """``open`` (exactly, the default: OPEN + IN_PROGRESS), ``all`` (any case; an empty value too, as before) or one
    status in any case (``done``, ``İn_progress`` typed with a Turkish dotted İ, NBSP tolerated; ``OPEN`` = OPEN
    only). Anything else is a 422 with the allowed values."""
    if status is None:
        return "open"
    text = tr_norm.clean_text(status) or ""
    if text == "open":
        return "open"
    key = text.replace("İ", "I").replace("ı", "i").upper()
    if key in ("", "ALL"):
        return "all"
    if key in DSR_STATUSES:
        return key
    raise KvkkError(
        422,
        "status",
        f"status: one of {', '.join(QUEUE_FILTERS)}",
        f"durum şunlardan biri olmalı: {', '.join(QUEUE_FILTERS)}",
        field="status",
        allowed=list(QUEUE_FILTERS),
    )


async def queue(session: AsyncSession, status: str | None) -> list[DsrRequest]:
    """The administrators' queue (exports are self-service and never queued), by due date."""
    which = queue_filter(status)
    q = select(DsrRequest).where(DsrRequest.kind != "export")
    if which == "open":
        q = q.where(DsrRequest.status.in_(OPEN_STATES))
    elif which != "all":
        q = q.where(DsrRequest.status == which)
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
    await audit.record(
        session, "kvkk.dsr_refuse", "dsr_request", r.id, after={"kind": r.kind}, reason=r.refusal_reason, actor=admin
    )
    await _tell(session, r, refused=True)
    return r


async def complete(session: AsyncSession, admin: User, request_id: int, note: str | None) -> DsrRequest:
    r = await _load_open(session, request_id)
    now = utcnow()
    result: dict[str, Any] = {"note": (note or "").strip() or None}
    was: User | None = None
    if r.kind == "erase":
        if r.user_id is None:
            raise KvkkError(409, "gone", "the account is gone already", "hesap zaten yok")
        if r.user_id == admin.id:
            raise KvkkError(
                409,
                "own_request",
                "another administrator completes your own erasure",
                "kendi silme talebinizi başka bir yönetici tamamlar",
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
                raise KvkkError(
                    409, "last_admin", "the last active administrator cannot be erased", "son etkin yönetici silinemez"
                )
        was = User(id=subject.id, email=subject.email, language=subject.language)
        result.update(await erase_user(session, admin, subject))
        r.subject_label = pseudonym(subject.id)
        r.user_id = None
    r.status, r.handled_by, r.handled_at, r.result = "DONE", admin.id, now, result
    await _tell(session, r, refused=False, erased=was)
    await session.flush()
    await audit.record(
        session,
        "kvkk.dsr_complete",
        "dsr_request",
        r.id,
        after={"kind": r.kind, "counts": result.get("counts")},
        actor=admin,
    )
    return r


async def _tell(session: AsyncSession, r: DsrRequest, *, refused: bool, erased: User | None = None) -> None:
    """The requester's in-app note and e-mail (outbox) of the decision. After an erasure (``erased``: the account as it
    was, read before) only the e-mail to the former address is queued; that outbox row is the last copy of the
    address and goes with the notification retention."""
    from app.services import bookings_notify as mail
    from app.services.bookings_notify import _language

    user = erased or (await session.get(User, r.user_id) if r.user_id is not None else None)
    if user is None:
        return
    tr = (await _language(session, user)) == "tr"
    kind_tr = {"erase": "silme", "rectify": "düzeltme", "info": "bilgi"}.get(r.kind, r.kind)
    if refused:
        title = f"Kişisel veri ({kind_tr}) talebiniz reddedildi" if tr else f"Your data request ({r.kind}) was refused"
        body = r.refusal_reason or ""
    elif r.kind == "erase":
        title = "Hesabınız ve kişisel verileriniz silindi" if tr else "Your account and personal data were erased"
        body = (
            "Denetim kayıtları yasal saklama süresince anonim olarak tutulur."
            if tr
            else "Audit records are kept anonymised for the legal retention period."
        )
    else:
        title = f"Kişisel veri ({kind_tr}) talebiniz tamamlandı" if tr else f"Your data request ({r.kind}) is done"
        body = (r.result or {}).get("note") or ""
    if erased is None:
        session.add(
            InAppNotification(
                user_id=user.id,
                kind="kvkk.request",
                title=title[:255],
                body=body,
                link="/profile#privacy",
                data={"request_id": r.id, "status": "REFUSED" if refused else "DONE"},
            )
        )
    if user.email:
        await mail.notify(
            session,
            kind="kvkk_request",
            to_email=user.email,
            subject=title[:255],
            body=body,
            user_id=None if erased is not None else user.id,
        )
    await session.flush()


_PERSONAL_KEYS = ("notes", "user_id", "created_by", "updated_by", "cancelled_by")


def _scrub_snapshot(v: Any) -> Any:
    if not isinstance(v, dict):
        return v
    return {k: (None if k in _PERSONAL_KEYS else val) for k, val in v.items()}


def _calendar_failure(provider: str, code: str, en: str, tr: str, **data: Any) -> dict[str, Any]:
    return {"provider": provider, "code": code, "message_en": en, "message_tr": tr, **data}


def _calendar_failures(res: dict[str, Any], label: str) -> list[dict[str, Any]]:
    """The follow-ups an administrator may need after one push calendar was disconnected (TR/EN)."""
    p, out = res["provider"], []
    detail = "; ".join(res.get("errors") or [])[:400] or None
    if res["revoke"] == "unreadable":
        out.append(
            _calendar_failure(
                p,
                "grant_unreadable",
                f"the stored {label} grant could not be read (the encryption key changed): it was deleted but not "
                "revoked at the provider; remove SmartSched's access in the provider's admin console",
                f"saklanan {label} yetkisi okunamadı (şifreleme anahtarı değişmiş): silindi ama sağlayıcıda iptal "
                "edilemedi; SmartSched erişimini sağlayıcının yönetim konsolundan kaldırın",
                error=detail,
            )
        )
    if res["events_failed"]:
        k = res["events_failed"]
        out.append(
            _calendar_failure(
                p,
                "events_not_removed",
                f"{k} event(s) SmartSched had added to the person's {label} could not be removed",
                f"kişinin {label} takvimine SmartSched'in eklediği {k} etkinlik silinemedi",
                count=k,
                error=detail,
            )
        )
    if res["revoke"] == "failed":
        out.append(
            _calendar_failure(
                p,
                "revoke_failed",
                f"the {label} grant could not be revoked at the provider; the stored tokens are deleted, remove "
                "SmartSched's access in the provider's admin console",
                f"{label} yetkisi sağlayıcıda iptal edilemedi; saklanan anahtarlar silindi, SmartSched erişimini "
                "sağlayıcının yönetim konsolundan kaldırın",
                error=detail,
            )
        )
    if res["revoke"] == "queued":
        out.append(
            _calendar_failure(
                p,
                "provider_timeout",
                f"{label} did not answer in time; removing the events and revoking the grant continue in the "
                "background",
                f"{label} zamanında yanıt vermedi; etkinliklerin silinmesi ve yetkinin iptali arka planda sürüyor",
                error=detail,
            )
        )
    return out


async def _erase_calendars(session: AsyncSession, uid: int) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    """Disconnect every push calendar of ``uid`` through ``calendar_connectors.disconnect`` (the events SmartSched
    pushed are removed and the grant revoked at the provider, awaited so the answer is recorded) before anything else
    of the erasure is written. A failure never blocks the erasure: it is listed (TR/EN) and the rows go anyway.
    Returns (connections, per-connection outcomes, failures)."""
    from app.services import calendar_connectors as conn_svc

    conns = list(
        (
            await session.execute(
                select(CalendarConnection).where(CalendarConnection.user_id == uid).order_by(CalendarConnection.id)
            )
        ).scalars()
    )
    outcomes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for conn in conns:
        provider = conn.provider
        p = conn_svc.PROVIDERS.get(provider)
        label = p.label if p is not None else provider
        try:
            async with session.begin_nested():
                res = await conn_svc.disconnect(session, conn, wait=True)
        except Exception as exc:  # any failure is recorded; the rows are deleted with the rest below
            error = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("kvkk erasure: disconnecting %s of user %s failed: %s", provider, uid, error)
            outcomes.append(
                {
                    "provider": provider,
                    "events": None,
                    "events_removed": 0,
                    "events_failed": None,
                    "revoke": "failed",
                    "errors": [error],
                }
            )
            failures.append(
                _calendar_failure(
                    provider,
                    "disconnect_failed",
                    f"disconnecting {label} failed; the connection was deleted without removing the events or "
                    "revoking the grant at the provider",
                    f"{label} bağlantısı kesilemedi; bağlantı silindi ama etkinlikler kaldırılamadı ve yetki "
                    "sağlayıcıda iptal edilemedi",
                    error=error,
                )
            )
            continue
        outcomes.append(res)
        failures += _calendar_failures(res, label)
    return len(conns), outcomes, failures


async def erase_user(session: AsyncSession, admin: User, subject: User) -> dict[str, Any]:
    """Erase / anonymise everything of ``subject`` (see the module docstring). Returns counts per table, the
    disconnected push calendars (``calendar``: provider, events, events_removed, events_failed, revoke, errors) and
    ``failures`` (TR/EN follow-ups for the administrator; they never block the erasure)."""
    from app.services import bookings as bsvc
    from app.services import learning

    uid = subject.id
    label = pseudonym(uid)
    counts: dict[str, int] = {}
    # 0. push calendars first, while nothing is written yet: pushed events removed, grants revoked at the provider
    n_conns, calendar_out, failures = await _erase_calendars(session, uid)
    today = await bsvc.today(session)
    now = utcnow()
    reason = "KVKK silme talebi / erasure request"
    own_bookings = [str(i) for i in (await session.execute(select(Booking.id).where(Booking.user_id == uid))).scalars()]
    own_series = [
        str(i) for i in (await session.execute(select(BookingSeries.id).where(BookingSeries.user_id == uid))).scalars()
    ]
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
    items: list[tuple[Any, dict[str, Any] | None, dict[str, Any] | None]] = []
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
        await publish_event(
            session,
            "booking.cancel",
            "booking",
            future[0].id,
            items=items,
            actor=admin,
            reason=reason,
            payload={"booking_ids": [b.id for b in future], "actor_id": admin.id},
        )
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
    from app.services import mail_senders  # RF-11: counted before the user.<id>.* settings go below

    counts["known_devices"] = await mail_senders.erase(session, uid)
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
    counts["calendar_connections"] += n_conns  # disconnected in step 0 (the delete above catches any left)
    from app.services import welcome as welcome_svc  # WG-03: the welcome guide's per-person state

    counts["welcome_progress"] = await welcome_svc.erase(session, uid)
    from app.services import mfa as mfa_svc  # AU-B: second factors, passkeys, trusted devices, challenges

    counts["sign_in_security"] = await mfa_svc.erase(session, uid)
    counts["profile_photo"] = delete_profile_photo(uid)
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
    await session.execute(update(LearnedObservation).where(LearnedObservation.actor_id == uid).values(actor_id=None))
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
    # other people's events about the person's bookings keep the booking but lose its notes and owner
    entity_windows = [
        AuditPurgeWindow(kind="anonymise", entity_type=et, entity_id=eid, created_at=now)
        for et, ids in (("booking", own_bookings), ("booking_series", own_series))
        for eid in ids
    ]
    session.add_all(entity_windows)
    await session.flush()
    scrubbed = 0
    if own_bookings or own_series:
        q = select(AuditEvent).where(
            or_(
                (AuditEvent.entity_type == "booking") & AuditEvent.entity_id.in_(own_bookings or ["-"]),
                (AuditEvent.entity_type == "booking_series") & AuditEvent.entity_id.in_(own_series or ["-"]),
            )
        )
        for ev in list((await session.execute(q)).scalars()):
            new_b, new_a, new_d = _scrub_snapshot(ev.before), _scrub_snapshot(ev.after), _scrub_snapshot(ev.diff)
            if (new_b, new_a, new_d) != (ev.before, ev.after, ev.diff):
                await session.execute(
                    update(AuditEvent).where(AuditEvent.id == ev.id).values(before=new_b, after=new_a, diff=new_d)
                )
                scrubbed += 1
    counts["audit_booking_rows"] = scrubbed
    await session.delete(window)
    for w in entity_windows:
        await session.delete(w)
    await session.flush()
    # 6. the account itself: no name, no address, cannot sign in. The flush hook of the administration tables is
    #    paused for this one flush: its "user.update" row would copy the old name and e-mail back into the log
    ctx = session.info.pop(audit.CTX_KEY, None)
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
    try:
        await session.flush()
    finally:
        if ctx is not None:
            session.info[audit.CTX_KEY] = ctx
    await audit.record(
        session,
        "kvkk.erase",
        "user",
        uid,
        after={"subject": label, "counts": counts, "calendar": calendar_out, "failures": failures},
        actor=admin,
    )
    return {
        "counts": counts,
        "calendar": calendar_out,
        "failures": failures,
        "partial": True,
        "partial_reason": "denetim kayıtları anonim olarak saklanır (yasal saklama) / audit records kept anonymised",
    }
