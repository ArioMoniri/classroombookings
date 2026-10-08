"""Build a ``SolverInput`` from the DB for a schedule run, solve, and persist the ``SolverResult``.

The real CP-SAT solver (``app.solver.cpsat``) is imported lazily; when it is absent the greedy
``app.solver.stub`` is used so the API and UI work end-to-end before the solver lands.
"""

from __future__ import annotations

import importlib
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Assignment,
    Block,
    ConstraintRow,
    ExamRequest,
    MeetingRequest,
    Room,
    ScheduleRun,
    Section,
    Term,
    Week,
)
from app.services.calendar import date_for, week_index_for_date
from app.solver import model as sm

log = logging.getLogger(__name__)
ProgressFn = Callable[[str, int], None]


SOLVER_MODULES = {"cpsat": "app.solver.cpsat", "stub": "app.solver.stub"}


def _solver_fn(choice: str = "auto") -> Callable[..., sm.SolverResult]:
    """``auto`` prefers CP-SAT and falls back to the greedy stub; ``cpsat``/``stub`` force one."""
    names = [SOLVER_MODULES[choice]] if choice in SOLVER_MODULES else list(SOLVER_MODULES.values())
    for name in names:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name and name.startswith(exc.name):
                continue
            raise
        fn = getattr(mod, "solve", None)
        if fn is not None:
            return fn  # type: ignore[no-any-return]
    raise RuntimeError(f"no solver module available for {choice!r}")


def solver_name(choice: str = "auto") -> str:
    try:
        return _solver_fn(choice).__module__
    except RuntimeError:
        return "none"


def _call_solver(inp: sm.SolverInput, progress: ProgressFn | None, choice: str = "auto") -> sm.SolverResult:
    fn = _solver_fn(choice)
    try:
        return fn(inp, progress=progress)
    except TypeError:
        return fn(inp)


def _cohort_keys(program: str | None, years: list[Any]) -> frozenset[str]:
    """Student-cohort keys ("PROG:<programme>:Y<year>"). Unknown programme or year => no key, because a
    row with no class year (electives, graduate pools) must not be treated as one giant cohort."""
    if not program:
        return frozenset()
    return frozenset(f"PROG:{program}:Y{int(y)}" for y in years if y is not None and int(y) > 0)


def horizon_weeks(run: ScheduleRun, term: Term) -> list[int]:
    hp = run.horizon_params or {}
    if run.horizon == "WEEK":
        w = hp.get("week") or (hp.get("weeks") or [1])[0]
        return [int(w)]
    if run.horizon == "MONTH":
        if hp.get("weeks"):
            return [int(w) for w in hp["weeks"]]
        start = int(hp.get("start_week", 1))
        return list(range(start, min(start + 4, (term.week_count or 14) + 1)))
    if hp.get("weeks"):
        return [int(w) for w in hp["weeks"]]
    return list(range(1, (term.week_count or 14) + 1))


