"""Administrator configuration of the notification channels (one row per kind in ``notify_channel_configs``).

A channel sends only when **all** of these hold (:attr:`ChannelConfig.missing` is empty):

* an administrator switched it on;
* the institution's sender credentials are complete (no demo or placeholder sender ships with the product);
* the KVKK officer's sign-off is recorded (who, user id, when, legal basis; :func:`kvkk_signed`, the same rule as
  calendar sync's ``calendar_sync_signoff``): every channel transfers data abroad (KVKK Art. 9 after Law 7499);
* WhatsApp Web bridge only: the administrator acknowledged the terms-of-service / ban risk, the operator set
  ``WHATSAPP_BRIDGE_URL`` and the bridge session is logged in (QR scanned once in Settings).

Secrets are Fernet-encrypted with APP_SECRET (:func:`app.core.security.encrypt_secret`, the helper calendar sync
uses for its client secrets) and leave this module only as ``{name: configured}`` flags.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, encrypt_secret
from app.importers import normalize as n
from app.models import NotifyChannelConfig, User
from app.models.base import utcnow
from app.services import audit
from app.services.bookings_settings import kvkk_signed

CONTENT_MODES = ("full", "link_only")
BRIDGE_ENV = "WHATSAPP_BRIDGE_URL"


class ConfigError(Exception):
    """A 422 (or 404 / 409) with a Turkish and an English message."""

    def __init__(self, code: str, message: str, message_tr: str, status: int = 422) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.message_tr = status, code, message, message_tr

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "message_tr": self.message_tr}


@dataclass(frozen=True)
class Kind:
    name: str
    label_tr: str
    label_en: str
    #: how a user connects it: webpush | telegram_deeplink | phone_code | department | sender (no own address)
    link: str
    secrets: tuple[str, ...] = ()  # administrator-entered secrets
    server_secrets: tuple[str, ...] = ()  # generated here (webhook secret, VAPID private key)
    options: tuple[str, ...] = ()  # administrator-entered, not secret
    server_options: tuple[str, ...] = ()  # set by SmartSched (VAPID public key, poll offset, bridge state)


KINDS: dict[str, Kind] = {
    k.name: k
    for k in (
        Kind(
            "webpush",
            "Tarayıcı / telefon bildirimi",
            "Browser / phone push",
            "webpush",
            server_secrets=("vapid_private_key",),
            options=("contact", "ttl_s"),
            server_options=("vapid_public_key",),
        ),
        Kind(
            "telegram",
            "Telegram",
            "Telegram",
            "telegram_deeplink",
            secrets=("bot_token",),
            server_secrets=("webhook_secret",),
            options=("bot_username", "update_mode"),
            server_options=("poll_offset",),
        ),
        Kind(
            "whatsapp",
            "WhatsApp (Business Cloud API)",
            "WhatsApp (Business Cloud API)",
            "phone_code",
            secrets=("access_token",),
            options=("phone_number_id", "template_notice", "template_code", "lang_tr", "lang_en"),
        ),
        Kind(
            "whatsapp_web",
            "WhatsApp (Web köprüsü, resmi değil)",
            "WhatsApp (Web bridge, unofficial)",
            "sender",
            secrets=("user_token",),
            server_options=("logged_in", "checked_at"),
        ),
        Kind(
            "sms",
            "SMS",
            "SMS",
            "phone_code",
            secrets=("account_sid", "auth_token", "api_key", "api_secret"),
            options=("provider", "from_number"),
        ),
        Kind("teams", "Microsoft Teams (bölüm kanalı)", "Microsoft Teams (department channel)", "department"),
        Kind("slack", "Slack (bölüm kanalı)", "Slack (department channel)", "department"),
    )
}
#: the address a user links -> the sender kinds that can deliver to it, in order of preference
SENDERS: dict[str, tuple[str, ...]] = {
    "webpush": ("webpush",),
    "telegram": ("telegram",),
    "whatsapp": ("whatsapp", "whatsapp_web"),  # the official Cloud API first; the bridge only if it is the one on
    "sms": ("sms",),
}
SMS_PROVIDERS: dict[str, tuple[str, str]] = {"twilio": ("account_sid", "auth_token"), "vonage": ("api_key", "api_secret")}

RISK_TR = (
    "WhatsApp Web köprüsü resmi olmayan WhatsApp Web (çoklu cihaz) protokolünü kullanır. Bu, WhatsApp kullanım "
    "koşullarına aykırıdır ve numara kalıcı olarak yasaklanabilir (ban). Yalnızca kuruma ait, bu işe ayrılmış bir "
    "numara kullanın; önerilen yol WhatsApp Business Cloud API'dir."
)
RISK_EN = (
    "The WhatsApp Web bridge uses the unofficial WhatsApp Web multi-device protocol. This violates WhatsApp's terms of "
    "service and the number can be banned permanently. Use a dedicated institution number only; the recommended path "
    "is the WhatsApp Business Cloud API."
)


def code_value(value: Any) -> str:
    """An ASCII code typed by a person (``LINK_ONLY``, ``Poll``): NBSP / whitespace dropped, Turkish dotted and
    dotless i folded to ``i`` before lower-casing (never ``tr_lower``: it would turn ``I`` into ``ı``)."""
    text = (n.clean_text(value) or "").replace("İ", "i").replace("ı", "i")
    return unicodedata.normalize("NFKC", text).lower().replace(" ", "")


@dataclass
class ChannelConfig:
    kind: str
    enabled_requested: bool = False
    content_mode: str = "link_only"
    secrets: dict[str, str] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    signoff: dict[str, Any] | None = None
    risk_ack: dict[str, Any] | None = None
    targets: int = 0  # department targets (teams / slack)
    updated_at: Any = None

    @property
    def spec(self) -> Kind:
        return KINDS[self.kind]

    def credential_gaps(self) -> list[str]:
        k, s, o = self.kind, self.secrets, self.options
        need: list[str] = []
        if k == "webpush":
            need = [x for x in ("vapid_private_key",) if not s.get(x)] + [x for x in ("contact",) if not o.get(x)]
        elif k == "telegram":
            need = [x for x in ("bot_token", "webhook_secret") if not s.get(x)]
            need += [x for x in ("bot_username",) if not o.get(x)]
        elif k == "whatsapp":
            need = [x for x in ("access_token",) if not s.get(x)]
            need += [x for x in ("phone_number_id", "template_notice", "template_code") if not o.get(x)]
        elif k == "whatsapp_web":
            need = [x for x in ("user_token",) if not s.get(x)]
            if not bridge_url():
                need.append(BRIDGE_ENV)
        elif k == "sms":
            provider = o.get("provider")
            if provider not in SMS_PROVIDERS:
                need.append("provider")
            else:
                need += [x for x in SMS_PROVIDERS[provider] if not s.get(x)]
            if not o.get("from_number"):
                need.append("from_number")
        elif k in ("teams", "slack") and self.targets == 0:
            need.append("department_targets")
        return need

    @property
    def configured(self) -> bool:
        return not self.credential_gaps()

    @property
    def missing(self) -> list[str]:
        out: list[str] = []
        if not self.enabled_requested:
            out.append("enabled")
        out += self.credential_gaps()
        if not kvkk_signed(self.signoff):
            out.append("kvkk_signoff")
        if self.kind == "whatsapp_web":
            if not _acknowledged(self.risk_ack):
                out.append("risk_ack")
            if not self.options.get("logged_in"):
                out.append("bridge_session")
        return out

    @property
    def effective(self) -> bool:
        return not self.missing


def _acknowledged(record: Any) -> bool:
    return isinstance(record, dict) and record.get("acknowledged") is True and isinstance(record.get("by_user_id"), int)


def bridge_url() -> str:
    """The WhatsApp Web bridge (wuzapi) inside the pod: operator configuration, never user input."""
    return (os.environ.get(BRIDGE_ENV) or "").strip().rstrip("/")


def _decrypt(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(decrypt_secret(raw))
    except (ValueError, TypeError):
        return {}  # APP_SECRET changed: the credentials read as missing, the channel as not configured
    return {str(k): str(v) for k, v in data.items() if v} if isinstance(data, dict) else {}


async def _row(session: AsyncSession, kind: str) -> NotifyChannelConfig | None:
    return await session.get(NotifyChannelConfig, kind)


async def _target_count(session: AsyncSession, kind: str) -> int:
    from sqlalchemy import func, select

    from app.models import ChannelDepartmentTarget

    q = select(func.count()).select_from(ChannelDepartmentTarget).where(ChannelDepartmentTarget.kind == kind)
    return int((await session.execute(q)).scalar_one())


async def load(session: AsyncSession, kind: str) -> ChannelConfig:
    if kind not in KINDS:
        raise ConfigError("unknown_channel", f"unknown channel {kind!r}", f"bilinmeyen kanal {kind!r}", status=404)
    row = await _row(session, kind)
    targets = await _target_count(session, kind) if kind in ("teams", "slack") else 0
    if row is None:
        return ChannelConfig(kind, targets=targets)
    return ChannelConfig(
        kind=kind,
        enabled_requested=bool(row.enabled),
        content_mode=row.content_mode if row.content_mode in CONTENT_MODES else "link_only",
        secrets=_decrypt(row.secrets_enc),
        options=dict(row.options or {}),
        signoff=row.kvkk_signoff,
        risk_ack=row.risk_ack,
        targets=targets,
        updated_at=row.updated_at,
    )


async def effective(session: AsyncSession, kind: str) -> ChannelConfig | None:
    cfg = await load(session, kind)
    return cfg if cfg.effective else None


async def sender_for(session: AsyncSession, address_kind: str) -> ChannelConfig | None:
    """The sender that delivers to a user's ``address_kind`` address now (None: nothing is on)."""
    for kind in SENDERS.get(address_kind, (address_kind,)):
        cfg = await effective(session, kind)
        if cfg is not None:
            return cfg
    return None


