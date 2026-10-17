"""Dashboard aggregates for one term: request counts, last runs and room utilisation.

Utilisation is measured on one week with the room heatmap's definition (``app/services/utilisation``,
``GET /analytics/heatmap/rooms``), so the dashboard and the heatmap print the same number: when the term has a
published run, the live board (its published runs, whatever their origin, an imported board included, plus the
term's blocks and BOOKED bookings); when none is published, the newest FEASIBLE/OPTIMAL run (else the newest
FEASIBLE_PARTIAL one). ``utilisation = occupied / (capacity - blocked)`` over the bookable rooms and every room
something occupies, on the weekdays plus any day in use. The week is the requested one or, by default, the
current week, else the closest week the run covers (an imported board of two sheets covers weeks 1-2). Building
rows use the room's building code (``A``, ``B`` ...), falling back to the first character of the room code.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Assignment, ExamRequest, MeetingRequest, Room, ScheduleRun, Section, Term, Week
from app.services import utilisation as util
from app.services.calendar import week_index_for_date
from app.services.grid import assignment_weeks, enrich_assignments
from app.services.solver_bridge import horizon_weeks

PERIODS_PER_DAY = 18
ALL_DAYS = (1, 2, 3, 4, 5, 6, 7)
GOOD = ("FEASIBLE", "OPTIMAL")  # complete timetables
USABLE = (*GOOD, "FEASIBLE_PARTIAL")  # a best-effort partial timetable is still a timetable


async def pick_term(session: AsyncSession, term_id: int | None) -> Term | None:
    if term_id:
        return await session.get(Term, term_id)
    from app.services.terms import load_current_term

    return await load_current_term(session)  # active, else today's term (not the last imported one)


async def utilisation_run(session: AsyncSession, term_id: int) -> ScheduleRun | None:
    base = select(ScheduleRun).where(ScheduleRun.term_id == term_id)
    for q in (
        base.where(ScheduleRun.is_active.is_(True), ScheduleRun.kind == "COURSE"),
        base.where(ScheduleRun.is_active.is_(True)),
        base.where(ScheduleRun.status.in_(GOOD), ScheduleRun.kind == "COURSE"),
        base.where(ScheduleRun.status.in_(GOOD)),
        base.where(ScheduleRun.status.in_(USABLE), ScheduleRun.kind == "COURSE"),
        base.where(ScheduleRun.status.in_(USABLE)),
    ):
        run = (await session.execute(q.order_by(ScheduleRun.id.desc()))).scalars().first()
        if run is not None:
            return run
    return None


def _covers(weeks: set[int], week: int) -> bool:
    return not weeks or week in weeks


def _ratio(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


async def build_dashboard(
    session: AsyncSession, term: Term, *, week: int | None = None, today: date | None = None
) -> dict[str, Any]:
    weeks_rows = list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())
    wk_count = term.week_count or 14
    cur = week_index_for_date(term, today or date.today(), weeks_rows)
    current_week = min(max(cur or 1, 1), wk_count)

    rooms = list((await session.execute(select(Room).options(selectinload(Room.building)))).scalars())
    bookable = [r for r in rooms if r.is_bookable]

    def building_of(r: Room) -> str:
        return r.building.code if r.building is not None else (r.code[:1] or "?")

    sections_total = (
        await session.execute(
            select(func.count(Section.id)).where(Section.term_id == term.id, Section.archived.is_(False))
        )
    ).scalar_one()
    meetings_by_status: dict[str, int] = {
        str(k): int(v)
        for k, v in (
            await session.execute(
                select(MeetingRequest.status, func.count(MeetingRequest.id))
                .join(Section, Section.id == MeetingRequest.section_id)
                .where(Section.term_id == term.id, MeetingRequest.archived.is_(False))
                .group_by(MeetingRequest.status)
            )
        ).all()
    }
    exams_by_status: dict[str, int] = {
        str(k): int(v)
        for k, v in (
            await session.execute(
                select(ExamRequest.status, func.count(ExamRequest.id))
                .where(ExamRequest.term_id == term.id, ExamRequest.archived.is_(False))
                .group_by(ExamRequest.status)
            )
        ).all()
    }
    meetings_total = sum(meetings_by_status.values())
    exams_total = sum(exams_by_status.values())
    locked = meetings_by_status.get("LOCKED", 0) + exams_by_status.get("LOCKED", 0)
    needs_review = meetings_by_status.get("NEEDS_REVIEW", 0) + exams_by_status.get("NEEDS_REVIEW", 0)

    last_runs = list(
        (
            await session.execute(
                select(ScheduleRun).where(ScheduleRun.term_id == term.id).order_by(ScheduleRun.id.desc()).limit(5)
            )
        ).scalars()
    )
    active = (
        (
            await session.execute(
                select(ScheduleRun)
                .where(ScheduleRun.term_id == term.id, ScheduleRun.is_active.is_(True))
                .order_by(ScheduleRun.id.desc())
            )
        )
        .scalars()
        .first()
    )

    run = await utilisation_run(session, term.id)
    run_rows: list[Assignment] = []
    if run is not None:
        run_rows = list(
            (
                await session.execute(
                    select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False))
                )
            ).scalars()
        )
    util_week = week or current_week
    if week is None and run is not None:
        # the calendar week may lie outside what the run covers (a one-week run, an imported board with
        # two sheets): fall back to the closest week the run actually occupies
        present: set[int] = set()
        for a in run_rows:
            present |= assignment_weeks(a)
        candidates = sorted(present) or horizon_weeks(run, term)
        if candidates and util_week not in candidates:
            util_week = min(candidates, key=lambda w: (abs(w - current_week), w))

    conflicts = 0
    if run is not None:
        rows = [a for a in run_rows if _covers(assignment_weeks(a), util_week)]
        if rows:
            enrich = await enrich_assignments(session, run, rows)
            conflicts = sum(1 for e in enrich.values() if e.is_conflict)

    # Occupancy on the heatmap's definition (app/services/utilisation): the live board when the term has a
    # published run (its published runs, blocks and BOOKED bookings, whatever the run's origin: an imported board
    # counts like a solver run), else the chosen run; pct = occupied / (capacity - blocked).
    n_book = len(bookable)
    building_rows: list[dict[str, Any]] = []
    building_day: list[dict[str, Any]] = []
    building_period: list[dict[str, Any]] = []
    all_p = range(1, PERIODS_PER_DAY + 1)
    board = active is not None or run is None
    sc = await util.build_scope(
        session, term_id=term.id if board else None, run_id=None if board or run is None else run.id, week=util_week
    )
    blocks_week = sc.counted["blocks"]
    in_scope = util._rooms_in_scope(sc)
    days = util._days_shown(sc)
    by_building: dict[str, list[int]] = defaultdict(list)
    for r in in_scope:
        by_building[building_of(r)].append(r.id)

    def share(ids: list[int], ds: list[int] | tuple[int, ...], ps: range) -> float:
        c = util._count(sc, ids, sc.weeks, list(ds), ps)
        return _ratio(int(c["occupied"]), int(c["capacity"]) - int(c["blocked"]))

    overall = share([r.id for r in in_scope], days, all_p)
    for b in sorted(by_building):
        ids = by_building[b]
        building_rows.append({"building": b, "utilisation": share(ids, days, all_p), "rooms": len(ids)})
        building_day += [{"building": b, "day": d, "utilisation": share(ids, (d,), all_p)} for d in ALL_DAYS]
        building_period += [
            {"building": b, "period": p, "utilisation": share(ids, days, range(p, p + 1))} for p in all_p
        ]
    everyone = [r.id for r in in_scope]
    peak = [
        {"day": d, "period": p, "occupancy": share(everyone, (d,), range(p, p + 1))} for d in ALL_DAYS for p in all_p
    ]
    return {
        "term": term,
        "current_week": current_week,
        "utilisation_week": util_week,
        "rooms_total": len(rooms),
        "rooms_bookable": n_book,
        "sections_total": int(sections_total),
        "requests_total": meetings_total + exams_total,
        "meetings_total": meetings_total,
        "exams_total": exams_total,
        "requests_needs_review": needs_review,
        "requests_pending": meetings_total + exams_total - locked,
        "requests_locked": locked,
        "meetings_by_status": meetings_by_status,
        "exams_by_status": exams_by_status,
        "active_run_id": active.id if active is not None else None,
        "utilisation_run_id": run.id if run is not None else None,
        "utilisation": overall,
        "utilisation_by_building": building_rows,
        "utilisation_building_day": building_day,
        "utilisation_building_period": building_period,
        "peak_hours": peak,
        "blocks_week": blocks_week,
        "conflicts": conflicts,
        "last_runs": last_runs,
    }
