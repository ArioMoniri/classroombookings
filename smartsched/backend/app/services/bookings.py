"""Bookings (CRBS ``Bookings_model``, ``Bookings_repeat_model``, ``SingleAgent``, ``MultiAgent``,
``UpdateAgent``, ``booking_helper``, ``components/bookings/Slot``).

Occupancy of a room on a date is the union of
* the published timetable: assignments of the **active** solver run(s) of every term covering the date;
* imported / admin blocks (HAZIRLIK, UZEM, legacy CRBS bookings …);
* other active bookings (``booking_slots``, unique per room/date/grid period at the DB level).

A booking never overlaps any of them; the solver in turn receives confirmed bookings as blocks
(:mod:`app.services.bookings_solver`)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    Block,
    Booking,
    BookingPeriod,
    BookingSchedule,
    BookingSeries,
    BookingSlot,
    MultiBooking,
    MultiBookingSlot,
    Program,
    RoomGroup,
    ScheduleRun,
    Term,
    User,
)
from app.models.base import utcnow
from app.models.booking import BOOKED, CANCELLED, PENDING
from app.models.catalog import Room
from app.services import audit, booking_policies, settings_service
from app.services.bookings_calendar import (
    CalendarError,
    DateInfo,
    TermInfo,
    applied_schedule,
    current_term_ids,
    date_infos,
    period_for,
    recurring_dates,
    resolve_term,
    term_info,
)
from app.services.bookings_collation import tr_sort_key
from app.services.bookings_perms import Access, effective_limits
from app.services.bookings_settings import get_value
from app.services.calendar import date_for
from app.services.events import publish_event
from app.services.grid import assignment_weeks

Day = date  # dataclass fields named ``date`` shadow the type


class BookingError(Exception):
    """Business-rule violation: ``status`` is the HTTP code, ``code`` a stable machine reason."""

    def __init__(self, status: int, code: str, message: str, **data: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.data = status, code, message, data

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.data}


def _forbid(code: str, message: str) -> BookingError:
    return BookingError(403, code, message)


def _conflict(code: str, message: str, **data: Any) -> BookingError:
    return BookingError(409, code, message, **data)


async def today(session: AsyncSession) -> date:
    tz = str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul")
    try:
        return datetime.now(ZoneInfo(tz)).date()
    except ZoneInfoNotFoundError:
        return date.today()


async def now_local(session: AsyncSession) -> datetime:
    tz = str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul")
    try:
        return datetime.now(ZoneInfo(tz)).replace(tzinfo=None)
    except ZoneInfoNotFoundError:
        return datetime.now()


# --------------------------------------------------------------------------------------------------
# Occupancy
# --------------------------------------------------------------------------------------------------


@dataclass
class Held:
    kind: Literal["timetable", "block", "booking"]
    room_id: int
    date: date
    start: int
    end: int
    label: str
    ref_id: int
    run_id: int | None = None
    series_id: int | None = None
    pending: bool = False  # a PENDING approval request (P1), not a booking yet

    def overlaps(self, start: int, end: int) -> bool:
        return self.start <= end and start <= self.end

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "room_id": self.room_id,
            "date": self.date.isoformat(),
            "start_period": self.start,
            "end_period": self.end,
            "label": self.label,
            "id": self.ref_id,
            "run_id": self.run_id,
            "series_id": self.series_id,
        }


Occ = dict[tuple[int, date], list[Held]]


async def timetable_occupancy(session: AsyncSession, room_ids: set[int] | None, d_from: date, d_to: date) -> Occ:
    """Active-run assignments and blocks holding rooms between ``d_from`` and ``d_to``."""
    out: Occ = defaultdict(list)
    infos: list[TermInfo] = []
    for term in (await session.execute(select(Term))).scalars():
        info = await term_info(session, term)
        if info is not None and info.start <= d_to and d_from <= info.end:
            infos.append(info)

    def add(held: Held) -> None:
        if (room_ids is None or held.room_id in room_ids) and d_from <= held.date <= d_to:
            out[(held.room_id, held.date)].append(held)

    for info in infos:
        term = info.term
        runs = list(
            (
                await session.execute(
                    select(ScheduleRun).where(ScheduleRun.term_id == term.id, ScheduleRun.is_active.is_(True))
                )
            ).scalars()
        )
        if runs:
            q = select(Assignment).where(
                Assignment.run_id.in_([r.id for r in runs]),
                Assignment.archived.is_(False),
                (Assignment.date.is_(None)) | (Assignment.date.between(d_from, d_to)),
            )
            assignments = list((await session.execute(q)).scalars())
            # solver-run rows carry no label / course codes: name them from the request's section (course code
            # and section, as the imported board rows read); nothing derivable stays empty (the UI localises it)
            need = {
                a.meeting_request_id for a in assignments if not a.label and not a.course_codes and a.meeting_request_id
            }
            request_labels = await _request_labels(session, need) if need else {}
            for a in assignments:
                rooms = [int(r) for r in (a.room_ids or [])]
                label = a.label or ", ".join(a.course_codes or []) or request_labels.get(a.meeting_request_id or 0, "")
                dates: list[date] = []
                if a.date is not None:
                    dates = [a.date]
                else:
                    weeks = assignment_weeks(a)
                    if weeks:
                        dates = [d for w in sorted(weeks) if (d := date_for(term, w, a.day, info.weeks)) is not None]
                    else:
                        d = d_from + timedelta(days=(a.day - d_from.isoweekday()) % 7)
                        while d <= min(d_to, info.end):
                            dates.append(d)
                            d += timedelta(days=7)
                for d in dates:
                    for rid in rooms:
                        add(Held("timetable", rid, d, a.start_period, a.end_period, label, a.id, run_id=a.run_id))
        bq = select(Block).where(
            Block.term_id == term.id,
            Block.archived.is_(False),
            (Block.date.is_(None)) | (Block.date.between(d_from, d_to)),
        )
        for b in (await session.execute(bq)).scalars():
            if b.date is not None:
                add(Held("block", b.room_id, b.date, b.start_period, b.end_period, b.label, b.id))
                continue
            if b.day is None:
                continue
            weeks = {int(w) for w in (b.weeks or [])}
            if weeks:
                for w in sorted(weeks):
                    d = date_for(term, w, b.day, info.weeks)
                    if d is not None:
                        add(Held("block", b.room_id, d, b.start_period, b.end_period, b.label, b.id))
            else:
                d = max(d_from, info.start)
                d += timedelta(days=(b.day - d.isoweekday()) % 7)
                while d <= min(d_to, info.end):
                    add(Held("block", b.room_id, d, b.start_period, b.end_period, b.label, b.id))
                    d += timedelta(days=7)
    return out


async def _request_labels(session: AsyncSession, request_ids: set[int]) -> dict[int, str]:
    """Meeting request id -> "MAT 112-2" (course display code and section label) for unlabelled assignments."""
    from app.models import Course, MeetingRequest, Section  # local: keeps this module's import list unchanged

    ids = [i for i in request_ids if i]
    rows = await session.execute(
        select(MeetingRequest.id, Course.display_code, Section.label)
        .join(Section, Section.id == MeetingRequest.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(MeetingRequest.id.in_(ids))
    )
    return {int(mid): f"{code}-{sec}" if sec else str(code) for mid, code, sec in rows}


async def booking_occupancy(
    session: AsyncSession,
    room_ids: set[int] | None,
    d_from: date,
    d_to: date,
    exclude: set[int] | None = None,
    *,
    viewer: Access | None = None,
) -> Occ:
    """Active bookings, plus PENDING requests (P1) whose tentative hold has not run out. With ``viewer`` (the grid),
    PENDING requests without a live hold are listed too when the viewer made them or approves them (persona test
    U-06: the requester saw the slot free again); they are marked ``pending`` and never block anyone."""
    from app.services import approvals

    out: Occ = defaultdict(list)
    q = select(Booking).where(Booking.status.in_((BOOKED, PENDING)), Booking.date.between(d_from, d_to))
    if room_ids is not None:
        q = q.where(Booking.room_id.in_(room_ids))
    now: datetime | None = None
    for b in (await session.execute(q)).scalars():
        if exclude and b.id in exclude:
            continue
        if b.status == PENDING:
            now = now or await now_local(session)
            if (b.held_until is None or b.held_until <= now) and not (
                viewer is not None and await approvals.sees_request(session, viewer, b)
            ):
                continue
        out[(b.room_id, b.date)].append(
            Held(
                "booking",
                b.room_id,
                b.date,
                b.start_period,
                b.end_period,
                b.notes or "",
                b.id,
                series_id=b.series_id,
                pending=b.status == PENDING,
            )
        )
    return out


UNPUBLISHED_TR = (
    "Bu dönemin ders programı henüz yayımlanmadı: derslikler boş görünebilir ama dersler planlanıyor. "
    "Rezervasyon, yayımlanan programla çakışabilir."
)
UNPUBLISHED_EN = (
    "The timetable of this term has not been published yet: rooms may look free although classes are being "
    "planned. A booking may clash with the timetable once it is published."
)


def _run_covers(run: ScheduleRun, info: TermInfo, d_from: date, d_to: date) -> bool:
    """Does the active ``run`` hold the timetable of some date in ``d_from..d_to``? A TERM run does; a WEEK / MONTH
    run only for its weeks."""
    from app.services.calendar import week_index_for_date

    if (run.horizon or "TERM") == "TERM":
        return True
    hp = run.horizon_params or {}
    weeks = {int(w) for w in (hp.get("weeks") or ([hp["week"]] if hp.get("week") else []))}
    if not weeks:
        return True
    d = max(d_from, info.start)
    while d <= min(d_to, info.end):
        if week_index_for_date(info.term, d, info.weeks) in weeks:
            return True
        d += timedelta(days=1)
    return False


async def timetable_state(session: AsyncSession, d_from: date, d_to: date) -> dict[str, Any]:
    """Persona test A-24: is the timetable behind the booking grid published for these dates?

    ``published``: an active run covers them; ``unpublished``: a planning term overlapping them has meeting / exam
    requests but no active run covering the dates (rooms look free although classes are planned); ``none``: no
    planning data. Bookings in the ``unpublished`` state need ``confirm_unpublished``."""
    from app.models import ExamRequest, MeetingRequest, Section

    states: list[str] = []
    total = 0
    term_ids: list[int] = []
    for term in (await session.execute(select(Term))).scalars():
        info = await term_info(session, term)
        if info is None or not (info.start <= d_to and d_from <= info.end):
            continue
        runs = list(
            (
                await session.execute(
                    select(ScheduleRun).where(ScheduleRun.term_id == term.id, ScheduleRun.is_active.is_(True))
                )
            ).scalars()
        )
        if any(_run_covers(r, info, d_from, d_to) for r in runs):
            states.append("published")
            term_ids.append(term.id)
            continue
        n = int(
            (
                await session.execute(
                    select(func.count(MeetingRequest.id))
                    .join(Section, Section.id == MeetingRequest.section_id)
                    .where(Section.term_id == term.id)
                )
            ).scalar_one()
        ) + int(
            (
                await session.execute(select(func.count(ExamRequest.id)).where(ExamRequest.term_id == term.id))
            ).scalar_one()
        )
        if n:
            states.append("unpublished")
            term_ids.append(term.id)
            total += n
    state = "unpublished" if "unpublished" in states else ("published" if states else "none")
    out: dict[str, Any] = {"state": state, "term_ids": term_ids, "meeting_requests": total}
    if state == "unpublished":
        out.update(message_tr=UNPUBLISHED_TR, message_en=UNPUBLISHED_EN)
    return out


async def find_conflict(
    session: AsyncSession, room_id: int, d: date, start: int, end: int, exclude: set[int] | None = None
) -> Held | None:
    for occ in (
        await booking_occupancy(session, {room_id}, d, d, exclude),
        await timetable_occupancy(session, {room_id}, d, d),
    ):
        for held in occ.get((room_id, d), []):
            if held.overlaps(start, end):
                return held
    return None


# --------------------------------------------------------------------------------------------------
# Permissions on bookings (booking_helper.php)
# --------------------------------------------------------------------------------------------------


def _kind(b: Booking | BookingSeries) -> str:
    return "book_recur" if getattr(b, "series_id", None) or isinstance(b, BookingSeries) else "book_single"


def is_owner(access: Access, b: Booking | BookingSeries) -> bool:
    return b.user_id is not None and b.user_id == access.user_id


def can_view_user(access: Access, b: Booking, room: Room) -> bool:
    return is_owner(access, b) or access.can(f"{_kind(b)}.view_other_users", room)


def can_view_notes(access: Access, b: Booking, room: Room) -> bool:
    return is_owner(access, b) or access.can(f"{_kind(b)}.view_other_notes", room)


def can_edit(access: Access, b: Booking, room: Room) -> bool:
    return is_owner(access, b) or access.can(f"{_kind(b)}.edit_other_booking", room)


async def booking_end(session: AsyncSession, b: Booking) -> datetime:
    period = await session.get(BookingPeriod, b.period_id)
    end = period.time_end if period else datetime.max.time()
    return datetime.combine(b.date, end)


async def can_cancel(session: AsyncSession, access: Access, b: Booking, room: Room) -> bool:
    perm = f"{_kind(b)}.cancel_other_booking"
    if access.can(perm):  # role-level: no date restrictions (CRBS checks without room first)
        return True
    now = await now_local(session)
    if await booking_end(session, b) < now or b.date < now.date():
        return False
    if is_owner(access, b):
        return True
    return access.can(perm, room)


def edit_features(access: Access, b: Booking, room: Room, scope: str) -> dict[str, bool]:
    """``UpdateAgent::load`` field rights."""
    kind = _kind(b)
    owner = is_owner(access, b)
    view_notes = access.can(f"{kind}.view_other_notes", room)
    view_user = access.can(f"{kind}.view_other_users", room)
    set_user = access.can(f"{kind}.set_user", room)
    edit_other = access.can(f"{kind}.edit_other_booking", room)
    set_dept = access.can(f"{kind}.set_department", room)
    f = {
        "date": owner or edit_other,
        "period": owner or edit_other,
        "room": owner or edit_other,
        "view_notes": owner or view_notes,
        "edit_notes": owner or (view_notes and edit_other),
        "department": set_dept,
        "view_user": owner or view_user,
        "edit_user": view_user and set_user,
    }
    if b.series_id and scope in ("future", "all"):
        f["date"] = f["period"] = f["room"] = False
    return f


# --------------------------------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------------------------------


def _uname(u: User | None) -> str | None:
    if u is None:
        return None
    return u.full_name or u.username or u.email


async def booking_out(session: AsyncSession, access: Access, b: Booking, *, detail: bool = False) -> dict[str, Any]:
    room = await session.get(Room, b.room_id)
    assert room is not None
    period = await session.get(BookingPeriod, b.period_id)
    show_user = can_view_user(access, b, room)
    show_notes = can_view_notes(access, b, room)
    user = await session.get(User, b.user_id) if (b.user_id and show_user) else None
    dep = await session.get(Program, b.department_id) if b.department_id else None
    out: dict[str, Any] = {
        "id": b.id,
        "type": "recurring" if b.series_id else "single",
        "series_id": b.series_id,
        "group_id": b.multi_booking_id,  # A-12: one submission (multi-booking) = one group
        "term_id": b.term_id,
        "status": b.status,
        "date": b.date.isoformat(),
        "weekday": b.date.isoweekday(),
        "period_id": b.period_id,
        "period_name": period.name if period else None,
        "time_start": f"{period.time_start:%H:%M}" if period else None,
        "time_end": f"{period.time_end:%H:%M}" if period else None,
        "start_period": b.start_period,
        "end_period": b.end_period,
        "room_id": b.room_id,
        "room_name": room.display_name,
        "user_id": b.user_id if show_user else None,
        "user_name": _uname(user),
        "user_hidden": bool(b.user_id) and not show_user,
        "department_id": b.department_id,
        "department_name": dep.name if dep else None,
        "notes": b.notes if show_notes else None,
        "notes_hidden": bool(b.notes) and not show_notes,
        "is_owner": is_owner(access, b),
        "cancel_reason": b.cancel_reason,
        "cancelled_at": b.cancelled_at.isoformat() if b.cancelled_at else None,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "headcount": b.headcount,
        "held_until": b.held_until.isoformat() if b.held_until else None,
    }
    if detail:
        out["can_edit"] = b.status == BOOKED and can_edit(access, b, room)
        out["can_cancel"] = b.status == BOOKED and await can_cancel(session, access, b, room)
        out["edit_features"] = {s: edit_features(access, b, room, s) for s in ("one", "future", "all")}
        if b.series_id:
            series = await session.get(BookingSeries, b.series_id)
            out["series"] = (
                {
                    "id": series.id,
                    "weekday": series.weekday,
                    "timetable_week_id": series.timetable_week_id,
                    "status": series.status,
                }
                if series
                else None
            )
    return out


# --------------------------------------------------------------------------------------------------
# Limits
# --------------------------------------------------------------------------------------------------


async def active_bookings(session: AsyncSession, user_id: int) -> list[Booking]:
    """``Users_model::get_scheduled_booking_count``'s rows: future single bookings the user made for themself."""
    now = await now_local(session)
    rows = (
        await session.execute(
            select(Booking, BookingPeriod)
            .join(BookingPeriod, BookingPeriod.id == Booking.period_id)
            .where(
                Booking.user_id == user_id,
                Booking.created_by == user_id,
                Booking.status == BOOKED,
                Booking.series_id.is_(None),
                Booking.date >= now.date(),
            )
        )
    ).all()
    return [b for b, p in rows if b.date > now.date() or p.time_start > now.time()]


