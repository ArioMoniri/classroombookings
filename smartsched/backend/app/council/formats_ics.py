"""iCalendar (.ics) in the registry: VEVENTs become a schedule map (booking records), never people.

* Parsed with :mod:`icalendar` (pinned main dependency). ``ORGANIZER`` and ``ATTENDEE`` are never read
  (KVKK: they are names and e-mail addresses); e-mail addresses in ``DESCRIPTION`` are masked.
* Times are local wall-clock times of the institution: a UTC / ``TZID`` time is converted to
  ``Europe/Istanbul``; floating times (SmartSched's own export) are kept as they are.
* ``RRULE`` / ``RDATE`` / ``EXDATE`` are expanded inside a window (the term's dates when the caller knows
  them, else one year from the first event), with at most ``max_instances`` instances per file and at most
  ``max_iterations`` recurrence steps walked, so ``FREQ=SECONDLY`` without ``UNTIL`` stays bounded.
  Sub-daily frequencies are not a timetable and are skipped with a warning. ``STATUS:CANCELLED`` is skipped.
* Rendered as one table (``events``: date, day, start, end, location, summary, uid) for the review screen;
  :func:`ics_records` turns the same instances into ``booking`` records (room, day, date, start, end, text,
  course codes), which commit maps onto the term's weeks and the baseline run (P19-I5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core import safe_files
from app.council import text as tx
from app.council.formats import FormatLimits, FormatSpec, MiB, Probe, register
from app.council.render import Grid, Rendered, RenderError

LOCAL_TZ = "Europe/Istanbul"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_SUBDAILY = {"SECONDLY", "MINUTELY", "HOURLY"}


@dataclass(frozen=True)
class Instance:
    uid: str
    when: date
    start: time | None
    end: time | None
    summary: str
    location: str
    description: str
    recurring: bool


def _local(v: Any, tz: ZoneInfo) -> tuple[date, time | None]:
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            v = v.astimezone(tz)
        return v.date(), v.time().replace(tzinfo=None, microsecond=0)
    return v, None  # all-day


def _calendar(data: bytes) -> Any:
    try:
        from icalendar import Calendar
    except ImportError as exc:  # pragma: no cover - pinned main dependency (P19-Q3)
        raise RenderError("icalendar is not installed on the server") from exc
    from app.council.formats_text import decode_text

    text, _ = decode_text(data)
    try:
        cals = Calendar.from_ical(text, multiple=True)
    except Exception as exc:  # noqa: BLE001 - malformed content lines
        raise safe_files.UnsafeFileError(400, f"the calendar is not valid iCalendar: {type(exc).__name__}") from exc
    if not cals:
        raise RenderError("the file holds no VCALENDAR")
    return cals


def instances(
    data: bytes, lim: FormatLimits, window: tuple[date, date] | None = None
) -> tuple[list[Instance], list[str]]:
    """Every event instance in ``window`` (see the module notes for the caps)."""
    from dateutil.rrule import rruleset, rrulestr

    tz = ZoneInfo(LOCAL_TZ)
    warnings: list[str] = []
    events = [ev for cal in _calendar(data) for ev in cal.walk("VEVENT")]
    if not events:
        return [], ["the calendar holds no events (VEVENT)"]
    starts = []
    for ev in events:
        ds = ev.get("DTSTART")
        if ds is not None:
            starts.append(_local(ds.dt, tz)[0])
    if window is None:
        first = min(starts) if starts else date.today()
        window = (first, first + timedelta(days=366))
    lo, hi = window
    out: list[Instance] = []
    steps = 0
    stopped = False
    for ev in events:
        if str(ev.get("STATUS") or "").upper() == "CANCELLED":
            continue
        ds = ev.get("DTSTART")
        if ds is None:
            warnings.append(f"event {ev.get('UID') or '?'} has no DTSTART; skipped")
            continue
        start_dt = ds.dt
        de = ev.get("DTEND")
        dur = ev.get("DURATION")
        if de is not None:
            length = de.dt - start_dt if type(de.dt) is type(start_dt) else None
        elif dur is not None:
            length = dur.dt
        else:
            length = timedelta(0) if isinstance(start_dt, datetime) else timedelta(days=1)
        uid = str(ev.get("UID") or "")
        summary = tx.cell_text(str(ev.get("SUMMARY") or ""))
        location = tx.cell_text(str(ev.get("LOCATION") or ""))
        description = _EMAIL.sub("[e-posta]", tx.cell_text(str(ev.get("DESCRIPTION") or "")))[:500]
        occurrences: list[Any] = []
        rrule = ev.get("RRULE")
        if rrule is not None or ev.get("RDATE") is not None:
            freq = str((rrule or {}).get("FREQ", [""])[0]).upper() if rrule is not None else ""
            if freq in _SUBDAILY:
                warnings.append(f"event {uid or summary!r}: a {freq} recurrence is not a timetable; skipped")
                continue
            rs = rruleset()
            naive = (
                start_dt.replace(tzinfo=None) if isinstance(start_dt, datetime) else datetime.combine(start_dt, time())
            )
            if rrule is not None:
                try:
                    rs.rrule(rrulestr(rrule.to_ical().decode(), dtstart=naive, ignoretz=True))  # type: ignore[arg-type]
                except (ValueError, TypeError) as exc:
                    warnings.append(f"event {uid or summary!r}: unreadable RRULE ({exc}); only its first date used")
                    rs.rdate(naive)
            else:
                rs.rdate(naive)
            for key in ("RDATE", "EXDATE"):
                vals = ev.get(key)
                for prop in vals if isinstance(vals, list) else ([vals] if vals is not None else []):
                    for d in getattr(prop, "dts", []):
                        v = d.dt
                        v = v.replace(tzinfo=None) if isinstance(v, datetime) else datetime.combine(v, time())
                        (rs.rdate if key == "RDATE" else rs.exdate)(v)
            for occ in rs:
                steps += 1
                if steps > lim.max_iterations:
                    stopped = True
                    break
                if occ.date() > hi:
                    break
                if occ.date() >= lo:
                    occurrences.append(occ if isinstance(start_dt, datetime) else occ.date())
            if isinstance(start_dt, datetime) and start_dt.tzinfo is not None:
                occurrences = [o.replace(tzinfo=start_dt.tzinfo) for o in occurrences]
        else:
            occurrences = [start_dt]
        for occ in occurrences:
            d, t0 = _local(occ, tz)
            if not lo <= d <= hi:
                continue
            t1 = None
            if t0 is not None and length is not None:
                d1, t1 = _local(occ + length, tz)
                if d1 != d:
                    t1 = time(23, 59)
            out.append(Instance(uid, d, t0, t1, summary, location, description, rrule is not None))
            if len(out) >= lim.max_instances:
                stopped = True
                break
        if stopped:
            break
    if stopped:
        warnings.append(
            f"recurrence expansion stopped at {lim.max_instances} instances / {lim.max_iterations} steps; "
            "later dates were not read"
        )
    out.sort(key=lambda i: (i.when, i.start or time(), i.location, i.summary))
    return out, warnings


def _render_ics(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    found, warnings = instances(data, lim)
    out.warnings.extend(warnings)
    rows = [["date", "day", "start", "end", "location", "summary", "uid"]]
    for i in found:
        rows.append(
            [
                i.when.isoformat(),
                str(i.when.isoweekday()),
                tx.hhmm(i.start) or "",
                tx.hhmm(i.end) or "",
                i.location,
                i.summary,
                i.uid,
            ]
        )
    out.grids.append(Grid("events", "table", rows, [], {"table": "events"}, list(range(1, len(rows) + 1))))


def _precheck_ics(data: bytes, lim: FormatLimits) -> None:
    instances(data, lim)


def ics_records(
    data: bytes, filename: str, lim: FormatLimits | None = None, window: tuple[date, date] | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Booking records of the instances (one per room named in ``LOCATION``; no person data)."""
    from app.importers import normalize as n

    found, warnings = instances(data, lim or FormatLimits(max_bytes=10 * MiB), window)
    out: list[dict[str, Any]] = []
    for i in found:
        rooms = [c for part in re.split(r"\s*(?:/|;|\+|&|,)\s*", i.location) for c in n.parse_room_codes(part)]
        rooms = list(dict.fromkeys(rooms)) or ([i.location] if i.location else [])
        if not rooms:
            warnings.append(f"{i.when} {i.summary!r}: no LOCATION; not placed in a room")
            continue
        codes = tx.course_codes(i.summary)
        section = None
        m = re.search(r"§\s*([0-9A-Za-zÇĞİÖŞÜçğıöşü]+)", i.summary)
        if m:
            section = n.parse_section_label(m.group(1))
        for room in rooms:
            out.append(
                {
                    "type": "booking",
                    "sheet": None,
                    "week_index": None,
                    "sheet_kind": None,
                    "day": i.when.isoweekday(),
                    "day_text": None,
                    "date": i.when.isoformat(),
                    "room_code": room,
                    "room_label": n.display_room_code(room),
                    "room_capacity": None,
                    "room_tags": [],
                    "start": tx.hhmm(i.start),
                    "end": tx.hhmm(i.end),
                    "slot_start": None,
                    "slot_end": None,
                    "text": i.summary,
                    "course_codes": codes,
                    "section": section,
                    "notes": i.description or None,
                    "warnings": [],
                    "confidence": 1.0,
                    "source": {"file": filename, "uid": i.uid, "date": i.when.isoformat()},
                }
            )
    return out, warnings


def _sniff_ics(p: Probe) -> float:
    if p.family != "text":
        return 0.0
    return 1.0 if p.text.lstrip("﻿ \t\r\n").upper().startswith("BEGIN:VCALENDAR") else 0.0


register(
    FormatSpec(
        "ics",
        "iCalendar",
        "text",
        (".ics", ".ical", ".ifb"),
        "structured",
        _sniff_ics,
        _render_ics,
        FormatLimits(max_bytes=10 * MiB),
        _precheck_ics,
    )
)

__all__ = ["Instance", "LOCAL_TZ", "ics_records", "instances"]
