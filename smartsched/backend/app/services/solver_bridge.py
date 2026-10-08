"""Build a ``SolverInput`` from the DB for a schedule run, solve, and persist the ``SolverResult``.

Runs are solved by CP-SAT (``app.solver.cpsat``, imported lazily); there is no fallback solver.
"""

from __future__ import annotations

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
from sqlalchemy.orm.attributes import flag_modified

from app.importers.normalize import LEADING_ZEROS_RX, non_person_reason
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


#: the production solver (``auto`` and ``cpsat`` both mean CP-SAT).  The greedy ``app.solver.stub`` is not a
#: run option (audit M1: a planner could store a greedy result as a real run); tests that want a fast
#: solver monkeypatch this entry (``tests/conftest.py`` fixture ``stub_solver``)
SOLVER_MODULES = {"cpsat": "app.solver.cpsat"}
SOLVER_CHOICES = ("auto", "cpsat")
CPSAT_MODULE = "app.solver.cpsat"


def _solver_fn(choice: str = "auto") -> Callable[..., sm.SolverResult]:
    """The solver for a run's ``params.solver`` (``auto`` | ``cpsat``); anything else is an error, never a
    silent fallback."""
    if choice not in SOLVER_CHOICES:
        raise ValueError(f"unknown solver {choice!r} (choose one of {', '.join(SOLVER_CHOICES)})")
    fn: Callable[..., sm.SolverResult] = importlib.import_module(SOLVER_MODULES["cpsat"]).solve
    return fn


def solver_name(choice: str = "auto") -> str:
    return _solver_fn(choice).__module__


#: run status of a best-effort run that stores a partial timetable (the solver reports INFEASIBLE with
#: ``stats.partial``: the full request set has no solution, the placed events satisfy every hard rule)
PARTIAL_STATUS = "FEASIBLE_PARTIAL"


def run_status(result: sm.SolverResult) -> str:
    """API status of a solver result: ``FEASIBLE_PARTIAL`` for a stored partial timetable (an infeasible
    request set, or a best-effort run whose search found no complete timetable in time: then the partial
    diagnosis says that the rest is not proven impossible)."""
    if result.status in ("INFEASIBLE", "TIMEOUT") and result.stats.get("partial") and result.assignments:
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
    if split_weeks and fn.__module__ == CPSAT_MODULE and any(len(e.weeks) > 1 for e in inp.events):
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
    from app.importers.normalize import cohort_key

    return frozenset(cohort_key(program, y) for y in years if y is not None and int(y) > 0)


#: run params (``ScheduleRun.params``) of the real-data modes and their defaults; see app/solver/README.md
MODE_DEFAULTS: dict[str, Any] = {
    "trust_locked_rooms": True,  # D1: keep a LOCKED definitive room smaller than the expected enrolment
    "fixed_conflicts_as_warnings": True,  # D2: fixed-vs-fixed cohort/instructor clashes are input warnings
    "best_effort": True,  # D3: an infeasible run still stores the maximum placement
    "merge_joint_lectures": True,  # D4
    "definitive_rooms": "lock",  # lock | prefer (soft hint) | ignore — planner's definitive rooms of LOCKED rows
    # term runs: a room blocked in some weeks only moves those weeks (week segments, app/solver/weeksplit.py)
    "split_blocked_weeks": True,
    # R4: a class larger than every suitable room that is free at its time may use several rooms of one
    # building (seats add up to its size); at most ``split_max_rooms`` rooms (run param, default 4)
    "split_large_classes": True,
}
SPLIT_MAX_ROOMS = 4


def events_for_requests(params: dict[str, Any], members: dict[int, list[int]]) -> dict[str, Any]:
    """``params["event_ids"]`` hold request ids (meeting / exam requests); a request merged into a joint
    lecture or a shared exam is solved as its head event: map member ids to the head (usability U3)."""
    ids = params.get("event_ids")
    if not isinstance(ids, list) or not members:
        return params
    head_of = {m: h for h, ms in members.items() for m in ms}
    mapped = list(
        dict.fromkeys(
            head_of.get(int(i), int(i)) for i in ids if isinstance(i, int | str) and str(i).lstrip("-").isdigit()
        )
    )
    return params if mapped == ids else {**params, "event_ids": mapped}


def run_mode(params: dict[str, Any] | None, key: str) -> Any:
    value = (params or {}).get(key, MODE_DEFAULTS[key])
    if key == "definitive_rooms":
        return value if value in ("lock", "prefer", "ignore") else "lock"
    return bool(value)


def _bridge_diag(
    event_ids: list[int],
    message: str,
    suggestions: list[str],
    code: str,
    kinds: list[str] | None = None,
    params: dict[str, Any] | None = None,
    *,
    severity: str = "warning",
) -> dict[str, Any]:
    return asdict(sm.Diagnosis(event_ids, kinds or [], message, suggestions, severity, code, dict(params or {})))


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


#: leading zeros of a course number: the importers' :data:`normalize.LEADING_ZEROS_RX` (one definition)
_LEADING_ZEROS = LEADING_ZEROS_RX


def _course_code(label: str) -> str:
    """``"MAT 112 §1 + ..."`` -> ``"MAT 112"`` (the course of a course event label); leading zeros of the
    number are dropped (``SYS 018`` = ``SYS 18``, orchestrator R1)."""
    code = " ".join(label.split("§", 1)[0].split("+", 1)[0].split()).upper()
    return _LEADING_ZEROS.sub("", code)


def _section(label: str) -> str:
    """``"MAT 112 §01"`` -> ``"1"`` (no section: ``""``)."""
    part = label.split("+", 1)[0]
    return part.split("§", 1)[1].strip().lstrip("0") if "§" in part else ""


def _planner_set(e: sm.Event, planner_sets: dict[int, list[int]] | None) -> set[int]:
    """The planner's room set of an event: its lock, else (definitive rooms as hints) its definitive set."""
    if e.locked is not None:
        return set(e.locked.room_ids)
    return set((planner_sets or {}).get(e.id, ()))


def _joinable(
    a: sm.Event,
    b: sm.Event,
    planner_locked: set[int] | frozenset[int] = frozenset(),
    planner_sets: dict[int, list[int]] | None = None,
) -> bool:
    """Two fixed-time course requests are one physical lecture at the same day/periods in overlapping weeks
    when the planner locked both to the same room set, or — neither of them locked by the planner — they
    are the same course with a shared instructor (``FIZ 111 §1`` listed once per programme).  A shared
    instructor never joins a locked row or two different courses (review B1: chains through an instructor
    dropped the planner's rooms); such a pair stays two requests and a clash at fixed times is an input
    conflict (D2), reported."""
    if (a.fixed_day, a.fixed_start, a.duration) != (b.fixed_day, b.fixed_start, b.duration) or a.fixed_day is None:
        return False
    if not a.weeks & b.weeks:
        return False
    ra = _planner_set(a, planner_sets)
    rb = _planner_set(b, planner_sets)
    if ra or rb:
        return bool(ra) and ra == rb  # the planner's own decision: the same rooms at the same time
    if a.id in planner_locked or b.id in planner_locked:
        return False  # locked to a room outside the pool: kept as the planner set it
    return bool(a.instructor_keys & b.instructor_keys) and _course_code(a.label) == _course_code(b.label)