async def active_booking_count(session: AsyncSession, user_id: int) -> int:
    """``Users_model::get_scheduled_booking_count``: the number of rows (the ``max_active_bookings`` limit counts
    periods, as CRBS does)."""
    return len(await active_bookings(session, user_id))


async def check_window(
    session: AsyncSession, access: Access, info: TermInfo, d: date, room: Room | None = None
) -> None:
    """Single bookings: ``range_min`` / ``range_max`` days from today (``SingleAgent::check_constraints``);
    users who can only make single bookings also cannot book the past (``Slot::check_free_constraints``).
    "Only single" is decided for the room (role ∪ room ACL), exactly as the grid does (audit B5)."""
    limits = await effective_limits(session, access.user)
    lo, hi = limits["range_min"], limits["range_max"]
    single_only = not access.can("book_recur.create", room)
    if lo is None and hi is None and not single_only:
        return
    t = await today(session)
    min_date = t + timedelta(days=lo or 0)
    # T-R2-17 (R2-S-13, R1-S-24): coded refusals with both languages; a date already gone is "past", not a window
    if d < t:
        raise _conflict(
            "past",
            f"{d:%d.%m.%Y} is in the past; bookings are made for today or later",
            message_en=f"{d:%d.%m.%Y} is in the past; bookings are made for today or later",
            message_tr=f"{d:%d.%m.%Y} geçmiş bir tarih; rezervasyon bugün ya da sonrası için yapılır",
            min_date=min_date.isoformat(),
        )
    if d < min_date:
        raise _conflict(
            "range_min",
            f"bookings must be made at least {lo or 0} day(s) ahead (from {min_date:%d.%m.%Y})",
            message_en=f"bookings must be made at least {lo or 0} day(s) ahead (from {min_date:%d.%m.%Y})",
            message_tr=f"rezervasyon en az {lo or 0} gün önceden yapılmalı ({min_date:%d.%m.%Y} tarihinden itibaren)",
            min_date=min_date.isoformat(),
        )
    max_date = t + timedelta(days=hi) if hi is not None else info.end
    if d > max_date:
        raise _conflict(
            "range_max",
            f"bookings can be made at most {hi} day(s) ahead (until {max_date:%d.%m.%Y})",
            message_en=f"bookings can be made at most {hi} day(s) ahead (until {max_date:%d.%m.%Y})",
            message_tr=f"rezervasyon en çok {hi} gün önceye kadar yapılabilir ({max_date:%d.%m.%Y} tarihine kadar)",
            max_date=max_date.isoformat(),
        )


