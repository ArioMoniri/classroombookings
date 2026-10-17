"""Utilisation heatmaps (docs/features.yml "utilisation heatmaps"; docs/design/dashboard.md §2.2).

Room occupancy as room x day x period for one run, or for the live published board of a term (the published
course and exam runs, the term's blocks and its bookings), grouped by building, room type or capacity band (or one
row per room), with counts and percentages; and an instructor load heatmap (who teaches when, periods per day,
idle gaps between classes). Pure reads: nothing is written.

Definitions (stated in every response under ``definitions``):

* a *room-period* is one room in one period of one day of one week (a course run) or one date (an exam run);
* ``occupied``: covered by a placement of the run (or of a published run) or by a booking (``BOOKED``);
  ``held``: a pending booking request that still holds its slot (``held_until`` ahead) - counted separately;
* ``blocked``: pre-occupied by a term block (prep school, distance education, events); the design hatches these
  and they are left out of the percentage: ``pct = occupied / (capacity - blocked)``; ``pct_with_blocks`` counts
  them as used (``(occupied + blocked) / capacity``);
* ``capacity``: rooms x weeks in scope for a cell (one week by default; ``scope=term`` averages the whole horizon).

Columns: ``axis=day`` (Monday..Sunday, aggregated over the weeks in scope; the course default) or ``axis=date``
(one column per week + day with its calendar date when the term has dates; the exam default).
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.export_safety import safe_writer
from app.models import (
    Assignment,
    Block,
    Booking,
    Instructor,
    MeetingRequest,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
    Week,
)
from app.services.calendar import date_for, week_index_for_date
from app.services.calendar_views import DAY_EN, DAY_EN_SHORT, DAY_TR, DAY_TR_SHORT, clock
from app.services.grid import assignment_weeks
from app.services.solver_bridge import horizon_weeks

PERIODS_PER_DAY = 18
WORKDAYS = (1, 2, 3, 4, 5)
#: runs whose placements are a timetable (a best-effort partial one included)
USABLE = ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL", "INFEASIBLE")
GROUP_BY = ("building", "room_type", "capacity_band", "room")
#: room type of a room: the first tag in this order, else STANDARD
ROOM_TYPES: tuple[tuple[str, str, str], ...] = (
    ("TIP", "Tıp", "Medicine (TIP)"),
    ("AMPHI", "Amfi", "Amphitheatre"),
    ("LAB", "Laboratuvar", "Laboratory"),
    ("PC", "Bilgisayar", "Computer room"),
    ("STANDARD", "Derslik", "Classroom"),
)
#: capacity bands (inclusive upper bounds; the last one is open)
CAPACITY_BANDS: tuple[tuple[int, str], ...] = ((30, "≤30"), (60, "31–60"), (100, "61–100"), (150, "101–150"))
CAPACITY_TOP = "151+"


class UtilisationError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


def _ints(values: Iterable[Any] | None) -> list[int]:
    out: list[int] = []
    for v in values or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def building_of(room: Room) -> str:
    return room.building.code if room.building is not None else (room.code[:1] or "?")


def room_type_of(room: Room) -> str:
    tags = {str(t).upper() for t in (room.tags or [])}
    for code, _tr, _en in ROOM_TYPES[:-1]:
        if code in tags:
            return code
    return "STANDARD"


def capacity_band_of(room: Room, exam: bool = False) -> str:
    cap = int((room.exam_capacity if exam else room.capacity) or 0)
    for upper, label in CAPACITY_BANDS:
        if cap <= upper:
            return label
    return CAPACITY_TOP


def group_key(room: Room, group_by: str, exam: bool = False) -> str:
    if group_by == "building":
        return building_of(room)
    if group_by == "room_type":
        return room_type_of(room)
    if group_by == "capacity_band":
        return capacity_band_of(room, exam)
    return room.code


def group_label(key: str, group_by: str, rooms: Mapping[int, Room]) -> dict[str, str]:
    if group_by == "building":
        return _t(f"{key} blok", f"Building {key}")
    if group_by == "room_type":
        names = {c: (tr, en) for c, tr, en in ROOM_TYPES}
        tr, en = names.get(key, (key, key))
        return _t(tr, en)
    if group_by == "capacity_band":
        return _t(f"{key} kişi", f"{key} seats")
    room = next((r for r in rooms.values() if r.code == key), None)
    name = room.display_name if room is not None else key
    return _t(name, name)


def _band_order(key: str) -> int:
    labels = [b for _u, b in CAPACITY_BANDS] + [CAPACITY_TOP]
    return labels.index(key) if key in labels else len(labels)


# ------------------------------------------------------------------------------------------- occupancy core


@dataclass
class Occupancy:
    """What covers each room-period, by source (``run`` / ``booking`` / ``held`` / ``block``)."""

    #: (room, week, day, period) -> set of sources
    cells: dict[tuple[int, int, int, int], set[str]] = field(default_factory=lambda: defaultdict(set))
    #: (week, day) -> calendar date (when the term has dates)
    dates: dict[tuple[int, int], date | None] = field(default_factory=dict)
    notes: list[dict[str, Any]] = field(default_factory=list)

    def add(self, room: int, week: int, day: int, start: int, end: int, source: str) -> None:
        for p in range(max(1, start), min(PERIODS_PER_DAY, end) + 1):
            self.cells[(room, week, day, p)].add(source)


async def _weeks_rows(session: AsyncSession, term: Term) -> list[Week]:
    return list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())


async def _rows(session: AsyncSession, run: ScheduleRun) -> list[Assignment]:
    return list(
        (
            await session.execute(select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False)))
        ).scalars()
    )


def _add_run(
    occ: Occupancy,
    run: ScheduleRun,
    rows: list[Assignment],
    weeks_in_scope: list[int],
    term: Term,
    weeks_rows: list[Week],
) -> None:
    scope = set(weeks_in_scope)
    for a in rows:
        ws = assignment_weeks(a)
        if a.date is not None and not ws:
            w = week_index_for_date(term, a.date, weeks_rows)
            ws = {w} if w is not None else set()
        cover = sorted(scope if not ws else ws & scope)
        for w in cover:
            if a.date is not None and len(cover) == 1:
                occ.dates.setdefault((w, a.day), a.date)
            for rid in _ints(a.room_ids):
                occ.add(rid, w, a.day, a.start_period, a.end_period, "run")


async def _add_blocks(
    session: AsyncSession, occ: Occupancy, term: Term, weeks_in_scope: list[int], weeks_rows: list[Week]
) -> int:
    scope = set(weeks_in_scope)
    n = 0
    for b in (
        await session.execute(select(Block).where(Block.term_id == term.id, Block.archived.is_(False)))
    ).scalars():
        if b.date is not None:
            w = week_index_for_date(term, b.date, weeks_rows)
            if w is None or w not in scope:
                continue
            pairs = [(w, b.date.isoweekday())]
        else:
            if b.day is None:
                continue
            ws = set(_ints(b.weeks))
            pairs = [(w, b.day) for w in sorted(scope if not ws else ws & scope)]
        for w, d in pairs:
            occ.add(b.room_id, w, d, b.start_period, b.end_period, "block")
            n += 1
    return n


async def _add_bookings(
    session: AsyncSession,
    occ: Occupancy,
    term: Term,
    weeks_in_scope: list[int],
    weeks_rows: list[Week],
    now: datetime | None = None,
) -> int:
    """Bookings of the term on dates inside the weeks in scope: ``BOOKED`` as occupied, a ``PENDING`` request that
    still holds its slot as ``held``. A term without dates cannot place a dated booking: noted, not guessed."""
    rows = list(
        (
            await session.execute(
                select(Booking).where(Booking.term_id == term.id, Booking.status.in_(("BOOKED", "PENDING")))
            )
        ).scalars()
    )
    if rows and week_index_for_date(term, rows[0].date, weeks_rows) is None:
        occ.notes.append(
            {
                "code": "bookings_unmapped",
                "count": len(rows),
                "text": _t(
                    f"Dönemin tarihleri yok: {len(rows)} rezervasyon haftalara yerleştirilemedi",
                    f"The term has no dates: {len(rows)} booking(s) could not be placed in its weeks",
                ),
            }
        )
        return 0
    scope = set(weeks_in_scope)
    clock_now = now or datetime.now()
    n = 0
    for b in rows:
        w = week_index_for_date(term, b.date, weeks_rows)
        if w is None or w not in scope:
            continue
        if b.status == "PENDING" and (b.held_until is None or b.held_until <= clock_now):
            continue
        occ.dates.setdefault((w, b.date.isoweekday()), b.date)
        occ.add(
            b.room_id,
            w,
            b.date.isoweekday(),
            b.start_period,
            b.end_period,
            "booking" if b.status == "BOOKED" else "held",
        )
        n += 1
    return n


async def published_runs(session: AsyncSession, term_id: int) -> list[ScheduleRun]:
    """The term's published runs (one per kind at most, ``uq_schedule_runs_active``), course first."""
    rows = list(
        (
            await session.execute(
                select(ScheduleRun).where(ScheduleRun.term_id == term_id, ScheduleRun.is_active.is_(True))
            )
        ).scalars()
    )
    return sorted(rows, key=lambda r: (r.kind != "COURSE", r.id))