def _base_label(label: str) -> str:
    return " ".join(label.split())


def _slot_of(e: sm.Event) -> tuple[int, int, int] | None:
    if e.locked is not None:
        return e.locked.day, e.locked.start, e.locked.end
    if e.fixed_day is None or e.fixed_start is None:
        return None
    return e.fixed_day, e.fixed_start, e.fixed_start + e.duration - 1


def _same_locked_lecture(a: sm.Event, b: sm.Event, planner_sets: dict[int, list[int]] | None = None) -> bool:
    """The planner put two rows into the same room set at overlapping times: one lecture listed twice when
    both start together or it is the same course (``BME 528`` P8-10 and ``BME 528 §1`` P7-9 in B 204;
    ``SYS 18`` / ``SYS 018 §1``).  With definitive rooms as hints the planner's sets count the same way."""
    ra, rb = _planner_set(a, planner_sets), _planner_set(b, planner_sets)
    sa, sb = _slot_of(a), _slot_of(b)
    if not ra or ra != rb or sa is None or sb is None or not a.weeks & b.weeks:
        return False
    if sa[0] != sb[0] or sa[1] > sb[2] or sb[1] > sa[2]:
        return False
    return sa[1] == sb[1] or _course_code(a.label) == _course_code(b.label)


def merge_joint_lectures(
    events: list[sm.Event],
    members: dict[int, list[int]],
    room_capacity: dict[int, int] | None = None,
    hint_rooms: dict[int, list[int]] | None = None,
    planner_locked: set[int] | frozenset[int] = frozenset(),
    planner_sets: dict[int, list[int]] | None = None,
) -> tuple[list[sm.Event], list[dict[str, Any]]]:
    """Merge requests that describe one joint lecture (``FIZ 111 §1`` listed once per programme, two rows
    the planner locked into one room at one time) into one solver event.

    The planning list has one row per programme; without merging, the planner's own definitive plan
    is infeasible (same instructor / same room twice at the same time).  The merged event seats the
    **sum** of the groups (never clipped: a planner-locked group too large for its rooms is a trusted lock,
    reported as ``trusted_lock_capacity``; definitive rooms used as hints are clipped by
    :func:`clip_to_planner_rooms`), carries every cohort and instructor key, spans the members' periods,
    is locked to the union of the members' locked rooms, and maps back to all its requests through
    ``members`` (one assignment per request is persisted, each with its own periods and weeks).  A group
    that would hold two different locked room sets is not merged (checked after the union-find).
    Returns (events, one summary dict per merged group, incl. ``planner_rooms`` and the rejected groups
    as ``{"rejected": [...]}``)."""
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
                if _joinable(events[idxs[x]], events[idxs[y]], planner_locked, planner_sets):
                    parent[find(idxs[x])] = find(idxs[y])
    # the planner locked two rows into the same room set at overlapping times: one lecture listed twice
    # when both start together (cross-listed MBG 408 / MBG 598 in A 207) or it is the same course and
    # section (CSE 102 §1 once per programme with slightly different times); the room holds the union
    by_rooms: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
    for i, e in enumerate(events):
        rs = _planner_set(e, planner_sets)
        slot = _slot_of(e)
        if rs and slot is not None:
            by_rooms[(slot[0], tuple(sorted(rs)))].append(i)
    for idxs in by_rooms.values():
        for x in range(len(idxs)):
            for y in range(x + 1, len(idxs)):
                if _same_locked_lecture(events[idxs[x]], events[idxs[y]], planner_sets):
                    parent[find(idxs[x])] = find(idxs[y])
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(events)):
        groups[find(i)].append(i)
    out: list[sm.Event] = []
    merged: list[dict[str, Any]] = []
    caps = room_capacity or {}
    for idxs in groups.values():
        evs = sorted((events[i] for i in idxs), key=lambda e: e.id)
        locked_sets = {frozenset(e.locked.room_ids) for e in evs if e.locked is not None and e.locked.room_ids}
        if len(locked_sets) > 1:
            # the whole group is checked after the union-find: two different planner room sets are two
            # sessions (or a data error the static checker reports), never one event in one of the sets
            merged.append(
                {
                    "rejected": [e.id for e in evs],
                    "labels": [e.label for e in evs],
                    "room_sets": [sorted(s) for s in locked_sets],
                }
            )
            out.extend(evs)
            continue
        if len(evs) == 1:
            out.append(evs[0])
            continue
        head = evs[0]
        locked_rooms = tuple(dict.fromkeys(r for e in evs if e.locked is not None for r in e.locked.room_ids))
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
        planner_rooms: list[int] = list(locked_rooms)
        if not planner_rooms and hint_rooms and all(e.id in hint_rooms for e in evs):
            # definitive rooms used as hints: the planner's room set (union) seats the joint lecture
            planner_rooms = list(dict.fromkeys(r for e in evs for r in hint_rooms[e.id]))
        if planner_rooms:
            info["planner_rooms"] = planner_rooms
            info["seats"] = sum(caps.get(r, 0) for r in planner_rooms)
        merged.append(info)
        out.append(
            replace(
                head,
                label=label,
                size=size,
                weeks=weeks,
                required_tags=frozenset().union(*(e.required_tags for e in evs)),
                max_rooms=max(len(planner_rooms), *(e.max_rooms for e in evs)),
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


def clip_to_planner_rooms(
    events: list[sm.Event],
    planner_rooms: dict[int, list[int]],
    room_capacity: dict[int, int],
    rooms: tuple[sm.Room, ...],
) -> tuple[list[sm.Event], list[tuple[int, int, int, list[int]]]]:
    """D1 for definitive rooms used as *hints* (``definitive_rooms="prefer"``): an event the planner seats in
    a room set with fewer seats than its expected size may use exactly that set with the planner's seat
    count as its size — and only that set: every other room that cannot seat the full group is forbidden,
    so a clipped size never lets the group into somebody else's small room (review MINOR); a room-sharing
    exam is restricted to the planner's set (its size is the seat demand in a shared room).  Returns the
    events and ``(event id, full size, seats, planner rooms)`` per clipped event."""
    out: list[sm.Event] = []
    clipped: list[tuple[int, int, int, list[int]]] = []
    for e in events:
        planner = planner_rooms.get(e.id)
        seats = sum(room_capacity.get(r, 0) for r in planner or [])
        if not planner or not 0 < seats < e.size or e.locked is not None:
            out.append(e)
            continue
        if e.share_room:
            # a shared exam room takes the event's *size* in seats: a clipped size is sound only in exactly
            # the planner's set, so a clipped exam may use no other room (it would under-count its students)
            small = frozenset(r.id for r in rooms if r.id not in planner)
        else:
            small = frozenset(r.id for r in rooms if r.id not in planner and room_capacity.get(r.id, 0) < e.size)
        clipped.append((e.id, e.size, seats, list(planner)))
        out.append(replace(e, size=seats, forbidden_room_ids=e.forbidden_room_ids | small))
    return out, clipped


def _suits(e: sm.Event, r: sm.Room) -> bool:
    if r.capacity <= 0 or r.id in e.forbidden_room_ids or e.forbidden_tags & r.tags:
        return False
    if not e.required_tags <= r.tags:
        return False
    return not e.required_room_ids or r.id in e.required_room_ids


def allow_large_splits(
    events: list[sm.Event],
    rooms: tuple[sm.Room, ...],
    blocks: list[sm.Block],
    max_rooms: int = SPLIT_MAX_ROOMS,
) -> tuple[list[sm.Event], list[dict[str, Any]]]:
    """R4 (planner comparison): a course larger than every suitable room that is free at its fixed time
    (no grid block, no locked class in any of its weeks) — or, without a fixed time, larger than every
    suitable room — may use up to ``max_rooms`` rooms of **one building** whose seats add up to its size
    (the solver's split linking: ``Σ cap·z ≥ size``).  The building is the event's requested building (or
    that of its requested rooms) when it can seat the class, else the one needing the fewest rooms (then
    the most free seats).  Rooms of other buildings stay allowed only when they seat the class alone, so
    a single big room that frees up in a week segment is never lost.  Locked, room-less, multi-room and
    exam events are left alone; an event no building can seat is left alone too.  Returns (events, one
    info dict per split event)."""
    if max_rooms < 2:
        return events, []
    by_id = {r.id: r for r in rooms}
    busy: dict[tuple[int, int], list[tuple[int, int, frozenset[int] | None]]] = defaultdict(list)
    for b in blocks:
        busy[(b.room_id, b.day)].append((b.start, b.end, None if b.week is None else frozenset({b.week})))
    for e in events:
        if e.locked is not None:
            for rid in e.locked.room_ids:
                busy[(rid, e.locked.day)].append((e.locked.start, e.locked.end, frozenset(e.locked.weeks)))

    def free(r: sm.Room, e: sm.Event) -> bool:
        if e.fixed_day is None or e.fixed_start is None:
            return True
        end = e.fixed_start + e.duration - 1
        return not any(
            a <= end and e.fixed_start <= b and (wk is None or wk & e.weeks) for a, b, wk in busy[(r.id, e.fixed_day)]
        )

    out: list[sm.Event] = []
    info: list[dict[str, Any]] = []
    for e in events:
        if e.kind != "course" or e.locked is not None or not e.needs_room or e.max_rooms > 1 or e.size <= 0:
            out.append(e)
            continue
        suitable = [r for r in rooms if _suits(e, r)]
        if not suitable or any(r.capacity >= e.size and free(r, e) for r in suitable):
            out.append(e)
            continue
        wanted = e.preferred_building or next((by_id[i].building for i in e.preferred_room_ids if i in by_id), None)
        best: tuple[tuple[int, int, int], str, int] | None = None
        for building in sorted({r.building for r in suitable}):
            caps = sorted((r.capacity for r in suitable if r.building == building and free(r, e)), reverse=True)
            total, k = 0, 0
            for c in caps:
                if total >= e.size:
                    break
                total, k = total + c, k + 1
            if total < e.size or k > max_rooms:
                continue
            rank = (0 if building == wanted else 1, k, -sum(caps))
            if best is None or rank < best[0]:
                best = (rank, building, k)
        if best is None:
            out.append(e)
            continue
        _rank, building, k = best
        outside = frozenset(r.id for r in rooms if r.building != building and r.capacity < e.size)
        out.append(replace(e, max_rooms=min(max_rooms, k + 1), forbidden_room_ids=e.forbidden_room_ids | outside))
        info.append({"event_id": e.id, "label": e.label, "size": e.size, "building": building, "rooms_needed": k})
    return out, info


def _median(values: list[int]) -> int:
    vals = sorted(v for v in values if v > 0)
    if not vals:
        return 0
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid] + 1) // 2


