"""Booking setup (CRBS ``Sessions``, ``Room_schedules``, ``Schedules``, ``Periods``, ``Weeks``,
``setup/Access_checker``) and the notification outbox."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select

from app.api.deps import DB, require_permission
from app.importers import normalize as n
from app.models import (
    Booking,
    BookingPeriod,
    BookingSchedule,
    Holiday,
    NotificationOutbox,
    Permission,
    RoomGroup,
    Term,
    TermBookingSettings,
    TermDate,
    TermSchedule,
    TimetableWeek,
    User,
)
from app.models.catalog import Room
from app.schemas.crbs import (
    ApplyWeekIn,
    DatesIn,
    PeriodIn,
    PeriodOut,
    PeriodUpdate,
    ScheduleIn,
    ScheduleOut,
    ScheduleUpdate,
    SessionOut,
    SessionSettingsIn,
    TermScheduleIn,
    TimetableWeekIn,
    TimetableWeekOut,
    TimetableWeekUpdate,
)
from app.services.bookings_calendar import date_infos, fgcol, grid_span, parse_clock, term_info
from app.services.bookings_notify import deliver
from app.services.bookings_perms import BOOKING_SCOPE_GROUPS, load_access

router = APIRouter(prefix="/booking-admin", tags=["booking-admin"])
SessionsAdmin = Annotated[User, Depends(require_permission("setup.sessions"))]
SchedulesAdmin = Annotated[User, Depends(require_permission("setup.schedules"))]
WeeksAdmin = Annotated[User, Depends(require_permission("setup.timetable_weeks"))]
SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]
CheckerUser = Annotated[User, Depends(require_permission("setup.rooms_acl", "setup.users"))]


# --- sessions (terms) ---------------------------------------------------------------------------------


async def _term(db: DB, term_id: int) -> Term:
    t = await db.get(Term, term_id)
    if t is None:
        raise HTTPException(404, "term not found")
    return t


async def _session_out(db: DB, t: Term) -> SessionOut:
    info = await term_info(db, t)
    mapped = (
        await db.execute(
            select(func.count())
            .select_from(TermDate)
            .where(TermDate.term_id == t.id, TermDate.timetable_week_id.is_not(None))
        )
    ).scalar_one()
    hols = (await db.execute(select(func.count(Holiday.id)).where(Holiday.term_id == t.id))).scalar_one()
    return SessionOut(
        term_id=t.id,
        code=t.code,
        name=t.name,
        kind=t.kind,
        date_start=info.start if info else t.start_date,
        date_end=info.end if info else t.end_date,
        is_current=t.is_active,
        is_selectable=info.is_selectable if info else False,
        default_schedule_id=info.default_schedule_id if info else None,
        mapped_dates=int(mapped),
        holidays=int(hols),
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(db: DB, _: SessionsAdmin) -> list[SessionOut]:
    return [await _session_out(db, t) for t in (await db.execute(select(Term).order_by(Term.id.desc()))).scalars()]


@router.put("/sessions/{term_id}", response_model=SessionOut)
async def update_session(term_id: int, body: SessionSettingsIn, db: DB, _: SessionsAdmin) -> SessionOut:
    t = await _term(db, term_id)
    row = await db.get(TermBookingSettings, t.id)
    if row is None:
        row = TermBookingSettings(term_id=t.id, is_selectable=bool(t.is_active))
        db.add(row)
    data = body.model_dump(exclude_unset=True)
    if (
        data.get("default_schedule_id") is not None
        and await db.get(BookingSchedule, data["default_schedule_id"]) is None
    ):
        raise HTTPException(422, f"schedule {data['default_schedule_id']} not found")
    if data.get("is_selectable") is not None:
        row.is_selectable = data["is_selectable"]
    if "default_schedule_id" in data:
        new_default = data["default_schedule_id"]
        # CRBS init_new_session: groups without a schedule get the default
        if new_default is not None:
            have = {
                ts.room_group_id
                for ts in (await db.execute(select(TermSchedule).where(TermSchedule.term_id == t.id))).scalars()
            }
            for g in (await db.execute(select(RoomGroup))).scalars():
                if g.id not in have:
                    db.add(TermSchedule(term_id=t.id, room_group_id=g.id, schedule_id=new_default))
        row.default_schedule_id = new_default
    await db.commit()
    return await _session_out(db, t)


@router.get("/sessions/{term_id}/schedules")
async def get_term_schedules(term_id: int, db: DB, _: SessionsAdmin) -> list[dict[str, Any]]:
    await _term(db, term_id)
    rows = {
        ts.room_group_id: ts
        for ts in (await db.execute(select(TermSchedule).where(TermSchedule.term_id == term_id))).scalars()
    }
    out = []
    for g in (await db.execute(select(RoomGroup).order_by(RoomGroup.pos))).scalars():
        ts = rows.get(g.id)
        out.append({"room_group_id": g.id, "room_group": g.name, "schedule_id": ts.schedule_id if ts else None})
    return out


@router.put("/sessions/{term_id}/schedules")
async def put_term_schedules(
    term_id: int, body: list[TermScheduleIn], db: DB, _: SessionsAdmin
) -> list[dict[str, Any]]:
    await _term(db, term_id)
    for item in body:
        if await db.get(RoomGroup, item.room_group_id) is None:
            raise HTTPException(422, f"room group {item.room_group_id} not found")
        if await db.get(BookingSchedule, item.schedule_id) is None:
            raise HTTPException(422, f"schedule {item.schedule_id} not found")
        row = await db.get(TermSchedule, (term_id, item.room_group_id))
        if row is None:
            db.add(TermSchedule(term_id=term_id, room_group_id=item.room_group_id, schedule_id=item.schedule_id))
        else:
            row.schedule_id = item.schedule_id
    await db.commit()
    return await get_term_schedules(term_id, db, _)


@router.get("/sessions/{term_id}/dates")
async def get_dates(term_id: int, db: DB, _: SessionsAdmin) -> dict[str, Any]:
    t = await _term(db, term_id)
    info = await term_info(db, t)
    if info is None:
        raise HTTPException(409, f"term {t.code} has no dates")
    days = [info.start + timedelta(days=i) for i in range((info.end - info.start).days + 1)]
    infos = await date_infos(db, info, days)
    return {
        "term_id": t.id,
        "start": info.start.isoformat(),
        "end": info.end.isoformat(),
        "dates": [
            {
                "date": d.isoformat(),
                "weekday": x.weekday,
                "term_week": x.term_week,
                "timetable_week_id": x.timetable_week_id,
                "holiday": x.holiday,
                "open": x.open,
            }
            for d, x in infos.items()
        ],
    }


@router.put("/sessions/{term_id}/dates")
async def put_dates(term_id: int, body: DatesIn, db: DB, _: SessionsAdmin) -> dict[str, Any]:
    """``Dates_model::set_weeks``: assign a timetable week (or none) to dates of the term."""
    t = await _term(db, term_id)
    info = await term_info(db, t)
    if info is None:
        raise HTTPException(409, f"term {t.code} has no dates")
    weeks = {w.id for w in (await db.execute(select(TimetableWeek))).scalars()}
    for d, wid in body.dates.items():
        if not (info.start <= d <= info.end):
            continue
        if wid is not None and wid not in weeks:
            raise HTTPException(422, f"timetable week {wid} not found")
        row = await db.get(TermDate, (t.id, d))
        if row is None:
            db.add(TermDate(term_id=t.id, date=d, timetable_week_id=wid))
        else:
            row.timetable_week_id = wid
    await db.commit()
    return await get_dates(term_id, db, _)


@router.post("/sessions/{term_id}/apply-week")
async def apply_week(term_id: int, body: ApplyWeekIn, db: DB, _: SessionsAdmin) -> dict[str, Any]:
    """``Dates_model::apply_week``: one timetable week for every date of the term."""
    t = await _term(db, term_id)
    info = await term_info(db, t)
    if info is None:
        raise HTTPException(409, f"term {t.code} has no dates")
    if body.timetable_week_id is not None and await db.get(TimetableWeek, body.timetable_week_id) is None:
        raise HTTPException(422, f"timetable week {body.timetable_week_id} not found")
    await db.execute(delete(TermDate).where(TermDate.term_id == t.id))
    d = info.start
    while d <= info.end:
        db.add(TermDate(term_id=t.id, date=d, timetable_week_id=body.timetable_week_id))
        d += timedelta(days=1)
    await db.commit()
    return await get_dates(term_id, db, _)


# --- schedules and periods ----------------------------------------------------------------------------


def _period_out(p: BookingPeriod) -> PeriodOut:
    return PeriodOut(
        id=p.id,
        schedule_id=p.schedule_id,
        name=p.name,
        time_start=f"{p.time_start:%H:%M}",
        time_end=f"{p.time_end:%H:%M}",
        bookable=p.bookable,
        days=[int(x) for x in (p.days or [])],
        start_period=p.start_period,
        end_period=p.end_period,
    )


def _schedule_out(s: BookingSchedule) -> ScheduleOut:
    return ScheduleOut(
        id=s.id, name=s.name, description=s.description, type=s.type, periods=[_period_out(p) for p in s.periods]
    )


async def _schedule(db: DB, sid: int) -> BookingSchedule:
    s = await db.get(BookingSchedule, sid)
    if s is None:
        raise HTTPException(404, "schedule not found")
    return s


@router.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(db: DB, _: SchedulesAdmin) -> list[ScheduleOut]:
    return [
        _schedule_out(s) for s in (await db.execute(select(BookingSchedule).order_by(BookingSchedule.name))).scalars()
    ]


@router.post("/schedules", response_model=ScheduleOut, status_code=201)
async def create_schedule(body: ScheduleIn, db: DB, _: SchedulesAdmin) -> ScheduleOut:
    s = BookingSchedule(name=body.name, description=body.description)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _schedule_out(s)


@router.get("/schedules/{sid}", response_model=ScheduleOut)
async def get_schedule(sid: int, db: DB, _: SchedulesAdmin) -> ScheduleOut:
    return _schedule_out(await _schedule(db, sid))


@router.put("/schedules/{sid}", response_model=ScheduleOut)
async def update_schedule(sid: int, body: ScheduleUpdate, db: DB, _: SchedulesAdmin) -> ScheduleOut:
    s = await _schedule(db, sid)
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        s.name = n.clean_text(data["name"]) or s.name
    if "description" in data:
        s.description = data["description"]
    await db.commit()
    await db.refresh(s)
    return _schedule_out(s)


@router.delete("/schedules/{sid}", status_code=204)
async def delete_schedule(sid: int, db: DB, _: SchedulesAdmin) -> None:
    s = await _schedule(db, sid)
    pids = [p.id for p in s.periods]
    if pids:
        used = (
            await db.execute(
                select(func.count(Booking.id)).where(Booking.period_id.in_(pids), Booking.status == "BOOKED")
            )
        ).scalar_one()
        if used:
            raise HTTPException(409, f"{used} active booking(s) use periods of {s.name}")
    await db.delete(s)
    await db.commit()


def _times(start: str, end: str) -> tuple[Any, Any, int, int]:
    try:
        ts, te = parse_clock(start), parse_clock(end)
        sp, ep = grid_span(ts, te)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ts, te, sp, ep


@router.post("/schedules/{sid}/periods", response_model=PeriodOut, status_code=201)
async def create_period(sid: int, body: PeriodIn, db: DB, _: SchedulesAdmin) -> PeriodOut:
    await _schedule(db, sid)
    ts, te, sp, ep = _times(body.time_start, body.time_end)
    p = BookingPeriod(
        schedule_id=sid,
        name=body.name,
        time_start=ts,
        time_end=te,
        bookable=body.bookable,
        days=body.days,
        start_period=sp,
        end_period=ep,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _period_out(p)


@router.post("/schedules/{sid}/periods/from-grid", response_model=ScheduleOut)
async def periods_from_grid(sid: int, db: DB, _: SchedulesAdmin, days: str = "1,2,3,4,5,6,7") -> ScheduleOut:
    """Create the university's 18 real periods (P1 08:30-09:10 … P18 22:10-22:50) in this schedule."""
    s = await _schedule(db, sid)
    if s.periods:
        raise HTTPException(409, f"{s.name} already has periods")
    try:
        day_list = sorted({int(x) for x in days.split(",") if x.strip()})
    except ValueError as exc:
        raise HTTPException(422, "days must be a comma-separated list of 1..7") from exc
    if not day_list or any(d < 1 or d > 7 for d in day_list):
        raise HTTPException(422, "days must be a comma-separated list of 1..7")
    for p in n.PERIODS:
        db.add(
            BookingPeriod(
                schedule_id=s.id,
                name=f"P{p.index}",
                time_start=p.start,
                time_end=p.end,
                bookable=True,
                days=day_list,
                start_period=p.index,
                end_period=p.index,
            )
        )
    await db.commit()
    await db.refresh(s)
    return _schedule_out(await _schedule(db, sid))


