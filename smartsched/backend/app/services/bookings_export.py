"""Booking exports: CSV with the CRBS columns (``Bookings_model::export_unbuffered``) and iCalendar feeds."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.export_safety import ics_text, safe_writer
from app.models import (
    Booking,
    BookingPeriod,
    BookingSchedule,
    Program,
    RoomGroup,
    Term,
    TermDate,
    TimetableWeek,
    User,
)
from app.models.booking import BOOKED
from app.models.catalog import Room
from app.services import settings_service
from app.services.bookings import can_view_notes, can_view_user
from app.services.bookings_perms import Access
from app.services.bookings_settings import get_value

CSV_COLUMNS = (
    "Booking ID",
    "Recurring ID",
    "Type",
    "Status",
    "Session",
    "Date",
    "Weekday",
    "Timetable Week",
    "Period",
    "Schedule",
    "Start Time",
    "End Time",
    "Room",
    "Room Group",
    "Notes",
    "Username",
    "User",
    "Department",
    "Created At",
    "Created User",
    "Updated At",
    "Updated User",
    "Cancelled At",
    "Cancelled User",
)
WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _ts(v: datetime | None) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S") if v else ""


async def export_csv(
    session: AsyncSession, *, term_id: int | None, room_group_id: int | None, include_cancelled: bool
) -> str:
    """UTF-8 CSV with a BOM so that Excel shows Turkish letters (ç, ğ, ı, İ, ö, ş, ü) correctly."""
    q = select(Booking).order_by(Booking.date, Booking.start_period, Booking.room_id)
    if not include_cancelled:
        q = q.where(Booking.status == BOOKED)
    if term_id is not None:
        q = q.where(Booking.term_id == term_id)
    rows = list((await session.execute(q)).scalars())
    cache: dict[tuple[type, int], Any] = {}

    async def get(model: type, key: int | None) -> Any:
        if key is None:
            return None
        if (model, key) not in cache:
            cache[(model, key)] = await session.get(model, key)
        return cache[(model, key)]

    weeks = {(r.term_id, r.date): r.timetable_week_id for r in (await session.execute(select(TermDate))).scalars()}
    # CRBS export_unbuffered joins room_groups INNER: rooms without a group are left out (deliberate
    # difference j; bookings.export_ungrouped_rooms includes them)
    include_ungrouped = bool(await get_value(session, "bookings", "export_ungrouped_rooms"))
    buf = io.StringIO()
    buf.write("\ufeff")
    w = safe_writer(csv.writer(buf, lineterminator="\r\n"))  # review M8
    w.writerow(CSV_COLUMNS)
    for b in rows:
        room: Room | None = await get(Room, b.room_id)
        if room_group_id is not None and (room is None or room.room_group_id != room_group_id):
            continue
        if not include_ungrouped and (room is None or room.room_group_id is None):
            continue
        period: BookingPeriod | None = await get(BookingPeriod, b.period_id)
        sched: BookingSchedule | None = await get(BookingSchedule, period.schedule_id if period else None)
        term: Term | None = await get(Term, b.term_id)
        group: RoomGroup | None = await get(RoomGroup, room.room_group_id if room else None)
        user: User | None = await get(User, b.user_id)
        tw: TimetableWeek | None = await get(TimetableWeek, weeks.get((b.term_id, b.date)))
        dep: Program | None = await get(Program, b.department_id)
        cre: User | None = await get(User, b.created_by)
        upd: User | None = await get(User, b.updated_by)
        can: User | None = await get(User, b.cancelled_by)
        w.writerow(
            [
                b.id,
                b.series_id or "",
                "Recurring" if b.series_id else "Single",
                "Booked" if b.status == BOOKED else "Cancelled",
                term.name if term else "",
                b.date.isoformat(),
                WEEKDAYS_EN[b.date.weekday()],
                tw.name if tw else "",
                period.name if period else "",
                sched.name if sched else "",
                f"{period.time_start:%H:%M}" if period else "",
                f"{period.time_end:%H:%M}" if period else "",
                room.display_name if room else "",
                group.name if group else "",
                b.notes or "",
                (user.username or user.email or "") if user else "",
                (user.full_name or user.username or user.email or "") if user else "",
                dep.name if dep else "",
                _ts(b.created_at),
                (cre.username or cre.email or "") if cre else "",
                _ts(b.updated_at),
                (upd.username or upd.email or "") if upd else "",
                _ts(b.cancelled_at),
                (can.username or can.email or "") if can else "",
            ]
        )
    return buf.getvalue()


# --------------------------------------------------------------------------------------------------
# iCalendar
# --------------------------------------------------------------------------------------------------


def _esc(text: str) -> str:
    return ics_text(text)  # RFC 5545 escaping; CR/LF can never start a new property (review M8)


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Istanbul")


def _fixed_offset(tz: ZoneInfo, years: set[int]) -> timedelta | None:
    """The zone's UTC offset when it is the same all year in ``years`` (Turkey: +03:00 since 2016)."""
    offsets = {datetime(y, m, 15, 12, tzinfo=tz).utcoffset() for y in years for m in (1, 4, 7, 10)}
    return next(iter(offsets)) if len(offsets) == 1 else None


