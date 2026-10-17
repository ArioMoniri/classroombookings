"""Integrations gallery status (wave 3b W3-HUB, ``/admin/integrations``; docs/design/v3/integrations.md).

``GET /integrations/status`` (``setup.settings`` or ``planning.admin``): one read-only answer for the gallery, the
connector cards of six areas (Kimlik, E-posta, Takvim, Kanallar, Webhook ve otomasyon, Yapay zekâ). Every setting
it reports is organisation-wide (database rows shared by every administrator), so each admin sees the same cards.

How an area is read (never through another lane's private helpers):

1. **Contract** — the area module exposes ``async def integration_status(session) -> list[dict]`` (see
   :class:`CardIn` for the fields; :data:`CONTRACTS` names the modules probed). Its answer wins.
2. **Built-in reader** — for the areas that existed before wave 3b (calendar push, notification channels,
   webhooks, the AI gateway) this module reads their *public* functions and models.
3. Otherwise the area answers one ``unknown`` card and the response lists the missing function in ``asks``.

A reader that raises becomes one ``unknown`` card for its area (logged here, the exception text never reaches the
answer: it may carry a credential). Answers never include a secret or a masked fragment of one. The endpoint does
not write (no settings, no audit rows): the switches on the cards call the owning area's own endpoint, named in
``toggle`` (``{method, path, field, enable_in_setup}``; ``enable_in_setup`` = switching on needs the guided setup,
e.g. a KVKK sign-off).
"""

from __future__ import annotations

import importlib
import logging
import re
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, require_permission
from app.models import AuditEvent, CalendarConnection, CalendarSyncJob, User, WebhookDelivery, WebhookEndpoint
from app.models.base import utcnow
from app.models.channels import ChannelDelivery

log = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])
HUB_PERMS = ("setup.settings", "planning.admin")
HubAdmin = Annotated[User, Depends(require_permission(*HUB_PERMS))]

Status = Literal["connected", "not_configured", "error", "disabled", "unknown"]
STATUSES: tuple[str, ...] = ("connected", "not_configured", "error", "disabled", "unknown")
Reader = Callable[[AsyncSession], Awaitable[list[dict[str, Any]]]]

#: (key, label_tr, label_en, tab of /admin/integrations)
AREAS: tuple[tuple[str, str, str], ...] = (
    ("identity", "Kimlik", "Identity"),
    ("email", "E-posta", "E-mail"),
    ("calendar", "Takvim", "Calendar"),
    ("channels", "Kanallar", "Channels"),
    ("automation", "Webhook ve otomasyon", "Webhooks and automation"),
    ("ai", "Yapay zekâ", "AI"),
)
#: modules that may expose ``integration_status(session)``, first found wins, and the lane asked for it
CONTRACTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "identity": ("W3-IDP", ("app.services.identity",)),
    "email": ("W3-MAIL", ("app.emails", "app.services.mail_status")),
    "calendar": ("calendar owners", ("app.services.calendar_connectors",)),
    "channels": ("channel owners", ("app.services.channels",)),
    "automation": ("webhook owners", ("app.services.webhooks",)),
    "ai": ("W3-AI", ("app.ai.gateway",)),
}
CONTRACT_FN = "integration_status"
#: the placeholder card of an area nobody reports yet
PLACEHOLDER: dict[str, tuple[str, str, str, str, str]] = {
    "identity": (
        "identity.providers",
        "Kimlik sağlayıcıları",
        "Identity providers",
        "Microsoft, Google, OIDC, SAML ya da LDAP ile oturum açmayı ve davetleri yönetir.",
        "Manages sign-in and invitations with Microsoft, Google, OIDC, SAML or LDAP.",
    ),
    "email": (
        "email.smtp",
        "E-posta (SMTP)",
        "E-mail (SMTP)",
        "Parola sıfırlama, davet ve rezervasyon e-postalarını kurumun SMTP sunucusuyla gönderir.",
        "Sends password-reset, invitation and booking e-mails through the institution's SMTP server.",
    ),
    "calendar": (
        "calendar.push",
        "Takvim eşitleme",
        "Calendar sync",
        "Rezervasyonları Google Takvim ve Microsoft 365 takvimlerine gönderir.",
        "Pushes bookings to Google Calendar and Microsoft 365 calendars.",
    ),
    "channels": (
        "channels.all",
        "Bildirim kanalları",
        "Notification channels",
        "Bildirimleri Telegram, WhatsApp, SMS, Teams ve Slack üzerinden iletir.",
        "Delivers notifications through Telegram, WhatsApp, SMS, Teams and Slack.",
    ),
    "automation": (
        "automation.webhooks",
        "Webhook gönderimi",
        "Outgoing webhooks",
        "Rezervasyon ve onay olaylarını imzalı webhook olarak dış sistemlere gönderir.",
        "Sends booking and approval events to other systems as signed webhooks.",
    ),
    "ai": (
        "ai.providers",
        "Yapay zekâ sağlayıcıları",
        "AI providers",
        "Planlama yardımcısının kullandığı yapay zekâ sağlayıcılarını ve anahtarlarını yönetir.",
        "Manages the AI providers and keys the planning assistant uses.",
    ),
}
UNKNOWN_TR = "Bu alanın durumu şu an okunamıyor; ayarları yine de açıp düzenleyebilirsiniz."
UNKNOWN_EN = "The status of this area cannot be read right now; you can still open and edit its settings."
_API_PATH = re.compile(r"^/[A-Za-z0-9_./{}-]{1,200}$")
_HREF = re.compile(r"^/(?!/)[A-Za-z0-9_./?=&%-]{0,300}$")


