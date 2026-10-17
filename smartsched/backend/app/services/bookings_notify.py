"""E-mail notifications behind the SMTP setting, with an outbox.

Every notification becomes a ``notification_outbox`` row. Only when SMTP is configured (host + from
address) is the message handed to the SMTP server; the row becomes ``SENT`` only after the server accepted
it, ``FAILED`` with the error otherwise. Without SMTP the row stays ``UNSENT`` ("SMTP is not configured"):
nothing pretends to have sent anything. Since 2026-10-15 notifications are ``PENDING`` until the integrations
worker sends them after the commit (retries with backoff); see :func:`notify`."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import smtplib  # noqa: F401  (tests replace bookings_notify.smtplib.SMTP; app.services.mail sends)
import weakref
from datetime import datetime
from email.message import EmailMessage
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingPeriod, NotificationOutbox, User
from app.models.base import utcnow
from app.models.catalog import Room
from app.services import bookings_events as events
from app.services import bookings_i18n
from app.services.bookings_settings import get_group, get_value

log = logging.getLogger(__name__)

NOT_CONFIGURED = "SMTP is not configured"
QUEUED = "PENDING"  # the integrations worker's queue status (app.models.integrations.PENDING)
T = bookings_i18n.text  # e-mail texts: admin overrides (translations, set "email") over the shipped ones


def _send(smtp: dict[str, Any], msg: EmailMessage) -> None:
    """Hand ``msg`` to the SMTP server (password, XOAUTH2 or no sign-in; app.services.mail.transmit)."""
    from app.services import mail

    mail.transmit(smtp, msg)


#: template context of a message sent at once (password reset: the code box); never stored, gone with the row object
_RENDER_CTX: weakref.WeakKeyDictionary[NotificationOutbox, dict[str, Any]] = weakref.WeakKeyDictionary()


async def _rendered(session: AsyncSession, row: NotificationOutbox) -> Any:
    """The themed HTML + plain text of ``row`` (wave 3b W3-MAIL): the stored subject and body themed by the renderer
    of the row's kind, in the reader's language. A rendering failure never stops the e-mail: it goes as plain text."""
    from app.services import mail

    try:
        user = await session.get(User, row.user_id) if row.user_id else None
        locale = await mail.resolve_locale(session, row.locale, user)
        ctx = _RENDER_CTX.get(row)
        if ctx is not None:
            return await mail.render_for(session, row.kind, locale, **ctx)
        name = (user.full_name or user.username or "") if user is not None else ""
        what = row.subject.split(": ", 1)[1] if ": " in row.subject else ""
        return await mail.render_for(
            session, row.kind, locale, subject=row.subject, body=row.body, link=row.link, name=name, what=what
        )
    except Exception:  # noqa: BLE001 - the plain-text e-mail still goes out
        log.exception("e-mail rendering failed for outbox row %s (%s)", row.id, row.kind)
        return None


async def deliver(session: AsyncSession, row: NotificationOutbox) -> NotificationOutbox:
    """Try to send ``row`` now (also used by the outbox "retry")."""
    from app.services import mail

    smtp = await get_group(session, "smtp", reveal=True)
    if not row.to_email:
        row.status, row.error = "UNSENT", "recipient has no e-mail address"
        return row
    if not (smtp["host"] and smtp["from_address"]):
        row.status, row.error = "UNSENT", NOT_CONFIGURED
        return row
    rendered = await _rendered(session, row)
    # an admin override of the subject (translation set "email") reaches the e-mail; otherwise it is the stored one
    subject = rendered.subject if rendered is not None else row.subject
    text = rendered.text if rendered is not None else row.body
    msg = mail.build_message(smtp, to=row.to_email, rendered=rendered, subject=subject, text=text)
    row.attempts = (row.attempts or 0) + 1
    try:
        await asyncio.to_thread(_send, smtp, msg)
    except Exception as exc:  # noqa: BLE001 - SMTP / network / OAuth2 token errors: recorded, retried with backoff
        row.status, row.error = "FAILED", f"{type(exc).__name__}: {exc}"[:500]
        return row
    row.status, row.error, row.sent_at = "SENT", None, utcnow()
    return row


async def notify(
    session: AsyncSession,
    *,
    kind: str,
    to_email: str | None,
    subject: str,
    body: str,
    user_id: int | None = None,
    booking_id: int | None = None,
    deliver_now: bool = False,
    link: str | None = None,
    locale: str | None = None,
    ctx: dict[str, Any] | None = None,
) -> NotificationOutbox:
    """Record an e-mail in the outbox. Without an address or SMTP it is ``UNSENT`` at once. ``deliver_now`` (password
    reset codes, the SMTP test: the caller needs the result) sends inside the request as before; everything else is
    ``PENDING`` and sent by the integrations worker after the commit, with retries and backoff (ROADMAP Phase 11).

    Wave 3b W3-MAIL: the e-mail goes as ``multipart/alternative`` -- this plain-text ``body`` first, the themed HTML of
    ``kind`` (app.emails) second. ``link`` is the button's panel path, ``locale`` the reader's language (both stored);
    ``ctx`` is the template context of a message sent at once (``deliver_now``; never stored)."""
    row = NotificationOutbox(
        kind=kind,
        to_email=to_email,
        subject=subject[:255],
        body=body,
        user_id=user_id,
        booking_id=booking_id,
        link=(link or None) and link[:500],
        locale=locale,
    )
    session.add(row)
    await session.flush()
    if ctx is not None:
        _RENDER_CTX[row] = dict(ctx)
    smtp = await get_group(session, "smtp", reveal=True)
    if deliver_now or not row.to_email or not (smtp["host"] and smtp["from_address"]):
        await deliver(session, row)  # UNSENT without an address / SMTP, else sent now
    else:
        from app.workers import integrations as worker

        row.status, row.next_attempt_at = QUEUED, utcnow()
        worker.kick_after_commit(session)
    await session.flush()
    return row


async def drain_due(now: datetime, limit: int = 200) -> int:
    """Send the queued e-mails that are due (called by the integrations worker); one transaction per row. A failed
    send is retried after 1 min, 5 min, 30 min, 2 h and 6 h, then the row is ``FAILED``."""
    from app.core.db import get_session_factory
    from app.workers import integrations as worker

    factory = get_session_factory()
    async with factory() as s:
        ids = list((await s.execute(worker.due(NotificationOutbox, now).limit(limit))).scalars())
    done = 0
    for rid in ids:
        async with factory() as s:
            if not await worker.claim(s, NotificationOutbox, rid, now):
                continue
            row = await s.get(NotificationOutbox, rid)
            if row is None:
                continue
            await deliver(s, row)
            row.locked_until = None
            if row.status == "FAILED":
                again = worker.next_attempt(row.attempts or 1, now)
                if again is not None:
                    row.status, row.next_attempt_at = QUEUED, again
                else:
                    row.next_attempt_at = None
            elif row.status in ("SENT", "UNSENT"):
                row.next_attempt_at = None
            await s.commit()
            done += 1
    return done


async def next_due() -> datetime | None:
    from app.core.db import get_session_factory

    async with get_session_factory()() as s:
        q = select(func.min(NotificationOutbox.next_attempt_at)).where(NotificationOutbox.status == QUEUED)
        return (await s.execute(q)).scalar_one_or_none()


# --------------------------------------------------------------------------------------------------
# Booking notifications (event handlers). Since 2026-10-15 they go through app.services.notify_dispatch: the
# recipients' channel preferences apply (events booking.created / booking.cancelled / room_owner.booking), the
# e-mail keeps its template and outbox kind, the in-app bell gets the same text, and the delivery ledger makes a
# repeated hook a no-op.
# --------------------------------------------------------------------------------------------------


def _who(u: User | None) -> str:
    if u is None:
        return "-"
    return u.full_name or u.username or u.email or f"#{u.id}"


async def _describe(session: AsyncSession, b: Booking, fmt: bookings_i18n.Formatter) -> str:
    """``A 101, Salı 17 Şubat 2026 P1 08:30-09:10`` with the organisation's date and time patterns."""
    room = await session.get(Room, b.room_id)
    period = await session.get(BookingPeriod, b.period_id)
    times = f"{fmt.time(period.time_start)}-{fmt.time(period.time_end)}" if period else ""
    pname = period.name if period else ""
    return f"{room.display_name if room else b.room_id}, {fmt.long(b.date)} {pname} {times}".strip()