async def _period(db: DB, pid: int) -> BookingPeriod:
    p = await db.get(BookingPeriod, pid)
    if p is None:
        raise HTTPException(404, "period not found")
    return p


@router.put("/periods/{pid}", response_model=PeriodOut)
async def update_period(pid: int, body: PeriodUpdate, db: DB, _: SchedulesAdmin) -> PeriodOut:
    p = await _period(db, pid)
    data = body.model_dump(exclude_unset=True)
    if "time_start" in data or "time_end" in data:
        ts, te, sp, ep = _times(
            data.get("time_start") or f"{p.time_start:%H:%M}", data.get("time_end") or f"{p.time_end:%H:%M}"
        )
        if (sp, ep) != (p.start_period, p.end_period):
            used = (
                await db.execute(
                    select(func.count(Booking.id)).where(Booking.period_id == p.id, Booking.status == "BOOKED")
                )
            ).scalar_one()
            if used:
                raise HTTPException(409, f"{used} active booking(s) use {p.name}; its grid span cannot change")
        p.time_start, p.time_end, p.start_period, p.end_period = ts, te, sp, ep
    if data.get("name"):
        p.name = n.clean_text(data["name"]) or p.name
    if data.get("bookable") is not None:
        p.bookable = data["bookable"]
    if data.get("days") is not None:
        if any(d < 1 or d > 7 for d in data["days"]):
            raise HTTPException(422, "days are ISO weekdays 1..7")
        p.days = sorted(set(data["days"]))
    await db.commit()
    await db.refresh(p)
    return _period_out(p)