class SizeFallback:
    """Fallback group sizes for requests without an enrolment (review M1): the median enrolment of the
    course's other sections (exams: the course's other exam rows), else of the cohort (programme + class
    year), else of the whole term.  ``source`` tells the planner which one was used."""

    def __init__(self) -> None:
        self.by_course: dict[Any, list[int]] = defaultdict(list)
        self.by_cohort: dict[tuple[Any, int], list[int]] = defaultdict(list)
        self.all: list[int] = []

    def add(self, course: Any, program: Any, years: list[int], size: int) -> None:
        if size <= 0:
            return
        self.by_course[course].append(size)
        for y in years:
            self.by_cohort[(program, y)].append(size)
        self.all.append(size)

    def size_for(self, course: Any, program: Any, years: list[int]) -> tuple[int, str]:
        if self.by_course.get(course):
            return _median(self.by_course[course]), "course_sections"
        cohort = [v for y in years for v in self.by_cohort.get((program, y), [])]
        if program is not None and cohort:
            return _median(cohort), "cohort_median"
        if self.all:
            return _median(self.all), "term_median"
        return 0, "none"


def _years(values: list[Any] | None, single: Any) -> list[int]:
    out = []
    for y in values or [single]:
        try:
            yi = int(y)
        except (TypeError, ValueError):
            continue
        if yi > 0:
            out.append(yi)
    return out


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
    tip_room_ids = {r.id for r in rooms_db if "TIP" in (r.tags or [])}
    definitive_mode = run_mode(params, "definitive_rooms")
    outside_pool: dict[int, list[int]] = {}  # request id -> planner rooms outside the solver's room pool
    #: LOCKED rows with planner rooms outside the pool: (request, rooms, day key, start, end, weeks)
    outside_slots: list[tuple[int, list[int], Any, int, int, frozenset[int]]] = []

    def split_definitive(ids: list[Any]) -> tuple[list[int], list[int]]:
        ids_i = list(dict.fromkeys(int(x) for x in ids or []))
        return [x for x in ids_i if x in room_ids], [x for x in ids_i if x not in room_ids]

    events: list[sm.Event] = []
    members: dict[int, list[int]] = {}
    extra_weeks: set[int] = set()
    room_cap = {r.id: (r.exam_capacity if exam else r.capacity) for r in rooms}
    trust_hints = run_mode(params, "trust_locked_rooms") and bool(params.get("trust_definitive_capacity", True))
    hint_sets: dict[int, list[int]] = {}  # prefer mode + D1: request -> the planner's definitive rooms (hint)
    planner_sets: dict[int, list[int]] = {}  # prefer mode: request -> the planner's definitive pooled rooms
    #: request id -> {"size", "source"}: fallback sizes of requests without an enrolment (review M1)
    fallbacks: dict[int, dict[str, Any]] = {}
    planner_locked: set[int] = set()  # LOCKED rows (definitive rooms in or outside the pool)
    tip_requested: set[int] = set()  # requests asking for a medicine (TIP) room
    tip_planned: set[int] = set()  # LOCKED requests the planner seats in a TIP room

    #: instructor values that name no person ("Yüz yüze", "UZEM", a pasted note; databases imported before
    #: the importer's check still link them): never an instructor key, reported as a data issue
    not_person: dict[int, list[str]] = defaultdict(list)  # request id -> the values dropped

    if not exam:
        ghost_instructors = {
            int(i): str(name)
            for i, name in (await session.execute(select(Instructor.id, Instructor.full_name))).all()
            if non_person_reason(name) is not None
        }
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
        sizes = SizeFallback()
        for cid, pid, cy, cys, enr in (
            await session.execute(
                select(
                    Section.course_id,
                    Section.program_id,
                    Section.class_year,
                    Section.class_years,
                    Section.enrolment,
                ).where(Section.term_id == term.id, Section.archived.is_(False))
            )
        ).all():
            sizes.add(cid, pid, _years(cys, cy), int(enr or 0))
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
            if "TIP" in tags:
                tip_requested.add(mr.id)
            required_tags = frozenset({"PC"} & tags)
            forbidden_tags: frozenset[str] = frozenset()
            if "TIP" not in tags:
                forbidden_tags = frozenset({"TIP"})
            locked = None
            definitive, outside = split_definitive(mr.definitive_room_ids or [])
            is_locked = mr.status == "LOCKED" and bool(definitive or outside) and bool(fixed_day)
            if is_locked:
                planner_locked.add(mr.id)
                if set(definitive) & tip_room_ids:
                    tip_planned.add(mr.id)
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
            elif is_locked and definitive_mode == "prefer" and not definitive:
                # only the planner's choice *inside* the pool becomes a soft hint; a room outside the pool
                # (lab/office without capacity) cannot be chosen or replaced by the solver, so the meeting
                # keeps it exactly as with locks (else it would compete for pooled rooms it never used)
                needs_room = False
                outside_pool[mr.id] = outside
            if is_locked and outside:
                outside_slots.append((mr.id, outside, fixed_day, mr.start_period, mr.end_period, ev_weeks))
            size = int(sec.enrolment or mr.requested_capacity or 0)
            if size <= 0:
                size, source = sizes.size_for(sec.course_id, sec.program_id, _years(sec.class_years, sec.class_year))
                fallbacks[mr.id] = {"size": size, "source": source}
            hint_rooms = 1
            if is_locked and definitive_mode == "prefer" and definitive:
                planner_sets[mr.id] = list(definitive)
            if is_locked and definitive_mode == "prefer":
                preferred = list(dict.fromkeys([*definitive, *preferred]))
                hint_rooms = max(1, len(definitive))  # the planner's room set may be used as a whole
                if trust_hints and definitive:
                    hint_sets[mr.id] = list(definitive)
            if is_locked and definitive_mode != "lock" and set(definitive) & tip_room_ids:
                forbidden_tags = frozenset()  # the planner seats this group in a medicine (TIP) room
            cohort = _cohort_keys(
                sec.program.canonical_name if sec.program else None, sec.class_years or [sec.class_year]
            )
            instr = frozenset(
                f"INS:{si.instructor_id}" for si in sec.instructors if si.instructor_id not in ghost_instructors
            )
            for si in sec.instructors:
                if si.instructor_id in ghost_instructors:
                    not_person[mr.id].append(ghost_instructors[si.instructor_id])
            label = f"{sec.course.display_code}{' §' + sec.label if sec.label else ''}"
            events.append(
                sm.Event(
                    id=mr.id,
                    kind="course",
                    label=label,
                    size=size,
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
                    max_rooms=hint_rooms,
                )
            )
            members[mr.id] = [mr.id]
        if run_mode(params, "merge_joint_lectures"):
            events, merged = merge_joint_lectures(
                events,
                members,
                {r.id: r.capacity for r in rooms},
                hint_sets,
                planner_locked,
                planner_sets if definitive_mode == "prefer" else None,
            )
            joint = [m for m in merged if "rejected" not in m]
            rejected = [m for m in merged if "rejected" in m]
            if merged:
                run.stats = {
                    **(run.stats or {}),
                    "merged_joint_lectures": len(joint),
                    "joint_lectures_rejected": len(rejected),
                }
            for m in rejected:
                bridge_diags.append(
                    _bridge_diag(
                        list(m["rejected"]),
                        f"{' / '.join(m['labels'])} share a slot but the planner locked them into different room "
                        "sets: kept as separate classes",
                        ["check whether they are one joint lecture; if so, give them one room set"],
                        "joint_lecture_rejected",
                        [],
                        {"room_sets": m["room_sets"]},
                        severity="info",
                    )
                )
    else:
        qe = (
            select(ExamRequest)
            .where(ExamRequest.term_id == term.id, ExamRequest.archived.is_(False), ExamRequest.needs_room.is_(True))
            .options(selectinload(ExamRequest.program))
        )
        groups: dict[str, list[ExamRequest]] = defaultdict(list)
        exam_sizes = SizeFallback()
        for ex in (await session.execute(qe)).scalars():
            exam_sizes.add(ex.course_code, ex.program_id, _years(ex.class_years, ex.class_year), int(ex.enrolment or 0))
            if ex.date is None or ex.start_period is None or ex.end_period is None:
                continue
            groups[ex.merge_key or f"single:{ex.id}"].append(ex)
        for rows in groups.values():
            head = min(rows, key=lambda r: r.id)
            head_date, head_start = head.date, head.start_period
            assert head_date is not None and head_start is not None
            # the group spans its rows' periods (the end time is the latest of the group, MINOR)
            head_end = max(int(r.end_period or head_start) for r in rows)
            first_start = min(int(r.start_period or head_start) for r in rows)
            week = week_index_for_date(term, head_date, list(weeks_rows))
            if week is None:
                week = weeks[0]
            if week not in week_set:
                if run.horizon != "TERM" and params.get("strict_horizon", True):
                    continue
                extra_weeks.add(week)  # exam dated outside the term's lecture weeks (e.g. early finals)
            size = 0
            for r in rows:
                n = int(r.enrolment or 0)
                if n <= 0:
                    n, source = exam_sizes.size_for(r.course_code, r.program_id, _years(r.class_years, r.class_year))
                    fallbacks[r.id] = {"size": n, "source": source}
                size += n
            tags = {str(t) for r in rows for t in (r.requested_tags or [])}
            if "TIP" in tags:
                tip_requested.add(head.id)
            # the planner's rooms are those of the LOCKED rows; a mixed locked/unlocked group sits in them
            # (MINOR: the locked rooms were lost when one row of the group was not locked)
            locked_rows = [r for r in rows if r.status == "LOCKED" and r.definitive_room_ids]
            definitive, outside = split_definitive([x for r in locked_rows for x in (r.definitive_room_ids or [])])
            locked = None
            exam_needs_room = True
            is_locked = bool(locked_rows) and bool(definitive or outside)
            if is_locked:
                planner_locked.update(r.id for r in rows)
            exam_preferred = list(
                dict.fromkeys(
                    [
                        *definitive,
                        *(
                            int(x)
                            for r in rows
                            for x in [*(r.definitive_room_ids or []), *(r.requested_room_ids or [])]
                            if int(x) in room_ids
                        ),
                    ]
                )
            )
            if is_locked and definitive_mode == "lock":
                if definitive:
                    locked = sm.Assignment(
                        head.id,
                        head_date.isoweekday(),
                        first_start,
                        head_end,
                        tuple(definitive),
                        frozenset({week}),
                        head_date,
                    )
                else:
                    exam_needs_room = False
                if outside:
                    outside_pool[head.id] = outside
            elif is_locked and definitive_mode == "prefer" and not definitive:
                exam_needs_room = False  # the planner's room is outside the pool: kept (see the course case)
                outside_pool[head.id] = outside
            elif is_locked and definitive_mode == "prefer" and trust_hints and definitive:
                hint_sets[head.id] = list(definitive)
            if is_locked and outside:
                outside_slots.append((head.id, outside, head_date, first_start, head_end, frozenset({week})))
            tip_ok = is_locked and bool(set(definitive) & tip_room_ids)
            if tip_ok:
                tip_planned.add(head.id)
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
                    duration=head_end - first_start + 1,
                    weeks=frozenset({week}),
                    fixed_day=head_date.isoweekday(),
                    fixed_start=first_start,
                    allowed_days=frozenset({head_date.isoweekday()}),
                    fixed_date=head_date,
                    required_tags=frozenset({"PC"} & tags),
                    forbidden_tags=frozenset() if "TIP" in tags or locked or tip_ok else frozenset({"TIP"}),
                    preferred_room_ids=tuple(exam_preferred),
                    needs_room=exam_needs_room,
                    preferred_building=head.requested_building,
                    max_rooms=max(max_rooms, 1),
                    cohort_keys=cohort,
                    instructor_keys=frozenset(
                        f"INS:{r.instructor_text}"
                        for r in rows
                        if r.instructor_text and non_person_reason(r.instructor_text) is None
                    ),
                    locked=locked,
                    # exams of different cohorts may sit in one room as long as the seats add up
                    # (the Final plan does this routinely); the solver checks the seat budget
                    share_room=True,
                )
            )
            members[head.id] = [r.id for r in rows]
            for r in rows:
                if r.instructor_text and non_person_reason(r.instructor_text) is not None:
                    not_person[r.id].append(r.instructor_text)

    head_of = {m: h for h, ms in members.items() for m in ms}
    labels = {e.id: e.label for e in events}

    if hint_sets and definitive_mode == "prefer":
        # D1 for hints, after merging: the planner's room set (union over a joint lecture) may seat fewer
        # than the expected size; only that set may then hold the clipped size (one warning per case)
        planner_of: dict[int, list[int]] = {}
        for e in events:
            ms = members.get(e.id, [e.id])
            if all(m in hint_sets for m in ms):
                planner_of[e.id] = list(dict.fromkeys(r for m in ms for r in hint_sets[m]))
        events, hint_clipped = clip_to_planner_rooms(events, planner_of, room_cap, rooms)
        what = "exam seats" if exam else "seats"
        for eid, sz, cap, planner_rooms in hint_clipped:
            hint_codes = [all_rooms.get(r, str(r)) for r in planner_rooms]
            ms = members.get(eid, [eid])
            code = "joint_lecture_clipped" if len(ms) > 1 and not exam else "trusted_hint_capacity"
            bridge_diags.append(
                _bridge_diag(
                    [eid],
                    f"{labels.get(eid, str(eid))} expects {sz} students; the planner's room "
                    f"{' + '.join(hint_codes)} has {cap} {what}: used as a hint with {cap} as the group size "
                    "(enrolments are estimates); any other room must seat all of them",
                    ["check the enrolment estimate", "set trust_locked_rooms=false to require full capacity"],
                    code,
                    ["capacity"],
                    {
                        "size": sz,
                        "seats": cap,
                        "room_codes": hint_codes,
                        "request_id": ms[0],
                        "request_ids": ms,
                        "clipped_to": cap,
                    },
                )
            )
        if hint_clipped:
            run.stats = {**(run.stats or {}), "trusted_hint_capacity": len(hint_clipped)}

    if fallbacks:
        # one warning per solver event with the members that have no enrolment, and the fallback used
        by_event: dict[int, list[int]] = defaultdict(list)
        for rid in fallbacks:
            by_event[head_of.get(rid, rid)].append(rid)
        for eid, rids in sorted(by_event.items()):
            sources = sorted({str(fallbacks[r]["source"]) for r in rids})
            fsize = sum(int(fallbacks[r]["size"]) for r in rids)
            bridge_diags.append(
                _bridge_diag(
                    [eid],
                    f"{labels.get(eid, str(eid))}: no enrolment in the data for {len(rids)} request(s); planned with "
                    f"{fsize} students ({', '.join(_FALLBACK_TEXT.get(x, x) for x in sources)})",
                    ["enter the enrolment in the planning list"],
                    "missing_enrolment",
                    ["capacity"],
                    {
                        "request_ids": sorted(rids),
                        "size": fsize,
                        "sizes": {str(r): int(fallbacks[r]["size"]) for r in sorted(rids)},
                        "sources": sources,
                    },
                )
            )
        run.stats = {**(run.stats or {}), "enrolment_fallbacks": {str(k): v for k, v in sorted(fallbacks.items())}}

    if not_person:
        names = sorted({v for vs in not_person.values() for v in vs})
        ev_ids = sorted({head_of.get(r, r) for r in not_person})
        bridge_diags.append(
            _bridge_diag(
                ev_ids,
                f"{len(not_person)} request(s) name no person as instructor ({', '.join(repr(x) for x in names[:8])}"
                + (" ..." if len(names) > 8 else "")
                + "): not used for instructor clashes",
                ["write the instructor's name in the planning list"],
                "instructor_not_person",
                [],
                {"names": names, "request_ids": sorted(not_person)},
                severity="info",
            )
        )

    if outside_slots:
        bridge_diags.extend(_outside_pool_overlaps(outside_slots, head_of, labels, all_rooms, exam))

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
    # confirmed user bookings (CRBS parity) are pre-occupied slots for the solver
    from app.services.bookings_solver import booking_blocks

    blocks.extend(await booking_blocks(session, term, weeks_rows, week_set))

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
    from app.importers.normalize import normalize_selector_params

    constraints = [  # cohort / programme selectors in the one canonical form (usability U1); request ids of
        # merged joint-lecture members point at their solver event (usability U3)
        sm.Constraint(
            c.kind,
            events_for_requests(normalize_selector_params(c.params), members),
            c.hardness == "hard",
            int(c.weight or 1),
            c.id,
        )
        for c in cons
    ]
    if fallbacks:
        constraints = _exclude_from_waste(constraints, sorted({head_of.get(r, r) for r in fallbacks}))

    previous: list[sm.Assignment] = []
    carried: dict[int, str] = {}  # request id -> origin of a tool-made lock carried over from the parent run
    if run.parent_run_id:
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
        # event (a manual move collapses them into one row anyway); a member's locked (moved) row wins
        parent_rows.sort(key=lambda a: (not a.is_locked, -len(a.weeks or []), a.id))
        manual_lines: dict[int, str] = {}
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
            pooled_rooms = tuple(r for r in a_rooms if r in room_ids)
            if a.is_locked and idx is not None and pooled_rooms:
                # a locked assignment of the parent run (manual move, fix button, AI edit) is carried over
                # as a hard lock; ``locked`` overrides the request's fixed day/time in the solver.  It is the
                # planner's own (trusted) decision only when it is exactly the planning list's lock
                ev = events[idx]
                own = ev.locked
                trusted = (
                    own is not None
                    and set(own.room_ids) == set(pooled_rooms)
                    and (own.day, own.start, own.end) == (a.day, a.start_period, a.end_period)
                )
                events[idx] = replace(
                    ev,
                    duration=a.end_period - a.start_period + 1,
                    locked=sm.Assignment(
                        ev.id, a.day, a.start_period, a.end_period, pooled_rooms, ev.weeks, a.date or ev.fixed_date
                    ),
                    # a tool-made lock gets the TIP ban back unless the class asks for a medicine room or the
                    # planner seats it in one (the planner's own lock keeps the cleared ban)
                    forbidden_tags=(
                        frozenset()
                        if trusted or {ev_id, *members.get(ev_id, [])} & (tip_requested | tip_planned)
                        else frozenset({"TIP"})
                    ),
                    max_rooms=max(len(pooled_rooms), 1) if ev.kind == "exam" else max(ev.max_rooms, len(pooled_rooms)),
                    lock_trusted=trusted,
                )
                if not trusted:
                    for mid in members.get(ev_id, [ev_id]):
                        carried[mid] = str(a.origin or "MANUAL")
                    manual_lines[ev_id] = (
                        f"day {a.day} P{a.start_period}-P{a.end_period} in "
                        + " + ".join(all_rooms.get(r, str(r)) for r in pooled_rooms)
                        + f" ({str(a.origin or 'MANUAL').lower()})"
                    )
        for ev_id, where in sorted(manual_lines.items()):
            bridge_diags.append(
                _bridge_diag(
                    [ev_id],
                    f"{labels.get(ev_id, str(ev_id))} keeps the placement made by hand or by a fix in the parent "
                    f"run: {where}; capacity and room tags are checked like any placement",
                    ["unlock it in the parent run to let the solver choose again"],
                    "manual_lock",
                    [],
                    {"origin": carried.get(members.get(ev_id, [ev_id])[0], "MANUAL")},
                    severity="info",
                )
            )
        if carried:
            run.stats = {**(run.stats or {}), "carried_locks": {str(k): v for k, v in sorted(carried.items())}}

    if not exam and run_mode(params, "split_large_classes"):
        events, splits = allow_large_splits(
            events, rooms, blocks, int(params.get("split_max_rooms", SPLIT_MAX_ROOMS) or SPLIT_MAX_ROOMS)
        )
        if splits:
            run.stats = {**(run.stats or {}), "split_large_classes": len(splits)}
            bridge_diags.append(
                _bridge_diag(
                    [x["event_id"] for x in splits],
                    f"{len(splits)} class(es) larger than every free room that fits may use several rooms of one "
                    "building: "
                    + "; ".join(f"{x['label']} ({x['size']}, {x['building']} block)" for x in splits[:10])
                    + (" ..." if len(splits) > 10 else ""),
                    ["set split_large_classes=false to keep every class in one room"],
                    "split_allowed",
                    ["capacity"],
                    {"events": splits},
                    severity="info",
                )
            )

    if exam and extra_weeks:
        weeks = sorted(week_set | extra_weeks)
    inp = sm.SolverInput(
        rooms=rooms,
        events=tuple(events),
        constraints=tuple(constraints),
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
        by_ev: dict[int, list[int]] = defaultdict(list)
        for rid, rooms_out in outside_pool.items():
            by_ev[head_of.get(rid, rid)].extend(rooms_out)
        ev_by_id = {e.id: e for e in inp.events}
        lines = []
        for eid, rids in sorted(by_ev.items()):
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
                    [x[0] for x in kept_out],
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
                    [x[0] for x in partly],
                    f"{len(partly)} locked request(s) also use a room outside the bookable pool; only their pooled "
                    "rooms are checked: " + "; ".join(x[1] for x in partly[:10]) + (" ..." if len(partly) > 10 else ""),
                    ["add these rooms with a capacity to the room master"],
                    "outside_room_pool",
                )
            )
        run.stats = {
            **(run.stats or {}),
            "outside_pool_rooms": {str(k): list(dict.fromkeys(v)) for k, v in outside_pool.items()},
        }
    run.stats = {**(run.stats or {}), "bridge_diagnoses": bridge_diags}
    return inp, members