#: role-level permission that lets a user cancel a booking after its period ended (``can_cancel``): the same users
#: may record a period that already started (persona test U-04)
PAST_BOOKING_PERM = "book_single.cancel_other_booking"


def period_started(d: date, period: BookingPeriod, now: datetime) -> bool:
    """True when ``period`` of ``d`` has begun at ``now`` (local wall time of the organisation)."""
    return datetime.combine(d, period.time_start) <= now


async def check_not_started(session: AsyncSession, access: Access, d: date, period: BookingPeriod) -> None:
    """U-04: a single booking for a period that already started is refused, unless the user may cancel other people's
    bookings at role level (administrators record past use and can cancel it again). Everyone else could not cancel
    such a booking once the period ended, so it is not creatable."""
    if access.can(PAST_BOOKING_PERM):
        return
    now = await now_local(session)
    if not period_started(d, period, now):
        return
    start = datetime.combine(d, period.time_start)
    raise _conflict(
        "past",
        f"{period.name} on {d:%d.%m.%Y} already started at {period.time_start:%H:%M}; it can no longer be booked",
        period_start=start.isoformat(),
        message_en=f"{period.name} on {d:%d.%m.%Y} already started at {period.time_start:%H:%M}; "
        "it can no longer be booked",
        message_tr=f"{d:%d.%m.%Y} {period.name} saat {period.time_start:%H:%M} itibarıyla başladı (geçmiş saat); "
        "artık rezerve edilemez",
    )


async def remaining_bookings(session: AsyncSession, access: Access) -> int | None:
    limits = await effective_limits(session, access.user)
    limit = limits["max_active_bookings"]
    if limit is None:
        return None
    return max(0, limit - await active_booking_count(session, access.user_id))


# --------------------------------------------------------------------------------------------------
# Single bookings
# --------------------------------------------------------------------------------------------------


@dataclass
class SingleIn:
    room_id: int
    date: Day
    period_id: int
    notes: str | None = None
    user_id: int | None = None
    department_id: int | None = None
    term_id: int | None = None
    #: set_user given explicitly (user_id may then be None = "no user")
    user_given: bool = False
    department_given: bool = False
    #: T1: what the booking was searched for (kept for P2 alternatives)
    headcount: int | None = None
    required_features: list[Any] | None = None
    #: A-24: the user saw the "timetable not published yet" warning and books anyway
    confirm_unpublished: bool = False


async def ungrouped_rooms_hidden(session: AsyncSession) -> bool:
    """CRBS behaviour: rooms without a room group are not offered for booking. Off when the room-group feature
    is switched off (one flat list) or when ``bookings.show_ungrouped_rooms`` is set."""
    if not await get_value(session, "org", "use_room_groups"):
        return False
    return not await get_value(session, "bookings", "show_ungrouped_rooms")


async def visible_room(session: AsyncSession, access: Access, room_id: int) -> Room:
    room = await session.get(Room, room_id)
    if room is None or not access.can_view_room(room):
        raise BookingError(404, "room_not_found", f"room {room_id} not found")
    if room.room_group_id is None and await ungrouped_rooms_hidden(session):
        raise BookingError(404, "room_not_found", f"{room.display_name} belongs to no room group")
    if not room.is_bookable:
        raise _conflict("room_not_bookable", f"{room.display_name} cannot be booked")
    return room


async def _who_and_department(
    session: AsyncSession, access: Access, room: Room, kind: str, body: SingleIn, *, multi_recurring: bool = False
) -> tuple[int | None, int | None]:
    """Who the booking is for and its department. Without ``set_user`` / ``set_department`` the choice is
    refused with 403; ``bookings.ignore_unauthorised_user_department`` restores CRBS, which silently books
    for the user and their own department (deliberate difference c). CRBS's multi-booking recurring step
    asks ``book_recur.create`` for the department (``MultiAgent::process_recurring_defaults``) unless
    ``bookings.recurring_department_needs_set_department`` is on (deliberate difference b)."""
    ignore = bool(await get_value(session, "bookings", "ignore_unauthorised_user_department"))
    user_id: int | None = access.user_id
    if body.user_given and body.user_id != access.user_id:
        if not access.can(f"{kind}.set_user", room):
            if not ignore:
                raise _forbid("set_user", "you may not book for another user")
        else:
            if body.user_id is not None:
                target = await session.get(User, body.user_id)
                if target is None or not target.is_active:
                    raise BookingError(422, "user", f"user {body.user_id} not found")
            user_id = body.user_id
    dep_id = access.user.department_id
    if body.department_given and body.department_id != dep_id:
        dept_perm = f"{kind}.set_department"
        if multi_recurring and not await get_value(session, "bookings", "recurring_department_needs_set_department"):
            dept_perm = "book_recur.create"
        if not access.can(dept_perm, room):
            if not ignore:
                raise _forbid("set_department", "you may not set the department of a booking")
        else:
            if body.department_id is not None and await session.get(Program, body.department_id) is None:
                raise BookingError(422, "department", f"department {body.department_id} not found")
            dep_id = body.department_id
    return user_id, dep_id


async def _open_date(session: AsyncSession, info: TermInfo, d: date) -> DateInfo:
    di = (await date_infos(session, info, [d]))[d]
    if not di.open:
        msg = {
            "holiday": f"{d:%d.%m.%Y} is a holiday ({di.holiday})",
            "no_week": f"{d:%d.%m.%Y} has no timetable week",
            "date_range": f"{d:%d.%m.%Y} is outside the term",
        }[di.reason or "date_range"]
        raise _conflict(di.reason or "closed", msg)
    return di


def _slot_rows(b: Booking) -> list[BookingSlot]:
    return [
        BookingSlot(booking_id=b.id, period=p, room_id=b.room_id, date=b.date)
        for p in range(b.start_period, b.end_period + 1)
    ]


slot_rows = _slot_rows


async def release_expired_holds(session: AsyncSession, room_id: int | None = None, d: date | None = None) -> int:
    """Free the slots of PENDING requests whose tentative hold ran out (the request itself stays open)."""
    now = await now_local(session)
    q = select(Booking.id).where(Booking.status == PENDING, Booking.held_until.is_not(None), Booking.held_until <= now)
    if room_id is not None:
        q = q.where(Booking.room_id == room_id)
    if d is not None:
        q = q.where(Booking.date == d)
    ids = list((await session.execute(q)).scalars())
    if not ids:
        return 0
    await session.execute(delete(BookingSlot).where(BookingSlot.booking_id.in_(ids)))
    for b in (await session.execute(select(Booking).where(Booking.id.in_(ids)))).scalars():
        b.held_until = None
    await session.flush()
    return len(ids)


def snap(b: Booking) -> dict[str, Any]:
    """The audited state of a booking (P7)."""
    return audit.snapshot(
        b,
        (
            "id",
            "status",
            "series_id",
            "term_id",
            "room_id",
            "date",
            "period_id",
            "start_period",
            "end_period",
            "user_id",
            "department_id",
            "notes",
            "headcount",
            "cancel_reason",
        ),
    )


async def _insert(session: AsyncSession, b: Booking) -> Booking:
    session.add(b)
    await session.flush()
    if b.status == PENDING and b.held_until is None:
        return b  # a request without a hold holds nothing
    await release_expired_holds(session, b.room_id, b.date)
    for s in _slot_rows(b):
        session.add(s)
    try:
        await session.flush()
    except IntegrityError as exc:  # a concurrent booking won the race; the unique key is the referee
        await session.rollback()
        raise _conflict("conflict", "the slot was booked by someone else a moment ago") from exc
    return b


async def _conflict_error(held: Held, room: Room, d: date) -> BookingError:
    what = {"booking": "an existing booking", "timetable": "the published timetable", "block": "a reserved block"}
    return _conflict(
        "conflict",
        f"{room.display_name} on {d:%d.%m.%Y} P{held.start}-P{held.end} is held by {what[held.kind]}"
        + (f" ({held.label})" if held.kind != "booking" and held.label else ""),
        conflict=held.as_dict(),
    )


async def _refuse_duplicate_request(
    session: AsyncSession, access: Access, room: Room, d: date, period: BookingPeriod, user_id: int | None
) -> None:
    """U-06: the same user asking again for the same room, date and period gets the open request back (409)."""
    from app.services import approvals

    q = select(Booking).where(
        Booking.status == PENDING,
        Booking.room_id == room.id,
        Booking.date == d,
        Booking.period_id == period.id,
        Booking.created_by == access.user_id,
        Booking.user_id == user_id if user_id is not None else Booking.user_id.is_(None),
    )
    b = (await session.execute(q.order_by(Booking.id))).scalars().first()
    if b is None:
        return
    req = await approvals.request_for_booking(session, b)
    raise _conflict(
        "duplicate_request",
        f"you already asked for {room.display_name} on {d:%d.%m.%Y} {period.name}; the request is waiting for approval",
        booking_id=b.id,
        request_id=req.id if req is not None else None,
        message_en=f"you already asked for {room.display_name} on {d:%d.%m.%Y} {period.name}; "
        "the request is waiting for approval",
        message_tr=f"{room.display_name} için {d:%d.%m.%Y} {period.name} talebiniz zaten var ve onay bekliyor",
    )