def _iso(v: datetime | str | None) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    text = v.isoformat(timespec="seconds")
    return text if v.tzinfo else text + "Z"


def _tab_href(area: str, card: str | None = None) -> str:
    return f"/admin/integrations?tab={area}" + (f"&setup={card}" if card else "")


# --------------------------------------------------------------------------------------------------- schema


class Toggle(BaseModel):
    """The owning area's endpoint that switches the connector (relative to /api/v1; body ``{field: bool}``)."""

    method: Literal["PUT", "PATCH", "POST"] = "PUT"
    path: str
    field: str = Field(default="enabled", pattern=r"^[a-z_]{1,64}$")
    enable_in_setup: bool = False

    @field_validator("path")
    @classmethod
    def _relative(cls, v: str) -> str:
        if not _API_PATH.match(v) or ".." in v:
            raise ValueError("toggle path must be a relative API path")
        return v


class CardIn(BaseModel):
    """What an area's ``integration_status`` returns per connector (unknown fields are dropped)."""

    key: str = Field(pattern=r"^[a-z0-9_.-]{1,64}$")
    name_tr: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)
    summary_tr: str | None = Field(default=None, max_length=300)
    summary_en: str | None = Field(default=None, max_length=300)
    status: str = "unknown"
    enabled: bool | None = None
    detail_tr: str | None = Field(default=None, max_length=500)
    detail_en: str | None = Field(default=None, max_length=500)
    last_check_at: str | None = None
    last_check_ok: bool | None = None
    changed_by: str | None = Field(default=None, max_length=255)
    changed_at: str | None = None
    setup_href: str | None = None
    toggle: dict[str, Any] | None = None
    ref: dict[str, int | str] | None = None


class CardOut(BaseModel):
    key: str
    area: str
    name_tr: str
    name_en: str
    summary_tr: str
    summary_en: str
    status: Status
    enabled: bool | None = None
    detail_tr: str | None = None
    detail_en: str | None = None
    last_check_at: str | None = None
    last_check_ok: bool | None = None
    changed_by: str | None = None
    changed_at: str | None = None
    setup_href: str
    toggle: Toggle | None = None
    ref: dict[str, int | str] | None = None
    source: Literal["contract", "builtin", "missing"]


class AreaOut(BaseModel):
    key: str
    label_tr: str
    label_en: str
    cards: list[CardOut]


class AskOut(BaseModel):
    area: str
    lane: str
    function: str


class StatusOut(BaseModel):
    generated_at: str
    areas: list[AreaOut]
    counts: dict[str, int]
    asks: list[AskOut]