_FALLBACK_TEXT = {
    "course_sections": "median of the course's other sections",
    "cohort_median": "median of the programme year",
    "term_median": "median of the term",
    "none": "no enrolment anywhere: size 0, capacity unchecked",
}


def _exclude_from_waste(constraints: list[sm.Constraint], event_ids: list[int]) -> list[sm.Constraint]:
    """Events planned with a fallback size stay out of ``min_capacity_waste`` (their size is a guess):
    added to the term's untargeted configuration of the rule, or as a new default configuration."""
    from app.solver.constraints._common import is_targeted

    out = list(constraints)
    for i, c in enumerate(out):
        if c.kind == "min_capacity_waste" and not is_targeted(c):
            ids = sorted({*(int(x) for x in c.params.get("exclude_event_ids") or []), *event_ids})
            out[i] = replace(c, params={**c.params, "exclude_event_ids": ids})
            return out
    out.append(sm.Constraint("min_capacity_waste", {"exclude_event_ids": event_ids}, False, 1))
    return out


def _outside_pool_overlaps(
    slots: list[tuple[int, list[int], Any, int, int, frozenset[int]]],
    head_of: dict[int, int],
    labels: dict[int, str],
    all_rooms: dict[int, str],
    exam: bool,
) -> list[dict[str, Any]]:
    """Two LOCKED requests holding one room outside the pool at overlapping times in shared weeks: the
    solver keeps both (it cannot check rooms it has no capacity for), so the double booking is reported as
    a data issue (``outside_pool_overlap``, review M6)."""
    by_room: dict[tuple[int, Any], list[tuple[int, int, int, frozenset[int]]]] = defaultdict(list)
    for rid, outside, day, start, end, wks in slots:
        for room in outside:
            by_room[(room, day)].append((head_of.get(rid, rid), start, end, wks))
    seen: set[tuple[int, int, int]] = set()
    out: list[dict[str, Any]] = []
    for (room, day), items in sorted(by_room.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if a[0] == b[0] or not (a[1] <= b[2] and b[1] <= a[2]) or not a[3] & b[3]:
                    continue
                key = (room, min(a[0], b[0]), max(a[0], b[0]))
                if key in seen:
                    continue
                seen.add(key)
                code = all_rooms.get(room, str(room))
                when = str(day) if exam else f"day {day}"
                out.append(
                    _bridge_diag(
                        [a[0], b[0]],
                        f"{labels.get(a[0], a[0])} and {labels.get(b[0], b[0])} are both locked to {code} (outside "
                        f"the bookable pool) on {when} P{max(a[1], b[1])}-P{min(a[2], b[2])}; both are kept",
                        [f"change the room or time of {labels.get(a[0], a[0])} or {labels.get(b[0], b[0])}"],
                        "outside_pool_overlap",
                        ["no_room_overlap"],
                        {
                            "rooms": [room],
                            "room_codes": [code],
                            "day": day if not exam else None,
                            "date": str(day) if exam else None,
                            "start": max(a[1], b[1]),
                            "end": min(a[2], b[2]),
                            "weeks": sorted(a[3] & b[3]),
                        },
                    )
                )
    return out


async def _member_rows(session: AsyncSession, exam: bool, ids: set[int]) -> dict[int, dict[str, Any]]:
    """Own periods / weeks / date / status / definitive rooms of the requests behind merged events."""
    out: dict[int, dict[str, Any]] = {}
    if not ids:
        return out
    if exam:
        for ex in (await session.execute(select(ExamRequest).where(ExamRequest.id.in_(ids)))).scalars():
            out[ex.id] = {
                "start": ex.start_period,
                "end": ex.end_period,
                "date": ex.date,
                "weeks": None,
                "locked": ex.status == "LOCKED",
                "definitive": [int(x) for x in ex.definitive_room_ids or []],
            }
    else:
        for mr in (await session.execute(select(MeetingRequest).where(MeetingRequest.id.in_(ids)))).scalars():
            out[mr.id] = {
                "start": mr.start_period,
                "end": mr.end_period,
                "date": None,
                "weeks": {int(w) for w in mr.weeks or []} or None,
                "locked": mr.status == "LOCKED",
                "definitive": [int(x) for x in mr.definitive_room_ids or []],
            }
    return out


def _member_placements(
    a: sm.Assignment, ms: list[int], info: dict[int, dict[str, Any]], outside: dict[int, list[int]]
) -> list[tuple[int, int, int, tuple[int, ...], frozenset[int]]]:
    """(request, start, end, rooms, weeks) of each request behind one solver assignment.  A joint lecture /
    exam cohort keeps one room set for the group, but every request keeps its own periods (shifted with the
    group when it was moved) and its own weeks; a group sitting exactly in its planner's rooms gives each
    LOCKED request back its own definitive rooms (an exam split by programme over C 301 / C 201 / C 501),
    and a room outside the pool is only added to the request the planner put there (MINOR, review B1)."""
    if len(ms) == 1:
        rid = ms[0]
        rooms = tuple(dict.fromkeys([*a.room_ids, *outside.get(rid, [])])) if a.room_ids else a.room_ids
        return [(rid, a.start, a.end, rooms, a.weeks)]
    own_start = [int(info[m]["start"]) for m in ms if m in info and info[m]["start"] is not None]
    offset = a.start - min(own_start) if own_start else 0
    pooled_of = {
        m: [r for r in info[m]["definitive"] if r not in set(outside.get(m, []))]
        for m in ms
        if m in info and info[m]["locked"]
    }
    planner = {r for rs in pooled_of.values() for r in rs}
    in_planner_rooms = bool(planner) and set(a.room_ids) == planner
    out = []
    for m in ms:
        meta = info.get(m)
        start, end = a.start, a.end
        weeks = a.weeks
        if meta is not None and meta["start"] is not None and meta["end"] is not None:
            start = max(a.start, int(meta["start"]) + offset)
            end = min(a.end, int(meta["end"]) + offset)
            if meta["weeks"]:
                weeks = frozenset(a.weeks & meta["weeks"])
        if not weeks or end < start:
            continue
        rooms = tuple(pooled_of[m]) if in_planner_rooms and pooled_of.get(m) else tuple(a.room_ids)
        if outside.get(m) and a.room_ids:
            rooms = tuple(dict.fromkeys([*rooms, *outside[m]]))
        out.append((m, start, end, rooms, weeks))
    return out


async def persist_result(
    session: AsyncSession, run: ScheduleRun, result: sm.SolverResult, members: dict[int, list[int]]
) -> int:
    """Store ``result`` on ``run`` (one row per request and room set).  Returns the number of rows, or -1
    when the run was cancelled meanwhile (nothing is stored then: the cancel wins, review MINOR)."""
    from app.workers import run_jobs

    term = await session.get(Term, run.term_id)
    assert term is not None
    weeks_rows = (await session.execute(select(Week).where(Week.term_id == term.id))).scalars().all()
    await session.execute(delete(Assignment).where(Assignment.run_id == run.id, Assignment.origin == "SOLVER"))
    count = 0
    exam = run.kind == "EXAM"
    stats_in = dict(run.stats or {})
    outside = {int(k): [int(r) for r in v] for k, v in (stats_in.get("outside_pool_rooms") or {}).items()}
    merged_ids = {m for a in result.assignments for m in members.get(a.event_id, []) if len(members[a.event_id]) > 1}
    info = await _member_rows(session, exam, merged_ids)
    for a in result.assignments:
        if not a.room_ids and a.event_id in outside:
            # the planner's room outside the pool (kept, not checked by the solver)
            a = replace(a, room_ids=tuple(dict.fromkeys(outside[a.event_id])))
        for req_id, start, end, rooms, req_weeks in _member_placements(
            a, members.get(a.event_id, [a.event_id]), info, outside
        ):
            weeks = sorted(req_weeks)
            session.add(
                Assignment(
                    run_id=run.id,
                    meeting_request_id=None if exam else req_id,
                    exam_request_id=req_id if exam else None,
                    week=weeks[0] if len(weeks) == 1 else None,
                    weeks=weeks,
                    day=a.day,
                    date=a.date or (date_for(term, weeks[0], a.day, list(weeks_rows)) if len(weeks) == 1 else None),
                    start_period=start,
                    end_period=end,
                    room_ids=list(rooms),
                    origin="SOLVER",
                )
            )
            count += 1
    new_status = run_status(result)
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
        # solver event -> its requests where one event stands for several (joint lectures, exam cohorts);
        # diagnosis event ids are solver events, the data-issues report lists every request involved
        "event_members": {str(k): list(v) for k, v in members.items() if len(v) > 1},
    }
    diags = [asdict(d) for d in result.diagnoses] + bridge_diags
    # accepted exceptions of the whole run (solver, week segments and bridge) by cause; the best-effort
    # summary lists them instead of claiming that every placed class keeps every rule (review M3)
    from app.solver.diagnose import accepted_exceptions, partial_message

    unplaced_n = int(run.stats.get("unplaced") or 0) if run.stats.get("partial") else 0
    exceptions = accepted_exceptions(diags, unplaced_n)
    run.stats["accepted_exceptions"] = exceptions
    for d in diags:
        if d.get("code") == "partial" and (d.get("params") or {}).get("reason") != "timeout":
            placed_n = int(run.stats.get("placed") or 0)
            total_n = int(run.stats.get("events_total") or placed_n)
            if not any(x.get("code") == "internal" for x in diags):
                d["message"] = partial_message(placed_n, total_n, exceptions)
            d["params"] = {**(d.get("params") or {}), "exceptions": exceptions}
    # planner-facing report: unplaced classes first, then data errors, clashes, warnings; every
    # diagnosis carries a TR / EN text rendered from code + params (names, days, clock times; no ids)
    from app.services.data_issues import order_for_report, planner_text, text_context

    diags = order_for_report(diags)
    try:
        ctx = await text_context(session, run, diags, members)
        for d in diags:
            if d.get("code") == "input_conflict" and len(d.get("event_ids") or []) == 2:
                # the same course and section at one time: one lecture listed twice in the planner's list, not
                # an instructor / cohort clash (orchestrator: label it as such)
                ea, eb = (int(i) for i in d["event_ids"])
                la, lb = ctx.labels.get(ea), ctx.labels.get(eb)
                if la and lb and _course_code(la) == _course_code(lb) and _section(la) == _section(lb):
                    d["params"] = {**(d.get("params") or {}), "same_lecture": True}
            d["text"] = planner_text(d, ctx)
    except Exception:  # noqa: BLE001 - texts are a convenience; the structured diagnosis is the truth
        log.exception("planner texts for run %s failed", run.id)
        ctx = None
    overflows = [d for d in diags if d.get("code") == "trusted_lock_capacity" and (d.get("params") or {}).get("shared")]
    if overflows:
        run.stats["shared_room_overflows"] = [
            {
                "rooms": (d.get("params") or {}).get("room_codes"),
                "day": (d.get("params") or {}).get("day"),
                "period": (d.get("params") or {}).get("period"),
                "week": (d.get("params") or {}).get("week"),
                "size": (d.get("params") or {}).get("size"),
                "seats": (d.get("params") or {}).get("seats"),
                "exams": [ctx.labels.get(int(i), str(i)) for i in d.get("event_ids") or []] if ctx else [],
                "text": d.get("text"),
            }
            for d in overflows[:50]
        ]
    run.stats["warnings_by_code"] = dict(
        sorted(Counter(str(d.get("code") or "other") for d in diags if d.get("severity") != "error").items())
    )
    run.stats["errors_by_code"] = dict(
        sorted(Counter(str(d.get("code") or "other") for d in diags if d.get("severity") == "error").items())
    )
    run.diagnosis = await _humanize(session, diags)
    # the texts above query the DB (autoflush): re-assign so the in-place additions to stats are written
    run.stats = dict(run.stats)
    flag_modified(run, "stats")
    run.finished_at = datetime.now(UTC).replace(tzinfo=None)
    if not await run_jobs.commit_unless_cancelled(session, run, new_status):
        return -1
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