async def create_single(session: AsyncSession, access: Access, body: SingleIn, *, commit: bool = True) -> Booking:
    """A booking, or (P1) a PENDING request when the room needs approval (``booking.status``)."""
    from app.services import approvals

    room = await visible_room(session, access, body.room_id)
    try:
        info = await resolve_term(session, body.date, body.term_id, view_all=access.can("system.view_all_sessions"))
    except CalendarError as exc:
        raise _conflict("calendar", str(exc)) from exc
    need = await approvals.need_for(session, access, room, "book_single", info.term.id)
    try:
        await _open_date(session, info, body.date)
        period = await period_for(session, info, room, body.period_id, body.date)
    except CalendarError as exc:
        raise _conflict("calendar", str(exc)) from exc
    if need is not None:
        await approvals.check_lead_time(session, need, info.term.id, body.date)
    user_id, dep_id = await _who_and_department(session, access, room, "book_single", body)
    # P8 booking policies + exam-period mode: refuse with a reason, or turn the booking into a request
    need = await booking_policies.enforce(session, access, room, info.term.id, body.date, period, user_id, need)
    await check_window(session, access, info, body.date, room)
    await check_not_started(session, access, body.date, period)
    # CRBS checks the limit in the grid (Slot) and in multi-booking, not in SingleAgent (deliberate
    # difference a); bookings.enforce_max_active_on_create refuses the POST too
    enforce = bool(await get_value(session, "bookings", "enforce_max_active_on_create"))
    left = await remaining_bookings(session, access) if enforce else None
    if left is not None and left < 1:
        limits = await effective_limits(session, access.user)
        raise _conflict(
            "max_active_bookings",
            f"you already have {limits['max_active_bookings']} active booking(s), the maximum",
            limit=limits["max_active_bookings"],
        )
    if need is not None:
        await _refuse_duplicate_request(session, access, room, body.date, period, user_id)
    held = await find_conflict(session, room.id, body.date, period.start_period, period.end_period)
    if held is not None:
        raise await _conflict_error(held, room, body.date)
    if not body.confirm_unpublished:
        st = await timetable_state(session, body.date, body.date)
        if st["state"] == "unpublished":
            raise _conflict(
                "timetable_unpublished",
                UNPUBLISHED_EN,
                confirm_field="confirm_unpublished",
                message_en=UNPUBLISHED_EN,
                message_tr=UNPUBLISHED_TR,
                meeting_requests=st["meeting_requests"],
            )
    b = Booking(
        term_id=info.term.id,
        period_id=period.id,
        room_id=room.id,
        user_id=user_id,
        department_id=dep_id,
        date=body.date,
        start_period=period.start_period,
        end_period=period.end_period,
        notes=body.notes,
        status=BOOKED if need is None else PENDING,
        created_by=access.user_id,
        headcount=body.headcount,
        required_features=body.required_features,
    )
    if need is not None:
        b.held_until = await approvals.hold_until(session, need, b)
    await _insert(session, b)
    if need is None:
        await publish_event(
            session,
            "booking.create",
            "booking",
            b.id,
            after=snap(b),
            actor=access.user,
            term_id=b.term_id,
            reversible=True,
            notify="booking.created",
            payload={"booking_id": b.id, "booking_ids": [b.id], "actor_id": access.user_id},
        )
    else:
        await approvals.open_request(session, access, need, room, [b])
    if commit:
        await session.commit()
    return b


# --------------------------------------------------------------------------------------------------
# Recurring bookings
# --------------------------------------------------------------------------------------------------


@dataclass
class RecurIn:
    room_id: int
    period_id: int
    date: Day  # anchor (the clicked slot)
    start: Day | None = None  # None = "session" (first recurring date)
    end: Day | None = None  # None = "session" (last recurring date)
    notes: str | None = None
    user_id: int | None = None
    department_id: int | None = None
    term_id: int | None = None
    user_given: bool = False
    department_given: bool = False
    instances: dict[Day, dict[str, Any]] | None = None
    #: created from a multi-booking selection (CRBS MultiAgent rules for the department)
    multi: bool = False


@dataclass
class RecurPlan:
    info: TermInfo
    room: Room
    period: BookingPeriod
    anchor: DateInfo
    instances: list[dict[str, Any]] = field(default_factory=list)
    bookable: int = 0
    max_instances: int | None = None
    #: P1: the series needs approval (a PENDING request) when set
    need: Any = None


def _actions_for(access: Access, holders: list[Held], existing: Booking | None, room: Room) -> list[str]:
    """``BaseAgent::get_actions``: owners may replace their own booking; others need cancel_other. "Replace"
    is offered only when that booking is the only thing holding the slot: if the published timetable, a
    block or a second booking holds it too, the new instance could not be booked after the cancellation
    (audit B1), so only "do not book" remains."""
    if existing is None or len(holders) != 1 or holders[0].kind != "booking":
        return ["do_not_book"]
    if is_owner(access, existing):
        return ["replace", "do_not_book"]
    acts = ["do_not_book"]
    if access.can(f"{_kind(existing)}.cancel_other_booking", room):
        acts.insert(0, "replace")
    return acts


async def plan_recurring(session: AsyncSession, access: Access, body: RecurIn) -> RecurPlan:
    from app.services import approvals

    room = await visible_room(session, access, body.room_id)
    try:
        info = await resolve_term(session, body.date, body.term_id, view_all=access.can("system.view_all_sessions"))
    except CalendarError as exc:
        raise _conflict("calendar", str(exc)) from exc
    need = await approvals.need_for(session, access, room, "book_recur", info.term.id)
    try:
        anchor = await _open_date(session, info, body.date)
        period = await period_for(session, info, room, body.period_id, body.date)
    except CalendarError as exc:
        raise _conflict("calendar", str(exc)) from exc
    dates = await recurring_dates(session, info, body.date)
    if not dates:
        raise _conflict("no_recurring_dates", "no dates to repeat this booking on")
    start = body.start or dates[0].date
    end = body.end or dates[-1].date
    if end < start:
        raise BookingError(422, "recurring_dates", f"end {end:%d.%m.%Y} is before start {start:%d.%m.%Y}")
    chosen = [d for d in dates if start <= d.date <= end]
    plan = RecurPlan(info, room, period, anchor, need=need)
    if chosen:
        d0, d1 = chosen[0].date, chosen[-1].date
        bocc = await booking_occupancy(session, {room.id}, d0, d1)
        tocc = await timetable_occupancy(session, {room.id}, d0, d1)
    else:
        bocc, tocc = {}, {}
    policies = await booking_policies.PolicyIndex.load(session)
    counted = False
    for di in chosen:
        holders = [
            h
            for h in [*bocc.get((room.id, di.date), []), *tocc.get((room.id, di.date), [])]
            if h.overlaps(period.start_period, period.end_period)
        ]
        held = holders[0] if holders else None
        item: dict[str, Any] = {"date": di.date.isoformat(), "term_week": di.term_week, "status": "free"}
        found = (
            await booking_policies.violations(
                session,
                access,
                room,
                info.term.id,
                di.date,
                period,
                body.user_id if body.user_given else access.user_id,
                index=policies,
                count_active=not counted,
            )
            if held is None
            else []
        )
        refused = [v for v in found if v.effect == "refuse"]
        if held is None and refused:
            # P8: an instance a policy refuses is offered as "do not book", with the reason
            item["status"] = "policy"
            item["policy"] = refused[0].as_dict()
            item["actions"] = ["do_not_book"]
        elif held is None:
            counted = True
            if found and plan.need is None:
                plan.need = booking_policies.request_need(found[0])
            item["actions"] = ["book", "do_not_book"]
            plan.bookable += 1
        else:
            existing = await session.get(Booking, held.ref_id) if held.kind == "booking" else None
            item["status"] = "booked" if held.kind == "booking" else held.kind
            item["held"] = held.as_dict()
            if len(holders) > 1:
                item["also_held"] = [h.as_dict() for h in holders[1:]]
            if existing is not None:
                item["booking"] = await booking_out(session, access, existing)
            item["actions"] = _actions_for(access, holders, existing, room)
        plan.instances.append(item)
    plan.max_instances = (await effective_limits(session, access.user))["recur_max_instances"]
    return plan


def plan_out(plan: RecurPlan) -> dict[str, Any]:
    exceeds = max(0, plan.bookable - plan.max_instances) if plan.max_instances is not None else 0
    return {
        "term_id": plan.info.term.id,
        "room_id": plan.room.id,
        "period_id": plan.period.id,
        "weekday": plan.anchor.weekday,
        "timetable_week_id": plan.anchor.timetable_week_id,
        "instances": plan.instances,
        "bookable_count": plan.bookable,
        "max_instances": plan.max_instances,
        "exceeds_by": exceeds,
        "requires_approval": plan.need is not None,
    }