def _normalise(area: str, raw: dict[str, Any], source: Literal["contract", "builtin"]) -> CardOut:
    card = CardIn.model_validate(raw)
    toggle: Toggle | None = None
    if card.toggle is not None:
        try:
            toggle = Toggle.model_validate(card.toggle)
        except ValidationError:
            toggle = None
    href = card.setup_href if card.setup_href and _HREF.match(card.setup_href) else _tab_href(area)
    ph = PLACEHOLDER[area]
    return CardOut(
        key=card.key,
        area=area,
        name_tr=card.name_tr,
        name_en=card.name_en,
        summary_tr=card.summary_tr or ph[3],
        summary_en=card.summary_en or ph[4],
        status=card.status if card.status in STATUSES else "unknown",
        enabled=card.enabled,
        detail_tr=card.detail_tr,
        detail_en=card.detail_en,
        last_check_at=card.last_check_at,
        last_check_ok=card.last_check_ok,
        changed_by=card.changed_by,
        changed_at=card.changed_at,
        setup_href=href,
        toggle=toggle,
        ref=card.ref,
        source=source,
    )


def _unknown(area: str, source: Literal["contract", "builtin", "missing"]) -> CardOut:
    key, name_tr, name_en, summary_tr, summary_en = PLACEHOLDER[area]
    return CardOut(
        key=key,
        area=area,
        name_tr=name_tr,
        name_en=name_en,
        summary_tr=summary_tr,
        summary_en=summary_en,
        status="unknown",
        detail_tr=UNKNOWN_TR,
        detail_en=UNKNOWN_EN,
        setup_href=_tab_href(area),
        source=source,
    )


# --------------------------------------------------------------------------------------------------- helpers


async def _last_change(session: AsyncSession, *conds: Any) -> tuple[str | None, str | None]:
    """(who, when) of the newest audit event matching any of ``conds`` (the audit log is the shared history)."""
    if not conds:
        return None, None
    q = (
        select(AuditEvent.actor_label, AuditEvent.ts)
        .where(or_(*conds))
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    row = (await session.execute(q)).first()
    return (row[0], _iso(row[1])) if row else (None, None)


def _settings_keys(*keys: str) -> Any:
    return and_(AuditEvent.entity_type == "settings", AuditEvent.entity_id.in_(keys))


def _changed(card: dict[str, Any], who_when: tuple[str | None, str | None]) -> dict[str, Any]:
    card["changed_by"], card["changed_at"] = who_when
    return card


# --------------------------------------------------------------------------------------------------- calendar


CAL_TEXT = {
    "google": (
        "Google Takvim",
        "Google Calendar",
        "Rezervasyonları kullanıcıların Google Takvim'ine gönderir.",
        "Pushes bookings to users' Google Calendar.",
    ),
    "microsoft": (
        "Microsoft 365 takvimi",
        "Microsoft 365 calendar",
        "Rezervasyonları kullanıcıların Outlook / Microsoft 365 takvimine gönderir.",
        "Pushes bookings to users' Outlook / Microsoft 365 calendar.",
    ),
}


async def calendar_cards(session: AsyncSession) -> list[dict[str, Any]]:
    from app.services import calendar_connectors as conn_svc
    from app.services.bookings_settings import get_group

    g = await get_group(session, "integrations")
    sync_on = bool(g["calendar_sync_enabled"])
    signoff_change = await _last_change(session, AuditEvent.action == "integrations.calendar_sync")
    out: list[dict[str, Any]] = []
    for name, provider in conn_svc.PROVIDERS.items():
        texts = CAL_TEXT.get(name, (name, name, PLACEHOLDER["calendar"][3], PLACEHOLDER["calendar"][4]))
        configured = await conn_svc.client_config(session, provider) is not None
        users = int(
            (
                await session.execute(
                    select(func.count()).select_from(CalendarConnection).where(CalendarConnection.provider == name)
                )
            ).scalar_one()
        )
        broken = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(CalendarConnection)
                    .where(CalendarConnection.provider == name, CalendarConnection.status != "ACTIVE")
                )
            ).scalar_one()
        )
        last = (
            await session.execute(
                select(CalendarSyncJob.status, CalendarSyncJob.done_at, CalendarSyncJob.created_at)
                .join(CalendarConnection, CalendarConnection.id == CalendarSyncJob.connection_id)
                .where(CalendarConnection.provider == name, CalendarSyncJob.status.in_(("DONE", "FAILED")))
                .order_by(CalendarSyncJob.id.desc())
                .limit(1)
            )
        ).first()
        if not configured:
            status, detail = (
                "not_configured",
                (
                    "OAuth istemci kimliği, gizli anahtarı ya da genel adres eksik.",
                    "The OAuth client id, secret or public address is missing.",
                ),
            )
        elif not sync_on:
            status, detail = (
                "disabled",
                (
                    "Takvim eşitleme kapalı (iki sağlayıcı için ortak anahtar).",
                    "Calendar sync is off (one switch for both providers).",
                ),
            )
        elif broken or (last is not None and last[0] == "FAILED"):
            status, detail = (
                "error",
                (
                    f"{broken} bağlantı yeniden yetki bekliyor ya da son gönderim başarısız oldu.",
                    f"{broken} connection(s) need re-authorisation or the last push failed.",
                ),
            )
        else:
            status, detail = (
                "connected",
                (f"{users} kullanıcı takvimini bağladı.", f"{users} user(s) connected a calendar."),
            )
        keys = [f"integrations.{name}_client_id", f"integrations.{name}_client_secret", "integrations.public_url"]
        if name == "microsoft":
            keys.append("integrations.microsoft_tenant")
        own = await _last_change(session, _settings_keys(*keys))
        who_when = max((own, signoff_change), key=lambda x: x[1] or "")
        out.append(
            _changed(
                {
                    "key": f"calendar.{name}",
                    "name_tr": texts[0],
                    "name_en": texts[1],
                    "summary_tr": texts[2],
                    "summary_en": texts[3],
                    "status": status,
                    "enabled": sync_on if configured else None,
                    "detail_tr": detail[0],
                    "detail_en": detail[1],
                    "last_check_at": _iso(last[1] or last[2]) if last else None,
                    "last_check_ok": (last[0] == "DONE") if last else None,
                    "setup_href": _tab_href("calendar", f"calendar.{name}"),
                    "toggle": {
                        "method": "PUT",
                        "path": "/calendar/admin/settings",
                        "field": "calendar_sync_enabled",
                        "enable_in_setup": True,
                    }
                    if configured
                    else None,
                },
                who_when,
            )
        )
    return out


