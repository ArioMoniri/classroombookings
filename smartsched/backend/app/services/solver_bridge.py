"""Build a ``SolverInput`` from the DB for a schedule run, solve, and persist the ``SolverResult``.

The real CP-SAT solver (``app.solver.cpsat``) is imported lazily; when it is absent the greedy
``app.solver.stub`` is used so the API and UI work end-to-end before the solver lands.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
from collections import Counter, defaultdict
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
    Instructor,
    MeetingRequest,
    Room,
    ScheduleRun,
    Section,
    Term,
    Week,
)
from app.services.calendar import date_for, week_index_for_date
from app.solver import model as sm
from app.workers.queue import worker_id

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


#: run status of a best-effort run that stores a partial timetable (the solver reports INFEASIBLE with
#: ``stats.partial``: the full request set has no solution, the placed events satisfy every hard rule)
PARTIAL_STATUS = "FEASIBLE_PARTIAL"


def run_status(result: sm.SolverResult) -> str:
    """API status of a solver result: ``FEASIBLE_PARTIAL`` for a stored partial timetable."""
    if result.status == "INFEASIBLE" and result.stats.get("partial") and result.assignments:
        return PARTIAL_STATUS
    return result.status


def _unlocked_forbidden_tags(inp: sm.SolverInput) -> dict[int, frozenset[str]]:
    """Locked course events have their ``TIP`` ban cleared (the planner's room wins); a week segment
    moved out of the lock gets it back unless the planner's room itself is a medicine (TIP) room."""
    tip_rooms = {r.id for r in inp.rooms if "TIP" in r.tags}
    return {
        e.id: frozenset() if set(e.locked.room_ids) & tip_rooms else frozenset({"TIP"})
        for e in inp.events
        if e.kind == "course" and e.locked is not None and not e.forbidden_tags
    }


def _call_solver(
    inp: sm.SolverInput, progress: ProgressFn | None, choice: str = "auto", *, split_weeks: bool | None = None
) -> sm.SolverResult:
    """Solve ``inp``.  With CP-SAT and multi-week events, term runs are solved in week segments
    (``app.solver.weeksplit``: a room blocked in some weeks only changes the room in those weeks; the
    planner's lock holds for the others); the result is translated back to the original event ids."""
    fn = _solver_fn(choice)
    if split_weeks is None:
        split_weeks = bool(MODE_DEFAULTS["split_blocked_weeks"])
    if split_weeks and fn.__module__ == SOLVER_MODULES["cpsat"] and any(len(e.weeks) > 1 for e in inp.events):
        from app.solver.weeksplit import solve_segmented, to_original

        res, split = solve_segmented(inp, unlocked_forbidden_tags=_unlocked_forbidden_tags(inp), rounds=1)
        out: sm.SolverResult = to_original(split, res)
        return out
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


#: run params (``ScheduleRun.params``) of the real-data modes and their defaults; see app/solver/README.md
MODE_DEFAULTS: dict[str, Any] = {
    "trust_locked_rooms": True,  # D1: keep a LOCKED definitive room smaller than the expected enrolment
    "fixed_conflicts_as_warnings": True,  # D2: fixed-vs-fixed cohort/instructor clashes are input warnings
    "best_effort": True,  # D3: an infeasible run still stores the maximum placement
    "merge_joint_lectures": True,  # D4
    "definitive_rooms": "lock",  # lock | prefer (soft hint) | ignore — planner's definitive rooms of LOCKED rows
    # term runs: a room blocked in some weeks only moves those weeks (week segments, app/solver/weeksplit.py)
    "split_blocked_weeks": True,
}


def run_mode(params: dict[str, Any] | None, key: str) -> Any:
    value = (params or {}).get(key, MODE_DEFAULTS[key])
    if key == "definitive_rooms":
        return value if value in ("lock", "prefer", "ignore") else "lock"
    return bool(value)


def _bridge_diag(
    event_ids: list[int], message: str, suggestions: list[str], code: str, kinds: list[str] | None = None
) -> dict[str, Any]:
    return asdict(sm.Diagnosis(event_ids, kinds or [], message, suggestions, "warning", code))


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


def _joinable(a: sm.Event, b: sm.Event) -> bool:
    """Two fixed-time course requests are one physical lecture when they share an instructor or the
    planner locked both to the same room set, at the same day/periods, in overlapping weeks."""
    if (a.fixed_day, a.fixed_start, a.duration) != (b.fixed_day, b.fixed_start, b.duration) or a.fixed_day is None:
        return False
    if not a.weeks & b.weeks:
        return False
    ra = set(a.locked.room_ids) if a.locked else set()
    rb = set(b.locked.room_ids) if b.locked else set()
    if ra and rb and ra != rb:
        return False  # the planner put them in different rooms: two sessions (or a data error to report)
    return bool(a.instructor_keys & b.instructor_keys) or (bool(ra) and ra == rb)


def _base_label(label: str) -> str:
    return " ".join(label.split())


def _same_locked_lecture(a: sm.Event, b: sm.Event) -> bool:
    if a.locked is None or b.locked is None or not a.weeks & b.weeks:
        return False
    la, lb = a.locked, b.locked
    if la.day != lb.day or set(la.room_ids) != set(lb.room_ids) or la.start > lb.end or lb.start > la.end:
        return False
    return la.start == lb.start or _base_label(a.label) == _base_label(b.label)


def merge_joint_lectures(
    events: list[sm.Event], members: dict[int, list[int]], room_capacity: dict[int, int] | None = None
) -> tuple[list[sm.Event], list[dict[str, Any]]]:
    """Merge requests that describe one joint lecture (``FIZ 111 §1`` listed once per programme,
    ``HEM 334 / NRS 304`` taught together) into one solver event.

    The planning list has one row per programme; without merging, the planner's own definitive plan
    is infeasible (same instructor / same room twice at the same time).  The merged event seats the
    sum of the groups, carries every cohort and instructor key, and maps back to all its requests
    through ``members`` (one assignment per request is persisted).  When the planner locked the group
    into rooms smaller than the summed enrolment (the list's enrolments are *expected* numbers and
    programmes overlap), the planner's rooms win: the size is clipped to their capacity and the clip
    is reported.  Returns (events, one summary dict per merged group).
    """
    by_slot: dict[tuple[int | None, int | None, int], list[int]] = defaultdict(list)
    for i, e in enumerate(events):
        if e.fixed_day is not None and e.fixed_start is not None:
            by_slot[(e.fixed_day, e.fixed_start, e.duration)].append(i)
    parent = list(range(len(events)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for idxs in by_slot.values():
        for x in range(len(idxs)):
            for y in range(x + 1, len(idxs)):
                if _joinable(events[idxs[x]], events[idxs[y]]):
                    parent[find(idxs[x])] = find(idxs[y])
    # the planner locked two rows into the same room set at overlapping times: one lecture listed twice
    # when both start together (cross-listed MBG 408 / MBG 598 in A 207) or it is the same course and
    # section (CSE 102 §1 once per programme with slightly different times); the room holds the union
    by_rooms: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
    for i, e in enumerate(events):
        if e.locked is not None and e.locked.room_ids and e.fixed_day is not None:
            by_rooms[(e.locked.day, tuple(sorted(e.locked.room_ids)))].append(i)
    for idxs in by_rooms.values():
        for x in range(len(idxs)):
            for y in range(x + 1, len(idxs)):
                if _same_locked_lecture(events[idxs[x]], events[idxs[y]]):
                    parent[find(idxs[x])] = find(idxs[y])
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(events)):
        groups[find(i)].append(i)
    out: list[sm.Event] = []
    merged: list[dict[str, Any]] = []
    caps = room_capacity or {}
    for idxs in groups.values():
        if len(idxs) == 1:
            out.append(events[idxs[0]])
            continue
        evs = sorted((events[i] for i in idxs), key=lambda e: e.id)
        head = evs[0]
        locked_rooms = next((e.locked.room_ids for e in evs if e.locked), None)
        first = min((e.locked.start if e.locked else e.fixed_start or 1) for e in evs)
        last = max((e.locked.end if e.locked else (e.fixed_start or 1) + e.duration - 1) for e in evs)
        span_changed = any(
            (e.locked.start if e.locked else e.fixed_start, e.duration) != (first, last - first + 1) for e in evs
        )
        if span_changed:
            head = replace(head, fixed_start=first, duration=last - first + 1)
        weeks = frozenset().union(*(e.weeks for e in evs))
        labels = list(dict.fromkeys(e.label for e in evs))
        label = " + ".join(labels) if len(labels) <= 3 else f"{labels[0]} + {len(labels) - 1} more"
        size = sum(e.size for e in evs)
        info: dict[str, Any] = {"event_id": head.id, "request_ids": [e.id for e in evs], "label": label, "size": size}
        if span_changed:
            info["span"] = [first, last]
        if locked_rooms:
            cap = sum(caps.get(r, 0) for r in locked_rooms)
            if cap and size > cap:
                info["clipped_to"] = cap
                size = max(cap, max(e.size for e in evs))
        merged.append(info)
        out.append(
            replace(
                head,
                label=label,
                size=size,
                weeks=weeks,
                required_tags=frozenset().union(*(e.required_tags for e in evs)),
                forbidden_tags=frozenset.intersection(*(e.forbidden_tags for e in evs)),
                preferred_room_ids=tuple(dict.fromkeys(r for e in evs for r in e.preferred_room_ids)),
                preferred_building=next((e.preferred_building for e in evs if e.preferred_building), None),
                cohort_keys=frozenset().union(*(e.cohort_keys for e in evs)),
                instructor_keys=frozenset().union(*(e.instructor_keys for e in evs)),
                # a member held in a room outside the pool needs no pooled room, the others do
                needs_room=bool(locked_rooms) or any(e.needs_room for e in evs),
                locked=(
                    sm.Assignment(
                        head.id,
                        head.fixed_day or 1,
                        head.fixed_start or 1,
                        (head.fixed_start or 1) + head.duration - 1,
                        locked_rooms,
                        weeks,
                    )
                    if locked_rooms
                    else None
                ),
            )
        )
        members[head.id] = [m for e in evs for m in members.pop(e.id, [e.id])]
    return out, merged


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
    bridge_diags: list[dict[str, Any]] = []
    if dropped:
        run.stats = {
            **(run.stats or {}),
            "rooms_without_capacity": dropped[:50],
            "rooms_without_capacity_count": len(dropped),
        }
        bridge_diags.append(
            _bridge_diag(
                [],
                f"{len(dropped)} bookable room(s) have no {'exam ' if exam else ''}capacity and are not used: "
                + ", ".join(dropped[:20]),
                ["set their capacity in the room master (python -m app.cli import room-master <csv>)"],
                "room_without_capacity",
                ["capacity"],
            )
        )
    all_rooms: dict[int, str] = {
        int(rid): str(code) for rid, code in (await session.execute(select(Room.id, Room.code))).all()
    }
    definitive_mode = run_mode(params, "definitive_rooms")
    outside_pool: dict[int, list[int]] = {}  # event id -> planner rooms outside the solver's room pool

    def split_definitive(ids: list[Any]) -> tuple[list[int], list[int]]:
        ids_i = list(dict.fromkeys(int(x) for x in ids or []))
        return [x for x in ids_i if x in room_ids], [x for x in ids_i if x not in room_ids]

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
            definitive, outside = split_definitive(mr.definitive_room_ids or [])
            is_locked = mr.status == "LOCKED" and bool(definitive or outside) and bool(fixed_day)
            needs_room = True
            preferred = [int(x) for x in (mr.requested_room_ids or []) if int(x) in room_ids]
            if is_locked and definitive_mode == "lock":
                if definitive:
                    locked = sm.Assignment(
                        mr.id, fixed_day or 1, mr.start_period, mr.end_period, tuple(definitive), ev_weeks
                    )
                    forbidden_tags = frozenset()
                else:
                    # the planner's room is outside the room pool (lab/office without capacity): the
                    # meeting keeps its time and cohort/instructor rules but needs no pooled room
                    needs_room = False
                if outside:
                    outside_pool[mr.id] = outside
            elif is_locked and definitive_mode == "prefer":
                preferred = list(dict.fromkeys([*definitive, *preferred]))
            if (
                is_locked
                and definitive_mode != "lock"
                and any(r.id in definitive and "TIP" in (r.tags or []) for r in rooms_db)
            ):
                forbidden_tags = frozenset()  # the planner seats this group in a medicine (TIP) room
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
                    preferred_room_ids=tuple(preferred),
                    preferred_building=mr.requested_building,
                    cohort_keys=cohort,
                    instructor_keys=instr,
                    locked=locked,
                    needs_room=needs_room,
                )
            )
            members[mr.id] = [mr.id]
        if run_mode(params, "merge_joint_lectures"):
            events, merged = merge_joint_lectures(events, members, {r.id: r.capacity for r in rooms})
            if merged:
                run.stats = {
                    **(run.stats or {}),
                    "merged_joint_lectures": len(merged),
                    "merged_joint_lectures_clipped": [m for m in merged if "clipped_to" in m][:50],
                }
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
            definitive, outside = split_definitive([x for r in rows for x in (r.definitive_room_ids or [])])
            locked = None
            exam_needs_room = True
            is_locked = all(r.status == "LOCKED" for r in rows) and bool(definitive or outside)
            exam_preferred = list(
                dict.fromkeys(int(x) for r in rows for x in (r.requested_room_ids or []) if int(x) in room_ids)
            )
            if is_locked and definitive_mode == "lock":
                if definitive:
                    locked = sm.Assignment(
                        head.id,
                        head_date.isoweekday(),
                        head_start,
                        head_end,
                        tuple(definitive),
                        frozenset({week}),
                        head_date,
                    )
                else:
                    exam_needs_room = False
                if outside:
                    outside_pool[head.id] = outside
            elif is_locked and definitive_mode == "prefer":
                exam_preferred = list(dict.fromkeys([*definitive, *exam_preferred]))
            tip_ok = is_locked and any(r.id in definitive and "TIP" in (r.tags or []) for r in rooms_db)
            cohort = frozenset().union(
                *(
                    _cohort_keys(r.program.canonical_name if r.program else None, r.class_years or [r.class_year])
                    for r in rows
                )
            )
            max_rooms = max(int(r.requested_room_count or 0) for r in rows) or 3
            if is_locked and definitive and definitive_mode != "lock":
                max_rooms = max(max_rooms, len(definitive))
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
                    forbidden_tags=frozenset() if "TIP" in tags or locked or tip_ok else frozenset({"TIP"}),
                    preferred_room_ids=tuple(exam_preferred),
                    needs_room=exam_needs_room,
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
        parent_rows = list(
            (
                await session.execute(
                    select(Assignment).where(Assignment.run_id == run.parent_run_id, Assignment.archived.is_(False))
                )
            ).scalars()
        )
        # a week-segmented parent stores one row per room set: the row covering most weeks stands for the
        # event (a manual move collapses them into one row anyway)
        parent_rows.sort(key=lambda a: (-len(a.weeks or []), a.id))
        for a in parent_rows:
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
        trust_locked_rooms=run_mode(params, "trust_locked_rooms"),
        fixed_conflicts_as_warnings=run_mode(params, "fixed_conflicts_as_warnings"),
        best_effort=run_mode(params, "best_effort"),
    )
    if outside_pool:
        head_of_member = {m: h for h, ms in members.items() for m in ms}
        by_event: dict[int, list[int]] = defaultdict(list)
        for rid, rooms_out in outside_pool.items():
            by_event[head_of_member.get(rid, rid)].extend(rooms_out)
        ev_by_id = {e.id: e for e in inp.events}
        lines = []
        for eid, rids in sorted(by_event.items()):
            held = ev_by_id.get(eid)
            if held is None:
                continue
            codes = ", ".join(all_rooms.get(r, str(r)) for r in dict.fromkeys(rids))
            lines.append((eid, f"{held.label} ({codes})", held.needs_room))
        kept_out = [x for x in lines if not x[2]]
        partly = [x for x in lines if x[2]]
        if kept_out:
            bridge_diags.append(
                _bridge_diag(
                    [x[0] for x in kept_out][:200],
                    f"{len(kept_out)} locked request(s) sit in the planner's room outside the bookable pool "
                    "(no capacity known) and keep it; times, cohorts and instructors still count: "
                    + "; ".join(x[1] for x in kept_out[:10])
                    + (" ..." if len(kept_out) > 10 else ""),
                    ["add these rooms with a capacity to the room master to let the solver check them"],
                    "outside_room_pool",
                )
            )
        if partly:
            bridge_diags.append(
                _bridge_diag(
                    [x[0] for x in partly][:200],
                    f"{len(partly)} locked request(s) also use a room outside the bookable pool; only their pooled "
                    "rooms are checked: " + "; ".join(x[1] for x in partly[:10]) + (" ..." if len(partly) > 10 else ""),
                    ["add these rooms with a capacity to the room master"],
                    "outside_room_pool",
                )
            )
        run.stats = {
            **(run.stats or {}),
            "outside_pool_rooms": {str(k): list(dict.fromkeys(v)) for k, v in by_event.items()},
        }
    run.stats = {**(run.stats or {}), "bridge_diagnoses": bridge_diags}
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
    stats_in = dict(run.stats or {})
    outside = {int(k): [int(r) for r in v] for k, v in (stats_in.get("outside_pool_rooms") or {}).items()}
    for a in result.assignments:
        if a.event_id in outside:  # the planner's room outside the pool (kept, not checked by the solver)
            a = replace(a, room_ids=tuple(dict.fromkeys([*a.room_ids, *outside[a.event_id]])))
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
    run.status = run_status(result)
    run.hard_score = result.hard_score
    run.soft_score = result.soft_score
    run.objective_value = float(sum(result.objective_breakdown.values())) if result.objective_breakdown else None
    bridge_diags = list(stats_in.pop("bridge_diagnoses", None) or [])
    run.stats = {
        **stats_in,
        **result.stats,
        "objective_breakdown": dict(result.objective_breakdown),
        "assignments": count,
        "progress": 100,
    }
    diags = [asdict(d) for d in result.diagnoses] + bridge_diags
    run.stats["warnings_by_code"] = dict(
        sorted(Counter(str(d.get("code") or "other") for d in diags if d.get("severity") != "error").items())
    )
    run.stats["errors_by_code"] = dict(
        sorted(Counter(str(d.get("code") or "other") for d in diags if d.get("severity") == "error").items())
    )
    run.diagnosis = await _humanize(session, diags)
    run.finished_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    return count


