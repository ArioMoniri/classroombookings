"""Booking calendar: term (session) ranges, holidays, date -> timetable week, recurring dates, schedules and
periods on the shared 18-period grid (CRBS ``Dates_model``, ``Sessions_model``, ``Schedules_model``)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import (
    BookingPeriod,
    BookingSchedule,
    Holiday,
    Term,
    TermBookingSettings,
    TermDate,
    TermSchedule,
    TimetableWeek,
    Week,
)
from app.models.catalog import Room
from app.services.calendar import term_monday, week_index_for_date


class CalendarError(ValueError):
    """A booking request does not fit the calendar (409 with this message)."""


# --------------------------------------------------------------------------------------------------
# Periods on the grid
# --------------------------------------------------------------------------------------------------


def parse_clock(value: str) -> time:
    """``09:20``, ``09.20`` (dotted), ``9:20`` or ``9`` -> time; NBSP and Turkish punctuation tolerated."""
    t = n.parse_time(value)
    if t is None:
        raise ValueError(f"cannot read time {value!r}")
    return t


def grid_span(start: time, end: time) -> tuple[int, int]:
    """Map a period's times onto the university grid (P1 08:30 … P18 22:10-22:50)."""
    if end <= start:
        raise ValueError("time_end must be after time_start")
    rng = n.time_range_to_periods(start, end)
    if rng.start_period is None or rng.end_period is None:
        raise ValueError(f"{start:%H:%M}-{end:%H:%M} is outside the 08:30-22:50 period grid")
    return rng.start_period, rng.end_period


def fgcol(bgcol: str) -> str:
    """CRBS ``colour_brightness``: black text on light backgrounds, white on dark ones."""
    h = bgcol.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    bright = (r * 299 + g * 587 + b * 114) / 1000
    return "#000000" if bright > 160 else "#ffffff"


# --------------------------------------------------------------------------------------------------
# Terms (sessions)
# --------------------------------------------------------------------------------------------------


@dataclass
class TermInfo:
    term: Term
    start: date
    end: date
    weeks: list[Week]
    is_selectable: bool
    default_schedule_id: int | None


async def term_info(session: AsyncSession, term: Term) -> TermInfo | None:
    """Range of a term: its dates, or the span of its calendar weeks when the end date is unknown."""
    weeks = list((await session.execute(select(Week).where(Week.term_id == term.id).order_by(Week.index))).scalars())
    starts = [w.start_date for w in weeks if w.start_date]
    start = term.start_date or (min(starts) if starts else None)
    if start is None:
        monday = term_monday(term, weeks)
        start = monday
    end = term.end_date
    if end is None and starts:
        end = max(starts) + timedelta(days=6)
    if end is None and start is not None and term.week_count:
        end = start + timedelta(weeks=term.week_count, days=-1)
    if start is None or end is None:
        return None
    settings = await session.get(TermBookingSettings, term.id)
    return TermInfo(
        term=term,
        start=start,
        end=end,
        weeks=weeks,
        # no settings row yet: the active (current) term is selectable, others are not
        is_selectable=settings.is_selectable if settings is not None else bool(term.is_active),
        default_schedule_id=settings.default_schedule_id if settings is not None else None,
    )


async def terms_for_date(session: AsyncSession, d: date) -> list[TermInfo]:
    out = []
    for term in (await session.execute(select(Term).order_by(Term.id))).scalars():
        info = await term_info(session, term)
        if info is not None and info.start <= d <= info.end:
            out.append(info)
    return out


async def resolve_term(session: AsyncSession, d: date, term_id: int | None, *, view_all: bool) -> TermInfo:
    if term_id is not None:
        term = await session.get(Term, term_id)
        if term is None:
            raise CalendarError(f"term {term_id} not found")
        info = await term_info(session, term)
        if info is None:
            raise CalendarError(f"term {term.code} has no dates")
        if not (info.start <= d <= info.end):
            raise CalendarError(f"{d:%d.%m.%Y} is outside term {term.code} ({info.start:%d.%m.%Y}-{info.end:%d.%m.%Y})")
    else:
        cands = await terms_for_date(session, d)
        cands.sort(key=lambda t: (not t.term.is_active, not t.is_selectable, t.term.id))
        if not cands:
            raise CalendarError(f"no term covers {d:%d.%m.%Y}")
        info = cands[0]
    if not view_all and not info.is_selectable:
        raise CalendarError(f"term {info.term.code} is not open for bookings")
    return info


# --------------------------------------------------------------------------------------------------
# Holidays and timetable weeks
# --------------------------------------------------------------------------------------------------