# --------------------------------------------------------------------------------------------------- channels


CHANNEL_SUMMARY: dict[str, tuple[str, str]] = {
    "webpush": (
        "Bildirimleri tarayıcıya ve telefona anlık bildirim olarak gönderir.",
        "Sends notifications to browsers and phones as push messages.",
    ),
    "telegram": (
        "Kullanıcılar bağladığında bildirimleri Telegram botuyla iletir.",
        "Delivers notifications through a Telegram bot once users link it.",
    ),
    "whatsapp": (
        "Bildirimleri WhatsApp Business Cloud API ile onaylı şablonlarla gönderir.",
        "Sends notifications with approved templates through the WhatsApp Business Cloud API.",
    ),
    "whatsapp_web": (
        "Bildirimleri resmi olmayan WhatsApp Web köprüsüyle gönderir.",
        "Sends notifications through the unofficial WhatsApp Web bridge.",
    ),
    "sms": (
        "Doğrulama kodlarını ve kısa bildirimleri SMS ile gönderir.",
        "Sends verification codes and short notices by SMS.",
    ),
    "teams": (
        "Bölüm duyurularını Microsoft Teams kanallarına gönderir.",
        "Posts department notices to Microsoft Teams channels.",
    ),
    "slack": ("Bölüm duyurularını Slack kanallarına gönderir.", "Posts department notices to Slack channels."),
}
MISSING_TR = {
    "enabled": "kanal kapalı",
    "kvkk_signoff": "KVKK onayı yok",
    "risk_ack": "risk onayı yok",
    "bridge_session": "köprü oturumu açık değil",
    "department_targets": "bölüm kanalı eşlenmedi",
}
MISSING_EN = {
    "enabled": "the channel is off",
    "kvkk_signoff": "no KVKK sign-off",
    "risk_ack": "no risk acknowledgement",
    "bridge_session": "the bridge session is not open",
    "department_targets": "no department channel mapped",
}


