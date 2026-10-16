"""The channels outbox (``channel_deliveries``), sent by the integrations worker.

Adapters only write rows inside the business transaction; after the commit :func:`kick` schedules a drain on the
integrations queue. One transaction per row, claimed with the worker's conditional UPDATE (several processes may
drain); a failed send backs off 1 min, 5 min, 30 min, 2 h, 6 h (``app.workers.integrations.BACKOFF_S``), then the
row is ``FAILED``. Failures are recorded on the row (redacted) and never raised into a request.

At send time the channel is checked again: a row queued before the administrator switched the channel off or the
KVKK sign-off was withdrawn is ``SKIPPED``, an address that was unlinked meanwhile took its rows with it.

Until ``app/workers/integrations.py`` lists :func:`drain_due` / :func:`next_due` among its drainers (the hook diff in
the hand-off), :func:`kick` runs this drain itself and re-arms its own timer for retries.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.models import ChannelDelivery, ChannelDepartmentTarget, ChannelLinkCode, UserChannel
from app.models.base import utcnow
from app.services.channels import config, text, transport

log = logging.getLogger(__name__)

PENDING, RUNNING, SENT, FAILED, SKIPPED = "PENDING", "RUNNING", "SENT", "FAILED", "SKIPPED"
KEY = "channels:drain"
NOT_CONFIGURED = "channel not configured by an administrator (or its KVKK sign-off was withdrawn)"


async def queue(
    session: AsyncSession,
    *,
    kind: str,
    event: str,
    dedupe_key: str,
    payload: dict[str, Any],
    user_id: int | None = None,
    user_channel_id: int | None = None,
    target_id: int | None = None,
    link_code_id: int | None = None,
) -> tuple[ChannelDelivery, bool]:
    """Insert one row unless the same (occurrence, recipient, target) is queued already: (row, created)."""
    key = dedupe_key[:255]
    existing = (await session.execute(select(ChannelDelivery).where(ChannelDelivery.dedupe_key == key))).scalar_one_or_none()
    if existing is not None:
        return existing, False
    row = ChannelDelivery(
        kind=kind,
        event=event[:40],
        dedupe_key=key,
        payload=payload,
        user_id=user_id,
        user_channel_id=user_channel_id,
        target_id=target_id,
        link_code_id=link_code_id,
        status=PENDING,
        next_attempt_at=utcnow(),
    )
    try:
        async with session.begin_nested():
            session.add(row)
    except IntegrityError:  # a concurrent transaction queued it first: the unique key is the referee
        again = (await session.execute(select(ChannelDelivery).where(ChannelDelivery.dedupe_key == key))).scalar_one()
        return again, False
    kick(session)
    return row, True


# --------------------------------------------------------------------------------------------------
# scheduling (own drain until the integrations worker lists this module)
# --------------------------------------------------------------------------------------------------

_timer: asyncio.TimerHandle | None = None


def _schedule(delay: float = 0.0) -> None:
    global _timer
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    from app.workers import integrations as worker

    if delay > 0:
        if _timer is not None and not _timer.cancelled() and _timer.when() <= loop.time() + delay:
            return
        if _timer is not None:
            _timer.cancel()
        _timer = loop.call_later(delay, _schedule)
        return

    async def job() -> None:
        await drain_due(utcnow(), 200)
        at = await next_due()
        if at is not None:
            _schedule(max(1.0, min(worker.MAX_TIMER_S, (at - utcnow()).total_seconds())))

    worker.run_detached(job, KEY)


def kick(session: AsyncSession) -> None:
    """Drain after the caller's transaction commits (no-op without a running loop, e.g. in sync tests)."""
    from sqlalchemy import event

    sync = session.sync_session
    if sync.info.get(KEY):
        return
    sync.info[KEY] = True

    def after_commit(s: Any) -> None:
        s.info.pop(KEY, None)
        _schedule()

    def after_rollback(s: Any) -> None:
        s.info.pop(KEY, None)

    event.listen(sync, "after_commit", after_commit, once=True)
    event.listen(sync, "after_soft_rollback", after_rollback, once=True)