@router.delete("/periods/{pid}", status_code=204)
async def delete_period(pid: int, db: DB, _: SchedulesAdmin) -> None:
    p = await _period(db, pid)
    used = (
        await db.execute(select(func.count(Booking.id)).where(Booking.period_id == p.id, Booking.status == "BOOKED"))
    ).scalar_one()
    if used:
        raise HTTPException(409, f"{used} active booking(s) use {p.name}")
    await db.delete(p)
    await db.commit()


# --- timetable weeks ----------------------------------------------------------------------------------


def _week_out(w: TimetableWeek) -> TimetableWeekOut:
    return TimetableWeekOut(id=w.id, name=w.name, bgcol=f"#{w.bgcol}", fgcol=fgcol(w.bgcol), icon=w.icon)


@router.get("/weeks", response_model=list[TimetableWeekOut])
async def list_weeks(db: DB, _: WeeksAdmin) -> list[TimetableWeekOut]:
    return [_week_out(w) for w in (await db.execute(select(TimetableWeek).order_by(TimetableWeek.name))).scalars()]


@router.post("/weeks", response_model=TimetableWeekOut, status_code=201)
async def create_week(body: TimetableWeekIn, db: DB, _: WeeksAdmin) -> TimetableWeekOut:
    w = TimetableWeek(name=body.name, bgcol=body.bgcol, icon=body.icon)
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return _week_out(w)