async def channel_cards(session: AsyncSession) -> list[dict[str, Any]]:
    from app.services.channels import config as channels

    out: list[dict[str, Any]] = []
    for kind, spec in channels.KINDS.items():
        cfg = await channels.load(session, kind)
        last = (
            await session.execute(
                select(ChannelDelivery.status, ChannelDelivery.sent_at, ChannelDelivery.created_at)
                .where(ChannelDelivery.kind == kind, ChannelDelivery.status.in_(("SENT", "FAILED")))
                .order_by(ChannelDelivery.id.desc())
                .limit(1)
            )
        ).first()
        missing = cfg.missing
        if not cfg.configured:
            status = "not_configured"
        elif cfg.effective:
            status = "error" if last is not None and last[0] == "FAILED" else "connected"
        else:
            status = "disabled"
        gaps = [m for m in missing if m != "enabled"] if status != "not_configured" else missing
        detail: tuple[str | None, str | None]
        if status == "error":
            detail = ("Son gönderim başarısız oldu.", "The last delivery failed.")
        elif gaps:
            detail = (
                "Eksik: " + ", ".join(MISSING_TR.get(m, m) for m in gaps) + ".",
                "Missing: " + ", ".join(MISSING_EN.get(m, m) for m in gaps) + ".",
            )
        else:
            detail = (None, None)
        summary = CHANNEL_SUMMARY.get(kind, (PLACEHOLDER["channels"][3], PLACEHOLDER["channels"][4]))
        change = await _last_change(
            session, and_(AuditEvent.entity_type == "notify_channel", AuditEvent.entity_id == kind)
        )
        out.append(
            _changed(
                {
                    "key": f"channels.{kind}",
                    "name_tr": spec.label_tr,
                    "name_en": spec.label_en,
                    "summary_tr": summary[0],
                    "summary_en": summary[1],
                    "status": status,
                    "enabled": cfg.enabled_requested if cfg.configured else None,
                    "detail_tr": detail[0],
                    "detail_en": detail[1],
                    "last_check_at": _iso(last[1] or last[2]) if last else None,
                    "last_check_ok": (last[0] == "SENT") if last else None,
                    "setup_href": _tab_href("channels", f"channels.{kind}"),
                    "toggle": {
                        "method": "PUT",
                        "path": f"/channels/admin/{kind}",
                        "field": "enabled",
                        "enable_in_setup": True,
                    }
                    if cfg.configured
                    else None,
                },
                change,
            )
        )
    return out


# --------------------------------------------------------------------------------------------------- automation

#: (id, name, summary_tr, summary_en, host / path test)
PLATFORMS: tuple[tuple[str, str, str, str, Callable[[str, str], bool]], ...] = (
    (
        "n8n",
        "n8n",
        "Rezervasyon olaylarını n8n iş akışındaki Webhook düğümüne gönderir.",
        "Sends booking events to the Webhook node of an n8n workflow.",
        lambda host, path: "n8n" in host or path.startswith(("/webhook/", "/webhook-test/")),
    ),
    (
        "activepieces",
        "Activepieces",
        "Rezervasyon olaylarını bir Activepieces akışının webhook tetikleyicisine gönderir.",
        "Sends booking events to the webhook trigger of an Activepieces flow.",
        lambda host, path: "activepieces" in host,
    ),
    (
        "pipedream",
        "Pipedream",
        "Rezervasyon olaylarını bir Pipedream iş akışının HTTP tetikleyicisine gönderir.",
        "Sends booking events to the HTTP trigger of a Pipedream workflow.",
        lambda host, path: host.endswith("pipedream.net") or host.endswith("pipedream.com"),
    ),
    (
        "zapier",
        "Zapier",
        "Rezervasyon olaylarını Zapier'deki “Webhooks by Zapier” tetikleyicisine gönderir.",
        "Sends booking events to the “Webhooks by Zapier” trigger.",
        lambda host, path: host.endswith("zapier.com"),
    ),
)


def platform_of(url: str, description: str | None) -> str | None:
    """Which automation platform an endpoint points at (its host, or the guided setup's description prefix)."""
    desc = (description or "").strip().lower()
    for pid, *_ in PLATFORMS:
        if desc.startswith(pid):
            return pid
    parts = urlsplit(url)
    host, path = (parts.hostname or "").lower(), parts.path or ""
    for pid, _name, _tr, _en, test in PLATFORMS:
        if test(host, path):
            return pid
    return None


