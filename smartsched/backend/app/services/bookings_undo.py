"""P7 undo (docs/product/booking-enhancements.md §4.6): reverse a booking create, move or cancel.

Allowed when the event is ``reversible``, not undone yet, younger than ``bookings.audit_undo_hours`` (24 h) or
before the booking starts, the caller holds the permission the inverse action needs, and **no later event
touched the same bookings** (409 otherwise). The inverse runs through the booking service, so the slot is
re-checked against the timetable, blocks and other bookings: a cancelled booking whose slot was taken answers
409 with free alternatives (T1). The undo is a new audit row with ``undo_of``; the original is never edited."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, Booking, BookingPeriod, BookingSeries
from app.models.base import utcnow
from app.models.booking import BOOKED, CANCELLED
from app.models.catalog import Room
from app.services import audit
from app.services import bookings as bsvc
from app.services import bookings_events as events
from app.services.bookings_perms import Access
from app.services.bookings_settings import get_value

UNDOABLE = ("booking.create", "series.create", "booking.move", "booking.cancel")


def _err(status: int, code: str, message: str, message_tr: str, **data: Any) -> bsvc.BookingError:
    return bsvc.BookingError(status, code, message, message_tr=message_tr, **data)


async def _group(session: AsyncSession, ev: AuditEvent) -> list[AuditEvent]:
    children = list(
        (await session.execute(select(AuditEvent).where(AuditEvent.parent_id == ev.id).order_by(AuditEvent.id))).scalars()
    )
    return [ev, *children]


def _booking_ids(group: list[AuditEvent]) -> list[int]:
    ids = [int(e.entity_id) for e in group if e.entity_type == "booking" and e.entity_id and e.entity_id.isdigit()]
    if len(group) > 1:  # the parent of a bulk event names the first booking again (or the series)
        ids = [int(e.entity_id) for e in group[1:] if e.entity_type == "booking" and (e.entity_id or "").isdigit()]
    return list(dict.fromkeys(ids))


async def _start(session: AsyncSession, b: Booking) -> datetime:
    period = await session.get(BookingPeriod, b.period_id)
    return datetime.combine(b.date, period.time_start if period else datetime.min.time())


async def check(session: AsyncSession, access: Access, event_id: int) -> tuple[AuditEvent, list[Booking]]:
    ev = await session.get(AuditEvent, event_id)
    if ev is None:
        raise _err(404, "not_found", "audit event not found", "kayıt bulunamadı")
    if not ev.reversible or ev.action not in UNDOABLE:
        raise _err(409, "not_reversible", "this change cannot be undone", "bu değişiklik geri alınamaz")
    done = (await session.execute(select(AuditEvent.id).where(AuditEvent.undo_of == ev.id))).first()
    if done is not None:
        raise _err(409, "already_undone", "this change was already undone", "bu değişiklik zaten geri alındı")
    group = await _group(session, ev)
    ids = _booking_ids(group)
    rows = [b for b in [await session.get(Booking, i) for i in ids] if b is not None]
    if not rows:
        raise _err(409, "gone", "the bookings no longer exist", "rezervasyonlar artık yok")
    group_ids = [e.id for e in group]
    later = list(
        (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.id > ev.id,
                    AuditEvent.entity_type == "booking",
                    AuditEvent.entity_id.in_([str(i) for i in ids]),
                    AuditEvent.id.notin_(group_ids),
                    or_(AuditEvent.parent_id.is_(None), AuditEvent.parent_id.notin_(group_ids)),
                )
            )
        ).scalars()
    )
    if later:
        raise _err(
            409,
            "changed_since",
            f"{len(later)} change(s) were made after this one",
            f"Bu kayıttan sonra {len(later)} değişiklik yapıldı",
            later=[e.id for e in later],
        )
    hours = int(await get_value(session, "bookings", "audit_undo_hours") or 24)
    young = utcnow() - ev.ts < timedelta(hours=hours)
    now = await bsvc.now_local(session)
    upcoming = any(await _start(session, b) > now for b in rows)
    if not (young or upcoming):
        raise _err(
            409,
            "too_old",
            f"changes can be undone within {hours} hours or before the booking starts",
            f"değişiklikler {hours} saat içinde ya da rezervasyon başlamadan geri alınabilir",
        )
    return ev, rows


async def undo(session: AsyncSession, access: Access, event_id: int) -> dict[str, Any]:
    ev, rows = await check(session, access, event_id)
    if ev.action in ("booking.create", "series.create"):
        return await _undo_create(session, access, ev, rows)
    if ev.action == "booking.move":
        return await _undo_move(session, access, ev, rows[0])
    return await _undo_cancel(session, access, ev, rows)


async def _undo_create(session: AsyncSession, access: Access, ev: AuditEvent, rows: list[Booking]) -> dict[str, Any]:
    targets = [b for b in rows if b.status == BOOKED]
    for b in targets:
        room = await session.get(Room, b.room_id)
        assert room is not None
        if not await bsvc.can_cancel(session, access, b, room):
            raise _err(403, "not_cancelable", "you may not cancel this booking", "bu rezervasyonu iptal edemezsiniz")
    before = {b.id: bsvc.snap(b) for b in targets}
    reason = f"undo of #{ev.id}"
    ids = await bsvc._cancel_rows(session, access, targets, reason)
    if ev.action == "series.create" and ev.entity_id:
        series = await session.get(BookingSeries, int(ev.entity_id))
        if series is not None and series.status == BOOKED:
            series.status, series.cancelled_at, series.cancelled_by = CANCELLED, utcnow(), access.user_id
            series.cancel_reason = reason
    target = await audit.record_many(
        session,
        "booking.cancel",
        "booking",
        [(b.id, before[b.id], bsvc.snap(b)) for b in targets],
        actor=access.user,
        reason=reason,
        undo_of=ev.id,
    )
    if target is None:  # nothing was still booked: mark the undo anyway
        await audit.record(session, "booking.cancel", "booking", ev.entity_id, actor=access.user, undo_of=ev.id)
    await events.emit(session, "booking.cancelled", {"booking_ids": ids, "actor_id": access.user_id, "reason": reason})
    await session.commit()
    return {"undone": ev.id, "action": "booking.cancel", "booking_ids": ids}


async def _undo_move(session: AsyncSession, access: Access, ev: AuditEvent, b: Booking) -> dict[str, Any]:
    before = ev.before or {}
    data: dict[str, Any] = {}
    if before.get("date") and before["date"] != b.date.isoformat():
        data["date"] = date.fromisoformat(before["date"])
    if before.get("period_id") and before["period_id"] != b.period_id:
        data["period_id"] = before["period_id"]
    if before.get("room_id") and before["room_id"] != b.room_id:
        data["room_id"] = before["room_id"]
    if not data:
        raise _err(409, "nothing_to_undo", "the booking is already where it was", "rezervasyon zaten eski yerinde")
    session.info["audit_undo_of"] = ev.id
    try:
        await bsvc.update(session, access, b.id, "one", data)
    except bsvc.BookingError as exc:
        if exc.status == 409 and exc.code == "conflict":
            await _attach_alternatives(session, access, exc, before)
        raise
    finally:
        session.info.pop("audit_undo_of", None)
    return {"undone": ev.id, "action": "booking.move", "booking_ids": [b.id]}


async def _attach_alternatives(session: AsyncSession, access: Access, exc: bsvc.BookingError, snap: dict[str, Any]) -> None:
    from app.services.find_room import alternatives_for

    room = await session.get(Room, snap.get("room_id")) if snap.get("room_id") else None
    if room is None or not snap.get("date"):
        return
    exc.data["alternatives"] = await alternatives_for(
        session,
        access,
        room,
        date.fromisoformat(snap["date"]),
        int(snap["start_period"]),
        int(snap["end_period"]),
        snap.get("headcount"),
    )
    exc.data.setdefault("message_tr", "eski saat artık boş değil")


async def _undo_cancel(session: AsyncSession, access: Access, ev: AuditEvent, rows: list[Booking]) -> dict[str, Any]:
    targets = [b for b in rows if b.status == CANCELLED]
    if not targets:
        raise _err(409, "nothing_to_undo", "the bookings are not cancelled any more", "rezervasyonlar iptal değil")
    for b in targets:
        room = await session.get(Room, b.room_id)
        assert room is not None
        kind = "book_recur" if b.series_id else "book_single"
        if not (bsvc.is_owner(access, b) or access.can(f"{kind}.cancel_other_booking", room)):
            raise _err(403, "not_permitted", "you may not restore this booking", "bu rezervasyonu geri getiremezsiniz")
        held = await bsvc.find_conflict(session, b.room_id, b.date, b.start_period, b.end_period, exclude={b.id})
        if held is not None:
            exc = _err(
                409,
                "conflict",
                f"{room.display_name} on {b.date:%d.%m.%Y} P{b.start_period}-P{b.end_period} is taken now",
                f"{room.display_name} {b.date:%d.%m.%Y} P{b.start_period}-P{b.end_period} artık dolu",
                conflict=held.as_dict(),
            )
            await _attach_alternatives(session, access, exc, bsvc.snap(b))
            raise exc
    before = {b.id: bsvc.snap(b) for b in targets}
    try:
        for b in targets:
            b.status, b.cancel_reason, b.cancelled_at, b.cancelled_by = BOOKED, None, None, None
            b.updated_at, b.updated_by = utcnow(), access.user_id
            await bsvc.release_expired_holds(session, b.room_id, b.date)
            for slot in bsvc.slot_rows(b):
                session.add(slot)
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise _err(409, "conflict", "the slot was booked a moment ago", "bu saat az önce alındı") from exc
    series_ids = {b.series_id for b in targets if b.series_id}
    for sid in series_ids:
        series = await session.get(BookingSeries, sid)
        if series is not None and series.status == CANCELLED:
            series.status, series.cancel_reason, series.cancelled_at, series.cancelled_by = BOOKED, None, None, None
    await audit.record_many(
        session,
        "booking.restore",
        "booking",
        [(b.id, before[b.id], bsvc.snap(b)) for b in targets],
        actor=access.user,
        reason=f"undo of #{ev.id}",
        undo_of=ev.id,
    )
    await events.emit(
        session, "booking.created", {"booking_id": targets[0].id, "booking_ids": [b.id for b in targets], "actor_id": access.user_id}
    )
    await session.commit()
    return {"undone": ev.id, "action": "booking.restore", "booking_ids": [b.id for b in targets]}