async def create_recurring(
    session: AsyncSession, access: Access, body: RecurIn, *, commit: bool = True
) -> dict[str, Any]:
    from app.services import approvals

    plan = await plan_recurring(session, access, body)
    room = plan.room
    need = plan.need
    user_id, dep_id = await _who_and_department(
        session,
        access,
        room,
        "book_recur",
        SingleIn(
            room_id=room.id,
            date=body.date,
            period_id=body.period_id,
            user_id=body.user_id,
            department_id=body.department_id,
            user_given=body.user_given,
            department_given=body.department_given,
        ),
        multi_recurring=body.multi,
    )
    series = BookingSeries(
        term_id=plan.info.term.id,
        period_id=plan.period.id,
        room_id=room.id,
        user_id=user_id,
        department_id=dep_id,
        timetable_week_id=plan.anchor.timetable_week_id,
        weekday=plan.anchor.weekday,
        notes=body.notes,
        status=BOOKED if need is None else PENDING,
        created_by=access.user_id,
    )
    session.add(series)
    await session.flush()
    created: list[Booking] = []
    skipped: list[dict[str, Any]] = []
    replaced: list[int] = []
    booked = 0
    # CRBS counts only "book" instances against recur_max_instances (deliberate difference f)
    count_replacements = bool(await get_value(session, "bookings", "recur_max_counts_replacements"))
    for item in plan.instances:
        d = date.fromisoformat(item["date"])
        wanted = (body.instances or {}).get(d, {})
        default = "book" if item["status"] == "free" else "do_not_book"
        action = wanted.get("action", default)
        if action not in item["actions"]:
            reason = f"policy_{item['policy']['rule']}" if item.get("policy") else f"action {action!r} not allowed"
            skipped.append({"date": item["date"], "reason": reason, "status": item["status"]})
            continue
        if item.get("policy") and action == "do_not_book" and (body.instances or {}).get(d) is None:
            skipped.append(
                {
                    "date": item["date"],
                    "reason": f"policy_{item['policy']['rule']}",
                    "status": "policy",
                    "policy": item["policy"],
                }
            )
            continue
        if action == "do_not_book":
            skipped.append({"date": item["date"], "reason": "not selected", "status": item["status"]})
            continue
        if action == "replace" and need is not None:
            skipped.append({"date": item["date"], "reason": "replace needs a direct booking", "status": item["status"]})
            continue
        counts = action == "book" or count_replacements
        if counts and plan.max_instances is not None and booked >= plan.max_instances:
            skipped.append({"date": item["date"], "reason": "recur_max_instances", "status": item["status"]})
            continue
        old: Booking | None = None
        if action == "replace":
            old = await session.get(Booking, item["held"]["id"])
            if old is not None and old.status != BOOKED:
                old = None
            # audit B1: decide before cancelling anything - is the slot free apart from the old booking?
            other = await find_conflict(
                session, room.id, d, plan.period.start_period, plan.period.end_period, exclude={old.id} if old else None
            )
            if other is not None:
                skipped.append({"date": item["date"], "reason": "conflict", "status": other.kind})
                continue
        b = Booking(
            series_id=series.id,
            term_id=plan.info.term.id,
            period_id=plan.period.id,
            room_id=room.id,
            user_id=user_id,
            department_id=dep_id,
            date=d,
            start_period=plan.period.start_period,
            end_period=plan.period.end_period,
            notes=body.notes,
            status=BOOKED if need is None else PENDING,
            created_by=access.user_id,
        )
        if need is not None:
            b.held_until = await approvals.hold_until(session, need, b)
        if old is None:
            held = await find_conflict(session, room.id, d, b.start_period, b.end_period)
            if held is not None:
                skipped.append({"date": item["date"], "reason": "conflict", "status": held.kind})
                continue
        # SAVEPOINT: the cancellation and the new instance stand or fall together (a concurrent booking that
        # wins the unique slot key rolls back this instance only, and the old booking stays booked)
        savepoint = await session.begin_nested()
        try:
            if old is not None:
                ids = await _cancel_rows(session, access, [old], replace_reason(series.id))
            session.add(b)
            await session.flush()
            if b.status != PENDING or b.held_until is not None:
                for slot in _slot_rows(b):
                    session.add(slot)
            await session.flush()
        except IntegrityError:
            await savepoint.rollback()
            skipped.append({"date": item["date"], "reason": "conflict", "status": "booking"})
            continue
        await savepoint.commit()
        if old is not None:
            replaced += ids
        created.append(b)
        if counts:
            booked += 1
    if not created:
        await session.rollback()
        raise _conflict("none_created", "no instances were booked", skipped=skipped)
    if replaced:
        await publish_event(
            session,
            "booking.cancel",
            "booking",
            replaced[0],
            items=[(i, {"status": BOOKED}, {"status": CANCELLED}) for i in replaced],
            actor=access.user,
            reason=replace_reason(series.id),
            term_id=series.term_id,
            notify="booking.cancelled",
            payload={"booking_ids": replaced, "actor_id": access.user_id, "reason": replace_reason(series.id)},
        )
    if need is None:
        await publish_event(
            session,
            "series.create",
            "booking_series",
            series.id,
            items=[(b.id, None, snap(b)) for b in created],
            item_type="booking",
            child_action="booking.create",
            parent_after={"room_id": room.id, "weekday": series.weekday},
            actor=access.user,
            term_id=series.term_id,
            reversible=True,
            notify="series.created",
            payload={"series_id": series.id, "booking_ids": [b.id for b in created], "actor_id": access.user_id},
        )
    else:
        await approvals.open_request(session, access, need, room, created, series)
    if commit:
        await session.commit()
    return {
        "series_id": series.id,
        "status": series.status,
        "created": [await booking_out(session, access, b) for b in created],
        "skipped": skipped,
    }


# --------------------------------------------------------------------------------------------------
# Cancel
# --------------------------------------------------------------------------------------------------


def replace_reason(series_id: int) -> str:
    """The cancel reason a series writes on the booking it replaces: a *code* (``replaced_by_series:<id>``) the UI
    renders in its language ("Seri #7 ile değiştirildi"), never an English sentence (T-R2-17, R2-M-18)."""
    return f"replaced_by_series:{series_id}"


async def _cancel_rows(session: AsyncSession, access: Access, rows: list[Booking], reason: str | None) -> list[int]:
    now = utcnow()
    ids = []
    for b in rows:
        if b.status != BOOKED:
            continue
        b.status = CANCELLED
        b.cancelled_at = now
        b.cancelled_by = access.user_id
        b.cancel_reason = reason
        ids.append(b.id)
    if ids:
        await session.execute(delete(BookingSlot).where(BookingSlot.booking_id.in_(ids)))
        await session.flush()
    return ids


async def cancel(
    session: AsyncSession, access: Access, booking_id: int, scope: str = "one", reason: str | None = None
) -> list[int]:
    b = await session.get(Booking, booking_id)
    if b is None:
        raise BookingError(404, "not_found", "booking not found")
    room = await session.get(Room, b.room_id)
    assert room is not None
    if b.status != BOOKED:
        raise _conflict("already_cancelled", "the booking is already cancelled")
    if not await can_cancel(session, access, b, room):
        raise _forbid("not_cancelable", "you may not cancel this booking")
    if scope != "one" and not b.series_id:
        raise BookingError(422, "scope", "only recurring bookings can be cancelled with scope future/all")
    if scope == "one":
        rows = [b]
    else:
        q = select(Booking).where(Booking.series_id == b.series_id, Booking.status == BOOKED)
        if scope == "future":
            q = q.where(Booking.date >= b.date)
        elif not await get_value(session, "bookings", "cancel_all_includes_past"):
            # "all" = the whole series from today on; past instances stay as history (CRBS cancel_all
            # cancels every instance: bookings.cancel_all_includes_past)
            q = q.where(Booking.date >= await today(session))
        rows = list((await session.execute(q)).scalars())
    before = {r.id: snap(r) for r in rows if r.status == BOOKED}
    ids = await _cancel_rows(session, access, rows, reason)
    if scope == "all" and b.series_id:
        series = await session.get(BookingSeries, b.series_id)
        if series is not None:
            series.status, series.cancelled_at, series.cancelled_by = CANCELLED, utcnow(), access.user_id
            series.cancel_reason = reason
    # T-R2-17 (e): a series scope is one event on the series with one child per booking, so no booking (the anchor)
    # gets two "Rezervasyon iptal edildi" rows; a single date stays one row on the booking itself
    many = scope != "one" and b.series_id is not None
    await publish_event(
        session,
        "booking.cancel",
        "booking_series" if many else "booking",
        b.series_id if many else b.id,
        items=[(r.id, before[r.id], snap(r)) for r in rows if r.id in before],
        item_type="booking" if many else None,
        parent_after={"scope": scope, "booking_id": b.id},
        actor=access.user,
        reason=reason,
        term_id=b.term_id,
        reversible=True,
        notify="booking.cancelled",
        payload={"booking_ids": ids, "actor_id": access.user_id, "reason": reason},
    )
    await session.commit()
    return ids


async def bookings_outside_term(session: AsyncSession, term: Term) -> list[Booking]:
    """Active bookings of ``term`` whose date is no longer inside its range (CRBS ``check_session_dates``)."""
    info = await term_info(session, term)
    if info is None:
        return []
    q = select(Booking).where(Booking.term_id == term.id, Booking.status == BOOKED).order_by(Booking.date)
    return [b for b in (await session.execute(q)).scalars() if not (info.start <= b.date <= info.end)]


async def booking_summary(session: AsyncSession, b: Booking) -> dict[str, Any]:
    room = await session.get(Room, b.room_id)
    period = await session.get(BookingPeriod, b.period_id)
    return {
        "id": b.id,
        "date": b.date.isoformat(),
        "room_id": b.room_id,
        "room_name": room.display_name if room else None,
        "period_name": period.name if period else None,
        "user_id": b.user_id,
        "series_id": b.series_id,
        "group_id": b.multi_booking_id,  # A-12: one submission (multi-booking) = one group
    }


async def cancel_outside_term(session: AsyncSession, term: Term, actor: User, rows: list[Booking]) -> list[int]:
    """Cancel (not delete, as CRBS does) with the reason, and tell the owners (``booking.cancelled``)."""
    from app.services.bookings_perms import load_access

    info = await term_info(session, term)
    span = f"{info.start:%d.%m.%Y}-{info.end:%d.%m.%Y}" if info else "-"
    reason = f"outside the dates of term {term.code} ({span})"
    access = await load_access(session, actor)
    before = {r.id: snap(r) for r in rows if r.status == BOOKED}
    ids = await _cancel_rows(session, access, rows, reason)
    if ids:
        await publish_event(
            session,
            "booking.cancel",
            "booking",
            ids[0],
            items=[(r.id, before[r.id], snap(r)) for r in rows if r.id in before],
            actor=actor,
            reason=reason,
            term_id=term.id,
            notify="booking.cancelled",
            payload={"booking_ids": ids, "actor_id": actor.id, "reason": reason},
        )
    return ids