async def save(session: AsyncSession, cfg: ChannelConfig, actor: User | None) -> None:
    row = await _row(session, cfg.kind)
    if row is None:
        row = NotifyChannelConfig(kind=cfg.kind)
        session.add(row)
    row.enabled = cfg.enabled_requested
    row.content_mode = cfg.content_mode
    row.secrets_enc = encrypt_secret(json.dumps(cfg.secrets, sort_keys=True)) if cfg.secrets else None
    row.options = dict(cfg.options)
    row.kvkk_signoff = cfg.signoff
    row.risk_ack = cfg.risk_ack
    row.updated_by = actor.id if actor is not None else None
    row.updated_at = utcnow()
    await session.flush()


def public(cfg: ChannelConfig) -> dict[str, Any]:
    """What the admin API returns: flags for the secrets, never a value or a masked fragment."""
    spec = cfg.spec
    out: dict[str, Any] = {
        "kind": cfg.kind,
        "label_tr": spec.label_tr,
        "label_en": spec.label_en,
        "link": spec.link,
        "enabled": cfg.effective,
        "enabled_requested": cfg.enabled_requested,
        "configured": cfg.configured,
        "content_mode": cfg.content_mode,
        "options": {k: v for k, v in cfg.options.items() if k != "poll_offset"},
        "secrets": {k: bool(cfg.secrets.get(k)) for k in (*spec.secrets, *spec.server_secrets)},
        "kvkk_signoff": cfg.signoff,
        "missing": cfg.missing,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }
    if cfg.kind == "sms":
        provider = cfg.options.get("provider")
        names = SMS_PROVIDERS.get(str(provider), ("account_sid", "auth_token"))
        out["secrets"] = {k: bool(cfg.secrets.get(k)) for k in names}
    if cfg.kind in ("teams", "slack"):
        out["department_targets"] = cfg.targets
    if cfg.kind == "whatsapp_web":
        out.update(
            risk_ack=cfg.risk_ack,
            risk_tr=RISK_TR,
            risk_en=RISK_EN,
            bridge_url_configured=bool(bridge_url()),
        )
    return out


