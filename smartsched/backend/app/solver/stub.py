"""Greedy first-fit fallback solver.

Used until ``app.solver.cpsat`` exists. Honours fixed day/time, capacity, tags, pins, blocks, locked
assignments and overlap constraints (room / cohort / instructor); returns FEASIBLE or INFEASIBLE with
per-event diagnoses. Deterministic (no randomness).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from app.solver.model import Assignment, Block, Diagnosis, Event, Room, SolverInput, SolverResult

Slot = tuple[int, int, int]  # (week, day, period)


@dataclass
class _State:
    room_busy: set[tuple[int, int, int, int]] = field(default_factory=set)  # room, week, day, period
    key_busy: set[tuple[str, int, int, int]] = field(default_factory=set)  # cohort/instructor key, week, day, period
    closed: set[tuple[int, int | None, int, int]] = field(default_factory=set)  # room, week|None, day, period


def _periods(start: int, duration: int) -> range:
    return range(start, start + duration)


def _room_fits(room: Room, ev: Event) -> bool:
    cap = room.exam_capacity if ev.kind == "exam" and room.exam_capacity > 0 else room.capacity
    if ev.required_room_ids and room.id not in ev.required_room_ids:
        return False
    if room.id in ev.forbidden_room_ids:
        return False
    if ev.required_tags and not ev.required_tags <= room.tags:
        return False
    if ev.forbidden_tags & room.tags:
        return False
    return cap >= ev.size or (ev.max_rooms > 1)


def _room_free(st: _State, room_id: int, weeks: Iterable[int], day: int, periods: range) -> bool:
    for w in weeks:
        for p in periods:
            if (room_id, w, day, p) in st.room_busy:
                return False
            if (room_id, w, day, p) in st.closed or (room_id, None, day, p) in st.closed:
                return False
    return True


def _keys_free(st: _State, keys: Iterable[str], weeks: Iterable[int], day: int, periods: range) -> bool:
    return not any((k, w, day, p) in st.key_busy for k in keys for w in weeks for p in periods)


def _occupy(st: _State, ev: Event, a: Assignment) -> None:
    for w in a.weeks:
        for p in range(a.start, a.end + 1):
            for r in a.room_ids:
                st.room_busy.add((r, w, a.day, p))
            for k in ev.cohort_keys | ev.instructor_keys:
                st.key_busy.add((k, w, a.day, p))


def _capacity(room: Room, ev: Event) -> int:
    return room.exam_capacity if ev.kind == "exam" and room.exam_capacity > 0 else room.capacity


def _candidate_slots(ev: Event, inp: SolverInput) -> list[tuple[int, int]]:
    days = [ev.fixed_day] if ev.fixed_day else sorted(ev.allowed_days or inp.days)
    if ev.fixed_start:
        starts = [ev.fixed_start]
    else:
        starts = list(range(ev.earliest_start, min(ev.latest_end, inp.periods_per_day) - ev.duration + 2))
    return [(d, s) for d in days for s in starts if s >= 1 and s + ev.duration - 1 <= inp.periods_per_day]


def _pick_rooms(
    ev: Event, rooms: list[Room], st: _State, day: int, start: int, previous: dict[int, Assignment]
) -> tuple[int, ...] | None:
    periods = _periods(start, ev.duration)
    usable = [r for r in rooms if _room_fits(r, ev) and _room_free(st, r.id, ev.weeks, day, periods)]
    if not usable:
        return None
    prev = previous.get(ev.id)

    def rank(r: Room) -> tuple[int, int, int, int]:
        pref = ev.preferred_room_ids.index(r.id) if r.id in ev.preferred_room_ids else len(ev.preferred_room_ids)
        stable = 0 if prev and r.id in prev.room_ids else 1
        bld = 0 if ev.preferred_building and r.building == ev.preferred_building else 1
        return (stable, pref, bld, max(_capacity(r, ev) - ev.size, 0))

    singles = sorted((r for r in usable if _capacity(r, ev) >= ev.size), key=rank)
    if singles and ev.min_rooms <= 1:
        return (singles[0].id,)
    if ev.max_rooms > 1:  # split across several rooms (exams): largest first
        chosen: list[Room] = []
        total = 0
        for r in sorted(usable, key=lambda r: (-_capacity(r, ev), rank(r))):
            chosen.append(r)
            total += _capacity(r, ev)
            if total >= ev.size and len(chosen) >= ev.min_rooms:
                return tuple(r.id for r in chosen)
            if len(chosen) >= ev.max_rooms:
                break
    return None


def solve(inp: SolverInput, progress: Callable[[str, int], None] | None = None) -> SolverResult:
    st = _State()
    for b in inp.blocks:
        for p in range(b.start, b.end + 1):
            st.closed.add((b.room_id, b.week, b.day, p))
    for c in inp.constraints:
        if c.kind == "room_closed" and c.hard:
            room_id = int(c.params.get("room_id", 0))
            day = int(c.params.get("day", 0))
            periods = c.params.get("periods") or range(1, inp.periods_per_day + 1)
            weeks = c.params.get("weeks") or [None]
            for w in weeks:
                for p in periods:
                    st.closed.add((room_id, w, day, int(p)))
    rooms = sorted(inp.rooms, key=lambda r: (r.capacity, r.id))
    previous = {a.event_id: a for a in inp.previous}
    assignments: list[Assignment] = []
    diagnoses: list[Diagnosis] = []
    pref_hits = 0
    pref_total = 0

    def order(ev: Event) -> tuple[int, int, int]:
        return (0 if ev.locked else 1, 0 if ev.fixed_day and ev.fixed_start else 1, -ev.size)

    events = sorted((e for e in inp.events if e.needs_room), key=order)
    total = len(events) or 1
    for i, ev in enumerate(events):
        if progress and i % 50 == 0:
            progress("solving", 10 + int(80 * i / total))
        if ev.locked:
            a = Assignment(
                ev.id,
                ev.locked.day,
                ev.locked.start,
                ev.locked.end,
                ev.locked.room_ids,
                ev.locked.weeks or ev.weeks,
                ev.locked.date or ev.fixed_date,
            )
            assignments.append(a)
            _occupy(st, ev, a)
            continue
        placed: Assignment | None = None
        for day, start in _candidate_slots(ev, inp):
            periods = _periods(start, ev.duration)
            if not _keys_free(st, ev.cohort_keys | ev.instructor_keys, ev.weeks, day, periods):
                continue
            room_ids = _pick_rooms(ev, rooms, st, day, start, previous)
            if room_ids is None:
                continue
            placed = Assignment(ev.id, day, start, start + ev.duration - 1, room_ids, ev.weeks, ev.fixed_date)
            break
        if placed is None:
            diagnoses.append(_diagnose(ev, rooms, st, inp))
            continue
        assignments.append(placed)
        _occupy(st, ev, placed)
        if ev.preferred_room_ids or ev.preferred_building:
            pref_total += 1
            if (placed.room_ids and placed.room_ids[0] in ev.preferred_room_ids) or any(
                r.id in placed.room_ids and r.building == ev.preferred_building for r in rooms
            ):
                pref_hits += 1
    if progress:
        progress("done", 100)
    unassigned = len(events) - len(assignments)
    hard = int(round(100 * len(assignments) / total))
    soft = 100 if pref_total == 0 else int(round(100 * pref_hits / pref_total))
    return SolverResult(
        status="FEASIBLE" if unassigned == 0 else "INFEASIBLE",
        assignments=assignments,
        hard_score=hard,
        soft_score=soft,
        objective_breakdown={"unassigned": unassigned, "preference_miss": pref_total - pref_hits},
        diagnoses=diagnoses,
        stats={"solver": "stub-greedy", "events": len(events), "rooms": len(rooms), "assigned": len(assignments)},
    )


def _diagnose(ev: Event, rooms: list[Room], st: _State, inp: SolverInput) -> Diagnosis:
    fitting = [r for r in rooms if _room_fits(r, ev) and _capacity(r, ev) >= ev.size]
    kinds: list[str] = []
    suggestions: list[str] = []
    if not fitting:
        kinds.append("capacity")
        biggest = max((_capacity(r, ev) for r in rooms if _room_fits(r, ev)), default=0)
        suggestions.append(f"largest eligible room has {biggest} seats; split the cohort or allow multi-room")
        if ev.required_tags:
            kinds.append("room_tags")
            suggestions.append(f"relax required tags {sorted(ev.required_tags)}")
        if ev.required_room_ids:
            kinds.append("room_pin")
            suggestions.append("release the room pin")
    else:
        kinds.append("no_room_overlap")
        if ev.fixed_day and ev.fixed_start:
            kinds.append("fixed_time")
            suggestions.append(
                f"move away from day {ev.fixed_day} P{ev.fixed_start}-P{ev.fixed_start + ev.duration - 1} or free one of {[r.code for r in fitting[:3]]}"
            )
        else:
            suggestions.append("widen allowed days/periods")
        if ev.cohort_keys or ev.instructor_keys:
            kinds.append("no_cohort_overlap")
    return Diagnosis(
        event_ids=[ev.id],
        constraint_kinds=kinds,
        message=f"{ev.label} ({ev.size} seats, {ev.duration} periods) could not be placed",
        suggestions=suggestions,
        severity="hard",
    )