# --------------------------------------------------------------------------------------------------
# drain
# --------------------------------------------------------------------------------------------------


async def drain_due(now: datetime, limit: int = 200) -> int:
    """Send the due rows (the integrations worker's drainer signature)."""
    from app.core.db import get_session_factory
    from app.workers import integrations as worker

    factory = get_session_factory()
    async with factory() as s:
        ids = list((await s.execute(worker.due(ChannelDelivery, now).limit(limit))).scalars())
    done = 0
    for rid in ids:
        async with factory() as s:
            if not await worker.claim(s, ChannelDelivery, rid, now):
                continue
            row = await s.get(ChannelDelivery, rid)
            if row is None:
                continue
            try:
                await deliver(s, row)
            except Exception as exc:  # noqa: BLE001 - recorded, the next row still goes
                log.warning("channel delivery %s failed: %s", rid, type(exc).__name__)
                row.status, row.last_error = FAILED, f"{type(exc).__name__}"[:500]
                row.attempts = (row.attempts or 0) + 1
            row.locked_until = None
            if row.status == FAILED:
                again = worker.next_attempt(row.attempts or 1, now)
                if again is not None and not getattr(row, "_final", False):
                    row.status, row.next_attempt_at = PENDING, again
                else:
                    row.next_attempt_at = None
            elif row.status in (SENT, SKIPPED):
                row.next_attempt_at = None
            await s.commit()
            done += 1
    return done


async def next_due() -> datetime | None:
    from app.core.db import get_session_factory

    async with get_session_factory()() as s:
        q = select(func.min(ChannelDelivery.next_attempt_at)).where(ChannelDelivery.status == PENDING)
        return (await s.execute(q)).scalar_one_or_none()


def _final(row: ChannelDelivery, error: str) -> None:
    """A failure that a retry cannot fix (address gone, recipient blocked the sender)."""
    row.status, row.last_error = FAILED, error[:500]
    row._final = True  # type: ignore[attr-defined]


def _message_id(row: ChannelDelivery) -> str:
    return hashlib.sha256(row.dedupe_key.encode("utf-8")).hexdigest()[:32].upper()


async def deliver(session: AsyncSession, row: ChannelDelivery) -> None:
    """Send one row now and record the outcome on it."""
    payload = dict(row.payload or {})
    address: str | None = None
    channel: UserChannel | None = None
    url: str | None = None
    if row.user_channel_id is not None:
        channel = await session.get(UserChannel, row.user_channel_id)
        if channel is None:
            row.status, row.last_error = SKIPPED, "the address was removed"
            return
        if channel.status != "active":
            row.status, row.last_error = SKIPPED, f"the address is {channel.status}"
            return
        address = decrypt_secret(channel.address_enc)
        address_kind = channel.kind
    elif row.link_code_id is not None:
        code_row = await session.get(ChannelLinkCode, row.link_code_id)
        if code_row is None or code_row.used_at is not None or not code_row.address_enc:
            row.status, row.last_error = SKIPPED, "the verification code is no longer needed"
            return
        address = decrypt_secret(code_row.address_enc)
        address_kind = code_row.kind
        payload["code"] = decrypt_secret(str(payload.get("code_enc") or ""))
    elif row.target_id is not None:
        target = await session.get(ChannelDepartmentTarget, row.target_id)
        if target is None:
            row.status, row.last_error = SKIPPED, "the department target was removed"
            return
        url = decrypt_secret(target.url_enc)
        address_kind = target.kind
    else:
        row.status, row.last_error = SKIPPED, "no recipient"
        return
    sender = await config.sender_for(session, address_kind)
    if sender is None:
        row.status, row.last_error = SKIPPED, NOT_CONFIGURED
        return
    title, body = text.render(payload)
    if sender.kind == "whatsapp" and row.event == "channel.verify":
        body = str(payload.get("code") or "")  # the authentication template's {{1}} is the code itself
    row.attempts = (row.attempts or 0) + 1
    result = await _send(sender, address_kind, address, url, title, body, row, payload)
    if result.ok:
        row.status, row.last_error, row.sent_at = SENT, None, utcnow()
        if channel is not None and channel.last_error:
            channel.last_error = None
        return
    error = result.error or "send failed"
    if result.gone and channel is not None:
        _final(row, error + "; the address was deleted")
        row.user_channel_id = None
        await session.flush()
        await session.delete(channel)
        return
    if result.blocked and channel is not None:
        channel.status, channel.last_error = "blocked", error[:255]
        _final(row, error)
        return
    row.status, row.last_error = FAILED, error[:500]
    if channel is not None:
        channel.last_error = error[:255]