_INS_RX = re.compile(r"INS:(\d+)")


async def _humanize(session: AsyncSession, diags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``instructor 'INS:42'`` -> ``instructor 'INS:42' (Dr. Ayşe Kaya)`` in diagnosis texts."""
    ids = {int(m) for d in diags for m in _INS_RX.findall(str(d.get("message", "")))}
    if not ids:
        return diags
    rows = (await session.execute(select(Instructor.id, Instructor.full_name).where(Instructor.id.in_(ids)))).all()
    names: dict[int, str] = {int(i): str(n) for i, n in rows}

    def sub(text: str) -> str:
        return _INS_RX.sub(
            lambda m: f"INS:{m.group(1)} ({names[int(m.group(1))]})" if int(m.group(1)) in names else m.group(0), text
        )

    return [{**d, "message": sub(str(d.get("message", "")))} for d in diags]


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
        run.stats = {**(run.stats or {}), "progress": 5, "phase": "loading", "worker": worker_id()}
        await session.commit()
        report("loading", 5)
        rparams = run.params or {}
        if rparams.get("studio") or rparams.get("draft_id"):
            # studio runs and their children keep the draft's exclusions / pins / disabled built-ins
            from app.services.studio import build_solver_input_for_run

            inp, members = await build_solver_input_for_run(session, run)
        else:
            inp, members = await build_solver_input(session, run)
        report("building", 15)
        choice = str((run.params or {}).get("solver", "auto"))
        solver_mod = _solver_fn(choice).__module__
        report("solving", 20)
        # CP-SAT holds the CPU for up to time_limit_s: solve in a worker thread so the event loop (health
        # checks, the UI, SSE progress) keeps running; ``progress`` is thread-safe (see workers.queue)
        result = await asyncio.to_thread(
            _call_solver,
            inp,
            lambda ph, pct: report(ph, 20 + int(pct * 0.7)),
            choice,
            split_weeks=run_mode(rparams, "split_blocked_weeks"),
        )
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
        return {"status": run_status(result), "assignments": n, "solver": solver_mod}