def _weeks_present(rows: Iterable[Assignment]) -> list[int]:
    out: set[int] = set()
    for a in rows:
        out |= assignment_weeks(a)
    return sorted(out)


@dataclass
class Scope:
    term: Term
    runs: list[ScheduleRun]
    source: str  # run | board
    weeks: list[int]
    exam: bool
    axis: str
    occ: Occupancy
    rooms: dict[int, Room]
    counted: dict[str, int]


async def build_scope(
    session: AsyncSession,
    *,
    term_id: int | None = None,
    run_id: int | None = None,
    week: int | None = None,
    scope: str = "week",
    axis: str | None = None,
    bookings: bool = True,
    blocks: bool = True,
    now: datetime | None = None,
    weeks: list[int] | None = None,
) -> Scope:
    """Occupancy of a run (``run_id``) or of the live board of ``term_id`` (published runs + blocks + bookings).

    ``scope``: ``week`` (one week: ``week`` or, by default, the week the run occupies most) or ``term`` (every week
    of the run's horizon / the term). Exam runs and boards whose only published run is an exam run default to
    ``scope=term`` and ``axis=date`` (an exam period spans its dates). ``weeks`` fixes the weeks outright (the
    scenario comparison counts both runs over the same weeks)."""
    if scope not in ("week", "term"):
        raise UtilisationError(422, "scope must be week or term")
    if axis is not None and axis not in ("day", "date"):
        raise UtilisationError(422, "axis must be day or date")
    runs: list[ScheduleRun]
    if run_id is not None:
        run = await session.get(ScheduleRun, run_id)
        if run is None:
            raise UtilisationError(404, f"run {run_id} not found")
        if run.status not in USABLE:
            raise UtilisationError(409, f"run {run.id} is {run.status}; a heatmap needs a finished run")
        term = await session.get(Term, run.term_id)
        runs, source = [run], "run"
    else:
        if term_id is None:
            raise UtilisationError(422, "give run_id or term_id")
        term = await session.get(Term, term_id)
        if term is None:
            raise UtilisationError(404, f"term {term_id} not found")
        runs, source = await published_runs(session, term.id), "board"
    assert term is not None
    exam = bool(runs) and all(r.kind == "EXAM" for r in runs)
    weeks_rows = await _weeks_rows(session, term)
    rows_by_run = {r.id: await _rows(session, r) for r in runs}
    horizon: list[int] = []
    for r in runs:
        horizon += horizon_weeks(r, term)
        horizon += _weeks_present(rows_by_run[r.id])
    if not runs:
        horizon = list(range(1, (term.week_count or 14) + 1))
    horizon = sorted(set(horizon))
    if exam and week is None:
        scope = "term"
    if weeks:
        weeks = sorted({int(w) for w in weeks})
    elif week is not None:
        weeks = [int(week)]
    elif scope == "term":
        weeks = horizon
    else:
        # the week the placements cover most (ties: the earliest), else the first of the horizon
        count: dict[int, int] = defaultdict(int)
        for rows in rows_by_run.values():
            for a in rows:
                for w in assignment_weeks(a) or set(horizon):
                    count[w] += 1
        weeks = [min(count, key=lambda w: (-count[w], w))] if count else horizon[:1]
    occ = Occupancy()
    for r in runs:
        _add_run(occ, r, rows_by_run[r.id], weeks, term, weeks_rows)
    counted = {"assignments": sum(len(v) for v in rows_by_run.values()), "blocks": 0, "bookings": 0}
    if blocks:
        counted["blocks"] = await _add_blocks(session, occ, term, weeks, weeks_rows)
    if bookings and source == "board":
        counted["bookings"] = await _add_bookings(session, occ, term, weeks, weeks_rows, now)
    for w in weeks:
        for d in range(1, 8):
            if (w, d) not in occ.dates:
                occ.dates[(w, d)] = date_for(term, w, d, weeks_rows)
    rooms = {r.id: r for r in (await session.execute(select(Room).options(selectinload(Room.building)))).scalars()}
    return Scope(
        term=term,
        runs=runs,
        source=source,
        weeks=weeks,
        exam=exam,
        axis=axis or ("date" if exam else "day"),
        occ=occ,
        rooms=rooms,
        counted=counted,
    )


