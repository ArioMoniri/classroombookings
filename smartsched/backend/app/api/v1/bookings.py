"""Bookings (CRBS ``Bookings``, ``Dashboard``, ``Export``, ``Rooms::info``): grid, single / recurring /
multi bookings, edit, cancel, my bookings, dashboard, CSV export, iCalendar feeds, timetable conflicts.

Every route here honours maintenance mode (503 unless ``system.bypass_maintenance_mode``)."""

from __future__ import annotations

import secrets
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.api.deps import DB, CurrentAccess, require_permission
from app.importers import normalize as n
from app.models import (
    Booking,
    Program,
    RoomCustomField,
    RoomCustomFieldValue,
    RoomGroup,
    Term,
    TimetableWeek,
    User,
)
from app.models.catalog import Room
from app.services import bookings as svc
from app.services import bookings_calendar as cal
from app.services import bookings_export as export
from app.services import bookings_notify  # noqa: F401  (registers the notification event handlers)
from app.services.bookings_calendar import date_infos, fgcol, term_info
from app.services.bookings_perms import Access, effective_limits, load_access
from app.services.bookings_settings import get_group

Day = date  # field names "date" shadow the type inside pydantic models

router = APIRouter(prefix="/bookings", tags=["bookings"])
ics_router = APIRouter(prefix="/ics", tags=["bookings"])


async def maintenance_gate(access: CurrentAccess, db: DB) -> Access:
    org = await get_group(db, "org")
    if org["maintenance_mode"] and not access.can("system.bypass_maintenance_mode"):
        raise HTTPException(503, org["maintenance_mode_message"] or "bookings are in maintenance mode")
    return access


Acc = Annotated[Access, Depends(maintenance_gate)]


