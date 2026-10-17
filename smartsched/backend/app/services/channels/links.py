"""Linking an address to a user (Profile > "Bildirim kanalları").

* Web Push: the browser's ``PushSubscription`` (endpoint + keys). The endpoint must be a real push service
  (allowlist below) and pass the M-41 SSRF guard; one row per browser (``address_hash`` = HMAC of the endpoint).
* Telegram: a one-time nonce in ``https://t.me/<bot>?start=<nonce>``; the bot receives ``/start <nonce>`` (webhook
  or long poll) and SmartSched stores the private chat's id.
* SMS / WhatsApp: the phone number (Turkish spellings normalised to E.164) is verified by a 6-digit code sent through
  the channel itself; 10 minutes, single use, 5 attempts, at most 3 codes per 10 minutes.

Codes are stored as HMACs (APP_SECRET) only; addresses are Fernet-encrypted. Unlinking deletes the address at once
(and whatever was still queued for it). Linking switches the channel on in the user's notification preferences for
every event the user has not chosen for (a channel that was never linked stays off).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.importers import normalize as n
from app.models import User
from app.models.base import utcnow
from app.models.channels import ChannelDelivery, ChannelLinkCode, UserChannel
from app.services import audit
from app.services.channels import config, outbox
from app.services.channels.config import ConfigError

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
MAX_CODES_PER_WINDOW = 3
MAX_PUSH_DEVICES = 10
USER_KINDS = ("webpush", "telegram", "whatsapp", "sms")
#: real browser push services (Chrome/Edge via FCM, Firefox, Safari, legacy Edge/WNS)
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com")
PUSH_SUFFIXES = (".push.apple.com", ".notify.windows.com")
OPT_IN_TR = (
    "Bu numaraya, kurumun WhatsApp hesabından SmartSched oda talebi bildirimleri gönderilmesini kabul ediyorum. "
    "İstediğim zaman Profil > Bildirim kanalları'ndan kaldırabilirim."
)
OPT_IN_EN = (
    "I agree to receive SmartSched room-request notifications on this number from the institution's WhatsApp "
    "account. I can remove it at any time under Profile > Notification channels."
)


class PhoneError(ValueError):
    pass


def _hmac(text: str) -> str:
    key = hashlib.sha256(("channels:" + get_settings().app_secret).encode("utf-8")).digest()
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()


def address_hash(kind: str, address: str) -> str:
    return _hmac(f"address:{kind}:{address}")


def _err(code: str, en: str, tr: str, status: int = 422) -> ConfigError:
    return ConfigError(code, en, tr, status=status)


# --------------------------------------------------------------------------------------------------
# phone numbers
# --------------------------------------------------------------------------------------------------


def normalize_phone(raw: Any) -> str:
    """E.164 (``+905321112233``) from how people write numbers in Turkey: ``0532 111 22 33``,
    ``0 (532) 111 22 33``, ``532-111-22-33``, ``+90 532 ...``, ``0090 ...``, NBSP and dots included."""
    text = n.clean_text(raw) or ""
    digits: list[str] = []
    plus = False
    for ch in text:
        if ch == "+" and not digits and not plus:
            plus = True
            continue
        if ch in " .-()/":
            continue
        d = unicodedata.decimal(ch, None)
        if d is None:
            raise PhoneError(text)
        digits.append(str(d))
    s = "".join(digits)
    if not plus:
        if s.startswith("00"):
            s = s[2:]
        elif s.startswith("0") and len(s) == 11:
            s = "90" + s[1:]
        elif len(s) == 10 and s.startswith("5"):
            s = "90" + s
        elif not (s.startswith("90") and len(s) == 12):
            raise PhoneError(text)
    if not 8 <= len(s) <= 15 or s.startswith("0") or (s.startswith("90") and len(s) != 12):
        raise PhoneError(text)
    return "+" + s


def phone_hint(e164: str) -> str:
    d = e164.lstrip("+")
    if d.startswith("90") and len(d) == 12:
        return f"+90 {d[2]}•• ••• •• {d[-2:]}"
    return f"+{d[:2]}•••{d[-2:]}"


# --------------------------------------------------------------------------------------------------
# reading / removing
# --------------------------------------------------------------------------------------------------


def channel_out(ch: UserChannel) -> dict[str, Any]:
    return {
        "id": ch.id,
        "kind": ch.kind,
        "display_hint": ch.display_hint,
        "label": ch.label,
        "status": ch.status,
        "last_error": ch.last_error,
        "verified_at": ch.verified_at.isoformat() if ch.verified_at else None,
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
    }


async def user_channels(session: AsyncSession, user_id: int, kind: str | None = None) -> list[UserChannel]:
    q = select(UserChannel).where(UserChannel.user_id == user_id)
    if kind:
        q = q.where(UserChannel.kind == kind)
    return list((await session.execute(q.order_by(UserChannel.id))).scalars())


async def active_channels(session: AsyncSession, user_id: int, kind: str) -> list[UserChannel]:
    return [c for c in await user_channels(session, user_id, kind) if c.status == "active"]


async def unlink(session: AsyncSession, user: User, channel_id: int) -> bool:
    ch = await session.get(UserChannel, channel_id)
    if ch is None or ch.user_id != user.id:
        return False
    await session.execute(delete(ChannelDelivery).where(ChannelDelivery.user_channel_id == ch.id))
    kind, hint = ch.kind, ch.display_hint
    await session.delete(ch)
    await session.flush()
    await audit.record(
        session, "channel.unlink", "user_channel", channel_id, before={"kind": kind, "hint": hint}, actor=user
    )
    return True


async def available(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    """The channels the administrator switched on, as the Profile card lists them."""
    out: list[dict[str, Any]] = []
    for kind in USER_KINDS:
        sender = await config.sender_for(session, kind)
        if sender is None:
            continue
        spec = config.KINDS[kind]
        item: dict[str, Any] = {
            "kind": kind,
            "label_tr": spec.label_tr if kind != "whatsapp" else "WhatsApp",
            "label_en": spec.label_en if kind != "whatsapp" else "WhatsApp",
            "link": spec.link,
            "content_mode": sender.content_mode,
        }
        if kind == "webpush":
            item["vapid_public_key"] = sender.options.get("vapid_public_key")
        if kind == "whatsapp":
            item.update(opt_in_tr=OPT_IN_TR, opt_in_en=OPT_IN_EN, sender=sender.kind)
        out.append(item)
    from app.services.channels import targets

    for kind in ("teams", "slack"):
        cfg = await config.effective(session, kind)
        if cfg is not None:
            spec = config.KINDS[kind]
            out.append(
                {
                    "kind": kind,
                    "label_tr": spec.label_tr,
                    "label_en": spec.label_en,
                    "link": "department",
                    "content_mode": cfg.content_mode,
                    "department_target": await targets.for_department(session, kind, user.department_id) is not None,
                }
            )
    return out


async def _switch_on(session: AsyncSession, user_id: int, kind: str) -> None:
    """Linking is the opt-in: the channel is turned on for every event the user has not chosen for yet."""
    from app.services import notify_dispatch as nd

    if kind not in {a.name for a in nd.channels()}:
        return
    prefs = await nd.load_preferences(session, user_id)
    events = {ev: {kind: True} for ev in nd.EVENTS if kind not in prefs.events.get(ev, {})}
    if events:
        await nd.update_preferences(session, user_id, events_in=events)


async def _store(
    session: AsyncSession, user: User, kind: str, address: str, hint: str, label: str | None = None
) -> UserChannel:
    h = address_hash(kind, address)
    q = select(UserChannel).where(
        UserChannel.user_id == user.id, UserChannel.kind == kind, UserChannel.address_hash == h
    )
    ch = (await session.execute(q)).scalar_one_or_none()
    now = utcnow()
    if ch is None:
        ch = UserChannel(user_id=user.id, kind=kind, address_hash=h)
        session.add(ch)
    ch.address_enc = encrypt_secret(address)
    ch.display_hint, ch.status, ch.last_error, ch.verified_at = hint[:64], "active", None, now
    if label is not None:
        ch.label = label[:64] or None
    await session.flush()
    await audit.record(
        session, "channel.link", "user_channel", ch.id, after={"kind": kind, "hint": ch.display_hint}, actor=user
    )
    await _switch_on(session, user.id, kind)
    return ch


# --------------------------------------------------------------------------------------------------
# Web Push
# --------------------------------------------------------------------------------------------------


def _b64url(value: Any, size: int, name: str) -> str:
    text = (n.clean_text(value) or "").replace(" ", "")
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise _err("subscription_invalid", f"{name} is not base64url", f"{name} base64url değil") from exc
    if len(raw) != size or (name == "p256dh" and raw[0] != 4):
        raise _err("subscription_invalid", f"{name} has the wrong length", f"{name} uzunluğu hatalı")
    return text.rstrip("=")


async def check_push_endpoint(endpoint: str) -> str:
    """A browser push endpoint: https, a real push service, and every address it resolves to is public."""
    from app.services import webhooks

    url = n.clean_text(endpoint) or ""
    try:
        url = webhooks.validate_url(url)
    except ValueError as exc:
        raise _err("endpoint_refused", str(exc), "bildirim adresi reddedildi: " + str(exc)) from exc
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https"
        or not (host in PUSH_HOSTS or host.endswith(PUSH_SUFFIXES))
        or parts.port not in (None, 443)
    ):
        raise _err(
            "endpoint_refused",
            "the subscription endpoint is not a browser push service (FCM, Mozilla, Apple, Windows)",
            "abonelik adresi bir tarayıcı bildirim servisi değil (FCM, Mozilla, Apple, Windows)",
        )
    try:
        await webhooks.check_resolved(url)
    except ValueError as exc:
        raise _err("endpoint_refused", str(exc), "bildirim adresi engellendi (blocked): " + str(exc)) from exc
    return url


async def add_push_subscription(
    session: AsyncSession, user: User, sub: dict[str, Any], label: str | None
) -> UserChannel:
    endpoint = await check_push_endpoint(str(sub.get("endpoint") or ""))
    keys = sub.get("keys") or {}
    if not isinstance(keys, dict):
        raise _err("subscription_invalid", "keys must be an object", "keys bir nesne olmalı")
    p256dh = _b64url(keys.get("p256dh"), 65, "p256dh")
    auth = _b64url(keys.get("auth"), 16, "auth")
    h = address_hash("webpush", endpoint)
    existing = [c for c in await user_channels(session, user.id, "webpush") if c.address_hash != h]
    if len(existing) >= MAX_PUSH_DEVICES:
        raise _err(
            "too_many_devices", f"at most {MAX_PUSH_DEVICES} browsers", f"en çok {MAX_PUSH_DEVICES} tarayıcı", 409
        )
    address = json.dumps({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}, sort_keys=True)
    # the address hash covers the endpoint only: the same browser subscribing again replaces its keys
    q = select(UserChannel).where(
        UserChannel.user_id == user.id, UserChannel.kind == "webpush", UserChannel.address_hash == h
    )
    ch = (await session.execute(q)).scalar_one_or_none()
    host = (urlsplit(endpoint).hostname or "")[:64]
    clean_label = n.clean_text(label) if label else None
    if ch is None:
        ch = await _store(session, user, "webpush", endpoint, host, clean_label)
    elif clean_label is not None:
        ch.label = clean_label[:64]
    ch.address_enc = encrypt_secret(address)
    ch.status, ch.last_error = "active", None
    await session.flush()
    return ch


# --------------------------------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------------------------------


def _tg_hash(code: str) -> str:
    return _hmac(f"telegram-start:{code}")


async def telegram_link(session: AsyncSession, user: User) -> dict[str, Any]:
    cfg = await config.sender_for(session, "telegram")
    if cfg is None:
        raise channel_off("telegram")
    await session.execute(
        delete(ChannelLinkCode).where(
            (ChannelLinkCode.user_id == user.id)
            & (ChannelLinkCode.kind == "telegram")
            & ChannelLinkCode.used_at.is_(None)
        )
    )
    code = secrets.token_urlsafe(24)  # 32 characters of A-Z a-z 0-9 _ - (Telegram's start parameter alphabet)
    now = utcnow()
    session.add(
        ChannelLinkCode(
            code_hash=_tg_hash(code), user_id=user.id, kind="telegram", created_at=now, expires_at=now + CODE_TTL
        )
    )
    await session.flush()
    bot = cfg.options["bot_username"]
    return {"deep_link": f"https://t.me/{bot}?start={code}", "expires_at": (now + CODE_TTL).isoformat() + "Z"}


_START_RX = re.compile(r"^/start(?:@[A-Za-z0-9_]+)?\s+([A-Za-z0-9_-]{16,64})$", re.IGNORECASE)


async def telegram_update(session: AsyncSession, update: dict[str, Any]) -> dict[str, Any]:
    """Handle one bot update; returns the webhook reply (a Bot API method call) or ``{}``."""
    from app.services.channels import text

    member = update.get("my_chat_member")
    if isinstance(member, dict):
        chat = member.get("chat") or {}
        status = ((member.get("new_chat_member") or {}).get("status")) or ""
        if status in ("kicked", "left"):
            await _telegram_block(session, chat.get("id"))
        return {}
    msg = update.get("message")
    if not isinstance(msg, dict):
        return {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not isinstance(chat_id, int) or isinstance(chat_id, bool) or chat.get("type") != "private":
        return {}
    body = n.clean_text(msg.get("text")) or ""
    lang = text.lang_of((msg.get("from") or {}).get("language_code"))
    if body.lower().split("@")[0] == "/stop":
        await _telegram_block(session, chat_id)
        return {"method": "sendMessage", "chat_id": chat_id, "text": text.both(text.STOPPED, lang)}
    m = _START_RX.match(body)
    if not m:
        return {}
    now = utcnow()
    row = (
        await session.execute(select(ChannelLinkCode).where(ChannelLinkCode.code_hash == _tg_hash(m.group(1))))
    ).scalar_one_or_none()
    if row is None or row.kind != "telegram" or row.used_at is not None or row.expires_at < now:
        return {"method": "sendMessage", "chat_id": chat_id, "text": text.both(text.INVALID_CODE, lang)}
    if await config.sender_for(session, "telegram") is None:
        return {}
    row.used_at = now
    user = await session.get(User, row.user_id)
    if user is None:
        return {}
    username = (msg.get("from") or {}).get("username")
    hint = f"@{username}" if isinstance(username, str) and username else f"Telegram ••{str(chat_id)[-2:]}"
    await _store(session, user, "telegram", str(chat_id), hint)
    user_lang = text.lang_of(user.language) if user.language else lang
    return {"method": "sendMessage", "chat_id": chat_id, "text": text.both(text.LINKED, user_lang)}


async def _telegram_block(session: AsyncSession, chat_id: Any) -> None:
    if not isinstance(chat_id, int):
        return
    h = address_hash("telegram", str(chat_id))
    for ch in (
        await session.execute(select(UserChannel).where(UserChannel.kind == "telegram", UserChannel.address_hash == h))
    ).scalars():
        ch.status, ch.last_error = "blocked", "the user stopped the bot"
    await session.flush()


async def telegram_poll(session: AsyncSession) -> int:
    """Long-poll mode: fetch pending bot updates once (no inbound webhook needed) and handle them."""
    from app.services.channels import transport

    cfg = await config.sender_for(session, "telegram")
    if cfg is None or cfg.options.get("update_mode") != "poll":
        return 0
    offset = int(cfg.options.get("poll_offset") or 0)
    data = await transport.telegram_api(
        cfg.secrets["bot_token"],
        "getUpdates",
        {"offset": offset, "timeout": 0, "allowed_updates": ["message", "my_chat_member"]},
    )
    updates = [u for u in data.get("result") or [] if isinstance(u, dict)] if data.get("ok") else []
    for u in updates:
        await telegram_update(session, u)
    ids = [int(u["update_id"]) for u in updates if isinstance(u.get("update_id"), int)]
    if ids:
        cfg.options["poll_offset"] = max(ids) + 1
        await config.save(session, cfg, None)
    return len(updates)


def channel_off(kind: str) -> ConfigError:
    return _err(
        "channel_off",
        f"{kind} is not switched on by an administrator (configuration and KVKK sign-off)",
        f"{kind} kanalı bir yönetici tarafından açılmadı (yapılandırma ve KVKK onayı)",
        409,
    )


# --------------------------------------------------------------------------------------------------
# SMS / WhatsApp
# --------------------------------------------------------------------------------------------------


def _code_hash(kind: str, user_id: int, code: str) -> str:
    return _hmac(f"phone-code:{kind}:{user_id}:{code}")


async def phone_link(session: AsyncSession, user: User, kind: str, phone: Any, consent: bool) -> dict[str, Any]:
    from app.services.bookings_notify import _language
    from app.services.channels import text

    if kind not in ("sms", "whatsapp"):
        raise _err("unknown_channel", f"{kind} is not verified by phone", f"{kind} telefonla doğrulanmaz", 404)
    sender = await config.sender_for(session, kind)
    if sender is None:
        raise channel_off(kind)
    try:
        e164 = normalize_phone(phone)
    except PhoneError as exc:
        raise _err(
            "phone_invalid",
            "a mobile number such as 0532 111 22 33 or +90 532 111 22 33",
            "0532 111 22 33 ya da +90 532 111 22 33 biçiminde bir cep telefonu numarası",
        ) from exc
    if kind == "whatsapp" and consent is not True:
        raise _err(
            "consent_required",
            "WhatsApp needs your explicit opt-in (consent: true) naming the institution",
            "WhatsApp için kurumu adlandıran açık onayınız gerekir (consent: true)",
        )
    now = utcnow()
    recent_q = (
        select(func.count())
        .select_from(ChannelLinkCode)
        .where(
            ChannelLinkCode.user_id == user.id,
            ChannelLinkCode.kind == kind,
            ChannelLinkCode.created_at > now - CODE_TTL,
        )
    )
    if int((await session.execute(recent_q)).scalar_one()) >= MAX_CODES_PER_WINDOW:
        raise _err(
            "too_many_codes", "too many codes; wait 10 minutes", "çok fazla kod istendi; 10 dakika bekleyin", 429
        )
    await session.execute(
        delete(ChannelLinkCode).where(
            (ChannelLinkCode.user_id == user.id) & (ChannelLinkCode.kind == kind) & ChannelLinkCode.used_at.is_(None)
        )
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    row = ChannelLinkCode(
        code_hash=_code_hash(kind, user.id, code + ":" + secrets.token_hex(4)),  # placeholder, unique; set below
        user_id=user.id,
        kind=kind,
        address_enc=encrypt_secret(e164),
        created_at=now,
        expires_at=now + CODE_TTL,
    )
    session.add(row)
    await session.flush()
    row.code_hash = _code_hash(kind, row.id, code)  # bound to the row: equal codes of two users never collide
    lang = await _language(session, user)
    await outbox.queue(
        session,
        kind=kind,
        event="channel.verify",
        dedupe_key=f"verify:{row.id}",
        payload={"event": "channel.verify", "lang": text.lang_of(lang), "code_enc": encrypt_secret(code)},
        user_id=user.id,
        link_code_id=row.id,
    )
    return {"display_hint": phone_hint(e164), "expires_at": (now + CODE_TTL).isoformat() + "Z", "sender": sender.kind}


def _clean_code(value: Any) -> str:
    text = n.clean_text(value) or ""
    out = []
    for ch in text:
        d = unicodedata.decimal(ch, None)
        if d is not None:
            out.append(str(d))
        elif ch not in " -.":
            return ""
    return "".join(out)


async def phone_verify(session: AsyncSession, user: User, kind: str, code: Any) -> UserChannel:
    q = (
        select(ChannelLinkCode)
        .where(ChannelLinkCode.user_id == user.id, ChannelLinkCode.kind == kind, ChannelLinkCode.used_at.is_(None))
        .order_by(ChannelLinkCode.id.desc())
    )
    row = (await session.execute(q)).scalars().first()
    expired = _err("code_expired", "the code expired; ask for a new one", "kodun süresi doldu; yeni kod isteyin")
    if row is None or row.expires_at < utcnow() or (row.attempts or 0) >= MAX_ATTEMPTS or not row.address_enc:
        raise expired
    if await config.sender_for(session, kind) is None:
        raise channel_off(kind)
    given = _clean_code(code)
    if len(given) != 6 or not hmac.compare_digest(_code_hash(kind, row.id, given), row.code_hash):
        row.attempts = (row.attempts or 0) + 1
        await session.commit()
        raise _err("code_invalid", "wrong code", "kod hatalı")
    row.used_at = utcnow()
    e164 = decrypt_secret(row.address_enc)
    # one verified number per user and channel: a new number replaces the old one
    for old in await user_channels(session, user.id, kind):
        if old.address_hash != address_hash(kind, e164):
            await session.execute(delete(ChannelDelivery).where(ChannelDelivery.user_channel_id == old.id))
            await session.delete(old)
    await session.flush()
    return await _store(session, user, kind, e164, phone_hint(e164))
