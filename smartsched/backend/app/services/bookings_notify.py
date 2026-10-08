"""E-mail notifications behind the SMTP setting, with an outbox.

Every notification becomes a ``notification_outbox`` row. Only when SMTP is configured (host + from
address) is the message handed to the SMTP server; the row becomes ``SENT`` only after the server accepted
it, ``FAILED`` with the error otherwise. Without SMTP the row stays ``UNSENT`` ("SMTP is not configured"):
nothing pretends to have sent anything."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingPeriod, NotificationOutbox, User
from app.models.base import utcnow
from app.models.catalog import Room
from app.services import bookings_events as events
from app.services.bookings_settings import get_group, get_value

NOT_CONFIGURED = "SMTP is not configured"


def _send(smtp: dict[str, Any], msg: EmailMessage) -> None:
    timeout = int(smtp.get("timeout_s") or 15)
    host, port = str(smtp["host"]), int(smtp.get("port") or 587)
    security = str(smtp.get("security") or "starttls").lower()
    server: smtplib.SMTP
    if security == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    try:
        if security == "starttls":
            server.starttls(context=ssl.create_default_context())
        if smtp.get("username"):
            server.login(str(smtp["username"]), str(smtp.get("password") or ""))
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            server.close()


async def deliver(session: AsyncSession, row: NotificationOutbox) -> NotificationOutbox:
    """Try to send ``row`` now (also used by the outbox "retry")."""
    smtp = await get_group(session, "smtp", reveal=True)
    if not row.to_email:
        row.status, row.error = "UNSENT", "recipient has no e-mail address"
        return row
    if not (smtp["host"] and smtp["from_address"]):
        row.status, row.error = "UNSENT", NOT_CONFIGURED
        return row
    msg = EmailMessage()
    msg["Subject"] = row.subject
    msg["From"] = formataddr((str(smtp.get("from_name") or ""), str(smtp["from_address"])))
    msg["To"] = row.to_email
    msg.set_content(row.body)
    row.attempts = (row.attempts or 0) + 1
    try:
        await asyncio.to_thread(_send, smtp, msg)
    except (OSError, smtplib.SMTPException) as exc:
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
) -> NotificationOutbox:
    row = NotificationOutbox(
        kind=kind, to_email=to_email, subject=subject[:255], body=body, user_id=user_id, booking_id=booking_id
    )
    session.add(row)
    await session.flush()
    await deliver(session, row)
    await session.flush()
    return row


# --------------------------------------------------------------------------------------------------
# Booking notifications (event handlers)
# --------------------------------------------------------------------------------------------------


def _who(u: User | None) -> str:
    if u is None:
        return "-"
    return u.full_name or u.username or u.email or f"#{u.id}"


async def _describe(session: AsyncSession, b: Booking) -> str:
    room = await session.get(Room, b.room_id)
    period = await session.get(BookingPeriod, b.period_id)
    times = f"{period.time_start:%H:%M}-{period.time_end:%H:%M}" if period else ""
    pname = period.name if period else ""
    return f"{room.display_name if room else b.room_id}, {b.date:%d.%m.%Y} {pname} {times}".strip()


async def _texts(session: AsyncSession) -> str:
    return str(await get_value(session, "org", "default_language") or "tr")


async def _on_created(session: AsyncSession, payload: dict[str, Any]) -> None:
    ids = payload.get("booking_ids") or [payload["booking_id"]]
    actor = await session.get(User, payload.get("actor_id")) if payload.get("actor_id") else None
    tr = (await _texts(session)) == "tr"
    first = await session.get(Booking, ids[0])
    if first is None:
        return
    lines = [await _describe(session, b) for b in [await session.get(Booking, i) for i in ids] if b is not None]
    what = "\n".join(f"- {x}" for x in lines)
    series = payload.get("series_id")
    if first.user_id and first.user_id != (actor.id if actor else None):
        target = await session.get(User, first.user_id)
        if target is not None:
            subject = "Sizin adınıza rezervasyon yapıldı" if tr else "A booking was made for you"
            body = (
                f"{_who(actor)} sizin adınıza {len(lines)} rezervasyon yaptı:\n{what}\n"
                if tr
                else f"{_who(actor)} made {len(lines)} booking(s) for you:\n{what}\n"
            )
            await notify(
                session, kind="booking_created", to_email=target.email, subject=subject, body=body,
                user_id=target.id, booking_id=first.id,
            )
    room = await session.get(Room, first.room_id)
    if room is not None and room.owner_user_id and room.owner_user_id not in {
        actor.id if actor else None,
        first.user_id,
    }:
        owner = await session.get(User, room.owner_user_id)
        if owner is not None:
            subject = f"{room.display_name} için yeni rezervasyon" if tr else f"New booking in {room.display_name}"
            body = (
                f"{_who(actor)} sorumlu olduğunuz dersliği ayırttı{' (seri #' + str(series) + ')' if series else ''}:\n{what}\n"
                if tr
                else f"{_who(actor)} booked a room you own{' (series #' + str(series) + ')' if series else ''}:\n{what}\n"
            )
            await notify(
                session, kind="room_owner_booking", to_email=owner.email, subject=subject, body=body,
                user_id=owner.id, booking_id=first.id,
            )


async def _on_cancelled(session: AsyncSession, payload: dict[str, Any]) -> None:
    actor_id = payload.get("actor_id")
    actor = await session.get(User, actor_id) if actor_id else None
    tr = (await _texts(session)) == "tr"
    by_user: dict[int, list[Booking]] = {}
    for bid in payload.get("booking_ids", []):
        b = await session.get(Booking, bid)
        if b is not None and b.user_id and b.user_id != actor_id:
            by_user.setdefault(b.user_id, []).append(b)
    reason = payload.get("reason")
    for uid, items in by_user.items():
        target = await session.get(User, uid)
        if target is None:
            continue
        what = "\n".join([f"- {await _describe(session, b)}" for b in items])
        why = f"\n{'Gerekçe' if tr else 'Reason'}: {reason}" if reason else ""
        subject = "Rezervasyonunuz iptal edildi" if tr else "Your booking was cancelled"
        body = (
            f"{_who(actor)} {len(items)} rezervasyonunuzu iptal etti:\n{what}{why}\n"
            if tr
            else f"{_who(actor)} cancelled {len(items)} of your bookings:\n{what}{why}\n"
        )
        await notify(
            session, kind="booking_cancelled", to_email=target.email, subject=subject, body=body,
            user_id=uid, booking_id=items[0].id,
        )


async def _on_series(session: AsyncSession, payload: dict[str, Any]) -> None:
    if payload.get("booking_ids"):
        await _on_created(session, payload)


events.on("booking.created", _on_created)
events.on("series.created", _on_series)
events.on("booking.cancelled", _on_cancelled)