async def build_solver_input(session: AsyncSession, run: ScheduleRun) -> tuple[sm.SolverInput, dict[int, list[int]]]:
    """Return (SolverInput, event_id -> request ids) for ``run``; exam cohorts are merged by merge_key."""
    term = await session.get(Term, run.term_id)
    assert term is not None
    weeks_rows = (await session.execute(select(Week).where(Week.term_id == term.id))).scalars().all()
    weeks = horizon_weeks(run, term)
    week_set = set(weeks)
    params = run.params or {}
    exam = run.kind == "EXAM"

    rooms_db = (
        (await session.execute(select(Room).where(Room.is_bookable.is_(True)).order_by(Room.code))).scalars().all()
    )
    rooms = tuple(
        sm.Room(
            id=r.id,
            code=r.code,
            capacity=r.capacity or 0,
            exam_capacity=r.exam_capacity or 0,
            building=r.code[:1],
            tags=frozenset(str(t) for t in (r.tags or [])),
        )
        for r in rooms_db
        if ((r.exam_capacity or r.capacity) if exam else r.capacity)
    )
    room_ids = {r.id for r in rooms}
    dropped = [r.code for r in rooms_db if r.id not in room_ids]
    if dropped:
        run.stats = {
            **(run.stats or {}),
            "rooms_without_capacity": dropped[:50],
            "rooms_without_capacity_count": len(dropped),
        }
    events: list[sm.Event] = []
    members: dict[int, list[int]] = {}
    extra_weeks: set[int] = set()

    if not exam:
        q = (
            select(MeetingRequest)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == term.id, MeetingRequest.archived.is_(False), MeetingRequest.needs_room.is_(True))
            .options(
                selectinload(MeetingRequest.section).selectinload(Section.course),
                selectinload(MeetingRequest.section).selectinload(Section.program),
                selectinload(MeetingRequest.section).selectinload(Section.instructors),
            )
        )
        for mr in (await session.execute(q)).scalars():
            if mr.start_period is None or mr.end_period is None:
                continue
            ev_weeks = frozenset(int(w) for w in (mr.weeks or weeks) if int(w) in week_set)
            if not ev_weeks:
                continue
            sec = mr.section
            days = [int(d) for d in (mr.days or [])] or ([mr.day] if mr.day else [])
            fixed_day = mr.day if mr.day else (days[0] if len(days) == 1 else None)
            tags = {str(t) for t in (mr.requested_tags or [])}
            required_tags = frozenset({"PC"} & tags)
            forbidden_tags: frozenset[str] = frozenset()
            if "TIP" not in tags:
                forbidden_tags = frozenset({"TIP"})
            locked = None
            definitive = [int(x) for x in (mr.definitive_room_ids or []) if int(x) in room_ids]
            if mr.status == "LOCKED" and definitive and fixed_day:
                locked = sm.Assignment(mr.id, fixed_day, mr.start_period, mr.end_period, tuple(definitive), ev_weeks)
                forbidden_tags = frozenset()
            cohort = _cohort_keys(
                sec.program.canonical_name if sec.program else None, sec.class_years or [sec.class_year]
            )
            instr = frozenset(f"INS:{si.instructor_id}" for si in sec.instructors)
            label = f"{sec.course.display_code}{' §' + sec.label if sec.label else ''}"
            events.append(
                sm.Event(
                    id=mr.id,
                    kind="course",
                    label=label,
                    size=int(sec.enrolment or mr.requested_capacity or 0),
                    duration=mr.end_period - mr.start_period + 1,
                    weeks=ev_weeks,
                    fixed_day=fixed_day,
                    fixed_start=mr.start_period,
                    allowed_days=frozenset(days or [1, 2, 3, 4, 5]),
                    required_tags=required_tags,
                    forbidden_tags=forbidden_tags,
                    preferred_room_ids=tuple(int(x) for x in (mr.requested_room_ids or []) if int(x) in room_ids),
                    preferred_building=mr.requested_building,
                    cohort_keys=cohort,
                    instructor_keys=instr,
                    locked=locked,
                )
            )
            members[mr.id] = [mr.id]
    else:
        qe = (
            select(ExamRequest)
            .where(ExamRequest.term_id == term.id, ExamRequest.archived.is_(False), ExamRequest.needs_room.is_(True))
            .options(selectinload(ExamRequest.program))
        )
        groups: dict[str, list[ExamRequest]] = defaultdict(list)
        for ex in (await session.execute(qe)).scalars():
            if ex.date is None or ex.start_period is None or ex.end_period is None:
                continue
            groups[ex.merge_key or f"single:{ex.id}"].append(ex)
        for rows in groups.values():
            head = min(rows, key=lambda r: r.id)
            head_date, head_start, head_end = head.date, head.start_period, head.end_period
            assert head_date is not None and head_start is not None and head_end is not None
            week = week_index_for_date(term, head_date, list(weeks_rows))
            if week is None:
                week = weeks[0]
            if week not in week_set:
                if run.horizon != "TERM" and params.get("strict_horizon", True):
                    continue
                extra_weeks.add(week)  # exam dated outside the term's lecture weeks (e.g. early finals)
            size = sum(int(r.enrolment or 0) for r in rows)
            tags = {str(t) for r in rows for t in (r.requested_tags or [])}
            definitive = [int(x) for r in rows for x in (r.definitive_room_ids or []) if int(x) in room_ids]
            definitive = list(dict.fromkeys(definitive))
            locked = None
            if all(r.status == "LOCKED" for r in rows) and definitive:
                locked = sm.Assignment(
                    head.id,
                    head_date.isoweekday(),
                    head_start,
                    head_end,
                    tuple(definitive),
                    frozenset({week}),
                    head_date,
                )
            cohort = frozenset().union(
                *(
                    _cohort_keys(r.program.canonical_name if r.program else None, r.class_years or [r.class_year])
                    for r in rows
                )
            )
            max_rooms = max(int(r.requested_room_count or 0) for r in rows) or 3
            if locked is not None:
                # the planner's definitive room set is the room count; a single locked room may then be
                # shared with other exams (the solver only shares single-room events)
                max_rooms = len(locked.room_ids)
            events.append(
                sm.Event(
                    id=head.id,
                    kind="exam",
                    label=f"{head.course_code} ({len(rows)} prog)" if len(rows) > 1 else head.course_code,
                    size=size,
                    duration=head_end - head_start + 1,
                    weeks=frozenset({week}),
                    fixed_day=head_date.isoweekday(),
                    fixed_start=head_start,
                    allowed_days=frozenset({head_date.isoweekday()}),
                    fixed_date=head_date,
                    required_tags=frozenset({"PC"} & tags),
                    forbidden_tags=frozenset() if "TIP" in tags or locked else frozenset({"TIP"}),
                    preferred_room_ids=tuple(
                        dict.fromkeys(int(x) for r in rows for x in (r.requested_room_ids or []) if int(x) in room_ids)
                    ),
                    preferred_building=head.requested_building,
                    max_rooms=max(max_rooms, 1),
                    cohort_keys=cohort,
                    instructor_keys=frozenset(f"INS:{r.instructor_text}" for r in rows if r.instructor_text),
                    locked=locked,
                    # exams of different cohorts may sit in one room as long as the seats add up
                    # (the Final plan does this routinely); the solver checks the seat budget
                    share_room=True,
                )
            )
            members[head.id] = [r.id for r in rows]

    blocks: list[sm.Block] = []
    for b in (
        await session.execute(select(Block).where(Block.term_id == term.id, Block.archived.is_(False)))
    ).scalars():
        day = b.day or (b.date.isoweekday() if b.date else None)
        if day is None:
            continue
        bweeks = [int(w) for w in (b.weeks or [])] or [None]  # type: ignore[list-item]
        for w in bweeks:
            if w is not None and w not in week_set:
                continue
            blocks.append(sm.Block(b.room_id, w, day, b.start_period, b.end_period))
    for rid in params.get("block_run_ids", []) or []:
        for a in (
            await session.execute(
                select(Assignment).where(Assignment.run_id == int(rid), Assignment.archived.is_(False))
            )
        ).scalars():
            for w in a.weeks or [a.week]:
                if w is None or int(w) in week_set:
                    for room_id in a.room_ids or []:
                        blocks.append(
                            sm.Block(
                                int(room_id), int(w) if w is not None else None, a.day, a.start_period, a.end_period
                            )
                        )

    cons = (
        (
            await session.execute(
                select(ConstraintRow)
                .where(ConstraintRow.enabled.is_(True))
                .where((ConstraintRow.term_id == term.id) | (ConstraintRow.run_id == run.id))
            )
        )
        .scalars()
        .all()
    )
    constraints = tuple(
        sm.Constraint(c.kind, dict(c.params or {}), c.hardness == "hard", int(c.weight or 1), c.id) for c in cons
    )

    previous: list[sm.Assignment] = []
    if run.parent_run_id:
        head_of = {rid: head for head, ids in members.items() for rid in ids}
        events_by_id = {e.id: i for i, e in enumerate(events)}
        seen_prev: set[int] = set()
        for a in (
            await session.execute(
                select(Assignment).where(Assignment.run_id == run.parent_run_id, Assignment.archived.is_(False))
            )
        ).scalars():
            req_id = a.meeting_request_id if not exam else a.exam_request_id
            if req_id is None:
                continue
            ev_id = head_of.get(req_id, req_id)
            if ev_id in seen_prev:
                continue  # merged exam cohorts: one assignment per member, one event
            seen_prev.add(ev_id)
            a_rooms = tuple(int(r) for r in a.room_ids or [])
            previous.append(
                sm.Assignment(
                    ev_id,
                    a.day,
                    a.start_period,
                    a.end_period,
                    a_rooms,
                    frozenset(int(w) for w in (a.weeks or [])),
                    a.date,
                )
            )
            idx = events_by_id.get(ev_id)
            if a.is_locked and idx is not None and all(r in room_ids for r in a_rooms):
                # a planner-locked (e.g. manually moved) assignment of the parent run is carried over as
                # a hard lock; ``locked`` overrides the request's fixed day/time in the solver
                ev = events[idx]
                events[idx] = replace(
                    ev,
                    duration=a.end_period - a.start_period + 1,
                    locked=sm.Assignment(
                        ev.id, a.day, a.start_period, a.end_period, a_rooms, ev.weeks, a.date or ev.fixed_date
                    ),
                    forbidden_tags=frozenset(),
                    max_rooms=max(len(a_rooms), 1) if ev.kind == "exam" else ev.max_rooms,
                )

    if exam and extra_weeks:
        weeks = sorted(week_set | extra_weeks)
    inp = sm.SolverInput(
        rooms=rooms,
        events=tuple(events),
        constraints=constraints,
        weeks=tuple(weeks),
        blocks=tuple(blocks),
        previous=tuple(previous),
        time_limit_s=float(params.get("time_limit_s", 60.0)),
        seed=int(params.get("seed", 0)),
        workers=int(params.get("workers", 8)),
        weights=dict(params.get("weights", {})),
    )
    return inp, members