async def cancel_many(
    session: AsyncSession, access: Access, booking_ids: list[int], reason: str | None
) -> dict[str, Any]:
    """``Bookings::cancel_multi``: each booking that the user may cancel is cancelled (single instance)."""
    done: list[int] = []
    skipped: list[dict[str, Any]] = []
    items: list[tuple[Any, dict[str, Any] | None, dict[str, Any] | None]] = []
    for bid in dict.fromkeys(booking_ids):
        b = await session.get(Booking, bid)
        if b is None:
            skipped.append({"id": bid, "reason": "not_found"})
            continue
        room = await session.get(Room, b.room_id)
        if b.status != BOOKED:
            skipped.append({"id": bid, "reason": "already_cancelled"})
        elif room is None or not await can_cancel(session, access, b, room):
            skipped.append({"id": bid, "reason": "not_cancelable"})
        else:
            before = snap(b)
            done += await _cancel_rows(session, access, [b], reason)
            items.append((b.id, before, snap(b)))
    if done:
        await publish_event(
            session,
            "booking.cancel",
            "booking",
            done[0],
            items=items,
            actor=access.user,
            reason=reason,
            reversible=True,
            notify="booking.cancelled",
            payload={"booking_ids": done, "actor_id": access.user_id, "reason": reason},
        )
    await session.commit()
    return {"cancelled": done, "skipped": skipped}


# --------------------------------------------------------------------------------------------------
# Edit
# --------------------------------------------------------------------------------------------------


async def update(
    session: AsyncSession, access: Access, booking_id: int, scope: str, data: dict[str, Any]
) -> list[Booking]:
    b = await session.get(Booking, booking_id)
    if b is None:
        raise BookingError(404, "not_found", "booking not found")
    room = await session.get(Room, b.room_id)
    assert room is not None
    if b.status != BOOKED:
        raise _conflict("cancelled", "a cancelled booking cannot be edited")
    if not can_edit(access, b, room):
        raise _forbid("not_editable", "you may not edit this booking")
    if scope != "one" and not b.series_id:
        raise BookingError(422, "scope", "scope future/all needs a recurring booking")
    for key in ("date", "period_id", "room_id"):
        if key in data and data[key] is None:  # audit B6
            raise BookingError(422, key, f"{key} cannot be empty")
    feats = edit_features(access, b, room, scope)
    need = {
        "date": "date",
        "period_id": "period",
        "room_id": "room",
        "notes": "edit_notes",
        "department_id": "department",
        "user_id": "edit_user",
    }
    for key in data:
        if not feats[need[key]]:
            raise _forbid(
                f"edit_{key}",
                f"you may not change {key} of this booking" + (f" with scope {scope}" if scope != "one" else ""),
            )
    if "user_id" in data and data["user_id"] is not None:
        target = await session.get(User, data["user_id"])
        if target is None or not target.is_active:
            raise BookingError(422, "user", f"user {data['user_id']} not found")
    if data.get("department_id") is not None and await session.get(Program, data["department_id"]) is None:
        raise BookingError(422, "department", f"department {data['department_id']} not found")
    if scope == "one":
        targets = [b]
    else:
        q = select(Booking).where(Booking.series_id == b.series_id, Booking.status == BOOKED)
        if scope == "future":
            q = q.where(Booking.date >= b.date)
        targets = list((await session.execute(q)).scalars())
    moving = any(k in data for k in ("date", "period_id", "room_id"))
    before = {t.id: snap(t) for t in targets}
    if moving:
        new_room = await visible_room(session, access, data.get("room_id", b.room_id))
        new_date = data.get("date", b.date)
        term = await session.get(Term, b.term_id)
        assert term is not None
        info = await term_info(session, term)
        try:
            if info is None or not (info.start <= new_date <= info.end):
                raise CalendarError(f"{new_date:%d.%m.%Y} is outside the booking's term")
            await _open_date(session, info, new_date)
            period = await period_for(session, info, new_room, data.get("period_id", b.period_id), new_date)
        except CalendarError as exc:
            raise _conflict("calendar", str(exc)) from exc
        if not access.can(f"{_kind(b)}.edit_other_booking") and "date" in data:
            # owners (and room-level editors) move a booking within their own booking window only: never into
            # the past, never beyond range_min / range_max (deliberate security difference)
            t = await today(session)
            if new_date < t:
                raise _conflict("range_min", f"a booking cannot be moved into the past ({new_date:%d.%m.%Y})")
            await check_window(session, access, info, new_date, new_room)
        if "date" in data or "period_id" in data:
            await check_not_started(session, access, new_date, period)
        # P8: a move must keep every policy; a move cannot become a request, so "request" rules refuse it here
        moved = await booking_policies.violations(
            session, access, new_room, b.term_id, new_date, period, b.user_id, exclude={b.id}
        )
        if moved:
            raise booking_policies.refusal(moved[0])
        held = await find_conflict(
            session, new_room.id, new_date, period.start_period, period.end_period, exclude={b.id}
        )
        if held is not None:
            raise await _conflict_error(held, new_room, new_date)
        await session.execute(delete(BookingSlot).where(BookingSlot.booking_id == b.id))
        b.room_id, b.date, b.period_id = new_room.id, new_date, period.id
        b.start_period, b.end_period = period.start_period, period.end_period
        await session.flush()
        for s in _slot_rows(b):
            session.add(s)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise _conflict("conflict", "the slot was booked by someone else a moment ago") from exc
    now = utcnow()
    for row in targets:
        for key in ("notes", "department_id", "user_id"):
            if key in data:
                setattr(row, key, data[key])
        row.updated_at, row.updated_by = now, access.user_id
    if scope == "all" and b.series_id:
        series = await session.get(BookingSeries, b.series_id)
        if series is not None:
            for key in ("notes", "department_id", "user_id"):
                if key in data:
                    setattr(series, key, data[key])
            series.updated_at, series.updated_by = now, access.user_id
    payload = {"booking_ids": [t.id for t in targets], "actor_id": access.user_id, "scope": scope}
    others = [t for t in targets if not (moving and t.id == b.id)]
    if moving:
        await publish_event(
            session,
            "booking.move",
            "booking",
            b.id,
            before=before[b.id],
            after=snap(b),
            actor=access.user,
            term_id=b.term_id,
            reversible=True,
            notify=None if others else "booking.updated",
            payload=payload,
        )
    if others:
        await publish_event(
            session,
            "booking.update",
            "booking",
            b.id,
            items=[(t.id, before[t.id], snap(t)) for t in others],
            parent_after={"scope": scope},
            actor=access.user,
            term_id=b.term_id,
            notify="booking.updated",
            payload=payload,
        )
    await session.commit()
    return targets


# --------------------------------------------------------------------------------------------------
# Multi-booking
# --------------------------------------------------------------------------------------------------


async def _slot_state(
    session: AsyncSession, access: Access, room: Room, d: date, period: BookingPeriod
) -> dict[str, Any]:
    held = await find_conflict(session, room.id, d, period.start_period, period.end_period)
    return {
        "single": access.can("book_single.create", room),
        "recur": access.can("book_recur.create", room),
        "status": "free" if held is None else ("booked" if held.kind == "booking" else held.kind),
        "held": held.as_dict() if held else None,
    }


async def create_selection(session: AsyncSession, access: Access, slots: list[dict[str, Any]]) -> MultiBooking:
    if not slots:
        raise BookingError(422, "no_slots", "select at least one slot")
    first = slots[0]
    try:
        info = await resolve_term(
            session, first["date"], first.get("term_id"), view_all=access.can("system.view_all_sessions")
        )
    except CalendarError as exc:
        raise _conflict("calendar", str(exc)) from exc
    anchor = (await date_infos(session, info, [first["date"]]))[first["date"]]
    mb = MultiBooking(user_id=access.user_id, term_id=info.term.id, timetable_week_id=anchor.timetable_week_id)
    seen = set()
    for s in slots:
        key = (s["date"], s["period_id"], s["room_id"])
        if key in seen:
            continue
        seen.add(key)
        if not (info.start <= s["date"] <= info.end):
            raise _conflict("calendar", f"{s['date']:%d.%m.%Y} is outside term {info.term.code}")
        room = await visible_room(session, access, s["room_id"])
        if await session.get(BookingPeriod, s["period_id"]) is None:
            raise BookingError(422, "period", f"period {s['period_id']} not found")
        mb.slots.append(MultiBookingSlot(date=s["date"], period_id=s["period_id"], room_id=room.id))
    session.add(mb)
    await session.commit()
    await session.refresh(mb)
    return mb


async def selection_out(session: AsyncSession, access: Access, mb: MultiBooking) -> dict[str, Any]:
    term = await session.get(Term, mb.term_id)
    assert term is not None
    info = await term_info(session, term)
    slots = []
    for s in mb.slots:
        room = await session.get(Room, s.room_id)
        period = await session.get(BookingPeriod, s.period_id)
        if room is None or period is None or info is None:
            continue
        state = await _slot_state(session, access, room, s.date, period)
        rec = await recurring_dates(session, info, s.date)
        slots.append(
            {
                "mbs_id": s.id,
                "date": s.date.isoformat(),
                "period_id": s.period_id,
                "period_name": period.name,
                "room_id": s.room_id,
                "room_name": room.display_name,
                **state,
                "recurring_dates": [d.date.isoformat() for d in rec],
            }
        )
    left = await remaining_bookings(session, access)
    return {
        "id": mb.id,
        "term_id": mb.term_id,
        "timetable_week_id": mb.timetable_week_id,
        "can_book_single": any(x["single"] for x in slots),
        "can_book_recur": any(x["recur"] for x in slots),
        "remaining_bookings": left,
        "slots": slots,
    }


async def get_selection(session: AsyncSession, access: Access, mb_id: int) -> MultiBooking:
    mb = await session.get(MultiBooking, mb_id)
    if mb is None or mb.user_id != access.user_id or not mb.slots:  # no slots left = consumed
        raise BookingError(404, "not_found", "multi-booking not found")
    return mb