async def _finish_empty_scope(session: AsyncSession, run: ScheduleRun) -> None:
    """The run has nothing to schedule: FAILED with an ``empty_scope`` diagnosis naming what the term has."""
    from sqlalchemy import func

    from app.workers import run_jobs

    term = await session.get(Term, run.term_id)
    n_course = (
        await session.execute(
            select(func.count(MeetingRequest.id))
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == run.term_id, MeetingRequest.archived.is_(False))
        )
    ).scalar_one()
    n_exam = (
        await session.execute(
            select(func.count(ExamRequest.id)).where(
                ExamRequest.term_id == run.term_id, ExamRequest.archived.is_(False)
            )
        )
    ).scalar_one()
    code = term.code if term else str(run.term_id)
    other = "EXAM" if run.kind != "EXAM" else "COURSE"
    other_n = n_exam if run.kind != "EXAM" else n_course
    what = "exam" if run.kind == "EXAM" else "course"
    msg = f"nothing to schedule: term {code} has no {what} requests in this run's weeks"
    if other_n:
        msg += f" (it has {other_n} {other.lower()} requests: start a {other} run)"
    diag = _bridge_diag(
        [],
        msg,
        [f"start a {other} run" if other_n else "import the planning list first", "check the run's weeks"],
        "empty_scope",
        [],
        {"kind": run.kind, "course_requests": int(n_course), "exam_requests": int(n_exam)},
        severity="error",
    )
    other_tr = "sınav" if other == "EXAM" else "ders"
    tail_tr = f" ({other_n} {other_tr} talebi var: {other} çalışması başlatın)." if other_n else "."
    diag["text"] = {
        "tr": f"Planlanacak ders yok: {code} döneminde bu çalışmanın haftalarında "
        + ("sınav" if run.kind == "EXAM" else "ders")
        + " talebi yok"
        + tail_tr,
        "en": msg[0].upper() + msg[1:] + ".",
    }
    run.diagnosis = [diag]
    run.error = msg
    run.hard_score = None
    run.soft_score = None
    run.stats = {**(run.stats or {}), "events_total": 0, "placed": 0, "progress": 100, "phase": "done"}
    run.finished_at = datetime.now(UTC).replace(tzinfo=None)
    await run_jobs.commit_unless_cancelled(session, run, "FAILED")


