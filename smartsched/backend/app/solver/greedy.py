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
from app.solver.domains import EventDomain, TimeOption, effective_capacity, weeks_intersect
from app.solver.model import Assignment, Event, Room


class _Occupancy:
    def __init__(self) -> None:
        self.room: dict[tuple[int, int, int], list[frozenset[int]]] = defaultdict(list)
        self.key: dict[tuple[str, int, int], list[frozenset[int]]] = defaultdict(list)

    def room_free(self, rid: int, t: TimeOption, weeks: frozenset[int]) -> bool:
        return all(not weeks_intersect(w, weeks) for p in t.periods for w in self.room.get((rid, t.day, p), ()))

    def keys_free(self, keys: frozenset[str], t: TimeOption, weeks: frozenset[int]) -> bool:
        return all(
            not weeks_intersect(w, weeks) for k in keys for p in t.periods for w in self.key.get((k, t.day, p), ())
        )

    def take(self, event: Event, t: TimeOption, rooms: list[int]) -> None:
        for p in t.periods:
            for rid in rooms:
                self.room[(rid, t.day, p)].append(event.weeks)
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
    occ = _Occupancy()
    previous = {a.event_id: a for a in hint_assignments(inp)}
    out: list[Assignment] = []
    for dom in _order(prep):
        e = dom.event
        prev = previous.get(e.id)
        times = list(dom.times)
        if prev is not None:
            times.sort(key=lambda t: 0 if (t.day, t.start) == (prev.day, prev.start) else 1)
        placed = False
        for t in times:
            if not occ.keys_free(e.cohort_keys | e.instructor_keys, t, e.weeks):
                continue
            if not e.needs_room:
                out.append(Assignment(e.id, t.day, t.start, t.end, (), e.weeks, e.fixed_date))
                occ.take(e, t, [])
                placed = True
                break
            free = [rooms_by_id[r] for r in dom.rooms if dom.is_pair_allowed(t, r) and occ.room_free(r, t, e.weeks)]
            if not free:
                continue
            chosen: list[int] = []
            if e.max_rooms <= 1:
                best = min(free, key=lambda r: (0 if prev and r.id in prev.room_ids else 1, _room_cost(e, r), r.id))
                chosen = [best.id]
            else:
                free.sort(key=lambda r: (0 if prev and r.id in prev.room_ids else 1, -effective_capacity(r, e)))
                total = 0
                for r in free:
                    if len(chosen) >= e.max_rooms:
                        break
                    chosen.append(r.id)
                    total += effective_capacity(r, e)
                    if total >= e.size and len(chosen) >= e.min_rooms:
                        break
                if total < e.size or len(chosen) < e.min_rooms:
                    continue
            out.append(Assignment(e.id, t.day, t.start, t.end, tuple(sorted(chosen)), e.weeks, e.fixed_date))
            occ.take(e, t, chosen)
            placed = True
            break
        if not placed:
            continue
    return out


__all__ = ["greedy_assignments"]