async def persist_result(
    session: AsyncSession, run: ScheduleRun, result: sm.SolverResult, members: dict[int, list[int]]
) -> int:
    term = await session.get(Term, run.term_id)
    assert term is not None
    weeks_rows = (await session.execute(select(Week).where(Week.term_id == term.id))).scalars().all()
    await session.execute(delete(Assignment).where(Assignment.run_id == run.id, Assignment.origin == "SOLVER"))
    count = 0
    exam = run.kind == "EXAM"
    for a in result.assignments:
        for req_id in members.get(a.event_id, [a.event_id]):
            weeks = sorted(a.weeks)
            session.add(
                Assignment(
                    run_id=run.id,
                    meeting_request_id=None if exam else req_id,
                    exam_request_id=req_id if exam else None,
                    week=weeks[0] if len(weeks) == 1 else None,
                    weeks=weeks,
                    day=a.day,
                    date=a.date or (date_for(term, weeks[0], a.day, list(weeks_rows)) if len(weeks) == 1 else None),
                    start_period=a.start,
                    end_period=a.end,
                    room_ids=list(a.room_ids),
                    origin="SOLVER",
                )
            )
            count += 1
    run.status = result.status
    run.hard_score = result.hard_score
    run.soft_score = result.soft_score
    run.objective_value = float(sum(result.objective_breakdown.values())) if result.objective_breakdown else None
    run.stats = {
        **(run.stats or {}),
        **result.stats,
        "objective_breakdown": dict(result.objective_breakdown),
        "assignments": count,
        "progress": 100,
    }
    run.diagnosis = [asdict(d) for d in result.diagnoses]
    run.finished_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    return count