# --------------------------------------------------------------------------------------------------
# validation of administrator input
# --------------------------------------------------------------------------------------------------

_BOT_RX = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_TEMPLATE_RX = re.compile(r"^[a-z0-9_]{1,512}$")
_LANG_RX = re.compile(r"^[a-z]{2,3}(_[A-Z]{2})?$")
_EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _bad(name: str, en: str, tr: str) -> ConfigError:
    return ConfigError("invalid_option", f"{name}: {en}", f"{name}: {tr}")


def clean_option(kind: str, name: str, value: Any) -> Any:
    """One administrator-entered option, normalised (NBSP, whitespace, ``@`` prefixes), or ``ConfigError``."""
    from app.services.channels.links import PhoneError, normalize_phone

    text = n.clean_text(value) if not isinstance(value, bool | int) else value
    if text in (None, ""):
        return None
    if name == "bot_username":
        user = str(text).lstrip("@").replace(" ", "")
        if user.lower().startswith("https://t.me/"):
            user = user[len("https://t.me/") :]
        if not _BOT_RX.match(user) or not user.lower().endswith("bot"):
            raise _bad(name, "a Telegram bot user name ends with 'bot'", "Telegram bot kullanıcı adı 'bot' ile biter")
        return user
    if name == "update_mode":
        mode = code_value(text)
        if mode not in ("webhook", "poll"):
            raise _bad(name, "webhook or poll", "webhook ya da poll")
        return mode
    if name == "contact":
        c = str(text).replace(" ", "")
        if c.lower().startswith("mailto:"):
            c = c[7:]
        if c.lower().startswith("https://"):
            return c
        if not _EMAIL_RX.match(c):
            raise _bad(name, "an e-mail address or https URL of the operator", "işletmecinin e-posta ya da https adresi")
        return f"mailto:{c}"
    if name == "ttl_s":
        try:
            ttl = int(str(text))
        except ValueError as exc:
            raise _bad(name, "seconds (60..2419200)", "saniye (60..2419200)") from exc
        if not 60 <= ttl <= 2419200:
            raise _bad(name, "seconds (60..2419200)", "saniye (60..2419200)")
        return ttl
    if name == "phone_number_id":
        digits = str(text).replace(" ", "")
        if not digits.isascii() or not digits.isdigit() or not 5 <= len(digits) <= 32:
            raise _bad(name, "the numeric Phone number ID from Meta", "Meta'daki sayısal telefon numarası kimliği")
        return digits
    if name in ("template_notice", "template_code"):
        t = str(text).replace(" ", "")
        if not _TEMPLATE_RX.match(t):
            raise _bad(name, "an approved template name (a-z, 0-9, _)", "onaylı şablon adı (a-z, 0-9, _)")
        return t
    if name in ("lang_tr", "lang_en"):
        lang = str(text).replace(" ", "").replace("-", "_")
        if not _LANG_RX.match(lang):
            raise _bad(name, "a template language code such as tr or en_US", "tr ya da en_US gibi şablon dil kodu")
        return lang
    if name == "provider":
        p = code_value(text)
        if p not in SMS_PROVIDERS:
            raise _bad(name, f"one of {', '.join(SMS_PROVIDERS)}", f"şunlardan biri: {', '.join(SMS_PROVIDERS)}")
        return p
    if name == "from_number":
        try:
            return normalize_phone(text)
        except PhoneError as exc:
            raise _bad(name, "the sender number (E.164)", "gönderen numara (E.164)") from exc
    raise _bad(name, "unknown option", "bilinmeyen seçenek")