async def _last_delivery(session: AsyncSession, endpoint_ids: Iterable[int]) -> Any:
    ids = list(endpoint_ids)
    if not ids:
        return None
    return (
        await session.execute(
            select(WebhookDelivery.status, WebhookDelivery.delivered_at, WebhookDelivery.created_at)
            .where(WebhookDelivery.endpoint_id.in_(ids), WebhookDelivery.status.in_(("SENT", "FAILED")))
            .order_by(WebhookDelivery.id.desc())
            .limit(1)
        )
    ).first()


async def automation_cards(session: AsyncSession) -> list[dict[str, Any]]:
    from app.services import webhooks as hooks

    global_on = await hooks.enabled(session)
    endpoints = list((await session.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.id))).scalars())
    active = [e for e in endpoints if e.active]
    last = await _last_delivery(session, (e.id for e in endpoints))
    auto_off = [e for e in endpoints if not e.active and e.disabled_reason]
    if not endpoints:
        status = "not_configured"
        detail = ("Henüz webhook adresi yok.", "No webhook address yet.")
    elif not global_on or not active:
        status = "disabled"
        detail = ("Webhook gönderimi kapalı.", "Webhook delivery is off.")
    elif auto_off or (last is not None and last[0] == "FAILED"):
        status = "error"
        detail = (
            "Bir adres art arda hatalar yüzünden kapandı ya da son gönderim başarısız oldu.",
            "An address was switched off after repeated failures or the last delivery failed.",
        )
    else:
        status = "connected"
        detail = (f"{len(active)} etkin adres.", f"{len(active)} active address(es).")
    ph = PLACEHOLDER["automation"]
    out: list[dict[str, Any]] = [
        _changed(
            {
                "key": ph[0],
                "name_tr": ph[1],
                "name_en": ph[2],
                "summary_tr": ph[3],
                "summary_en": ph[4],
                "status": status,
                "enabled": global_on if endpoints else None,
                "detail_tr": detail[0],
                "detail_en": detail[1],
                "last_check_at": _iso(last[1] or last[2]) if last else None,
                "last_check_ok": (last[0] == "SENT") if last else None,
                "setup_href": _tab_href("automation", ph[0]),
                "toggle": {"method": "PUT", "path": "/calendar/admin/settings", "field": "webhooks_enabled"}
                if endpoints
                else None,
            },
            await _last_change(
                session, AuditEvent.entity_type == "webhook", _settings_keys("integrations.webhooks_enabled")
            ),
        )
    ]
    for pid, name, summary_tr, summary_en, _test in PLATFORMS:
        mine = [e for e in endpoints if platform_of(e.url, e.description) == pid]
        e = next((x for x in mine if x.active), mine[0] if mine else None)
        card: dict[str, Any] = {
            "key": f"automation.{pid}",
            "name_tr": name,
            "name_en": name,
            "summary_tr": summary_tr,
            "summary_en": summary_en,
            "setup_href": _tab_href("automation", f"automation.{pid}"),
        }
        if e is None:
            card.update(status="not_configured", toggle=None)
            out.append(card)
            continue
        own = await _last_delivery(session, [e.id])
        dt: tuple[str | None, str | None]
        if not e.active:
            st, dt = (
                "disabled",
                (
                    ("Art arda hatalar yüzünden kapandı.", "Switched off after repeated failures.")
                    if e.disabled_reason
                    else ("Bu adres kapalı.", "This address is off.")
                ),
            )
        elif not global_on:
            st, dt = "disabled", ("Webhook gönderimi kapalı.", "Webhook delivery is off.")
        elif own is not None and own[0] == "FAILED":
            st, dt = "error", ("Son gönderim başarısız oldu.", "The last delivery failed.")
        else:
            st, dt = "connected", (None, None)
        card.update(
            status=st,
            enabled=bool(e.active),
            detail_tr=dt[0],
            detail_en=dt[1],
            last_check_at=_iso(own[1] or own[2]) if own else None,
            last_check_ok=(own[0] == "SENT") if own else None,
            toggle={"method": "PUT", "path": f"/webhooks/{e.id}", "field": "active"},
            ref={"webhook_id": e.id},
        )
        out.append(
            _changed(
                card,
                await _last_change(
                    session, and_(AuditEvent.entity_type == "webhook", AuditEvent.entity_id == str(e.id))
                ),
            )
        )
    return out