def _offset(td: timedelta) -> str:
    minutes = int(td.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}{minutes % 60:02d}"


def _vtimezone(name: str, offset: timedelta) -> list[str]:
    return [
        "BEGIN:VTIMEZONE",
        f"TZID:{name}",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        f"TZOFFSETFROM:{_offset(offset)}",
        f"TZOFFSETTO:{_offset(offset)}",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]


def _fold(line: str) -> list[str]:
    """RFC 5545 line folding at 75 octets (UTF-8 aware, never splitting a multi-byte character)."""
    out: list[str] = []
    cur = ""
    for ch in line:
        limit = 75 if not out else 74
        if len((cur + ch).encode("utf-8")) > limit:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return [out[0]] + [" " + x for x in out[1:]]


async def ics_feed(
    session: AsyncSession, access: Access, *, title: str, user_id: int | None = None, room_id: int | None = None
) -> str:
    q = select(Booking).where(Booking.status == BOOKED).order_by(Booking.date, Booking.start_period)
    if user_id is not None:
        q = q.where(Booking.user_id == user_id)
    if room_id is not None:
        q = q.where(Booking.room_id == room_id)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    # audit B11: the organisation's time zone. A zone with one offset all year (Europe/Istanbul) is written
    # as TZID + VTIMEZONE; a zone with daylight saving is written in UTC, which every client reads correctly.
    tz_name = str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul")
    tz = _tz(tz_name)
    rows = list((await session.execute(q)).scalars())
    fixed = _fixed_offset(tz, {b.date.year for b in rows} or {datetime.now(UTC).year})
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SmartSched//Bookings//TR",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_esc(title)}",
        f"X-WR-TIMEZONE:{tz.key}",
    ]
    if fixed is not None:
        lines += _vtimezone(tz.key, fixed)

    def when(prop: str, local: datetime) -> str:
        if fixed is not None:
            return f"{prop};TZID={tz.key}:{local:%Y%m%dT%H%M%S}"
        utc = local.replace(tzinfo=tz).astimezone(UTC)
        return f"{prop}:{utc:%Y%m%dT%H%M%SZ}"

    for b in rows:
        room = await session.get(Room, b.room_id)
        period = await session.get(BookingPeriod, b.period_id)
        if room is None or period is None:
            continue
        start = datetime.combine(b.date, period.time_start)
        end = datetime.combine(b.date, period.time_end)
        if end <= start:
            end = start + timedelta(minutes=40)
        summary = f"{room.display_name} – {period.name}"
        desc = []
        if b.notes and can_view_notes(access, b, room):
            desc.append(b.notes)
        if b.user_id and can_view_user(access, b, room):
            u = await session.get(User, b.user_id)
            if u is not None:
                desc.append(u.full_name or u.username or u.email or "")
        ev = [
            "BEGIN:VEVENT",
            f"UID:booking-{b.id}@smartsched",
            f"DTSTAMP:{stamp}",
            when("DTSTART", start),
            when("DTEND", end),
            f"SUMMARY:{_esc(summary)}",
            f"LOCATION:{_esc(room.display_name)}",
        ]
        if desc:
            ev.append(f"DESCRIPTION:{_esc(' / '.join(x for x in desc if x))}")
        ev.append("END:VEVENT")
        for line in ev:
            lines.extend(_fold(line))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