# ------------------------------------------------------------------------------------------- room heatmap


def _rooms_in_scope(sc: Scope) -> list[Room]:
    """Bookable rooms plus every room something occupies (a used non-bookable room is still shown)."""
    used = {k[0] for k in sc.occ.cells}
    return sorted(
        (r for r in sc.rooms.values() if r.is_bookable or r.id in used),
        key=lambda r: (r.pos or 0, r.code),
    )


def _days_shown(sc: Scope) -> list[int]:
    used = {k[2] for k in sc.occ.cells}
    return sorted(set(WORKDAYS) | used)


def _columns(sc: Scope) -> list[dict[str, Any]]:
    days = _days_shown(sc)
    if sc.axis == "day":
        return [{"key": f"d{d}", "day": d, "weeks": sc.weeks, "label": _t(DAY_TR[d], DAY_EN[d])} for d in days]
    used = {(k[1], k[2]) for k in sc.occ.cells}
    cols: list[dict[str, Any]] = []
    for w in sc.weeks:
        for d in days:
            if sc.exam and (w, d) not in used:
                continue  # an exam period shows its exam dates only
            dt = sc.occ.dates.get((w, d))
            iso = dt.isoformat() if dt else None
            cols.append(
                {
                    "key": f"w{w}d{d}",
                    "week": w,
                    "day": d,
                    "date": iso,
                    "label": _t(
                        f"{DAY_TR_SHORT[d]} {dt:%d.%m.%Y}" if dt else f"{w}. hafta {DAY_TR_SHORT[d]}",
                        f"{DAY_EN_SHORT[d]} {dt:%Y-%m-%d}" if dt else f"Week {w} {DAY_EN_SHORT[d]}",
                    ),
                }
            )
    return cols


