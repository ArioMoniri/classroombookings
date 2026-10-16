"""Notification channels API ("Bildirim kanalları"; owner decision 2026-10-15).

Administrator (``setup.settings``)::

    GET    /channels/admin                                   every channel: switch, configured, missing, sign-off
    PUT    /channels/admin/{kind}                            switch / credentials / options / content mode / sign-off
    POST   /channels/admin/webpush/vapid                     generate the VAPID key pair (once; rotate=true renews)
    POST   /channels/admin/telegram/setup                    getMe + setWebhook (webhook mode) / deleteWebhook (poll)
    GET    /channels/admin/departments                       department -> Teams / Slack targets (host only)
    PUT    /channels/admin/{kind}/departments/{department}   map a department to a channel webhook (SSRF-guarded)
    DELETE /channels/admin/{kind}/departments/{department}
    GET    /channels/admin/deliveries                        delivery log (no addresses, no secrets)
    POST   /channels/admin/whatsapp_web/connect              QR code of the bridge session (admin only)
    GET    /channels/admin/whatsapp_web/status
    POST   /channels/admin/whatsapp_web/logout

Telegram: ``POST /channels/telegram/webhook`` (checks ``X-Telegram-Bot-Api-Secret-Token``).

Signed-in user (Profile)::

    GET    /me/channels                       {available: [...], linked: [...]}
    POST   /me/channels/telegram/link         one-time deep link t.me/<bot>?start=<nonce>
    POST   /me/channels/telegram/check        long-poll mode: fetch the bot's updates; {linked}
    POST   /me/channels/{sms|whatsapp}/link   {phone, consent}: a code is sent through the channel
    POST   /me/channels/{sms|whatsapp}/verify {code}
    POST   /me/channels/webpush               {subscription, label}: the browser's PushSubscription
    POST   /me/channels/{id}/test             queue a test message
    DELETE /me/channels/{id}                  unlink: the address is deleted
"""

from __future__ import annotations

import hmac
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, require_permission
from app.models import User
from app.models.channels import ChannelDelivery, UserChannel
from app.schemas.channels import ChannelConfigIn, CodeIn, DepartmentTargetIn, PhoneLinkIn, VapidIn, WebPushLinkIn
from app.services import audit
from app.services.channels import bridge, config, links, outbox, targets, transport
from app.services.channels.config import ConfigError

router = APIRouter(tags=["channels"])
SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]


