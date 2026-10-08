"""Greedy constructive heuristic used as a CP-SAT hint (warm start).

Events are placed in a fixed order (locked → fixed-time by size desc → flexible by number of
options asc) into the free (time, room) option with the smallest soft cost (preferred room rank,
preferred building, capacity waste, previous assignment).  The result may be partial; whatever is
placed is hinted so CP-SAT starts from a good incumbent instead of searching for its first
solution.  Pure Python, O(events × options).
"""

from __future__ import annotations

from collections import defaultdict

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


def _room_cost(event: Event, room: Room) -> int:
    cost = 0
    if event.preferred_room_ids:
        cost += 10 * (
            event.preferred_room_ids.index(room.id)
            if room.id in event.preferred_room_ids
            else len(event.preferred_room_ids)
        )
    if event.preferred_building and room.building != event.preferred_building:
        cost += 5
    cost += max(0, effective_capacity(room, event) - event.size) // 10
    return cost


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
    for dom in _order(prep):
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
                break
            picked = _pick_rooms(e, t, dom, occ, prev, sharing)
            if picked is None:
                continue
            chosen, seats = picked
            out.append(Assignment(e.id, t.day, t.start, t.end, tuple(sorted(chosen)), e.weeks, e.fixed_date))
            occ.take(e, t, chosen, seats)
            break
    return out


def _pick_rooms(
    e: Event, t: TimeOption, dom: EventDomain, occ: _Occupancy, prev: Assignment | None, sharing: bool
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
            best = min(fits, key=lambda r: (0 if prev and r.id in prev.room_ids else 1, _room_cost(e, r), r.id))
            return [best.id], {best.id: min(e.size, effective_capacity(best, e))}
        order = sorted(
            (r for r in allowed if free[r] > 0),
            key=lambda r: (0 if prev and r in prev.room_ids else 1, -free[r], r),
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
        best = min(free_rooms, key=lambda r: (0 if prev and r.id in prev.room_ids else 1, _room_cost(e, r), r.id))
        return [best.id], None
    free_rooms.sort(key=lambda r: (0 if prev and r.id in prev.room_ids else 1, -effective_capacity(r, e)))
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


__all__ = ["greedy_assignments"]