def _col_weeks(col: Mapping[str, Any]) -> list[int]:
    return [int(col["week"])] if "week" in col else [int(w) for w in col["weeks"]]


def _pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d > 0 else 0.0


def _cell(occupied: int, held: int, blocked: int, capacity: int) -> dict[str, Any]:
    return {
        "occupied": occupied,
        "held": held,
        "blocked": blocked,
        "capacity": capacity,
        "pct": _pct(occupied, capacity - blocked),
        "pct_with_blocks": _pct(occupied + blocked, capacity),
    }


def _count(sc: Scope, room_ids: list[int], weeks: list[int], days: list[int], periods: Iterable[int]) -> dict[str, Any]:
    occupied = held = blocked = 0
    ps = list(periods)
    for rid in room_ids:
        for w in weeks:
            for d in days:
                for p in ps:
                    src = sc.occ.cells.get((rid, w, d, p))
                    if not src:
                        continue
                    if "run" in src or "booking" in src:
                        occupied += 1
                    elif "held" in src:
                        held += 1
                    elif "block" in src:
                        blocked += 1
    cap = len(room_ids) * len(weeks) * len(days) * len(ps)
    return _cell(occupied, held, blocked, cap)


def _matrix(sc: Scope, room_ids: list[int], cols: list[dict[str, Any]]) -> dict[str, Any]:
    periods = range(1, PERIODS_PER_DAY + 1)
    cells = [
        {"col": c["key"], "period": p, **_count(sc, room_ids, _col_weeks(c), [int(c["day"])], (p,))}
        for c in cols
        for p in periods
    ]
    by_col = [{"col": c["key"], **_count(sc, room_ids, _col_weeks(c), [int(c["day"])], periods)} for c in cols]
    all_weeks = sorted({w for c in cols for w in _col_weeks(c)})
    all_days = sorted({int(c["day"]) for c in cols})
    by_period = [{"period": p, **_count(sc, room_ids, all_weeks, all_days, (p,))} for p in periods]
    if sc.axis == "date":  # the totals of a date axis are over the shown dates only
        occupied = sum(x["occupied"] for x in by_col)
        held = sum(x["held"] for x in by_col)
        blocked = sum(x["blocked"] for x in by_col)
        cap = sum(x["capacity"] for x in by_col)
        total = _cell(occupied, held, blocked, cap)
    else:
        total = _count(sc, room_ids, all_weeks, all_days, periods)
    return {"cells": cells, "by_col": by_col, "by_period": by_period, "total": total}