def clean_secret(name: str, value: Any) -> str | None:
    """A pasted credential: surrounding whitespace / NBSP dropped; inner whitespace or control characters refused."""
    if value is None:
        return None
    text = str(value).replace("\xa0", " ").strip()
    if not text:
        return None
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in text) or len(text) > 4096:
        raise ConfigError(
            "invalid_secret",
            f"{name}: contains spaces or control characters; paste it again",
            f"{name}: boşluk ya da kontrol karakteri içeriyor; yeniden yapıştırın",
        )
    return text


async def update(session: AsyncSession, kind: str, body: dict[str, Any], admin: User) -> ChannelConfig:
    """Apply the administrator's change; records ``channels.config`` (and ``channels.kvkk_signoff``) in the audit
    log without any secret value."""
    cfg = await load(session, kind)
    spec = cfg.spec
    before = public(cfg)
    if "enabled" in body and body["enabled"] is not None:
        cfg.enabled_requested = bool(body["enabled"])
    if body.get("content_mode") is not None:
        mode = code_value(body["content_mode"])
        if mode not in CONTENT_MODES:
            raise ConfigError(
                "content_mode",
                f"content_mode must be one of {', '.join(CONTENT_MODES)}",
                f"içerik modu şunlardan biri olmalı: {', '.join(CONTENT_MODES)}",
            )
        cfg.content_mode = mode
    for name, value in (body.get("options") or {}).items():
        if name not in spec.options:
            raise _bad(name, f"not an option of {kind}", f"{kind} kanalının seçeneği değil")
        cleaned = clean_option(kind, name, value)
        if cleaned is None:
            cfg.options.pop(name, None)
        else:
            cfg.options[name] = cleaned
    secrets_in = body.get("secrets") or {}
    for name, value in secrets_in.items():
        if name not in spec.secrets:
            raise ConfigError(
                "invalid_secret", f"{name}: not a credential of {kind}", f"{name}: {kind} kanalının kimlik bilgisi değil"
            )
        cleaned_secret = clean_secret(name, value)
        if cleaned_secret is None:
            cfg.secrets.pop(name, None)
        else:
            cfg.secrets[name] = cleaned_secret
    if kind == "telegram":
        if "bot_token" in secrets_in:
            cfg.options.pop("poll_offset", None)
        if cfg.secrets.get("bot_token") and not cfg.secrets.get("webhook_secret"):
            cfg.secrets["webhook_secret"] = secrets.token_urlsafe(32)  # X-Telegram-Bot-Api-Secret-Token
        if not cfg.secrets.get("bot_token"):
            cfg.secrets.pop("webhook_secret", None)
    if kind == "whatsapp_web" and "user_token" in secrets_in:
        cfg.options.pop("logged_in", None)
    now = utcnow().isoformat(timespec="seconds") + "Z"
    sign = body.get("kvkk_signoff")
    if sign is not None:
        if not isinstance(sign, dict):
            raise ConfigError("kvkk_signoff", "kvkk_signoff must be an object", "kvkk_signoff bir nesne olmalı")
        if sign.get("signed") is True:
            basis = n.clean_text(sign.get("legal_basis"))
            officer = n.clean_text(sign.get("officer"))
            if not basis:
                raise ConfigError(
                    "legal_basis_required",
                    "a KVKK sign-off needs its legal basis (e.g. the standard contract notified to the Board)",
                    "KVKK onayı için hukuki dayanak gerekir (ör. Kurula bildirilen standart sözleşme)",
                )
            cfg.signoff = {
                "enabled": True,
                "signed": True,
                "channel": kind,
                "by": audit.user_label(admin),
                "by_user_id": admin.id,
                "at": now,
                "legal_basis": basis[:500],
                "officer": (officer or audit.user_label(admin) or "")[:200],
            }
        else:
            cfg.signoff = {
                "enabled": False,
                "signed": False,
                "channel": kind,
                "by": audit.user_label(admin),
                "by_user_id": admin.id,
                "at": now,
            }
        await audit.record(
            session,
            "channels.kvkk_signoff",
            "notify_channel",
            kind,
            before={"signed": kvkk_signed(before["kvkk_signoff"])},
            after={"signed": kvkk_signed(cfg.signoff), "legal_basis": (cfg.signoff or {}).get("legal_basis")},
            actor=admin,
        )
    if body.get("risk_ack") is not None:
        if kind != "whatsapp_web":
            raise ConfigError("risk_ack", "only the WhatsApp Web bridge needs a risk acknowledgement", "yalnızca WhatsApp Web köprüsü")
        cfg.risk_ack = (
            {"acknowledged": True, "by": audit.user_label(admin), "by_user_id": admin.id, "at": now, "text_en": RISK_EN}
            if body["risk_ack"] is True
            else None
        )
    await save(session, cfg, admin)
    after = public(cfg)
    await audit.record(
        session,
        "channels.config",
        "notify_channel",
        kind,
        before={k: before[k] for k in ("enabled", "enabled_requested", "content_mode", "secrets", "options")},
        after={k: after[k] for k in ("enabled", "enabled_requested", "content_mode", "secrets", "options")},
        actor=admin,
    )
    return cfg