# --------------------------------------------------------------------------------------------------- AI


async def ai_cards(session: AsyncSession) -> list[dict[str, Any]]:
    from app.ai import gateway as gw
    from app.ai.providers import PROVIDERS

    usable: list[str] = []
    tests: list[dict[str, Any]] = []
    for pid, spec in PROVIDERS.items():
        if await gw.provider_usable(session, pid):
            usable.append(spec.label_tr)
            t = await gw.get_json(session, f"ai.provider.{pid}.test", {})
            if isinstance(t, dict) and t.get("at"):
                tests.append(t)
    latest = max(tests, key=lambda t: str(t["at"])) if tests else None
    if not usable:
        status, detail = "not_configured", ("Kullanılabilir sağlayıcı yok.", "No usable provider.")
    elif latest is not None and latest.get("ok") is False:
        status, detail = "error", ("Son bağlantı denemesi başarısız oldu.", "The last connection test failed.")
    else:
        status, detail = (
            "connected",
            ("Kullanılabilir: " + ", ".join(usable) + ".", f"{len(usable)} usable provider(s)."),
        )
    ph = PLACEHOLDER["ai"]
    return [
        _changed(
            {
                "key": ph[0],
                "name_tr": ph[1],
                "name_en": ph[2],
                "summary_tr": ph[3],
                "summary_en": ph[4],
                "status": status,
                "detail_tr": detail[0],
                "detail_en": detail[1],
                "last_check_at": str(latest["at"]) if latest else None,
                "last_check_ok": bool(latest.get("ok")) if latest else None,
                "setup_href": "/admin/ai",
                "toggle": None,
            },
            await _last_change(session, AuditEvent.action.like("ai.%"), _settings_keys("anthropic_api_key")),
        )
    ]


BUILTINS: dict[str, Reader] = {
    "calendar": calendar_cards,
    "channels": channel_cards,
    "automation": automation_cards,
    "ai": ai_cards,
}


# --------------------------------------------------------------------------------------------------- aggregation


def contract_for(area: str) -> Reader | None:
    """The area's own ``integration_status`` when its module exposes one (only that public name is used)."""
    for module in CONTRACTS[area][1]:
        try:
            mod = importlib.import_module(module)
        except ModuleNotFoundError:
            continue
        fn = getattr(mod, CONTRACT_FN, None)
        if callable(fn):
            return fn  # type: ignore[no-any-return]
    return None


async def _read(session: AsyncSession, area: str) -> tuple[list[CardOut], AskOut | None]:
    reader = contract_for(area)
    source: Literal["contract", "builtin"] = "contract"
    if reader is None:
        builtin = BUILTINS.get(area)
        if builtin is None:
            lane, modules = CONTRACTS[area]
            return [_unknown(area, "missing")], AskOut(
                area=area, lane=lane, function=f"{modules[0]}.{CONTRACT_FN}(session) -> list[dict]"
            )
        reader, source = builtin, "builtin"
    try:
        raw = await reader(session)
    except Exception:  # noqa: BLE001  one area must not take the gallery down; the text may hold a credential
        log.exception("integrations: the %s status reader failed", area)
        await session.rollback()
        return [_unknown(area, source)], None
    cards: list[CardOut] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            cards.append(_normalise(area, item, source))
        except ValidationError:
            log.warning("integrations: dropped an invalid %s card", area)
    return (cards or [_unknown(area, source)]), None


@router.get("/status", response_model=StatusOut)
async def integrations_status(db: DB, _: HubAdmin) -> StatusOut:
    areas: list[AreaOut] = []
    asks: list[AskOut] = []
    for key, label_tr, label_en in AREAS:
        cards, ask = await _read(db, key)
        areas.append(AreaOut(key=key, label_tr=label_tr, label_en=label_en, cards=cards))
        if ask is not None:
            asks.append(ask)
    counts = dict.fromkeys(STATUSES, 0)
    for a in areas:
        for c in a.cards:
            counts[c.status] += 1
    return StatusOut(generated_at=_iso(utcnow()) or "", areas=areas, counts=counts, asks=asks)