async def _send(
    sender: config.ChannelConfig,
    address_kind: str,
    address: str | None,
    url: str | None,
    title: str,
    body: str,
    row: ChannelDelivery,
    payload: dict[str, Any],
) -> transport.SendResult:
    s, o = sender.secrets, sender.options
    lang = text.lang_of(payload.get("lang"))
    if sender.kind == "webpush":
        sub = json.loads(address or "{}")
        from app.services.channels import links

        try:
            await links.check_push_endpoint(str(sub.get("endpoint") or ""))
        except config.ConfigError as exc:
            return transport.SendResult(False, exc.message, gone=True)
        data = json.dumps(
            {"title": title, "body": body, "url": payload.get("link"), "tag": row.dedupe_key[:64]}, ensure_ascii=False
        ).encode("utf-8")
        ttl = int(o.get("ttl_s") or 86400)
        return await transport.webpush_send(sub, data, s["vapid_private_key"], str(o["contact"]), ttl)
    if sender.kind == "whatsapp_web":
        digits = (address or "").lstrip("+")
        try:
            out = await transport.bridge_api(
                "POST", "/chat/send/text", s["user_token"], {"Phone": digits, "Body": body, "Id": _message_id(row)}
            )
        except transport.ProviderCallError as exc:
            return transport.SendResult(False, str(exc))
        ok = out.get("http_status") == 200 and out.get("success") is not False
        return transport.SendResult(ok, None if ok else f"bridge answered HTTP {out.get('http_status')}")
    if sender.kind in ("teams", "slack"):
        from app.services.channels import targets

        try:
            await targets.check_url(sender.kind, url or "", resolve=True)
        except config.ConfigError as exc:
            return transport.SendResult(False, exc.message)
        return await transport.apprise_send(url or "", title, body, [url or ""])
    apprise_url, secrets = _apprise_url(sender, address or "", row.event, lang)
    # the address is personal data: kept out of the stored error and the logs like the credentials
    personal = [address or "", (address or "").lstrip("+")]
    return await transport.apprise_send(apprise_url, title, body, [*secrets, *personal])


def _apprise_url(sender: config.ChannelConfig, address: str, event: str, lang: str) -> tuple[str, list[str]]:
    s, o = sender.secrets, sender.options
    if sender.kind == "telegram":
        return f"tgram://{s['bot_token']}/{address}/?format=text", [s["bot_token"]]
    if sender.kind == "whatsapp":
        template = o["template_code"] if event == "channel.verify" else o["template_notice"]
        code = o.get("lang_tr" if lang == "tr" else "lang_en") or ("tr" if lang == "tr" else "en_US")
        to = address.lstrip("+")
        url = f"whatsapp://{template}:{s['access_token']}@{o['phone_number_id']}/{to}?lang={code}&:1=body"
        return url, [s["access_token"]]
    if sender.kind == "sms":
        provider = o.get("provider")
        frm = str(o["from_number"])
        if provider == "vonage":
            url = f"vonage://{s['api_key']}:{s['api_secret']}@{frm.lstrip('+')}/{address.lstrip('+')}"
            return url, [s["api_key"], s["api_secret"]]
        return f"twilio://{s['account_sid']}:{s['auth_token']}@{frm}/{address}", [s["account_sid"], s["auth_token"]]
    raise ValueError(f"no Apprise sender for {sender.kind}")