# --------------------------------------------------------------------------------------------------
# VAPID (Web Push): generated on the server once
# --------------------------------------------------------------------------------------------------


def _generate_vapid() -> tuple[str, str]:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from py_vapid import Vapid02, b64urlencode

    v = Vapid02()
    v.generate_keys()
    pem = v.private_pem().decode("ascii")
    public_key = b64urlencode(v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))
    return pem, str(public_key)


async def ensure_vapid(session: AsyncSession, admin: User, rotate: bool = False) -> tuple[ChannelConfig, bool]:
    """The VAPID key pair (P-256): created once; ``rotate`` makes a new pair and removes every browser subscription
    (they are bound to the old public key). Returns (config, created)."""
    cfg = await load(session, "webpush")
    if cfg.secrets.get("vapid_private_key") and cfg.options.get("vapid_public_key") and not rotate:
        return cfg, False
    pem, public_key = _generate_vapid()
    cfg.secrets["vapid_private_key"] = pem
    cfg.options["vapid_public_key"] = public_key
    if rotate:
        from sqlalchemy import delete

        from app.models import UserChannel

        await session.execute(delete(UserChannel).where(UserChannel.kind == "webpush"))
    await save(session, cfg, admin)
    await audit.record(
        session,
        "channels.vapid",
        "notify_channel",
        "webpush",
        after={"vapid_public_key": public_key, "rotated": rotate},
        actor=admin,
    )
    return cfg, True