def _consume_selection(mb: MultiBooking) -> None:
    """Mark a selection as turned into bookings: drop its slots but keep the ``multi_bookings`` row.

    The row id is the submission's ``group_id`` on every booking it created (A-12 / T-R1-13). Deleting the
    row let SQLite hand the same rowid to the next selection, so every submission of a person read as one
    group ("P1–P12"); a kept row keeps ids unique. A slot-less selection answers 404 like a deleted one.
    """
    mb.slots.clear()


async def create_from_selection(
    session: AsyncSession,
    access: Access,
    mb_id: int,
    kind: str,
    choices: dict[int, dict[str, Any]],
    dry_run: bool,
    *,
    confirm_unpublished: bool = False,
) -> dict[str, Any]:
    mb = await get_selection(session, access, mb_id)
    selected = [s for s in mb.slots if choices.get(s.id, {}).get("create", True)]
    if not selected:
        raise BookingError(422, "none_selected", "no slots selected")
    if kind == "single":
        left = await remaining_bookings(session, access)
        if left is not None and len(selected) > left:
            raise _conflict(
                "must_select_fewer", f"you can make {left} more booking(s); select fewer slots", remaining=left
            )
        problems: list[dict[str, Any]] = []
        bodies: list[SingleIn] = []
        for s in selected:
            c = choices.get(s.id, {})
            body = SingleIn(
                room_id=s.room_id,
                date=s.date,
                period_id=s.period_id,
                notes=c.get("notes"),
                user_id=c.get("user_id"),
                department_id=c.get("department_id"),
                term_id=mb.term_id,
                user_given="user_id" in c,
                department_given="department_id" in c,
                confirm_unpublished=confirm_unpublished,
            )
            bodies.append(body)
            room = await session.get(Room, s.room_id)
            period = await session.get(BookingPeriod, s.period_id)
            if room is None or period is None:
                problems.append({"mbs_id": s.id, "code": "not_found", "message": "room or period gone"})
                continue
            if not access.can("book_single.create", room):
                problems.append(
                    {"mbs_id": s.id, "code": "book_single.create", "message": f"not allowed in {room.display_name}"}
                )
                continue
            held = await find_conflict(session, room.id, s.date, period.start_period, period.end_period)
            if held is not None:
                problems.append(
                    {"mbs_id": s.id, "code": "conflict", "message": "slot is taken", "conflict": held.as_dict()}
                )
                continue
            refused = [
                v
                for v in await booking_policies.violations(
                    session, access, room, mb.term_id, s.date, period, access.user_id
                )
                if v.effect == "refuse"
            ]
            if refused:
                problems.append(
                    {
                        "mbs_id": s.id,
                        "code": f"policy_{refused[0].rule}",
                        "message": refused[0].message_en,
                        "message_tr": refused[0].message_tr,
                        "policy": refused[0].as_dict(),
                    }
                )
        if problems or dry_run:
            if problems and not dry_run:
                raise _conflict("slots_unavailable", f"{len(problems)} slot(s) cannot be booked", problems=problems)
            return {"dry_run": True, "problems": problems, "would_create": len(selected) - len(problems)}
        created = []
        try:
            for body in bodies:
                created.append(await create_single(session, access, body, commit=False))
        except BookingError:
            await session.rollback()
            raise
        for b in created:
            b.multi_booking_id = mb.id
        _consume_selection(mb)
        await session.commit()
        return {"created": [await booking_out(session, access, b) for b in created], "skipped": []}
    # recurring: one series per selected slot
    results = []
    for s in selected:
        c = choices.get(s.id, {})
        rbody = RecurIn(
            room_id=s.room_id,
            period_id=s.period_id,
            date=s.date,
            start=c.get("recurring_start"),
            end=c.get("recurring_end"),
            notes=c.get("notes"),
            user_id=c.get("user_id"),
            department_id=c.get("department_id"),
            term_id=mb.term_id,
            user_given="user_id" in c,
            department_given="department_id" in c,
            multi=True,
            instances=c.get("instances"),  # per-date book / do not book / replace (reservation panel)
        )
        if dry_run:
            results.append({"mbs_id": s.id, "preview": plan_out(await plan_recurring(session, access, rbody))})
            continue
        mbs_id = s.id  # read before a rollback expires the row
        try:
            res = await create_recurring(session, access, rbody, commit=False)
        except BookingError as exc:
            await session.rollback()
            raise BookingError(exc.status, exc.code, f"slot {mbs_id}: {exc.message}", **exc.data) from exc
        results.append({"mbs_id": mbs_id, **res})
    if dry_run:
        return {"dry_run": True, "slots": results}
    mb = await get_selection(session, access, mb_id)
    _consume_selection(mb)
    await session.commit()
    return {"series": results}


# --------------------------------------------------------------------------------------------------
# Lists: mine, dashboard, owned rooms
# --------------------------------------------------------------------------------------------------