async def _language(session: AsyncSession, user: User | None) -> str:
    """The recipient's profile language when it is enabled, else the organisation's default."""
    org_default = str(await get_value(session, "org", "default_language") or "tr")
    enabled = await get_value(session, "org", "languages") or []
    if user is not None and user.language and user.language in enabled:
        return user.language
    return org_default


async def _dispatch(
    session: AsyncSession,
    user: User,
    *,
    event: str,
    key: str,
    subject: str,
    body: str,
    link: str,
    rows: list[Booking],
    data: dict[str, Any],
) -> None:
    """Hand one booking notice to :mod:`app.services.notify_dispatch`: the user's channel preferences apply, the
    e-mail keeps its outbox kind (``booking.created`` -> ``booking_created``) and its template text, the in-app copy
    carries the same title and body, and the ledger key makes a re-run of the hook a no-op."""
    from app.services import notify_dispatch as nd  # notify_dispatch imports this module

    await nd.dispatch(
        session,
        user,
        nd.Notice(
            event=event,
            key=key,
            title=subject,
            body=body,
            link=link,
            booking_id=rows[0].id,
            data={"booking_ids": [b.id for b in rows], "room_id": rows[0].room_id, **data},
        ),
    )


async def _on_created(session: AsyncSession, payload: dict[str, Any]) -> None:
    ids = payload.get("booking_ids") or [payload["booking_id"]]
    actor = await session.get(User, payload.get("actor_id")) if payload.get("actor_id") else None
    first = await session.get(Booking, ids[0])
    if first is None:
        return
    rows = [b for b in [await session.get(Booking, i) for i in ids] if b is not None]
    series = payload.get("series_id")
    who = {"actor": {"id": actor.id, "name": _who(actor)} if actor else None, "series_id": series}

    async def items(lang: str) -> str:
        fmt = await bookings_i18n.formatter(session, lang)
        return "\n".join([f"- {await _describe(session, b, fmt)}" for b in rows])

    if first.user_id and first.user_id != (actor.id if actor else None):
        target = await session.get(User, first.user_id)
        if target is not None:
            lang = await _language(session, target)
            what = await items(lang)
            await _dispatch(
                session,
                target,
                event="booking.created",
                key=f"booking:{first.id}:created",
                subject=await T(session, lang, "booking_created.subject", actor=_who(actor), count=len(rows)),
                body=await T(session, lang, "booking_created.body", actor=_who(actor), count=len(rows), items=what),
                link="/bookings/mine",
                rows=rows,
                data=who,
            )
    room = await session.get(Room, first.room_id)
    if (
        room is not None
        and room.owner_user_id
        and room.owner_user_id
        not in {
            actor.id if actor else None,
            first.user_id,
        }
    ):
        owner = await session.get(User, room.owner_user_id)
        if owner is not None:
            lang = await _language(session, owner)
            tag = await T(session, lang, "room_owner.series", series_id=series) if series else ""
            await _dispatch(
                session,
                owner,
                event="room_owner.booking",
                key=f"booking:{first.id}:room_owner",
                subject=await T(session, lang, "room_owner.subject", room=room.display_name),
                body=await T(session, lang, "room_owner.body", actor=_who(actor), series=tag, items=await items(lang)),
                link="/bookings",
                rows=rows,
                data={**who, "room": room.display_name},
            )


