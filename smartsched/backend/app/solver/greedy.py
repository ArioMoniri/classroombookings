"""Greedy constructive heuristic used as a CP-SAT hint (warm start).

Events are placed in a fixed order (locked → fixed-time by size desc → flexible by number of
options asc) into the free (time, room) option with the smallest soft cost (preferred room rank,
preferred building, capacity waste, previous assignment).  The result may be partial; whatever is
placed is hinted so CP-SAT starts from a good incumbent instead of searching for its first
solution.  Pure Python, O(events × options).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from app.solver.build import Prepared, hint_assignments
from app.solver.domains import (
    EventDomain,
    TimeOption,
    effective_capacity,
    is_input_fixed,
    shares_room,
    sharing_capacity,
    weeks_intersect,
)
from app.solver.model import Assignment, Event, Room
from app.solver.seats import seat_target
from app.solver.weights import CAPACITY_WASTE_UNIT, base_weight


class _Occupancy:
    def __init__(self, rooms_by_id: dict[int, Room]) -> None:
        self.rooms_by_id = rooms_by_id
        # (room, day, period) -> [(weeks, seats or None for exclusive use)]
        self.room: dict[tuple[int, int, int], list[tuple[frozenset[int], int | None]]] = defaultdict(list)
        self.key: dict[tuple[str, int, int], list[frozenset[int]]] = defaultdict(list)

    def room_free(self, rid: int, t: TimeOption, weeks: frozenset[int]) -> bool:
        return all(not weeks_intersect(w, weeks) for p in t.periods for w, _ in self.room.get((rid, t.day, p), ()))

    def free_seats(self, rid: int, t: TimeOption, event: Event) -> int:
        """Seats a sharing event can still take in ``rid`` at ``t`` (0 if an exclusive user is there)."""
        cap = sharing_capacity(self.rooms_by_id[rid], [event])
        free = cap
        for p in t.periods:
            entries = [(w, s) for w, s in self.room.get((rid, t.day, p), ()) if weeks_intersect(w, event.weeks)]
            if any(s is None for _, s in entries):
                return 0
            for wk in event.weeks:
                used = sum(s or 0 for w, s in entries if wk in w)
                free = min(free, cap - used)
        return max(0, free)

    def keys_free(self, keys: frozenset[str], t: TimeOption, weeks: frozenset[int]) -> bool:
        return all(
            not weeks_intersect(w, weeks) for k in keys for p in t.periods for w in self.key.get((k, t.day, p), ())
        )

    def take(self, event: Event, t: TimeOption, rooms: list[int], seats: dict[int, int] | None = None) -> None:
        for p in t.periods:
            for rid in rooms:
                self.room[(rid, t.day, p)].append((event.weeks, None if seats is None else seats.get(rid, 0)))
            for k in event.cohort_keys | event.instructor_keys:
                self.key[(k, t.day, p)].append(event.weeks)


def _room_cost(event: Event, room: Room, weights: Mapping[str, int] | None = None) -> int:
    """The objective's per-room soft cost (same weights as the model: ``SolverInput.weights`` over
    ``weights.DEFAULT_WEIGHTS``), so the warm start already follows the calibrated preferences."""
    w = weights or {}
    cost = 0
    if event.preferred_room_ids:
        cost += base_weight(w, "room_preference") * (
            event.preferred_room_ids.index(room.id)
            if room.id in event.preferred_room_ids
            else len(event.preferred_room_ids)
        )
    if event.preferred_building and room.building != event.preferred_building:
        cost += base_weight(w, "building_preference")
    cost += base_weight(w, "min_capacity_waste") * (
        max(0, effective_capacity(room, event) - event.size) // CAPACITY_WASTE_UNIT
    )
    return cost


def _preferred_set(e: Event, dom: EventDomain, t: TimeOption) -> list[int]:
    """The event's preferred rooms usable at ``t`` as one room set: the first preferred room, or (for a
    multi-room event) the leading preferred rooms up to ``max_rooms`` until they seat the group."""
    allowed = [r for r in e.preferred_room_ids if r in dom.rooms and dom.is_pair_allowed(t, r)]
    if not allowed:
        return []
    if e.max_rooms <= 1:
        return allowed[:1]
    return allowed[: max(1, e.max_rooms)]


def _order(prep: Prepared) -> list[EventDomain]:
    doms = [prep.doms.domain(e.id) for e in prep.inp.events]

    def key(d: EventDomain) -> tuple[int, int, int]:
        locked = 0 if d.event.locked is not None else 1
        fixed = 0 if d.fixed_time else 1
        return (locked, fixed, -d.event.size if d.fixed_time else d.option_count())

    return sorted(doms, key=key)


def greedy_assignments(prep: Prepared) -> list[Assignment]:
    inp = prep.inp
    rooms_by_id = prep.doms.rooms_by_id
    occ = _Occupancy(rooms_by_id)
    previous = {a.event_id: a for a in hint_assignments(inp)}
    waive = inp.fixed_conflicts_as_warnings
    out: list[Assignment] = []
    order = _order(prep)
    done: set[int] = set()

    def place(dom: EventDomain) -> None:
        e = dom.event
        prev = previous.get(e.id)
        times = list(dom.times)
        if prev is not None:
            times.sort(key=lambda t: 0 if (t.day, t.start) == (prev.day, prev.start) else 1)
        # fixed requests whose key clashes are waived input conflicts keep their time regardless
        check_keys = not (waive and dom.fixed_time and is_input_fixed(e, prep.doms.soft))
        sharing = shares_room(e)
        for t in times:
            if check_keys and not occ.keys_free(e.cohort_keys | e.instructor_keys, t, e.weeks):
                continue
            if not e.needs_room:
                out.append(Assignment(e.id, t.day, t.start, t.end, (), e.weeks, e.fixed_date))
                occ.take(e, t, [])
                return
            picked = _pick_rooms(e, t, dom, occ, prev, sharing, inp.weights)
            if picked is None:
                continue
            chosen, seats = picked
            out.append(Assignment(e.id, t.day, t.start, t.end, tuple(sorted(chosen)), e.weeks, e.fixed_date))
            occ.take(e, t, chosen, seats)
            return

    # 1) the planner's locks
    for dom in order:
        if dom.event.locked is not None:
            place(dom)
            done.add(dom.event.id)
    # 2) preference pass: fixed-time events whose preferred room set (the planner's room when definitive
    #    rooms are hints) is still free take it before anybody else can, largest groups first
    for dom in order:
        e = dom.event
        if e.id in done or not dom.fixed_time or not e.needs_room or not e.preferred_room_ids:
            continue
        if shares_room(e) or e.id in previous:
            continue
        t = dom.times[0]
        check_keys = not (waive and is_input_fixed(e, prep.doms.soft))
        if check_keys and not occ.keys_free(e.cohort_keys | e.instructor_keys, t, e.weeks):
            continue
        want = _preferred_set(e, dom, t)
        if not want or not all(occ.room_free(r, t, e.weeks) for r in want):
            continue
        if sum(effective_capacity(rooms_by_id[r], e) for r in want) < e.size:
            continue
        out.append(Assignment(e.id, t.day, t.start, t.end, tuple(sorted(want)), e.weeks, e.fixed_date))
        occ.take(e, t, want)
        done.add(e.id)
    # 3) everything else: fixed-time by size, then flexible by number of options
    for dom in order:
        if dom.event.id not in done:
            place(dom)
    return out


def _pick_rooms(
    e: Event,
    t: TimeOption,
    dom: EventDomain,
    occ: _Occupancy,
    prev: Assignment | None,
    sharing: bool,
    weights: Mapping[str, int] | None = None,
) -> tuple[list[int], dict[int, int] | None] | None:
    rooms_by_id = occ.rooms_by_id
    allowed = [r for r in dom.rooms if dom.is_pair_allowed(t, r)]
    locked = e.locked.room_ids if e.locked is not None else ()
    if sharing:
        free = {r: occ.free_seats(r, t, e) for r in allowed}
        if locked:
            target = seat_target(e, locked, rooms_by_id)
            if sum(free.get(r, 0) for r in locked) < target or any(free.get(r, 0) < 1 for r in locked):
                return None
            seats = _fill(target, [(r, free[r]) for r in locked])
            return list(locked), seats
        if e.max_rooms <= 1:
            fits = [rooms_by_id[r] for r in allowed if free[r] >= min(e.size, effective_capacity(rooms_by_id[r], e))]
            if not fits:
                return None
            best = min(
                fits, key=lambda r: (0 if prev and r.id in prev.room_ids else 1, _room_cost(e, r, weights), r.id)
            )
            return [best.id], {best.id: min(e.size, effective_capacity(best, e))}
        prefs = {r: i for i, r in enumerate(e.preferred_room_ids)}
        order = sorted(
            (r for r in allowed if free[r] > 0),
            key=lambda r: (0 if prev and r in prev.room_ids else 1, prefs.get(r, len(prefs)), -free[r], r),
        )
        chosen: list[int] = []
        total = 0
        for r in order:
            if len(chosen) >= e.max_rooms or total >= e.size:
                break
            chosen.append(r)
            total += free[r]
        if total < e.size or len(chosen) < max(1, e.min_rooms):
            return None
        return chosen, _fill(e.size, [(r, free[r]) for r in chosen])
    free_rooms = [rooms_by_id[r] for r in allowed if occ.room_free(r, t, e.weeks)]
    if locked:
        return (list(locked), None) if all(rooms_by_id[r] in free_rooms for r in locked) else None
    if not free_rooms:
        return None
    if e.max_rooms <= 1:
        best = min(
            free_rooms, key=lambda r: (0 if prev and r.id in prev.room_ids else 1, _room_cost(e, r, weights), r.id)
        )
        return [best.id], None
    prefs_m = {r: i for i, r in enumerate(e.preferred_room_ids)}
    free_rooms.sort(
        key=lambda r: (
            0 if prev and r.id in prev.room_ids else 1,
            prefs_m.get(r.id, len(prefs_m)),
            -effective_capacity(r, e),
        )
    )
    chosen = []
    total = 0
    for r in free_rooms:
        if len(chosen) >= e.max_rooms:
            break
        chosen.append(r.id)
        total += effective_capacity(r, e)
        if total >= e.size and len(chosen) >= e.min_rooms:
            break
    if total < e.size or len(chosen) < e.min_rooms:
        return None
    return chosen, None


def _fill(target: int, rooms: list[tuple[int, int]]) -> dict[int, int]:
    """Seats per room: one each first, then fill in order (deterministic)."""
    seats = {r: min(1, f) for r, f in rooms}
    rest = target - sum(seats.values())
    for r, f in rooms:
        add = max(0, min(rest, f - seats[r]))
        seats[r] += add
        rest -= add
    return seats


def prefer_rooms(prep: Prepared, assignments: list[Assignment]) -> list[Assignment]:
    """Local repair of a hint (e.g. the slack relaxation's placement, which ignores soft terms): every
    placed single-room / multi-room event that is not in its preferred room set moves there when that
    set is free at its time in every week (largest groups first, locks never move).  Exclusive room use
    only — room-sharing events are left alone.  The caller validates the result."""
    inp = prep.inp
    doms = prep.doms
    rooms_by_id = doms.rooms_by_id
    by_id = {a.event_id: a for a in assignments}
    occ: dict[tuple[int, int, int], list[tuple[int, frozenset[int]]]] = defaultdict(list)
    for a in assignments:
        for r in a.room_ids:
            for p in range(a.start, a.end + 1):
                occ[(r, a.day, p)].append((a.event_id, a.weeks))
    events = sorted((e for e in inp.events if e.id in by_id), key=lambda e: (-e.size, e.id))
    for e in events:
        a = by_id[e.id]
        if e.locked is not None or not e.needs_room or not e.preferred_room_ids or shares_room(e):
            continue
        dom = doms.domain(e.id)
        t = TimeOption(a.day, a.start, a.end - a.start + 1)
        want = _preferred_set(e, dom, t)
        if not want or set(want) == set(a.room_ids):
            continue
        if sum(effective_capacity(rooms_by_id[r], e) for r in want) < e.size:
            continue
        busy = any(
            other != e.id and weeks_intersect(w, a.weeks)
            for r in want
            for p in t.periods
            for other, w in occ.get((r, t.day, p), ())
        )
        if busy:
            continue
        for r in a.room_ids:
            for p in t.periods:
                occ[(r, t.day, p)] = [x for x in occ[(r, t.day, p)] if x[0] != e.id]
        for r in want:
            for p in t.periods:
                occ[(r, t.day, p)].append((e.id, a.weeks))
        by_id[e.id] = Assignment(e.id, a.day, a.start, a.end, tuple(sorted(want)), a.weeks, a.date)
    return [by_id[a.event_id] for a in assignments]


__all__ = ["greedy_assignments", "prefer_rooms"]
