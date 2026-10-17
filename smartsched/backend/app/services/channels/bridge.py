"""The optional WhatsApp Web bridge: a wuzapi container (MIT, Go, built on whatsmeow, MPL-2.0) next to the backend.

Unofficial protocol: it violates WhatsApp's terms and the number can be banned, so the sender is off by default,
needs the administrator's explicit risk acknowledgement and a dedicated institution number; the WhatsApp Business
Cloud API (Apprise) stays the recommended path. The administrator links the number once by scanning the QR code
shown in Settings; the whatsmeow session store lives in the bridge's own volume (see
docs/deploy/notification-channels.md). ``logged_in`` is cached in the channel options so the send gate does not
call the bridge on every notification.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.base import utcnow
from app.services import audit
from app.services.channels import config, transport
from app.services.channels.config import ConfigError


async def _cfg(session: AsyncSession) -> config.ChannelConfig:
    cfg = await config.load(session, "whatsapp_web")
    token = cfg.secrets.get("user_token")
    if not token or not config.bridge_url():
        raise ConfigError(
            "bridge_not_configured",
            "set WHATSAPP_BRIDGE_URL on the backend and the bridge user token first",
            "önce arka uçta WHATSAPP_BRIDGE_URL'yi ve köprü kullanıcı jetonunu ayarlayın",
            409,
        )
    return cfg


async def _remember(session: AsyncSession, cfg: config.ChannelConfig, logged_in: bool) -> None:
    if bool(cfg.options.get("logged_in")) != logged_in:
        cfg.options["logged_in"] = logged_in
    cfg.options["checked_at"] = utcnow().isoformat(timespec="seconds") + "Z"
    await config.save(session, cfg, None)


def _flag(data: dict[str, Any], *names: str) -> bool:
    raw = data.get("data")
    inner: dict[str, Any] = raw if isinstance(raw, dict) else {}
    return any(inner.get(n) is True for n in names)


async def status(session: AsyncSession) -> dict[str, Any]:
    cfg = await _cfg(session)
    try:
        data = await transport.bridge_api("GET", "/session/status", cfg.secrets["user_token"])
    except transport.ProviderCallError:
        return {"reachable": False, "connected": False, "logged_in": False}
    logged_in = _flag(data, "loggedIn", "LoggedIn")
    await _remember(session, cfg, logged_in)
    return {"reachable": True, "connected": _flag(data, "connected", "Connected"), "logged_in": logged_in}


async def connect(session: AsyncSession, admin: User) -> dict[str, Any]:
    """Start the bridge session and return the QR code to scan with the institution's WhatsApp (shown to the
    administrator only, never logged or stored)."""
    cfg = await _cfg(session)
    if config._acknowledged(cfg.risk_ack) is False:
        raise ConfigError(
            "risk_ack_required",
            "acknowledge the terms-of-service / ban risk first",
            "önce kullanım koşulları / yasaklanma riskini onaylayın",
            409,
        )
    token = cfg.secrets["user_token"]
    try:
        await transport.bridge_api("POST", "/session/connect", token, {"Subscribe": ["Message"], "Immediate": True})
        st = await transport.bridge_api("GET", "/session/status", token)
        logged_in = _flag(st, "loggedIn", "LoggedIn")
        qr = None
        if not logged_in:
            data = await transport.bridge_api("GET", "/session/qr", token)
            raw = data.get("data")
            qr = (raw.get("QRCode") if isinstance(raw, dict) else None) or None
    except transport.ProviderCallError as exc:
        raise ConfigError("bridge_unreachable", str(exc), "WhatsApp köprüsüne ulaşılamadı", 502) from exc
    await _remember(session, cfg, logged_in)
    await audit.record(
        session,
        "channels.bridge_connect",
        "notify_channel",
        "whatsapp_web",
        after={"logged_in": logged_in},
        actor=admin,
    )
    return {"qr": qr, "logged_in": logged_in}


async def logout(session: AsyncSession, admin: User) -> dict[str, Any]:
    cfg = await _cfg(session)
    try:
        await transport.bridge_api("POST", "/session/logout", cfg.secrets["user_token"])
    except transport.ProviderCallError as exc:
        raise ConfigError("bridge_unreachable", str(exc), "WhatsApp köprüsüne ulaşılamadı", 502) from exc
    await _remember(session, cfg, False)
    await audit.record(
        session, "channels.bridge_logout", "notify_channel", "whatsapp_web", after={"logged_in": False}, actor=admin
    )
    return {"reachable": True, "connected": False, "logged_in": False}