def _sources(sc: Scope) -> list[dict[str, Any]]:
    return [
        {"run_id": r.id, "kind": r.kind, "status": r.status, "label": r.label, "is_active": bool(r.is_active)}
        for r in sc.runs
    ]


DEFINITIONS = {
    "room_period": _t(
        "Bir oda-periyot: bir odanın bir haftadaki (sınavda bir tarihteki) bir günün bir periyodu",
        "A room-period is one room in one period of one day of one week (one date for exams)",
    ),
    "pct": _t(
        "Doluluk % = dolu / (kapasite − önceden dolu); taralı (önceden dolu) hücreler yüzdeye girmez",
        "Utilisation % = occupied / (capacity − blocked); hatched (pre-occupied) cells are left out",
    ),
    "held": _t(
        "Bekleyen rezervasyon talebi slotu tutuyorsa ayrıca sayılır (dolu sayılmaz)",
        "A pending booking request that still holds its slot is counted separately (not as occupied)",
    ),
}


async def room_heatmap(
    session: AsyncSession,
    *,
    term_id: int | None = None,
    run_id: int | None = None,
    group_by: str = "building",
    week: int | None = None,
    scope: str = "week",
    axis: str | None = None,
    bookings: bool = True,
    blocks: bool = True,
    rooms_detail: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    if group_by not in GROUP_BY:
        raise UtilisationError(422, f"group_by must be one of {', '.join(GROUP_BY)}")
    sc = await build_scope(
        session,
        term_id=term_id,
        run_id=run_id,
        week=week,
        scope=scope,
        axis=axis,
        bookings=bookings,
        blocks=blocks,
        now=now,
    )
    cols = _columns(sc)
    rooms = _rooms_in_scope(sc)
    groups: dict[str, list[Room]] = defaultdict(list)
    for r in rooms:
        groups[group_key(r, group_by, sc.exam)].append(r)
    if group_by == "capacity_band":
        order = sorted(groups, key=_band_order)
    elif group_by == "room_type":
        codes = [c for c, _a, _b in ROOM_TYPES]
        order = sorted(groups, key=lambda k: codes.index(k) if k in codes else len(codes))
    elif group_by == "room":
        order = [r.code for r in rooms]
    else:
        order = sorted(groups)
    out_rows: list[dict[str, Any]] = []
    for key in order:
        members = groups[key]
        row: dict[str, Any] = {
            "key": key,
            "label": group_label(key, group_by, sc.rooms),
            "rooms": len(members),
            "room_ids": [r.id for r in members],
            **_matrix(sc, [r.id for r in members], cols),
        }
        if rooms_detail and group_by != "room":
            row["room_rows"] = [
                {
                    "room_id": r.id,
                    "code": r.code,
                    "label": _t(r.display_name, r.display_name),
                    "capacity": r.capacity,
                    "exam_capacity": r.exam_capacity,
                    **_matrix(sc, [r.id], cols),
                }
                for r in members
            ]
        if group_by == "room":
            r0 = members[0]
            row.update(capacity=r0.capacity, exam_capacity=r0.exam_capacity, building=building_of(r0))
        out_rows.append(row)
    overall = _matrix(sc, [r.id for r in rooms], cols)
    return {
        "term_id": sc.term.id,
        "term_code": sc.term.code,
        "source": sc.source,
        "runs": _sources(sc),
        "kind": "EXAM" if sc.exam else "COURSE",
        "group_by": group_by,
        "axis": sc.axis,
        "scope": "week" if len(sc.weeks) == 1 and scope == "week" else "term",
        "weeks": sc.weeks,
        "periods": [{"period": p, "start": clock(p), "end": clock(p, True)} for p in range(1, PERIODS_PER_DAY + 1)],
        "columns": cols,
        "rows": out_rows,
        "overall": {"rooms": len(rooms), **overall},
        "counted": sc.counted,
        "notes": sc.occ.notes,
        "definitions": DEFINITIONS,
        "empty": not sc.occ.cells,
        "empty_text": _t("Bu kapsamda atama yok", "No placements in this scope") if not sc.occ.cells else None,
    }


def room_heatmap_csv(data: Mapping[str, Any]) -> str:
    """One line per (group, column, period) cell; ``;``-free plain CSV with a header (Excel opens it)."""
    buf = io.StringIO()
    w = safe_writer(csv.writer(buf))  # formula injection (W3-SEC)
    w.writerow(
        [
            "group_by",
            "group",
            "group_label_tr",
            "group_label_en",
            "rooms",
            "column",
            "week",
            "day",
            "date",
            "period",
            "start",
            "end",
            "occupied",
            "held",
            "blocked",
            "capacity",
            "pct",
            "pct_with_blocks",
        ]
    )
    cols = {c["key"]: c for c in data["columns"]}
    times = {p["period"]: p for p in data["periods"]}
    for row in data["rows"]:
        for c in row["cells"]:
            col = cols[c["col"]]
            t = times[c["period"]]
            w.writerow(
                [
                    data["group_by"],
                    row["key"],
                    row["label"]["tr"],
                    row["label"]["en"],
                    row["rooms"],
                    c["col"],
                    col.get("week", ""),
                    col["day"],
                    col.get("date") or "",
                    c["period"],
                    t["start"],
                    t["end"],
                    c["occupied"],
                    c["held"],
                    c["blocked"],
                    c["capacity"],
                    c["pct"],
                    c["pct_with_blocks"],
                ]
            )
    return buf.getvalue()


# ------------------------------------------------------------------------------------------- per-room usage


def room_usage(sc: Scope) -> dict[int, dict[str, Any]]:
    """Per room over the whole scope: occupied / blocked / capacity room-periods and the percentage (the scenario
    comparison's room deltas use this)."""
    days = _days_shown(sc)
    out: dict[int, dict[str, Any]] = {}
    for r in _rooms_in_scope(sc):
        out[r.id] = {
            "room_id": r.id,
            "code": r.code,
            "building": building_of(r),
            **_count(sc, [r.id], sc.weeks, days, range(1, PERIODS_PER_DAY + 1)),
        }
    return out


# ------------------------------------------------------------------------------------------- instructor load


@dataclass
class TeachSpan:
    instructor_id: int
    week: int
    day: int
    start: int
    end: int
    request_id: int


async def teaching_spans(session: AsyncSession, run: ScheduleRun, weeks: list[int]) -> list[TeachSpan]:
    """Every (instructor, week, day, period span) a course run gives a teacher, inside ``weeks``."""
    rows = [a for a in await _rows(session, run) if a.meeting_request_id is not None]
    if not rows:
        return []
    mr_ids = sorted({int(a.meeting_request_id) for a in rows if a.meeting_request_id is not None})
    teach: dict[int, list[int]] = defaultdict(list)
    q = (
        select(MeetingRequest.id, SectionInstructor.instructor_id)
        .join(Section, Section.id == MeetingRequest.section_id)
        .join(SectionInstructor, SectionInstructor.section_id == Section.id)
        .where(MeetingRequest.id.in_(mr_ids))
    )
    for mr_id, ins_id in (await session.execute(q)).all():
        if ins_id is not None and ins_id not in teach[int(mr_id)]:
            teach[int(mr_id)].append(int(ins_id))
    scope = set(weeks)
    out: list[TeachSpan] = []
    for a in rows:
        assert a.meeting_request_id is not None
        ws = assignment_weeks(a)
        for w in sorted(scope if not ws else ws & scope):
            for ins in teach.get(int(a.meeting_request_id), []):
                out.append(TeachSpan(ins, w, a.day, a.start_period, a.end_period, int(a.meeting_request_id)))
    return out


def day_profile(periods: set[int]) -> dict[str, int]:
    """Periods taught, idle gaps between the first and the last class, and the longest run of consecutive periods."""
    if not periods:
        return {"periods": 0, "gaps": 0, "longest_block": 0, "first": 0, "last": 0}
    first, last = min(periods), max(periods)
    longest = cur = 0
    for p in range(first, last + 1):
        cur = cur + 1 if p in periods else 0
        longest = max(longest, cur)
    return {
        "periods": len(periods),
        "gaps": (last - first + 1) - len(periods),
        "longest_block": longest,
        "first": first,
        "last": last,
    }


def instructor_profiles(spans: Iterable[TeachSpan], weeks: list[int]) -> dict[int, dict[str, Any]]:
    """Per instructor, averaged over ``weeks``: periods per week, gap periods per week, teaching days per week, the
    busiest day and the per-day profile of the first week in scope that has classes."""
    taught: dict[int, dict[tuple[int, int], set[int]]] = defaultdict(lambda: defaultdict(set))
    for s in spans:
        for p in range(s.start, s.end + 1):
            taught[s.instructor_id][(s.week, s.day)].add(p)
    n_weeks = max(1, len(weeks))
    out: dict[int, dict[str, Any]] = {}
    for ins, by_slot in taught.items():
        profiles = {k: day_profile(v) for k, v in by_slot.items()}
        periods = sum(p["periods"] for p in profiles.values())
        gaps = sum(p["gaps"] for p in profiles.values())
        per_day: dict[int, int] = defaultdict(int)
        for (_w, d), prof in profiles.items():
            per_day[d] += prof["periods"]
        out[ins] = {
            "instructor_id": ins,
            "periods_per_week": round(periods / n_weeks, 2),
            "gaps_per_week": round(gaps / n_weeks, 2),
            "days_per_week": round(len(profiles) / n_weeks, 2),
            "max_periods_day": max(p["periods"] for p in profiles.values()),
            "max_gaps_day": max(p["gaps"] for p in profiles.values()),
            "longest_block": max(p["longest_block"] for p in profiles.values()),
            "by_day": {str(d): round(v / n_weeks, 2) for d, v in sorted(per_day.items())},
        }
    return out


async def instructor_heatmap(
    session: AsyncSession,
    *,
    term_id: int | None = None,
    run_id: int | None = None,
    week: int | None = None,
    scope: str = "week",
    limit: int = 500,
    q: str | None = None,
) -> dict[str, Any]:
    """Instructor load of a course run (or of the term's published course run): a day x period matrix of how many
    instructors teach, and one row per instructor (periods / gaps per week, busiest day, longest block and their own
    day x period cells). Exam runs: :func:`app.services.invigilation.load_heatmap` covers exams and duties."""
    sc = await build_scope(
        session, term_id=term_id, run_id=run_id, week=week, scope=scope, blocks=False, bookings=False
    )
    course = [r for r in sc.runs if r.kind == "COURSE"]
    if not course:
        raise UtilisationError(
            409,
            _t(
                "Eğitmen yükü bir ders çalıştırması ister (bu dönemin yayımlanmış ders çalıştırması yok)",
                "An instructor load heatmap needs a course run (the term has no published course run)",
            ),
        )
    run = course[0]
    spans = await teaching_spans(session, run, sc.weeks)
    profiles = instructor_profiles(spans, sc.weeks)
    names = {
        i.id: i
        for i in (await session.execute(select(Instructor).where(Instructor.id.in_(list(profiles) or [0])))).scalars()
    }
    days = sorted(set(WORKDAYS) | {s.day for s in spans})
    teaching: dict[tuple[int, int], set[int]] = defaultdict(set)  # (day, period) -> instructors (any week)
    per_ins_cells: dict[int, dict[tuple[int, int], int]] = defaultdict(lambda: defaultdict(int))
    seen: set[tuple[int, int, int, int]] = set()
    for s in spans:
        for p in range(s.start, s.end + 1):
            if (s.instructor_id, s.week, s.day, p) in seen:
                continue
            seen.add((s.instructor_id, s.week, s.day, p))
            teaching[(s.day, p)].add(s.instructor_id)
            per_ins_cells[s.instructor_id][(s.day, p)] += 1
    n_weeks = max(1, len(sc.weeks))
    total_people = max(1, len(profiles))
    matrix = [
        {
            "day": d,
            "period": p,
            "instructors": len(teaching.get((d, p), set())),
            "pct": _pct(len(teaching.get((d, p), set())), total_people),
        }
        for d in days
        for p in range(1, PERIODS_PER_DAY + 1)
    ]
    fold = (q or "").casefold().strip()
    rows = []
    for ins_id, prof in sorted(profiles.items(), key=lambda kv: (-kv[1]["periods_per_week"], kv[0])):
        ins = names.get(ins_id)
        name = ins.full_name if ins is not None else f"#{ins_id}"
        if fold and fold not in name.casefold():
            continue
        rows.append(
            {
                **prof,
                "name": name,
                "title": ins.title if ins is not None else None,
                "cells": [
                    {"day": d, "period": p, "weeks": c, "share": round(c / n_weeks, 2)}
                    for (d, p), c in sorted(per_ins_cells[ins_id].items())
                ],
            }
        )
    loads = [p["periods_per_week"] for p in profiles.values()]
    return {
        "term_id": sc.term.id,
        "term_code": sc.term.code,
        "source": sc.source,
        "run_id": run.id,
        "weeks": sc.weeks,
        "days": [{"day": d, "label": _t(DAY_TR[d], DAY_EN[d])} for d in days],
        "periods": [{"period": p, "start": clock(p), "end": clock(p, True)} for p in range(1, PERIODS_PER_DAY + 1)],
        "matrix": matrix,
        "instructors_total": len(profiles),
        "summary": {
            "periods_per_week_mean": round(sum(loads) / len(loads), 2) if loads else 0,
            "periods_per_week_max": max(loads) if loads else 0,
            "gaps_per_week_total": round(sum(p["gaps_per_week"] for p in profiles.values()), 2),
            "with_gaps": sum(1 for p in profiles.values() if p["gaps_per_week"] > 0),
        },
        "rows": rows[: max(1, int(limit))],
        "truncated": len(rows) > limit,
        "definitions": {
            "gap": _t(
                "Boşluk: aynı gün ilk ve son ders arasındaki boş periyotlar",
                "Gap: idle periods between the first and the last class of a day",
            ),
            "per_week": _t("Kapsamdaki haftaların ortalaması", "Mean over the weeks in scope"),
        },
    }


def instructor_heatmap_csv(data: Mapping[str, Any]) -> str:
    buf = io.StringIO()
    w = safe_writer(csv.writer(buf))  # formula injection (W3-SEC)
    w.writerow(
        [
            "instructor_id",
            "name",
            "periods_per_week",
            "gaps_per_week",
            "days_per_week",
            "max_periods_day",
            "max_gaps_day",
            "longest_block",
            "day",
            "period",
            "weeks_teaching",
        ]
    )
    for r in data["rows"]:
        base = [
            r["instructor_id"],
            r["name"],
            r["periods_per_week"],
            r["gaps_per_week"],
            r["days_per_week"],
            r["max_periods_day"],
            r["max_gaps_day"],
            r["longest_block"],
        ]
        if not r["cells"]:
            w.writerow([*base, "", "", ""])
        for c in r["cells"]:
            w.writerow([*base, c["day"], c["period"], c["weeks"]])
    return buf.getvalue()