def _http(exc: ConfigError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


# --------------------------------------------------------------------------------------------------
# administrator
# --------------------------------------------------------------------------------------------------


@router.get("/channels/admin")
async def admin_list(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    from app.services.calendar_feeds import public_base

    base, _src = await public_base(db)
    return {
        "channels": [config.public(await config.load(db, k)) for k in config.KINDS],
        "public_url": base,
        "telegram_webhook_url": f"{base}/api/v1/channels/telegram/webhook" if base else None,
    }


@router.put("/channels/admin/{kind}")
async def admin_put(kind: str, body: ChannelConfigIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    if body.kvkk_signoff is not None:
        data["kvkk_signoff"] = body.kvkk_signoff.model_dump()
    try:
        cfg = await config.update(db, kind, data, admin)
    except ConfigError as exc:
        await db.rollback()
        raise _http(exc) from None
    await db.commit()
    return config.public(await config.load(db, cfg.kind))


@router.post("/channels/admin/webpush/vapid")
async def admin_vapid(db: DB, admin: SettingsAdmin, body: VapidIn | None = None) -> dict[str, Any]:
    await config.ensure_vapid(db, admin, rotate=bool(body and body.rotate))
    await db.commit()
    return config.public(await config.load(db, "webpush"))


@router.post("/channels/admin/telegram/setup")
async def admin_telegram_setup(db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    from app.services.calendar_feeds import public_base

    cfg = await config.load(db, "telegram")
    token = cfg.secrets.get("bot_token")
    if not token:
        raise _http(ConfigError("not_configured", "enter the bot token first", "önce bot jetonunu girin", 409))
    try:
        me = await transport.telegram_api(token, "getMe")
        if not me.get("ok"):
            raise ConfigError(
                "telegram_refused",
                f"Telegram refused the token: {me.get('description') or me.get('http_status')}",
                "Telegram jetonu reddetti",
                502,
            )
        username = str((me.get("result") or {}).get("username") or "")
        if username:
            cfg.options["bot_username"] = username
        mode = cfg.options.get("update_mode") or "webhook"
        base, _src = await public_base(db)
        webhook_url = f"{base}/api/v1/channels/telegram/webhook" if base else None
        webhook_set = False
        if mode == "webhook" and webhook_url:
            if not cfg.secrets.get("webhook_secret"):
                cfg.secrets["webhook_secret"] = secrets.token_urlsafe(32)
            res = await transport.telegram_api(
                token,
                "setWebhook",
                {
                    "url": webhook_url,
                    "secret_token": cfg.secrets["webhook_secret"],
                    "allowed_updates": ["message", "my_chat_member"],
                },
            )
            webhook_set = bool(res.get("ok"))
        elif mode == "poll":
            await transport.telegram_api(token, "deleteWebhook", {"drop_pending_updates": False})
    except transport.ProviderCallError as exc:
        raise HTTPException(
            502, {"code": "telegram_unreachable", "message": str(exc), "message_tr": "Telegram'a ulaşılamadı"}
        ) from None
    except ConfigError as exc:
        raise _http(exc) from None
    await config.save(db, cfg, admin)
    await audit.record(
        db,
        "channels.telegram_setup",
        "notify_channel",
        "telegram",
        after={"mode": mode, "webhook_set": webhook_set, "bot": username},
        actor=admin,
    )
    await db.commit()
    return {
        "bot_username": cfg.options.get("bot_username"),
        "mode": mode,
        "webhook_set": webhook_set,
        "webhook_url": webhook_url,
    }


@router.get("/channels/admin/departments")
async def admin_departments(
    db: DB, _: SettingsAdmin, kind: str | None = Query(default=None, pattern="^(teams|slack)$")
) -> list[dict[str, Any]]:
    return await targets.listing(db, kind)


@router.put("/channels/admin/{kind}/departments/{department_id}")
async def admin_put_department(
    kind: str, department_id: int, body: DepartmentTargetIn, db: DB, admin: SettingsAdmin
) -> dict[str, Any]:
    try:
        out = await targets.put(db, kind, department_id, body.url, admin)
    except ConfigError as exc:
        await db.rollback()
        raise _http(exc) from None
    await db.commit()
    return out


@router.delete("/channels/admin/{kind}/departments/{department_id}", status_code=204)
async def admin_delete_department(kind: str, department_id: int, db: DB, admin: SettingsAdmin) -> Response:
    if not await targets.remove(db, kind, department_id, admin):
        raise HTTPException(404, "department target not found")
    await db.commit()
    return Response(status_code=204)


@router.get("/channels/admin/deliveries")
async def admin_deliveries(
    db: DB,
    _: SettingsAdmin,
    status: str | None = Query(default=None, pattern="^(PENDING|RUNNING|SENT|FAILED|SKIPPED)$"),
    kind: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    q = select(ChannelDelivery).order_by(ChannelDelivery.id.desc()).limit(limit)
    if status:
        q = q.where(ChannelDelivery.status == status)
    if kind:
        q = q.where(ChannelDelivery.kind == kind)
    rows = list((await db.execute(q)).scalars())
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "event": r.event,
            "user_id": r.user_id,
            "status": r.status,
            "attempts": r.attempts,
            "last_error": r.last_error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "next_attempt_at": r.next_attempt_at.isoformat() if r.next_attempt_at else None,
        }
        for r in rows
    ]


@router.post("/channels/admin/whatsapp_web/connect")
async def admin_bridge_connect(db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    try:
        out = await bridge.connect(db, admin)
    except ConfigError as exc:
        raise _http(exc) from None
    await db.commit()
    return out


@router.get("/channels/admin/whatsapp_web/status")
async def admin_bridge_status(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    try:
        out = await bridge.status(db)
    except ConfigError as exc:
        raise _http(exc) from None
    await db.commit()
    return out


@router.post("/channels/admin/whatsapp_web/logout")
async def admin_bridge_logout(db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    try:
        out = await bridge.logout(db, admin)
    except ConfigError as exc:
        raise _http(exc) from None
    await db.commit()
    return out


# --------------------------------------------------------------------------------------------------
# Telegram webhook (called by Telegram)
# --------------------------------------------------------------------------------------------------


@router.post("/channels/telegram/webhook")
async def telegram_webhook(
    request: Request,
    db: DB,
    secret_header: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> dict[str, Any]:
    cfg = await config.load(db, "telegram")
    expected = cfg.secrets.get("webhook_secret")
    if not expected or not cfg.secrets.get("bot_token"):
        raise HTTPException(404, "not found")
    if not secret_header or not hmac.compare_digest(secret_header.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "invalid secret token")
    try:
        update = await request.json()
    except ValueError:
        return {}
    if not isinstance(update, dict):
        return {}
    reply = await links.telegram_update(db, update)
    await db.commit()
    return reply


# --------------------------------------------------------------------------------------------------
# the signed-in user's channels
# --------------------------------------------------------------------------------------------------


@router.get("/me/channels")
async def my_channels(db: DB, user: CurrentUser) -> dict[str, Any]:
    return {
        "available": await links.available(db, user),
        "linked": [links.channel_out(c) for c in await links.user_channels(db, user.id)],
    }


@router.post("/me/channels/telegram/link", status_code=201)
async def telegram_link(db: DB, user: CurrentUser) -> dict[str, Any]:
    try:
        out = await links.telegram_link(db, user)
    except ConfigError as exc:
        raise _http(exc) from None
    await db.commit()
    return out


@router.post("/me/channels/telegram/check")
async def telegram_check(db: DB, user: CurrentUser) -> dict[str, Any]:
    try:
        await links.telegram_poll(db)
    except transport.ProviderCallError:
        pass  # the Profile card polls again; nothing to report to the user
    await db.commit()
    chans = await links.user_channels(db, user.id, "telegram")
    return {"linked": any(c.status == "active" for c in chans), "channels": [links.channel_out(c) for c in chans]}


@router.post("/me/channels/webpush", status_code=201)
async def webpush_link(body: WebPushLinkIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    if await config.sender_for(db, "webpush") is None:
        raise _http(links.channel_off("webpush"))
    try:
        ch = await links.add_push_subscription(db, user, body.subscription.model_dump(), body.label)
    except ConfigError as exc:
        await db.rollback()
        raise _http(exc) from None
    await db.commit()
    return links.channel_out(ch)


@router.post("/me/channels/{kind}/link", status_code=201)
async def phone_link(kind: str, body: PhoneLinkIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    try:
        out = await links.phone_link(db, user, kind, body.phone, body.consent)
    except ConfigError as exc:
        await db.rollback()
        raise _http(exc) from None
    await db.commit()
    return out


@router.post("/me/channels/{kind}/verify")
async def phone_verify(kind: str, body: CodeIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    try:
        ch = await links.phone_verify(db, user, kind, body.code)
    except ConfigError as exc:
        raise _http(exc) from None
    await db.commit()
    return links.channel_out(ch)


@router.post("/me/channels/{channel_id}/test", status_code=202)
async def channel_test(channel_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    from app.services.bookings_notify import _language
    from app.services.channels import text

    ch = await db.get(UserChannel, channel_id)
    if ch is None or ch.user_id != user.id:
        raise HTTPException(404, "channel not found")
    if await config.sender_for(db, ch.kind) is None:
        raise _http(links.channel_off(ch.kind))
    row, _new = await outbox.queue(
        db,
        kind=ch.kind,
        event="channel.test",
        dedupe_key=f"test:{ch.id}:{secrets.token_hex(8)}",
        payload={"event": "channel.test", "lang": text.lang_of(await _language(db, user))},
        user_id=user.id,
        user_channel_id=ch.id,
    )
    await db.commit()
    return {"queued": True, "delivery_id": row.id}


@router.delete("/me/channels/{channel_id}", status_code=204)
async def channel_unlink(channel_id: int, db: DB, user: CurrentUser) -> Response:
    if not await links.unlink(db, user, channel_id):
        raise HTTPException(404, "channel not found")
    await db.commit()
    return Response(status_code=204)
