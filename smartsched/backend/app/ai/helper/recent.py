"""The person's own last confirmed helper actions (HB-D; ``GET /helper/actions/recent?limit=5``).

Read from ``helper_action_invocations`` (one row per confirmed click; RLS ``rls_owner`` plus an explicit
``user_id`` filter, so nobody else's rows are ever read). Each row: the action, the entity kind and id, a short
TR/EN label built from database values (room, day, time; never another person's name or a note of someone else),
when it was done, its status and whether "Geri al" is still possible, with a fresh ``undo_token`` then.

``undoable`` is the server's best estimate (24 h after the click, before the booking starts, the booking still in the
state the click left it, the note still there); ``POST /helper/actions/undo`` re-checks everything and may still
answer 409 (``bookings_undo`` sees a later change).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.helper import cards, schema
from app.models.base import utcnow
from app.models.helper import HelperActionInvocation, HelperNote
from app.services.bookings_perms import Access

MAX_LIMIT = 20
#: past-tense labels (Turkish first)
DONE_LABELS: dict[str, tuple[str, str]] = {
    "create_booking": ("Rezervasyon yapıldı", "Booked"),
    "cancel_my_booking": ("Rezervasyon iptal edildi", "Booking cancelled"),
    "withdraw_my_request": ("Talep geri çekildi", "Request withdrawn"),
    "decide_approval": ("Talep karara bağlandı", "Request decided"),
    "undo_last_helper_action": ("Geri alındı", "Undone"),
    "remember_note": ("Not kaydedildi", "Note saved"),
}
FEATURES = {"booking": "my_bookings", "approval_request": "requests", "note": "profile.helper_memory"}
#: the booking status a click leaves (undo is offered only while it still holds)
_LEFT = {"create_booking": ("BOOKED", "PENDING"), "cancel_my_booking": ("CANCELLED",)}


async def _booking(session: AsyncSession, booking_id: int) -> tuple[str | None, datetime | None, str | None]:
    """(label, start as naive UTC, status) of one of the person's bookings."""
    from app.models import Booking, BookingPeriod
    from app.models.catalog import Room
    from app.services import bookings as bsvc

    b = await session.get(Booking, booking_id)
    if b is None:
        return None, None, None
    room = await session.get(Room, b.room_id)
    period = await session.get(BookingPeriod, b.period_id)
    label = f"{room.display_name if room else ''} · {b.date:%d.%m.%Y}"
    start_local = datetime.combine(b.date, period.time_start if period else datetime.min.time())
    if period is not None:
        label += f" {period.time_start:%H:%M}"
    start = utcnow() + (start_local - await bsvc.now_local(session))
    return label.strip(" ·"), start, b.status


async def _request(session: AsyncSession, request_id: int) -> str | None:
    from app.models import ApprovalRequest
    from app.models.catalog import Room

    req = await session.get(ApprovalRequest, request_id)
    room = await session.get(Room, req.room_id) if req is not None else None
    return room.display_name if room is not None else None


async def recent(session: AsyncSession, access: Access, limit: int = 5) -> list[dict[str, Any]]:
    from app.ai.helper import confirm as cf
    from app.ai.helper.index import get_index

    known = {e.id for e in get_index().entries}
    rows = (
        (
            await session.execute(
                select(HelperActionInvocation)
                .where(
                    HelperActionInvocation.user_id == access.user_id,
                    HelperActionInvocation.status.in_(("done", "undone")),
                )
                .order_by(HelperActionInvocation.id.desc())
                .limit(max(1, min(limit, MAX_LIMIT)))
            )
        )
        .scalars()
        .all()
    )
    now = utcnow()
    out: list[dict[str, Any]] = []
    for inv in rows:
        tr, en = DONE_LABELS.get(inv.action, (inv.action, inv.action))
        detail: str | None = None
        until: datetime | None = None
        possible = inv.status == "done" and inv.undo_of is None and inv.done_at is not None
        if inv.entity_type == "booking" and inv.entity_id is not None:
            detail, start, status = await _booking(session, inv.entity_id)
            possible = possible and inv.undo_event_id is not None and status in _LEFT.get(inv.action, ())
            if possible and inv.done_at is not None and start is not None:
                until = min(inv.done_at + cf.UNDO_TTL, start)
        elif inv.entity_type == "approval_request" and inv.entity_id is not None:
            detail = await _request(session, inv.entity_id)
            possible = False  # withdrawals and decisions have no undo
        elif inv.entity_type == "note" and inv.entity_id is not None:
            note = await session.get(HelperNote, inv.entity_id)
            mine = note is not None and note.user_id == access.user_id
            detail = note.text if mine and note is not None else None
            if possible and mine and inv.done_at is not None:
                until = inv.done_at + cf.UNDO_TTL
        else:
            possible = False
        undoable = bool(possible and until is not None and until > now)
        if detail:
            tr, en = f"{tr}: {detail}", f"{en}: {detail}"
        feature = FEATURES.get(inv.entity_type or "")
        row: dict[str, Any] = {
            "id": inv.id,
            "action": inv.action,
            "kind": inv.entity_type,
            "entity_id": inv.entity_id,
            "feature_id": feature if feature in known else None,
            "label": {"tr": cards.clean(tr, 120), "en": cards.clean(en, 120)},
            "at": schema.utc_iso(inv.done_at or inv.created_at),
            "status": inv.status,
            "undoable": undoable,
        }
        if undoable and until is not None:
            row["undo_token"] = cf.undo_token(access.user_id, inv.id, until)
            row["undo_expires_at"] = schema.utc_iso(until)
        out.append(row)
    return out


__all__ = ["DONE_LABELS", "MAX_LIMIT", "recent"]