async def _on_cancelled(session: AsyncSession, payload: dict[str, Any]) -> None:
    actor_id = payload.get("actor_id")
    actor = await session.get(User, actor_id) if actor_id else None
    by_user: dict[int, list[Booking]] = {}
    for bid in payload.get("booking_ids", []):
        b = await session.get(Booking, bid)
        if b is not None and b.user_id and b.user_id != actor_id:
            by_user.setdefault(b.user_id, []).append(b)
    reason = payload.get("reason")
    for uid, bookings in by_user.items():
        target = await session.get(User, uid)
        if target is None:
            continue
        lang = await _language(session, target)
        fmt = await bookings_i18n.formatter(session, lang)
        what = "\n".join([f"- {await _describe(session, b, fmt)}" for b in bookings])
        # a code (replaced_by_series:<id>, undo_of:<id>) reads in the reader's language; typed words stay as they are
        reason_text = await bookings_i18n.cancel_reason(session, lang, reason)
        why = await T(session, lang, "booking_cancelled.reason", reason=reason_text) if reason_text else ""
        # one occurrence = these bookings cancelled at this moment (a booking restored by an undo and cancelled
        # again is a new occurrence and is announced again)
        when = max((b.cancelled_at for b in bookings if b.cancelled_at is not None), default=None)
        stamp = when.isoformat(timespec="seconds") if when is not None else "-"
        digest = hashlib.sha1(",".join(str(b.id) for b in sorted(bookings, key=lambda x: x.id)).encode()).hexdigest()
        await _dispatch(
            session,
            target,
            event="booking.cancelled",
            key=f"booking_cancel:{digest[:16]}:{stamp}",
            subject=await T(session, lang, "booking_cancelled.subject", actor=_who(actor), count=len(bookings)),
            body=await T(
                session,
                lang,
                "booking_cancelled.body",
                actor=_who(actor),
                count=len(bookings),
                items=what,
                reason=why,
            ),
            link="/bookings/mine",
            rows=bookings,
            data={"actor": {"id": actor.id, "name": _who(actor)} if actor else None, "reason": reason},
        )


async def _on_series(session: AsyncSession, payload: dict[str, Any]) -> None:
    if payload.get("booking_ids"):
        await _on_created(session, payload)


events.on("booking.created", _on_created)
events.on("series.created", _on_series)
events.on("booking.cancelled", _on_cancelled)
