"""Dashboard aggregates for one term: request counts, last runs and room utilisation.

Utilisation is measured on one week of one run: the term's *active* run (preferring COURSE) or, when
none is published, the newest FEASIBLE/OPTIMAL run (else the newest FEASIBLE_PARTIAL one). A (room,
day, period) cell counts as occupied when a non-archived assignment of that run or a term block covers
it in that week. Only bookable rooms are counted. Building rows use the room's building code (``A``,
``B`` ...), falling back to the first character of the canonical room code.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Assignment, Block, ExamRequest, MeetingRequest, Room, ScheduleRun, Section, Term, Week
from app.services.calendar import week_index_for_date
from app.services.grid import assignment_weeks, enrich_assignments
from app.services.solver_bridge import horizon_weeks

PERIODS_PER_DAY = 18
WORKDAYS = (1, 2, 3, 4, 5)
ALL_DAYS = (1, 2, 3, 4, 5, 6, 7)
GOOD = ("FEASIBLE", "OPTIMAL")  # complete timetables
USABLE = (*GOOD, "FEASIBLE_PARTIAL")  # a best-effort partial timetable is still a timetable


async def pick_term(session: AsyncSession, term_id: int | None) -> Term | None:
    if term_id:
        return await session.get(Term, term_id)
    active = (
        (await session.execute(select(Term).where(Term.is_active.is_(True)).order_by(Term.id.desc()))).scalars().first()
    )
    if active is not None:
        return active
    return (await session.execute(select(Term).order_by(Term.id.desc()))).scalars().first()


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

    occupied: set[tuple[int, int, int]] = set()  # (room, day, period)
    bookable_ids = {r.id for r in bookable}
    conflicts = 0
    if run is not None:
        rows = [a for a in run_rows if _covers(assignment_weeks(a), util_week)]
        for a in rows:
            for rid in a.room_ids or []:
                if int(rid) in bookable_ids:
                    for p in range(a.start_period, a.end_period + 1):
                        occupied.add((int(rid), a.day, p))
        if rows:
            enrich = await enrich_assignments(session, run, rows)
            conflicts = sum(1 for e in enrich.values() if e.is_conflict)
    blocks_week = 0
    for b in (
        await session.execute(select(Block).where(Block.term_id == term.id, Block.archived.is_(False)))
    ).scalars():
        if b.date is not None:
            if week_index_for_date(term, b.date, weeks_rows) != util_week:
                continue
            day = b.date.isoweekday()
        else:
            if not _covers({int(w) for w in (b.weeks or [])}, util_week) or b.day is None:
                continue
            day = b.day
        blocks_week += 1
        if b.room_id in bookable_ids:
            for p in range(b.start_period, b.end_period + 1):
                occupied.add((b.room_id, day, p))

    by_building: dict[str, list[Room]] = defaultdict(list)
    for r in bookable:
        by_building[building_of(r)].append(r)
    buildings = sorted(by_building)
    occ_bdp: dict[tuple[str, int, int], int] = defaultdict(int)
    room_building = {r.id: building_of(r) for r in bookable}
    for rid, day, p in occupied:
        occ_bdp[(room_building[rid], day, p)] += 1

    def occ(b: str, days: tuple[int, ...], periods: range) -> int:
        return sum(occ_bdp.get((b, d, p), 0) for d in days for p in periods)

    all_p = range(1, PERIODS_PER_DAY + 1)
    util_by_building = [
        {
            "building": b,
            "utilisation": _ratio(occ(b, WORKDAYS, all_p), len(by_building[b]) * len(WORKDAYS) * PERIODS_PER_DAY),
            "rooms": len(by_building[b]),
        }
        for b in buildings
    ]
    building_day = [
        {
            "building": b,
            "day": d,
            "utilisation": _ratio(occ(b, (d,), all_p), len(by_building[b]) * PERIODS_PER_DAY),
        }
        for b in buildings
        for d in ALL_DAYS
    ]
    building_period = [
        {
            "building": b,
            "period": p,
            "utilisation": _ratio(occ(b, WORKDAYS, range(p, p + 1)), len(by_building[b]) * len(WORKDAYS)),
        }
        for b in buildings
        for p in all_p
    ]
    n_book = len(bookable)
    peak = [
        {"day": d, "period": p, "occupancy": _ratio(sum(occ_bdp.get((b, d, p), 0) for b in buildings), n_book)}
        for d in ALL_DAYS
        for p in all_p
    ]
    total_occ = sum(1 for _, d, _p in occupied if d in WORKDAYS)
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
        "utilisation": _ratio(total_occ, n_book * len(WORKDAYS) * PERIODS_PER_DAY),
        "utilisation_by_building": util_by_building,
        "utilisation_building_day": building_day,
        "utilisation_building_period": building_period,
        "peak_hours": peak,
        "blocks_week": blocks_week,
        "conflicts": conflicts,
        "last_runs": last_runs,
    }
