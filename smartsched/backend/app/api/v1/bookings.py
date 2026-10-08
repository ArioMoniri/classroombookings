"""Bookings (CRBS ``Bookings``, ``Dashboard``, ``Export``, ``Rooms::info``): grid, single / recurring /
multi bookings, edit, cancel, my bookings, dashboard, CSV export, iCalendar feeds, timetable conflicts.

Every route here honours maintenance mode (503 unless ``system.bypass_maintenance_mode``)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.api.deps import DB, CurrentAccess, require_permission
from app.importers import normalize as n
from app.models import (
    Assignment,
    Booking,
    Building,
    Course,
    MeetingRequest,
    Program,
    RoomGroup,
    ScheduleRun,
    Section,
    Term,
    TimetableWeek,
    User,
)
from app.models.catalog import Room
from app.services import bookings as svc
from app.services import bookings_calendar as cal
from app.services import bookings_export as export
from app.services import bookings_notify  # noqa: F401  (registers the notification event handlers)
from app.services import rooms_features as features
from app.services.bookings_calendar import date_infos, fgcol, term_info
from app.services.bookings_collation import tr_sort_key
from app.services.bookings_perms import Access, effective_limits
from app.services.bookings_settings import get_group, get_value

Day = date  # field names "date" shadow the type inside pydantic models

router = APIRouter(prefix="/bookings", tags=["bookings"])
ics_router = APIRouter(prefix="/ics", tags=["bookings"])


async def maintenance_gate(access: CurrentAccess, db: DB) -> Access:
    org = await get_group(db, "org")
    if org["maintenance_mode"] and not access.can("system.bypass_maintenance_mode"):
        raise HTTPException(503, org["maintenance_mode_message"] or "bookings are in maintenance mode")
    return access


Acc = Annotated[Access, Depends(maintenance_gate)]


async def list_gate(access: CurrentAccess, db: DB) -> Access:
    """Dashboard, my bookings, owned rooms and calendar feeds. CRBS's maintenance gate is the Bookings
    controller only (its Dashboard stays open); ``bookings.maintenance_gates_lists`` closes these too
    (audit deliberate difference g)."""
    if await get_value(db, "bookings", "maintenance_gates_lists"):
        return await maintenance_gate(access, db)
    return access


ListAcc = Annotated[Access, Depends(list_gate)]


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
    #: T1: filled when the booking comes from "find me a room" (P2 ranks alternatives with them)
    headcount: int | None = Field(default=None, ge=0, le=5000)
    required_features: list[Any] | None = Field(default=None, max_length=20)

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
    #: recurring only: book / do not book / replace per date of this slot's series (CRBS multi recur preview)
    instances: list[InstanceChoice] | None = None


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
        headcount=body.headcount,
        required_features=body.required_features,
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
    current = await cal.current_term_ids(db, await svc.today(db))  # CRBS: computed from the dates (audit B3)
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
                "is_current": term.id in current,
                "is_selectable": info.is_selectable,
            }
        )
    rooms = await svc.visible_rooms(db, access)
    gids = sorted({r.room_group_id for r in rooms if r.room_group_id is not None})
    groups = (
        sorted(
            await db.execute(select(RoomGroup).where(RoomGroup.id.in_(gids))),
            key=lambda row: (row[0].pos, tr_sort_key(row[0].name)),  # position, then Turkish name order
        )
        if gids
        else []
    )
    return {
        "sessions": sessions,
        "current_term_id": next(
            (s["id"] for s in sessions if s["is_current"]), sessions[0]["id"] if sessions else None
        ),
        # room_count: CRBS shows "Name (n)" on the room-group tabs (Grid.php:112)
        "room_groups": [
            {
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "room_count": sum(1 for r in rooms if r.room_group_id == g.id),
            }
            for (g,) in groups
        ]
        + (
            [
                {
                    "id": 0,
                    "name": "—",
                    "description": None,
                    "room_count": sum(1 for r in rooms if r.room_group_id is None),
                }
            ]
            if any(r.room_group_id is None for r in rooms)
            else []
        ),
        "display": {
            "type": org["displaytype"],
            "columns": org["d_columns"],
            "use_room_groups": org["use_room_groups"],
            "grid_highlight": org["grid_highlight"],  # CRBS settings/General (MISSING 5)
        },
        "date_patterns": {k: org[k] for k in ("pattern_long", "pattern_weekday", "pattern_time")},
        "permissions": sorted(access.perms),
        "limits": await effective_limits(db, access.user),
        "active_bookings": await svc.active_booking_count(db, access.user_id),
        "remaining_bookings": await svc.remaining_bookings(db, access),
    }


def _person(u: User) -> str:
    """Display name: CRBS displayname (full_name), else first + last name, else username / e-mail."""
    full = " ".join(x for x in (u.firstname, u.lastname) if x)
    return u.full_name or full or u.username or u.email or f"#{u.id}"


async def _room_info(db: DB, room: Room) -> dict[str, Any]:
    group = await db.get(RoomGroup, room.room_group_id) if room.room_group_id else None
    owner = await db.get(User, room.owner_user_id) if room.owner_user_id else None
    building = await db.get(Building, room.building_id) if room.building_id else None
    # typed features (P10): CHECKBOX/BOOLEAN bool, SELECT option text, NUMBER number, MULTISELECT option texts
    catalogue = [f for f in await features.catalogue(db) if f.public is not False]
    typed = (await features.room_values(db, [room], catalogue))[room.id]
    fields = [
        {
            "field_id": f.id,
            "name": f.name,
            "type": f.type,
            "value": features.display(f, typed[f.id]),
            "unit": f.unit,
            "icon": f.icon,
        }
        for f in catalogue
    ]
    return {
        "id": room.id,
        "code": room.code,
        "name": room.display_name,
        "capacity": room.capacity,
        # reservation panel room details: exam seating, building and floor (rooms master data)
        "exam_capacity": room.exam_capacity,
        "building": building.name if building else None,
        "building_code": building.code if building else None,
        "floor": room.floor,
        "tags": room.tags or [],
        "room_group_id": room.room_group_id,
        "group": group.name if group else None,
        "location": room.location,
        "owner_user_id": room.owner_user_id,
        "owner": _person(owner) if owner else None,
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
        out = await svc.grid(
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
    return await _grid_extras(db, access, out)


async def _grid_extras(db: DB, access: Access, out: dict[str, Any]) -> dict[str, Any]:
    """CRBS grid details the reservation panel shows: the room owner under the room name
    (``col_room.php:14-20``) and, per booked slot, whether the viewer may cancel it (multi-select bulk
    cancel, ``slot/booked.php:66-90``)."""
    rooms: dict[int, Room] = {}
    for r in out["rooms"]:
        room = await db.get(Room, r["id"])
        owner = await db.get(User, room.owner_user_id) if room is not None and room.owner_user_id else None
        r["owner"] = _person(owner) if owner else None
        if room is not None:
            rooms[room.id] = room
    for slot in out["slots"]:
        b_out = slot.get("booking")
        if not b_out:
            continue
        b = await db.get(Booking, b_out["id"])
        room = rooms.get(slot["room_id"])
        b_out["can_cancel"] = bool(
            b is not None and room is not None and b.status == "BOOKED" and await svc.can_cancel(db, access, b, room)
        )
    return out


@router.get("/users")
async def booking_users(
    db: DB,
    access: Acc,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[dict[str, Any]]:
    """ "Booked by" choices for the create / edit forms (CRBS ``single_form.php:80-95``): active users by
    display name. Guarded by ``book_single.set_user`` / ``book_recur.set_user`` (role or any room ACL), so
    planners who may book for others need no ``setup.users``."""
    perms = ("book_single.set_user", "book_recur.set_user")
    if not any(p in access.perms for p in perms) and not any(
        p in acl for acl in (*access.acl_rooms.values(), *access.acl_groups.values()) for p in perms
    ):
        raise HTTPException(403, "requires book_single.set_user or book_recur.set_user")
    users = list((await db.execute(select(User).where(User.is_active.is_(True)))).scalars())

    rows = [{"id": u.id, "name": _person(u), "username": u.username} for u in users]
    if q:
        needle = n.tr_casefold(q)
        rows = [r for r in rows if needle in n.tr_casefold(f"{r['name']} {r['username'] or ''}")]
    rows.sort(key=lambda r: tr_sort_key(str(r["name"])))
    return rows[:limit]


# --- create ---------------------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_booking(body: BookingIn, db: DB, access: Acc, response: Response) -> dict[str, Any]:
    """201 with the booking; 202 with ``status: PENDING`` when the room needs approval (P1)."""
    try:
        b = await svc.create_single(db, access, _single(body))
    except svc.BookingError as exc:
        raise _err(exc) from exc
    if b.status == "PENDING":
        response.status_code = 202
    return await svc.booking_out(db, access, b, detail=True)


@router.post("/recurring/preview")
async def recurring_preview(body: RecurringIn, db: DB, access: Acc) -> dict[str, Any]:
    try:
        return svc.plan_out(await svc.plan_recurring(db, access, _recur(body)))
    except svc.BookingError as exc:
        raise _err(exc) from exc


@router.post("/recurring", status_code=201)
async def recurring_create(body: RecurringIn, db: DB, access: Acc, response: Response) -> dict[str, Any]:
    """201; 202 with ``status: PENDING`` when the room needs approval (P1)."""
    try:
        out = await svc.create_recurring(db, access, _recur(body))
    except svc.BookingError as exc:
        raise _err(exc) from exc
    if out.get("status") == "PENDING":
        response.status_code = 202
    return out


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
        if c.instances is not None:
            d["instances"] = {i.date: {"action": i.action} for i in c.instances}
        else:
            d.pop("instances", None)
        choices[c.mbs_id] = d
    try:
        return await svc.create_from_selection(db, access, mb_id, body.type, choices, body.dry_run)
    except svc.BookingError as exc:
        raise _err(exc) from exc


# --- lists ----------------------------------------------------------------------------------------


@router.get("/mine")
async def mine(
    db: DB,
    access: ListAcc,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    status: Literal["BOOKED", "CANCELLED", "ALL"] = "BOOKED",
) -> list[dict[str, Any]]:
    return await svc.list_bookings(
        db, access, user_id=access.user_id, d_from=from_, d_to=to, status=None if status == "ALL" else status
    )


@router.get("/dashboard")
async def dashboard(db: DB, access: ListAcc) -> dict[str, Any]:
    return await svc.dashboard(db, access)


@router.get("/owned-rooms")
async def owned_rooms(db: DB, access: ListAcc) -> list[dict[str, Any]]:
    t = await svc.today(db)
    out = []
    for room in (await db.execute(select(Room).where(Room.owner_user_id == access.user_id))).scalars():
        info = await _room_info(db, room)
        info["upcoming"] = await svc.list_bookings(db, access, room_ids=[room.id], d_from=t)
        out.append(info)
    return out


@router.get("/departments/{department_id}/rooms")
async def department_rooms(
    department_id: int,
    db: DB,
    access: Acc,
    term_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> dict[str, Any]:
    """Rooms a department (programme) uses most in a session, for the reservation panel's department
    view: its active bookings plus its weekly classes in the published timetable, counted per room.
    Only bookable rooms the caller may view are listed (same set as the grid)."""
    dep = await db.get(Program, department_id)
    if dep is None:
        raise HTTPException(404, "department not found")
    if term_id is not None:
        term = await db.get(Term, term_id)
        info = await term_info(db, term) if term else None
        if info is None:
            raise HTTPException(404, "session not found")
    else:
        try:
            info = await cal.resolve_term(
                db, await svc.today(db), None, view_all=access.can("system.view_all_sessions")
            )
        except cal.CalendarError as exc:
            raise HTTPException(409, {"code": "calendar", "message": str(exc)}) from exc
    booked: dict[int, int] = {
        int(rid): int(cnt)
        for rid, cnt in await db.execute(
            select(Booking.room_id, func.count(Booking.id))
            .where(
                Booking.department_id == department_id,
                Booking.status == "BOOKED",
                Booking.date.between(info.start, info.end),
            )
            .group_by(Booking.room_id)
        )
    }
    # classes: published-timetable meetings of the department's sections (solver runs link the meeting
    # request; imported boards carry only course codes, matched to the department's courses this term)
    sections = {
        int(sid): code
        for sid, code in await db.execute(
            select(Section.id, Course.code)
            .join(Course, Course.id == Section.course_id)
            .where(Section.term_id == info.term.id, Section.program_id == department_id)
        )
    }
    codes = set(sections.values())
    classes: dict[int, int] = {}
    runs = select(ScheduleRun.id).where(ScheduleRun.term_id == info.term.id, ScheduleRun.is_active.is_(True))
    q = (
        select(Assignment.room_ids, Assignment.course_codes, MeetingRequest.section_id)
        .outerjoin(MeetingRequest, MeetingRequest.id == Assignment.meeting_request_id)
        .where(Assignment.run_id.in_(runs), Assignment.archived.is_(False))
    )
    for room_ids, course_codes, section_id in await db.execute(q):
        ours = section_id in sections if section_id is not None else bool(codes.intersection(course_codes or []))
        if not ours:
            continue
        for rid in {int(r) for r in room_ids or []}:
            classes[rid] = classes.get(rid, 0) + 1
    visible = await svc.visible_rooms(db, access)
    used = [r for r in visible if booked.get(r.id) or classes.get(r.id)]
    used.sort(key=lambda r: (-(booked.get(r.id, 0) + classes.get(r.id, 0)), tr_sort_key(r.display_name or r.code)))
    return {
        "department": {"id": dep.id, "name": dep.name},
        "term_id": info.term.id,
        "rooms": [
            {
                "room_id": r.id,
                "code": r.code,
                "name": r.display_name,
                "room_group_id": r.room_group_id,
                "capacity": r.capacity,
                "bookings": booked.get(r.id, 0),
                "classes": classes.get(r.id, 0),
            }
            for r in used[:limit]
        ],
    }


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
async def my_feed(db: DB, access: ListAcc) -> Response:
    u = access.user
    return _ics(
        await export.ics_feed(db, access, title=f"SmartSched – {u.full_name or u.username or u.email}", user_id=u.id),
        "bookings.ics",
    )


@router.get("/feed/room/{room_id}.ics")
async def room_feed(room_id: int, db: DB, access: ListAcc) -> Response:
    room = await db.get(Room, room_id)
    if room is None or not access.can_view_room(room):
        raise HTTPException(404, "room not found")
    return _ics(
        await export.ics_feed(db, access, title=f"SmartSched – {room.display_name}", room_id=room.id),
        f"{room.code}.ics",
    )


@router.post("/feed/token")
async def rotate_feed_token(db: DB, access: Acc) -> dict[str, Any]:
    """New secret for calendar subscriptions; every older link of the user stops working (= ``POST
    /calendar/feeds/reset``, docs/product/calendar-sync-api.md). Only the token's SHA-256 is stored."""
    from app.services import calendar_feeds

    row, tok = await calendar_feeds.reset_tokens(db, access.user)
    await db.commit()
    urls = await calendar_feeds.url_templates(db, tok)
    return {
        "token": tok,
        "user_feed": f"/api/v1/ics/{tok}/user.ics",
        "room_feed": f"/api/v1/ics/{tok}/room/{{room_id}}.ics",
        **calendar_feeds.token_out(row),
        "urls": urls,
        "subscribe": calendar_feeds.subscribe_links(urls["mine"]),
    }


@ics_router.get("/{token}/user.ics")
async def token_user_feed(token: str, request: Request, db: DB) -> Response:
    from app.api.v1 import calendar_sync

    return await calendar_sync.serve_feed(request, db, token, "mine", None)


@ics_router.get("/{token}/room/{room_id}.ics")
async def token_room_feed(token: str, room_id: int, request: Request, db: DB) -> Response:
    from app.api.v1 import calendar_sync

    return await calendar_sync.serve_feed(request, db, token, "room", room_id)


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