async def holidays_by_date(session: AsyncSession, info: TermInfo) -> dict[date, str]:
    """Dates closed for bookings: ``holidays`` rows, plus whole calendar weeks marked HOLIDAY."""
    out: dict[date, str] = {}
    for h in (await session.execute(select(Holiday).where(Holiday.term_id == info.term.id))).scalars():
        d = h.date_start
        while d <= h.date_end:
            out[d] = h.name
            d += timedelta(days=1)
    for w in info.weeks:
        if w.kind == "HOLIDAY" and w.start_date:
            for i in range(7):
                out.setdefault(w.start_date + timedelta(days=i), w.label or "Tatil")
    return out


async def week_map(session: AsyncSession, term_id: int) -> dict[date, int | None]:
    rows = (await session.execute(select(TermDate).where(TermDate.term_id == term_id))).scalars()
    return {r.date: r.timetable_week_id for r in rows}


@dataclass
class DateInfo:
    date: date
    weekday: int
    term_week: int | None  # calendar week index of the term
    timetable_week_id: int | None
    mapped: bool  # the term uses timetable weeks and this date has one
    holiday: str | None
    open: bool  # bookable as far as the calendar is concerned
    reason: str | None


async def date_infos(session: AsyncSession, info: TermInfo, dates: list[date]) -> dict[date, DateInfo]:
    holidays = await holidays_by_date(session, info)
    mapping = await week_map(session, info.term.id)
    uses_weeks = any(v is not None for v in mapping.values())
    out: dict[date, DateInfo] = {}
    for d in dates:
        wk = week_index_for_date(info.term, d, info.weeks)
        tw = mapping.get(d)
        reason = None
        if not (info.start <= d <= info.end):
            reason = "date_range"
        elif d in holidays:
            reason = "holiday"
        elif uses_weeks and tw is None:
            reason = "no_week"
        out[d] = DateInfo(
            date=d,
            weekday=d.isoweekday(),
            term_week=wk,
            timetable_week_id=tw,
            mapped=tw is not None,
            holiday=holidays.get(d),
            open=reason is None,
            reason=reason,
        )
    return out


async def recurring_dates(session: AsyncSession, info: TermInfo, anchor: date) -> list[DateInfo]:
    """CRBS ``get_recurring_dates``: same weekday and same timetable week as ``anchor``, holidays skipped.
    A term without timetable-week mapping recurs every week."""
    all_dates = []
    d = info.start + timedelta(days=(anchor.isoweekday() - info.start.isoweekday()) % 7)
    while d <= info.end:
        all_dates.append(d)
        d += timedelta(days=7)
    infos = await date_infos(session, info, all_dates)
    anchor_info = (await date_infos(session, info, [anchor]))[anchor]
    return [
        x
        for x in infos.values()
        if x.holiday is None and x.reason in (None,) and x.timetable_week_id == anchor_info.timetable_week_id
    ]


async def timetable_week(session: AsyncSession, week_id: int | None) -> TimetableWeek | None:
    return await session.get(TimetableWeek, week_id) if week_id else None


# --------------------------------------------------------------------------------------------------
# Schedules
# --------------------------------------------------------------------------------------------------


async def applied_schedule(session: AsyncSession, info: TermInfo, room: Room) -> BookingSchedule | None:
    """CRBS ``get_applied_schedule``: the term's schedule for the room's group, else the term default."""
    if room.room_group_id is not None:
        ts = await session.get(TermSchedule, (info.term.id, room.room_group_id))
        if ts is not None:
            return await session.get(BookingSchedule, ts.schedule_id)
    if info.default_schedule_id is not None:
        return await session.get(BookingSchedule, info.default_schedule_id)
    return None


async def period_for(session: AsyncSession, info: TermInfo, room: Room, period_id: int, d: date) -> BookingPeriod:
    period = await session.get(BookingPeriod, period_id)
    if period is None:
        raise CalendarError(f"period {period_id} not found")
    schedule = await applied_schedule(session, info, room)
    if schedule is None:
        raise CalendarError(f"no schedule is set for {room.display_name} in term {info.term.code}")
    if period.schedule_id != schedule.id:
        raise CalendarError(f"period {period.name} is not in the schedule of {room.display_name} ({schedule.name})")
    if not period.bookable:
        raise CalendarError(f"period {period.name} is not bookable")
    if d.isoweekday() not in (period.days or []):
        raise CalendarError(f"period {period.name} is not available on {n.DAY_LABELS_TR.get(d.isoweekday(), d)}")
    return period