async def run_schedule(session_factory: Any, run_id: int, progress: ProgressFn | None = None) -> dict[str, Any]:
    """Job body for the queue: load, build, solve, persist."""

    def report(phase: str, pct: int) -> None:
        if progress:
            progress(phase, pct)

    async with session_factory() as session:
        run = await session.get(ScheduleRun, run_id)
        if run is None:
            raise ValueError(f"run {run_id} not found")
        run.status = "RUNNING"
        run.started_at = datetime.now(UTC).replace(tzinfo=None)
        run.stats = {**(run.stats or {}), "progress": 5, "phase": "loading"}
        await session.commit()
        report("loading", 5)
        inp, members = await build_solver_input(session, run)
        report("building", 15)
        choice = str((run.params or {}).get("solver", "auto"))
        solver_mod = _solver_fn(choice).__module__
        report("solving", 20)
        result = _call_solver(inp, lambda ph, pct: report(ph, 20 + int(pct * 0.7)), choice)
        report("persisting", 92)
        run = await session.get(ScheduleRun, run_id)
        assert run is not None
        result.stats = {
            **result.stats,
            "solver": solver_mod,
            "events": result.stats.get("events", len(inp.events)),
            "rooms": result.stats.get("rooms", len(inp.rooms)),
        }
        n = await persist_result(session, run, result, members)
        report("done", 100)
        return {"status": result.status, "assignments": n, "solver": solver_mod}