def _err(exc: svc.BookingError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


def _notes(v: str | None) -> str | None:
    text = n.clean_text(v) if v is not None else None
    if text is not None and len(text) > 255:
        raise ValueError("notes are limited to 255 characters")
    return text


# --- schemas ---------------------------------------------------------------------------------------


class BookingIn(BaseModel):
    room_id: int
    date: Day
    period_id: int
    notes: str | None = None
    user_id: int | None = None
    department_id: int | None = None
    term_id: int | None = None

    @model_validator(mode="after")
    def _clean(self) -> BookingIn:
        self.notes = _notes(self.notes)
        return self


class InstanceChoice(BaseModel):
    date: Day
    action: Literal["book", "do_not_book", "replace"]


class RecurringIn(BaseModel):
    room_id: int
    period_id: int
    date: Day
    start: Day | Literal["session"] | None = None
    end: Day | Literal["session"] | None = None
    notes: str | None = None
    user_id: int | None = None
    department_id: int | None = None
    term_id: int | None = None
    instances: list[InstanceChoice] | None = None

    @model_validator(mode="after")
    def _clean(self) -> RecurringIn:
        self.notes = _notes(self.notes)
        return self


class SlotIn(BaseModel):
    date: Day
    period_id: int
    room_id: int


class SelectionIn(BaseModel):
    slots: list[SlotIn] = Field(min_length=1, max_length=500)
    term_id: int | None = None


class SlotChoice(BaseModel):
    mbs_id: int
    create: bool = True
    notes: str | None = None
    user_id: int | None = None
    department_id: int | None = None
    recurring_start: Day | Literal["session"] | None = None
    recurring_end: Day | Literal["session"] | None = None


class MultiCreateIn(BaseModel):
    type: Literal["single", "recurring"] = "single"
    slots: list[SlotChoice] = Field(default_factory=list)
    dry_run: bool = False


class UpdateIn(BaseModel):
    date: Day | None = None
    period_id: int | None = None
    room_id: int | None = None
    notes: str | None = None
    user_id: int | None = None
    department_id: int | None = None


class CancelIn(BaseModel):
    scope: Literal["one", "future", "all"] = "one"
    reason: str | None = Field(default=None, max_length=1000)


class CancelManyIn(BaseModel):
    booking_ids: list[int] = Field(min_length=1, max_length=1000)
    reason: str | None = Field(default=None, max_length=1000)


def _single(body: BookingIn) -> svc.SingleIn:
    sent = body.model_fields_set
    return svc.SingleIn(
        room_id=body.room_id,
        date=body.date,
        period_id=body.period_id,
        notes=body.notes,
        user_id=body.user_id,
        department_id=body.department_id,
        term_id=body.term_id,
        user_given="user_id" in sent,
        department_given="department_id" in sent,
    )


def _recur(body: RecurringIn) -> svc.RecurIn:
    sent = body.model_fields_set
    return svc.RecurIn(
        room_id=body.room_id,
        period_id=body.period_id,
        date=body.date,
        start=body.start if isinstance(body.start, date) else None,
        end=body.end if isinstance(body.end, date) else None,
        notes=body.notes,
        user_id=body.user_id,
        department_id=body.department_id,
        term_id=body.term_id,
        user_given="user_id" in sent,
        department_given="department_id" in sent,
        instances={i.date: {"action": i.action} for i in body.instances} if body.instances is not None else None,
    )


# --- context, rooms, grid --------------------------------------------------------------------------


@router.get("/context")
async def context(db: DB, access: Acc) -> dict[str, Any]:
    """Sessions the user may use, room groups, display settings, the user's limits and active count."""
    org = await get_group(db, "org")
    view_all = access.can("system.view_all_sessions")
    sessions = []
    for term in (await db.execute(select(Term).order_by(Term.start_date.desc().nullslast(), Term.id))).scalars():
        info = await term_info(db, term)
        if info is None or not (view_all or info.is_selectable):
            continue
        sessions.append(
            {
                "id": term.id,
                "code": term.code,
                "name": term.name,
                "start": info.start.isoformat(),
                "end": info.end.isoformat(),
                "is_current": term.is_active,
                "is_selectable": info.is_selectable,
            }
        )
    rooms = await svc.visible_rooms(db, access)
    gids = sorted({r.room_group_id for r in rooms if r.room_group_id is not None})
    groups = (
        list(await db.execute(select(RoomGroup).where(RoomGroup.id.in_(gids)).order_by(RoomGroup.pos))) if gids else []
    )
    return {
        "sessions": sessions,
        "current_term_id": next(
            (s["id"] for s in sessions if s["is_current"]), sessions[0]["id"] if sessions else None
        ),
        "room_groups": [{"id": g.id, "name": g.name, "description": g.description} for (g,) in groups]
        + ([{"id": 0, "name": "—", "description": None}] if any(r.room_group_id is None for r in rooms) else []),
        "display": {"type": org["displaytype"], "columns": org["d_columns"], "use_room_groups": org["use_room_groups"]},
        "date_patterns": {k: org[k] for k in ("pattern_long", "pattern_weekday", "pattern_time")},
        "permissions": sorted(access.perms),
        "limits": await effective_limits(db, access.user),
        "active_bookings": await svc.active_booking_count(db, access.user_id),
        "remaining_bookings": await svc.remaining_bookings(db, access),
    }


async def _room_info(db: DB, room: Room) -> dict[str, Any]:
    group = await db.get(RoomGroup, room.room_group_id) if room.room_group_id else None
    owner = await db.get(User, room.owner_user_id) if room.owner_user_id else None
    fields = []
    values = {
        v.field_id: v.value
        for v in (
            await db.execute(select(RoomCustomFieldValue).where(RoomCustomFieldValue.room_id == room.id))
        ).scalars()
    }
    for f in (await db.execute(select(RoomCustomField).order_by(RoomCustomField.pos, RoomCustomField.name))).scalars():
        raw = values.get(f.id)
        val: Any = raw
        if f.type == "CHECKBOX":
            val = raw == "1"
        elif f.type == "SELECT":
            val = next((o.value for o in f.options if str(o.id) == str(raw)), None)
        fields.append({"field_id": f.id, "name": f.name, "type": f.type, "value": val})
    return {
        "id": room.id,
        "code": room.code,
        "name": room.display_name,
        "capacity": room.capacity,
        "tags": room.tags or [],
        "room_group_id": room.room_group_id,
        "group": group.name if group else None,
        "location": room.location,
        "owner_user_id": room.owner_user_id,
        "owner": (owner.full_name or owner.username or owner.email) if owner else None,
        "notes": room.notes,
        "icon": room.icon,
        "photo_url": room.photo_url,
        "fields": fields,
    }


@router.get("/rooms")
async def rooms(db: DB, access: Acc, room_group_id: int | None = None) -> list[dict[str, Any]]:
    out = await svc.visible_rooms(db, access)
    if room_group_id is not None:
        out = [r for r in out if (r.room_group_id or 0) == room_group_id]
    return [await _room_info(db, r) for r in out]


@router.get("/rooms/{room_id}")
async def room_detail(room_id: int, db: DB, access: Acc) -> dict[str, Any]:
    room = await db.get(Room, room_id)
    if room is None or not access.can_view_room(room):
        raise HTTPException(404, "room not found")
    return await _room_info(db, room)


@router.get("/dates")
async def dates(
    db: DB,
    access: Acc,
    term_id: int | None = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> dict[str, Any]:
    """Date picker data (CRBS ``Bookings::filter('date')``): each date with its timetable week (colours),
    holiday and whether it is open for bookings; at most one term's range."""
    t = await svc.today(db)
    try:
        info = await cal.resolve_term(db, from_ or t, term_id, view_all=access.can("system.view_all_sessions"))
    except cal.CalendarError as exc:
        raise HTTPException(409, {"code": "calendar", "message": str(exc)}) from exc
    start = max(from_ or info.start, info.start)
    end = min(to or info.end, info.end)
    if (end - start).days > 400:
        raise HTTPException(422, "range too long")
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    infos = await date_infos(db, info, days)
    weeks = {
        w.id: {"id": w.id, "name": w.name, "bgcol": f"#{w.bgcol}", "fgcol": fgcol(w.bgcol)}
        for w in (await db.execute(select(TimetableWeek))).scalars()
    }
    return {
        "term_id": info.term.id,
        "today": t.isoformat(),
        "weeks": list(weeks.values()),
        "dates": [
            {
                "date": d.isoformat(),
                "weekday": x.weekday,
                "term_week": x.term_week,
                "timetable_week_id": x.timetable_week_id,
                "holiday": x.holiday,
                "open": x.open,
                "reason": x.reason,
            }
            for d, x in infos.items()
        ],
    }


@router.get("/grid")
async def grid(
    db: DB,
    access: Acc,
    display: Literal["day", "room"] | None = None,
    date_: Annotated[date | None, Query(alias="date")] = None,
    term_id: int | None = None,
    room_group_id: int | None = None,
    room_id: int | None = None,
) -> dict[str, Any]:
    org = await get_group(db, "org")
    try:
        return await svc.grid(
            db,
            access,
            display=display or org["displaytype"],
            d=date_,
            term_id=term_id,
            room_group_id=room_group_id,
            room_id=room_id,
            use_room_groups=org["use_room_groups"],
        )
    except cal.CalendarError as exc:
        raise HTTPException(409, {"code": "calendar", "message": str(exc)}) from exc


# --- create ---------------------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_booking(body: BookingIn, db: DB, access: Acc) -> dict[str, Any]:
    try:
        b = await svc.create_single(db, access, _single(body))
    except svc.BookingError as exc:
        raise _err(exc) from exc
    return await svc.booking_out(db, access, b, detail=True)


@router.post("/recurring/preview")
async def recurring_preview(body: RecurringIn, db: DB, access: Acc) -> dict[str, Any]:
    try:
        return svc.plan_out(await svc.plan_recurring(db, access, _recur(body)))
    except svc.BookingError as exc:
        raise _err(exc) from exc


@router.post("/recurring", status_code=201)
async def recurring_create(body: RecurringIn, db: DB, access: Acc) -> dict[str, Any]:
    try:
        return await svc.create_recurring(db, access, _recur(body))
    except svc.BookingError as exc:
        raise _err(exc) from exc


@router.post("/multi", status_code=201)
async def multi_select(body: SelectionIn, db: DB, access: Acc) -> dict[str, Any]:
    try:
        mb = await svc.create_selection(db, access, [{**s.model_dump(), "term_id": body.term_id} for s in body.slots])
        return await svc.selection_out(db, access, mb)
    except svc.BookingError as exc:
        raise _err(exc) from exc


@router.get("/multi/{mb_id}")
async def multi_get(mb_id: int, db: DB, access: Acc) -> dict[str, Any]:
    try:
        return await svc.selection_out(db, access, await svc.get_selection(db, access, mb_id))
    except svc.BookingError as exc:
        raise _err(exc) from exc


@router.delete("/multi/{mb_id}", status_code=204)
async def multi_delete(mb_id: int, db: DB, access: Acc) -> None:
    try:
        mb = await svc.get_selection(db, access, mb_id)
    except svc.BookingError as exc:
        raise _err(exc) from exc
    await db.delete(mb)
    await db.commit()


@router.post("/multi/{mb_id}/create")
async def multi_create(mb_id: int, body: MultiCreateIn, db: DB, access: Acc) -> dict[str, Any]:
    choices: dict[int, dict[str, Any]] = {}
    for c in body.slots:
        d = c.model_dump(exclude_unset=True)
        d.pop("mbs_id", None)
        for k in ("recurring_start", "recurring_end"):
            if d.get(k) == "session":
                d.pop(k)
        if "notes" in d:
            d["notes"] = _notes(d["notes"])
        choices[c.mbs_id] = d
    try:
        return await svc.create_from_selection(db, access, mb_id, body.type, choices, body.dry_run)
    except svc.BookingError as exc:
        raise _err(exc) from exc


# --- lists ----------------------------------------------------------------------------------------


@router.get("/mine")
async def mine(
    db: DB,
    access: Acc,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    status: Literal["BOOKED", "CANCELLED", "ALL"] = "BOOKED",
) -> list[dict[str, Any]]:
    return await svc.list_bookings(
        db, access, user_id=access.user_id, d_from=from_, d_to=to, status=None if status == "ALL" else status
    )


@router.get("/dashboard")
async def dashboard(db: DB, access: Acc) -> dict[str, Any]:
    return await svc.dashboard(db, access)


@router.get("/owned-rooms")
async def owned_rooms(db: DB, access: Acc) -> list[dict[str, Any]]:
    t = await svc.today(db)
    out = []
    for room in (await db.execute(select(Room).where(Room.owner_user_id == access.user_id))).scalars():
        info = await _room_info(db, room)
        info["upcoming"] = await svc.list_bookings(db, access, room_ids=[room.id], d_from=t)
        out.append(info)
    return out


@router.get("/conflicts", dependencies=[Depends(require_permission("planning.view"))])
async def conflicts(db: DB, access: Acc, term_id: int | None = None) -> list[dict[str, Any]]:
    return await svc.conflicts_with_timetable(db, term_id)


@router.get("/export.csv", dependencies=[Depends(require_permission("system.export_bookings"))])
async def export_csv(
    db: DB, access: Acc, term_id: int | None = None, room_group_id: int | None = None, include_cancelled: bool = False
) -> Response:
    text = await export.export_csv(
        db, term_id=term_id, room_group_id=room_group_id, include_cancelled=include_cancelled
    )
    name = "bookings.csv"
    if term_id is not None:
        term = await db.get(Term, term_id)
        if term is not None:
            name = f"bookings-{term.code}.csv"
    return Response(
        text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# --- iCalendar --------------------------------------------------------------------------------------


def _ics(text: str, name: str) -> Response:
    return Response(
        text.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


@router.get("/feed/user.ics")
async def my_feed(db: DB, access: Acc) -> Response:
    u = access.user
    return _ics(
        await export.ics_feed(db, access, title=f"SmartSched – {u.full_name or u.username or u.email}", user_id=u.id),
        "bookings.ics",
    )


@router.get("/feed/room/{room_id}.ics")
async def room_feed(room_id: int, db: DB, access: Acc) -> Response:
    room = await db.get(Room, room_id)
    if room is None or not access.can_view_room(room):
        raise HTTPException(404, "room not found")
    return _ics(
        await export.ics_feed(db, access, title=f"SmartSched – {room.display_name}", room_id=room.id),
        f"{room.code}.ics",
    )


@router.post("/feed/token")
async def rotate_feed_token(db: DB, access: Acc) -> dict[str, str]:
    """New secret for calendar subscriptions (``/ics/{token}/…``); the old links stop working."""
    access.user.calendar_token = secrets.token_urlsafe(32)
    await db.commit()
    tok = access.user.calendar_token
    return {
        "token": tok,
        "user_feed": f"/api/v1/ics/{tok}/user.ics",
        "room_feed": f"/api/v1/ics/{tok}/room/{{room_id}}.ics",
    }


async def _token_access(db: DB, token: str) -> Access:
    if len(token) < 20:
        raise HTTPException(404, "feed not found")
    user = (await db.execute(select(User).where(User.calendar_token == token))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(404, "feed not found")
    return await load_access(db, user)


@ics_router.get("/{token}/user.ics")
async def token_user_feed(token: str, db: DB) -> Response:
    access = await _token_access(db, token)
    u = access.user
    return _ics(
        await export.ics_feed(db, access, title=f"SmartSched – {u.full_name or u.username or u.email}", user_id=u.id),
        "bookings.ics",
    )


@ics_router.get("/{token}/room/{room_id}.ics")
async def token_room_feed(token: str, room_id: int, db: DB) -> Response:
    access = await _token_access(db, token)
    room = await db.get(Room, room_id)
    if room is None or not access.can_view_room(room):
        raise HTTPException(404, "room not found")
    return _ics(
        await export.ics_feed(db, access, title=f"SmartSched – {room.display_name}", room_id=room.id),
        f"{room.code}.ics",
    )


# --- one booking (keep these after the fixed paths above) -------------------------------------------


async def _booking(db: DB, access: Access, booking_id: int) -> Booking:
    b = await db.get(Booking, booking_id)
    if b is None:
        raise HTTPException(404, "booking not found")
    room = await db.get(Room, b.room_id)
    if room is None or not (access.can_view_room(room) or svc.is_owner(access, b)):
        raise HTTPException(404, "booking not found")
    return b


@router.get("/{booking_id}")
async def get_booking(booking_id: int, db: DB, access: Acc) -> dict[str, Any]:
    b = await _booking(db, access, booking_id)
    out = await svc.booking_out(db, access, b, detail=True)
    out["room"] = await _room_info(db, await db.get(Room, b.room_id))  # type: ignore[arg-type]
    if b.department_id:
        dep = await db.get(Program, b.department_id)
        out["department_name"] = dep.name if dep else None
    return out


@router.get("/{booking_id}/series")
async def get_series(booking_id: int, db: DB, access: Acc) -> list[dict[str, Any]]:
    b = await _booking(db, access, booking_id)
    if not b.series_id:
        raise HTTPException(404, "not a recurring booking")
    rows = (await db.execute(select(Booking).where(Booking.series_id == b.series_id).order_by(Booking.date))).scalars()
    return [await svc.booking_out(db, access, x) for x in rows]


@router.put("/{booking_id}")
async def update_booking(
    booking_id: int, body: UpdateIn, db: DB, access: Acc, scope: Literal["one", "future", "all"] = "one"
) -> list[dict[str, Any]]:
    await _booking(db, access, booking_id)
    data = body.model_dump(exclude_unset=True)
    if "notes" in data:
        try:
            data["notes"] = _notes(data["notes"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if not data:
        raise HTTPException(422, "nothing to change")
    try:
        rows = await svc.update(db, access, booking_id, scope, data)
    except svc.BookingError as exc:
        raise _err(exc) from exc
    return [await svc.booking_out(db, access, b) for b in rows]


@router.post("/{booking_id}/cancel")
async def cancel_booking(booking_id: int, body: CancelIn, db: DB, access: Acc) -> dict[str, Any]:
    await _booking(db, access, booking_id)
    try:
        ids = await svc.cancel(db, access, booking_id, body.scope, n.clean_text(body.reason) if body.reason else None)
    except svc.BookingError as exc:
        raise _err(exc) from exc
    return {"cancelled": ids}


@router.post("/cancel-multi")
async def cancel_many(body: CancelManyIn, db: DB, access: Acc) -> dict[str, Any]:
    return await svc.cancel_many(db, access, body.booking_ids, n.clean_text(body.reason) if body.reason else None)