def _studio_run(run: ScheduleRun) -> bool:
    """Only a server-sealed ``params.studio`` (studio.generate and its child runs) is honoured (review B3)."""
    from app.services.run_params import trusted_studio_snapshot

    return trusted_studio_snapshot(run) is not None


async def run_schedule(session_factory: Any, run_id: int, progress: ProgressFn | None = None) -> dict[str, Any]:
    """Job body for the queue: load + build (one session, committed and closed), solve off the event loop
    with no DB transaction open (review M7), persist in a fresh session. Cancellation and the wall-clock
    limit are handled by :mod:`app.workers.run_jobs` (review M6/M13)."""
    from app.workers import run_jobs

    def report(phase: str, pct: int) -> None:
        if progress:
            progress(phase, pct)

    async with session_factory() as session:
        run = await session.get(ScheduleRun, run_id)
        if run is None:
            raise ValueError(f"run {run_id} not found")
        if not await run_jobs.start_run(session, run):
            return await run_jobs.finish_cancelled(session_factory, run_id)
        run.stats = {**(run.stats or {}), "progress": 5, "phase": "loading", "worker": worker_id()}
        await session.commit()
        report("loading", 5)
        rparams = dict(run.params or {})
        if _studio_run(run):
            # studio runs and their children keep the draft's exclusions / pins / disabled built-ins
            from app.services.studio import build_solver_input_for_run

            inp, members = await build_solver_input_for_run(session, run)
        else:
            inp, members = await build_solver_input(session, run)
        if not inp.events:
            # nothing in scope (a COURSE run on an exam term, a week without classes ...): a clear message,
            # never "hard 100 with 0 events" (review MINOR)
            await _finish_empty_scope(session, run)
            return {"status": "FAILED", "assignments": 0, "solver": None}
        await session.commit()  # bridge stats are kept on the row; no transaction stays open during the solve
    report("building", 15)
    choice = str(rparams.get("solver", "auto"))
    solver_mod = _solver_fn(choice).__module__
    report("solving", 20)
    # CP-SAT holds the CPU for up to time_limit_s: solve in a worker thread so the event loop (health
    # checks, the UI, SSE progress) keeps running; ``progress`` is thread-safe (see workers.queue)
    try:
        result = await run_jobs.solve_off_loop(
            run_id,
            float(inp.time_limit_s),
            _call_solver,
            inp,
            lambda ph, pct: report(ph, 20 + int(pct * 0.7)),
            choice,
            split_weeks=run_mode(rparams, "split_blocked_weeks"),
        )
    except run_jobs.RunCancelled:
        return await run_jobs.finish_cancelled(session_factory, run_id)
    report("persisting", 92)
    async with session_factory() as session:
        run = await session.get(ScheduleRun, run_id)
        if run is None:
            raise ValueError(f"run {run_id} was deleted while solving")
        if run.status == "CANCELLED":
            return {"status": "CANCELLED"}
        result.stats = {
            **result.stats,
            "solver": solver_mod,
            "events": result.stats.get("events", len(inp.events)),
            "rooms": result.stats.get("rooms", len(inp.rooms)),
        }
        n = await persist_result(session, run, result, members)
        if n < 0:
            return {"status": "CANCELLED"}
    report("done", 100)
    return {"status": run_status(result), "assignments": n, "solver": solver_mod}