async def list_bookings(
    session: AsyncSession,
    access: Access,
    *,
    user_id: int | None = None,
    room_ids: list[int] | None = None,
    d_from: date | None = None,
    d_to: date | None = None,
    status: str | None = BOOKED,
    single_only: bool = False,
    exclude_user_id: int | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    q = select(Booking).order_by(Booking.date, Booking.start_period)
    if user_id is not None:
        q = q.where(Booking.user_id == user_id)
    if exclude_user_id is not None:
        q = q.where((Booking.user_id.is_(None)) | (Booking.user_id != exclude_user_id))
    if room_ids is not None:
        q = q.where(Booking.room_id.in_(room_ids))
    if d_from is not None:
        q = q.where(Booking.date >= d_from)
    if d_to is not None:
        q = q.where(Booking.date <= d_to)
    if status:
        q = q.where(Booking.status == status)
    if single_only:
        q = q.where(Booking.series_id.is_(None))
    rows = list((await session.execute(q.limit(limit))).scalars())
    out = []
    for b in rows:
        room = await session.get(Room, b.room_id)
        if room is None or not (access.can_view_room(room) or is_owner(access, b)):
            continue
        out.append(await booking_out(session, access, b))
    return out


async def dashboard(session: AsyncSession, access: Access) -> dict[str, Any]:
    """CRBS ``Dashboard::index``: my next 14 days, bookings by others in rooms I own, totals, limits."""
    t = await today(session)
    end = t + timedelta(days=14)
    owned = [r.id for r in (await session.execute(select(Room).where(Room.owner_user_id == access.user_id))).scalars()]
    mine = await list_bookings(session, access, user_id=access.user_id, d_from=t, d_to=end, single_only=True)
    in_my_rooms = (
        await list_bookings(
            session, access, room_ids=owned, d_from=t, d_to=end, single_only=True, exclude_user_id=access.user_id
        )
        if owned
        else []
    )
    # A-12: totals count sessions -- the periods of one submission (multi-booking) on one day and room are one
    # session; ``*_periods`` keep CRBS's row counts
    # T-R2-13 (R2-S-10): one basis for the three numbers: live rows only (a cancelled booking is not a booking any
    # more), counted as sessions like ``active``; ``cancelled`` and ``pending`` are apart
    all_rows = (
        await session.execute(
            select(
                Booking.id, Booking.multi_booking_id, Booking.date, Booking.room_id, Booking.term_id, Booking.status
            ).where(Booking.user_id == access.user_id)
        )
    ).all()
    # W3-SLOT (round-3 academician): only live bookings count; a rejected / withdrawn / expired request never was one,
    # and an open request is shown apart (``pending``), so the line matches the bookings listed under it
    rows = [r for r in all_rows if r.status == BOOKED]
    pending_rows = [r for r in all_rows if r.status == PENDING]
    current = sorted(await current_term_ids(session, t))  # computed from the dates like CRBS (audit B3)

    def sessions(items: list[Any]) -> int:
        return len({(r.multi_booking_id, r.date, r.room_id) if r.multi_booking_id else r.id for r in items})

    in_session = [r for r in rows if current and r.term_id == current[0]]
    total_all, total_session = sessions(list(rows)), sessions(in_session)
    active = await active_bookings(session, access.user_id)
    return {
        "user_bookings": mine,
        "room_bookings": in_my_rooms,
        "owned_room_ids": owned,
        "totals": {
            "all": int(total_all),
            "session": int(total_session),
            "all_periods": len(rows),
            "session_periods": len(in_session),
            "cancelled": sum(1 for r in all_rows if r.status == CANCELLED),
            "pending": sessions(pending_rows),
            # sessions, like ``all`` / ``session``; ``active_periods`` is the row count the booking limit uses
            "active": sessions(active),
            "active_periods": len(active),
        },
        "limits": await effective_limits(session, access.user),
    }


# --------------------------------------------------------------------------------------------------
# Rooms visible to a user, and the grid
# --------------------------------------------------------------------------------------------------


async def visible_rooms(session: AsyncSession, access: Access, room_group_id: int | None = None) -> list[Room]:
    """``Rooms_model::get_bookable_rooms``: bookable rooms with ``room.view`` (role or ACL)."""
    q = select(Room).where(Room.is_bookable.is_(True))
    if room_group_id is not None:
        q = q.where(Room.room_group_id == room_group_id)
    hide_ungrouped = await ungrouped_rooms_hidden(session)
    rooms = [
        r
        for r in (await session.execute(q)).scalars()
        if access.can_view_room(r) and not (hide_ungrouped and r.room_group_id is None)
    ]
    # audit B7: the configured order (room_groups.pos, then rooms.pos), ungrouped rooms last; equal positions
    # fall back to the names in Turkish alphabetical order (CRBS rg.name / rooms.name, Unicode collation)
    group_pos = {
        g.id: (g.pos or 0, tr_sort_key(g.name), g.id) for g in (await session.execute(select(RoomGroup))).scalars()
    }
    rooms.sort(
        key=lambda r: (
            r.room_group_id is None,
            group_pos.get(r.room_group_id or 0, ()),
            r.pos or 0,
            tr_sort_key(r.display_name or r.code),
            r.code,
        )
    )
    return rooms


async def grid(
    session: AsyncSession,
    access: Access,
    *,
    display: str,
    d: date | None,
    term_id: int | None,
    room_group_id: int | None,
    room_id: int | None,
    use_room_groups: bool,
) -> dict[str, Any]:
    t = await today(session)
    target = d or t
    view_all = access.can("system.view_all_sessions")
    try:
        info = await resolve_term(session, target, term_id, view_all=view_all)
    except CalendarError:
        if term_id is None or d is not None:
            raise
        term = await session.get(Term, term_id)
        info_opt = await term_info(session, term) if term else None
        if info_opt is None:
            raise
        info = info_opt
        target = info.start
    rooms = await visible_rooms(session, access)
    if display == "day":
        if use_room_groups and rooms:
            # group 0 = rooms without a group: only present when bookings.show_ungrouped_rooms is on (CRBS hides
            # them); the default tab is the first group in the configured order (audit B7)
            valid = list(dict.fromkeys(r.room_group_id or 0 for r in rooms))
            room_group_id = room_group_id if room_group_id in valid else valid[0]
            rooms = [r for r in rooms if (r.room_group_id or 0) == room_group_id]
        dates = [target]
    else:
        room = next((r for r in rooms if r.id == room_id), None)
        if room is None:
            owned = next((r for r in rooms if r.owner_user_id == access.user_id), None)
            room = owned or (rooms[0] if rooms else None)
        rooms = [room] if room else []
        monday = target - timedelta(days=target.isoweekday() - 1)
        dates = [monday + timedelta(days=i) for i in range(7)]
    # audit B13: every room uses its own applied schedule (rooms of several groups share the grid when room
    # groups are off); the period columns are the union, a period outside a room's schedule is "schedule"
    by_group: dict[int, BookingSchedule | None] = {}
    room_schedule: dict[int, BookingSchedule | None] = {}
    for r in rooms:
        key = r.room_group_id or 0
        if key not in by_group:
            by_group[key] = await applied_schedule(session, info, r)
        room_schedule[r.id] = by_group[key]
    schedule = room_schedule.get(rooms[0].id) if rooms else None
    room_periods = {
        rid: {p.id for p in sch.periods if p.bookable} if sch else set() for rid, sch in room_schedule.items()
    }
    seen_periods: dict[int, BookingPeriod] = {}
    for sch in by_group.values():
        for p in sch.periods if sch else []:
            if p.bookable:
                seen_periods.setdefault(p.id, p)
    periods = sorted(seen_periods.values(), key=lambda p: (p.time_start, p.start_period, p.id))
    period_days = {int(x) for p in periods for x in (p.days or [])}
    if display == "day":
        periods = [p for p in periods if target.isoweekday() in (p.days or [])]
    elif period_days:
        # CRBS Context::init_week: dates whose weekday has no period are not shown (audit B15)
        dates = [x for x in dates if x.isoweekday() in period_days] or dates
    dinfos = await date_infos(session, info, dates)
    room_ids = {r.id for r in rooms}
    d0, d1 = min(dates), max(dates)
    bocc = await booking_occupancy(session, room_ids, d0, d1, viewer=access)
    tocc = await timetable_occupancy(session, room_ids, d0, d1)
    limits = await effective_limits(session, access.user)
    left = await remaining_bookings(session, access)
    lo, hi = limits["range_min"], limits["range_max"]
    min_date = t + timedelta(days=lo or 0)
    max_date = t + timedelta(days=hi) if hi is not None else info.end
    now = await now_local(session)
    may_book_past = access.can(PAST_BOOKING_PERM)
    policies = await booking_policies.PolicyIndex.load(session)
    booking_cache: dict[int, Booking] = {}
    slots = []
    for day in dates:
        di = dinfos[day]
        for p in periods:
            for r in rooms:
                past = period_started(day, p, now)
                slot: dict[str, Any] = {"date": day.isoformat(), "period_id": p.id, "room_id": r.id, "past": past}
                status, reason, label = "available", None, None
                held_b = next((h for h in bocc.get((r.id, day), []) if h.overlaps(p.start_period, p.end_period)), None)
                held_t = next((h for h in tocc.get((r.id, day), []) if h.overlaps(p.start_period, p.end_period)), None)
                if p.id not in room_periods.get(r.id, set()):
                    status, reason = "unavailable", "schedule"
                elif di.reason == "holiday":
                    status, reason, label = "unavailable", "holiday", di.holiday
                elif day.isoweekday() not in (p.days or []):
                    status, reason = "unavailable", "period"
                elif held_b is not None:
                    b = booking_cache.get(held_b.ref_id) or await session.get(Booking, held_b.ref_id)
                    assert b is not None
                    booking_cache[b.id] = b
                    status, reason = "booked", ("recurring" if b.series_id else "single")
                    if held_b.pending:  # U-06: the viewer's own (or to-be-approved) request
                        reason, slot["pending"] = "pending", True
                    slot["booking"] = await booking_out(session, access, b)
                elif held_t is not None:
                    status, reason, label = "timetable", held_t.kind, held_t.label
                elif not di.open:
                    status, reason = "unavailable", di.reason
                else:
                    single = access.can("book_single.create", r)
                    recur = access.can("book_recur.create", r)
                    slot["allow_single"], slot["allow_recur"] = single, recur
                    if left is not None and left < 1:
                        status, reason = "unavailable", "limit"
                    elif not single and not recur:
                        status, reason = "unavailable", "permissions"
                    elif single and not recur and day < min_date:
                        status, reason = "unavailable", "range_min"
                    elif single and not recur and day > max_date:
                        status, reason = "unavailable", "range_max"
                    elif past and not may_book_past:
                        status, reason = "unavailable", "past"  # U-04: the period already started
                    else:
                        # P8: a policy refuses the slot ("unavailable", reason "policy") or makes it request-only
                        found = await policies.static_violations(
                            session, access, r, info.term.id, day, p.time_start, p.time_end, t
                        )
                        refused = next((v for v in found if v.effect == "refuse"), None)
                        if refused is not None:
                            status, reason = "unavailable", "policy"
                            slot["policy"] = refused.as_dict()
                        elif found:
                            slot["request_only"] = True
                            slot["policy"] = found[0].as_dict()
                slot.update(status=status, reason=reason, label=label)
                slots.append(slot)
    prev_d, next_d = await _prev_next(session, info, target, display, period_days)
    return {
        "timetable_state": await timetable_state(session, d0, d1),
        "display": display,
        "term": {
            "id": info.term.id,
            "code": info.term.code,
            "name": info.term.name,
            "start": info.start.isoformat(),
            "end": info.end.isoformat(),
        },
        "date": target.isoformat(),
        "room_group_id": room_group_id,
        "schedule": {"id": schedule.id, "name": schedule.name} if schedule else None,
        "room_schedules": {str(rid): sch.id if sch else None for rid, sch in room_schedule.items()},
        "dates": [
            {
                "date": x.date.isoformat(),
                "weekday": x.weekday,
                "term_week": x.term_week,
                "timetable_week_id": x.timetable_week_id,
                "holiday": x.holiday,
                "open": x.open,
                "reason": x.reason,
            }
            for x in dinfos.values()
        ],
        "periods": [
            {
                "id": p.id,
                "name": p.name,
                "time_start": f"{p.time_start:%H:%M}",
                "time_end": f"{p.time_end:%H:%M}",
                "start_period": p.start_period,
                "end_period": p.end_period,
                "days": p.days,
            }
            for p in periods
        ],
        "rooms": [
            {
                "id": r.id,
                "name": r.display_name,
                "code": r.code,
                "room_group_id": r.room_group_id,
                "capacity": r.capacity,
            }
            for r in rooms
        ],
        "slots": slots,
        "nav": {
            "prev": prev_d.isoformat() if prev_d else None,
            "next": next_d.isoformat() if next_d else None,
        },
        "limits": limits,
        "remaining_bookings": left,
        "problems": ([] if schedule else ["no_schedule"]) + ([] if rooms else ["no_rooms"]),
    }


async def _prev_next(
    session: AsyncSession, info: TermInfo, target: date, display: str, period_days: set[int]
) -> tuple[date | None, date | None]:
    """CRBS ``Dates_model::get_prev_next``: the nearest dates of the term whose weekday has periods (and, once
    the term uses timetable weeks, that have a week); day view also skips holidays, week view jumps at least
    7 days (audit B15)."""
    if not period_days:
        return None, None
    span = (info.end - info.start).days
    every = [info.start + timedelta(days=i) for i in range(span + 1)]
    infos = await date_infos(session, info, every)
    uses_weeks = any(x.mapped for x in infos.values())

    def ok(x: DateInfo) -> bool:
        if x.weekday not in period_days or (uses_weeks and not x.mapped):
            return False
        return not (display == "day" and x.holiday is not None)

    if display == "day":
        before = [d for d, x in infos.items() if d < target and ok(x)]
        after = [d for d, x in infos.items() if d > target and ok(x)]
    else:
        before = [d for d, x in infos.items() if d <= target - timedelta(days=7) and ok(x)]
        after = [d for d, x in infos.items() if d >= target + timedelta(days=7) and ok(x)]
    return (max(before) if before else None), (min(after) if after else None)


async def conflicts_with_timetable(session: AsyncSession, term_id: int | None) -> list[dict[str, Any]]:
    """Active bookings that overlap the published timetable or a block (e.g. after a run was activated)."""
    q = select(Booking).where(Booking.status == BOOKED)
    if term_id is not None:
        q = q.where(Booking.term_id == term_id)
    rows = list((await session.execute(q)).scalars())
    if not rows:
        return []
    occ = await timetable_occupancy(
        session, {b.room_id for b in rows}, min(b.date for b in rows), max(b.date for b in rows)
    )
    out = []
    for b in rows:
        for held in occ.get((b.room_id, b.date), []):
            if held.overlaps(b.start_period, b.end_period):
                out.append(
                    {"booking_id": b.id, "room_id": b.room_id, "date": b.date.isoformat(), "held": held.as_dict()}
                )
    return out