@router.put("/weeks/{wid}", response_model=TimetableWeekOut)
async def update_week(wid: int, body: TimetableWeekUpdate, db: DB, _: WeeksAdmin) -> TimetableWeekOut:
    w = await db.get(TimetableWeek, wid)
    if w is None:
        raise HTTPException(404, "timetable week not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        w.name = n.clean_text(data["name"]) or w.name
    if data.get("bgcol"):
        w.bgcol = data["bgcol"]
    if "icon" in data:
        w.icon = data["icon"]
    await db.commit()
    return _week_out(w)


@router.delete("/weeks/{wid}", status_code=204)
async def delete_week(wid: int, db: DB, _: WeeksAdmin) -> None:
    """CRBS ``Weeks_model::delete``: dates of the week lose their week (FK ON DELETE SET NULL)."""
    w = await db.get(TimetableWeek, wid)
    if w is None:
        raise HTTPException(404, "timetable week not found")
    for row in (await db.execute(select(TermDate).where(TermDate.timetable_week_id == w.id))).scalars():
        row.timetable_week_id = None
    await db.delete(w)
    await db.commit()


# --- access checker -----------------------------------------------------------------------------------


@router.get("/access-check")
async def access_check(user_id: int, room_id: int, db: DB, _: CheckerUser) -> dict[str, Any]:
    """``Access_checker::get_unified_permissions``: booking permissions of a user in a room, by source."""
    user = await db.get(User, user_id)
    room = await db.get(Room, room_id)
    if user is None or room is None:
        raise HTTPException(404, "user or room not found")
    acc = await load_access(db, user)
    from_acl = acc.room_acl(room)
    names = sorted(p.name for p in (await db.execute(select(Permission))).scalars() if p.group in BOOKING_SCOPE_GROUPS)
    effective: dict[str, dict[str, bool]] = {}
    for name in names:
        g, action = name.split(".", 1)
        effective.setdefault(g, {})[name] = name in acc.perms or name in from_acl
    return {
        "user_id": user.id,
        "room_id": room.id,
        "role": acc.role.name if acc.role else None,
        "from_role": sorted(x for x in acc.perms if x in names),
        "from_acl": sorted(from_acl),
        "effective": effective,
        "room_bookable": room.is_bookable,
    }


# --- outbox -----------------------------------------------------------------------------------------------


def _outbox_out(r: NotificationOutbox) -> dict[str, Any]:
    return {
        "id": r.id,
        "kind": r.kind,
        "to_email": r.to_email,
        "user_id": r.user_id,
        "booking_id": r.booking_id,
        "subject": r.subject,
        "body": r.body,
        "status": r.status,
        "error": r.error,
        "attempts": r.attempts,
        "created_at": r.created_at,
        "sent_at": r.sent_at,
    }


@router.get("/outbox")
async def outbox(db: DB, _: SettingsAdmin, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    q = select(NotificationOutbox).order_by(NotificationOutbox.id.desc()).limit(max(1, min(limit, 1000)))
    if status:
        q = q.where(NotificationOutbox.status == status.upper())
    return [_outbox_out(r) for r in (await db.execute(q)).scalars()]


@router.post("/outbox/{oid}/retry")
async def outbox_retry(oid: int, db: DB, _: SettingsAdmin) -> dict[str, Any]:
    r = await db.get(NotificationOutbox, oid)
    if r is None:
        raise HTTPException(404, "notification not found")
    if r.status == "SENT":
        raise HTTPException(409, "already sent")
    if r.kind == "password_reset":
        raise HTTPException(409, "password reset codes are not stored; issue a new one")
    await deliver(db, r)
    await db.commit()
    return _outbox_out(r)
