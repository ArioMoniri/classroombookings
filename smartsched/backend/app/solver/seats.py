"""Seat budgets of shared rooms (``Event.share_room``), incl. split (multi-room) exams.

Rule (README "Shared exam rooms"): an event that shares rooms needs ``target = min(size, Σ seats of
its rooms)`` seats in total (``min`` only bites for a trusted, planner-locked room set that is too
small: such an event fills its rooms).  A single-room event puts all of them in its room.  A split
event may divide its students over its rooms *in any way* (at least one seat per room it uses); a set
of sharing events in a room-period is valid iff some allocation gives every event its target and no
room more than its seat budget (exam capacity when an exam is involved).  CP-SAT models the
allocation with one integer ``seats[e, r]`` per (split event, room) — constant over the event's
duration — inside one ``Cumulative`` per room; :func:`seat_conflicts` checks a finished timetable
per (day, period, week) with a max-flow (Gale/Hall condition) and, where a split exam meets different
neighbours in different periods, with one constant split over its whole duration, so ``validate`` accepts
exactly the timetables for which such an allocation exists.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping

from app.solver.domains import effective_capacity, shares_room, sharing_capacity
from app.solver.model import Assignment, Event, Room, SolverInput


def seat_target(event: Event, room_ids: Iterable[int], rooms_by_id: Mapping[int, Room]) -> int:
    caps = sum(effective_capacity(rooms_by_id[r], event) for r in room_ids if r in rooms_by_id)
    return max(0, min(event.size, caps))


def proportional_allocation(event: Event, room_ids: Iterable[int], rooms_by_id: Mapping[int, Room]) -> dict[int, int]:
    """Deterministic allocation used for hints and reports: proportional to capacity, largest
    remainder first (ties by room id), at least one seat per used room when possible."""
    rooms = sorted(r for r in room_ids if r in rooms_by_id)
    caps = {r: effective_capacity(rooms_by_id[r], event) for r in rooms}
    total = sum(caps.values())
    target = seat_target(event, rooms, rooms_by_id)
    if not rooms or total <= 0:
        return {r: 0 for r in rooms}
    alloc = {r: (target * caps[r]) // total for r in rooms}
    rest = target - sum(alloc.values())
    order = sorted(rooms, key=lambda r: (-((target * caps[r]) % total), r))
    for r in order:
        if rest <= 0:
            break
        if alloc[r] < caps[r]:
            alloc[r] += 1
            rest -= 1
    return alloc


def seats_feasible(demands: Mapping[int, int], rooms_of: Mapping[int, Iterable[int]], caps: Mapping[int, int]) -> bool:
    """Is there an allocation ``x[e, r] >= 0`` (``r`` in ``rooms_of[e]``) with ``Σ_r x = demand[e]`` and
    ``Σ_e x <= caps[r]``?  Max-flow source -> events -> rooms -> sink (graphs here are tiny)."""
    need = sum(demands.values())
    if need <= 0:
        return True
    cap: dict[tuple[str, str], int] = defaultdict(int)
    adj: dict[str, set[str]] = defaultdict(set)

    def edge(u: str, v: str, c: int) -> None:
        cap[(u, v)] += c
        adj[u].add(v)
        adj[v].add(u)

    for e, d in demands.items():
        edge("s", f"e{e}", d)
        for r in rooms_of[e]:
            edge(f"e{e}", f"r{r}", d)
    for r, c in caps.items():
        edge(f"r{r}", "t", max(0, c))
    flow = 0
    while True:
        parent: dict[str, str] = {"s": "s"}
        q: deque[str] = deque(["s"])
        while q and "t" not in parent:
            u = q.popleft()
            for v in sorted(adj[u]):
                if v not in parent and cap[(u, v)] > 0:
                    parent[v] = u
                    q.append(v)
        if "t" not in parent:
            break
        path: list[tuple[str, str]] = []
        v = "t"
        while v != "s":
            path.append((parent[v], v))
            v = parent[v]
        push = min(cap[e] for e in path)
        for u, v in path:
            cap[(u, v)] -= push
            cap[(v, u)] += push
        flow += push
    return flow >= need


def seat_conflicts(
    inp: SolverInput,
    events_by_id: Mapping[int, Event],
    rooms_by_id: Mapping[int, Room],
    assignments: Mapping[int, Assignment],
) -> list[tuple[tuple[int, ...], tuple[int, ...], int, int, int]]:
    """Over-full shared room groups: ``(event ids, room ids, day, period, week)``, one entry per
    distinct (events, rooms) group (first slot where it happens)."""
    horizon = set(inp.weeks)
    slots: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for eid, a in assignments.items():
        e = events_by_id.get(eid)
        if e is None or not shares_room(e) or not a.room_ids:
            continue
        for w in sorted(e.weeks & horizon) or sorted(e.weeks):
            for p in range(a.start, a.end + 1):
                slots[(a.day, p, w)].append(eid)
    out: list[tuple[tuple[int, ...], tuple[int, ...], int, int, int]] = []
    seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    for (day, p, w), eids in sorted(slots.items()):
        if len(eids) < 2:
            continue
        for comp in _components(eids, assignments):
            if len(comp) < 2:
                continue
            events = [events_by_id[i] for i in comp]
            room_ids = sorted({r for i in comp for r in assignments[i].room_ids if r in rooms_by_id})
            caps = {r: sharing_capacity(rooms_by_id[r], events) for r in room_ids}
            demands = {i: seat_target(events_by_id[i], assignments[i].room_ids, rooms_by_id) for i in comp}
            rooms_of = {i: [r for r in assignments[i].room_ids if r in rooms_by_id] for i in comp}
            if seats_feasible(demands, rooms_of, caps):
                continue
            key = (tuple(sorted(comp)), tuple(room_ids))
            if key in seen:
                continue
            seen.add(key)
            out.append((key[0], key[1], day, p, w))
    out.extend(_fixed_split_conflicts(inp, events_by_id, rooms_by_id, assignments, slots, seen))
    return out


#: memo of the fixed-split checks (component signature -> feasible); evaluate() runs them many times
_FIXED_SPLIT_CACHE: dict[tuple[object, ...], bool] = {}


def _fixed_split_conflicts(
    inp: SolverInput,
    events_by_id: Mapping[int, Event],
    rooms_by_id: Mapping[int, Room],
    assignments: Mapping[int, Assignment],
    slots: Mapping[tuple[int, int, int], list[int]],
    seen: set[tuple[tuple[int, ...], tuple[int, ...]]],
) -> list[tuple[tuple[int, ...], tuple[int, ...], int, int, int]]:
    """The CP model gives a split exam **one** seat split for its whole duration (``seats[e, r]`` is constant);
    a per-period max-flow would also accept a timetable that needs a different split in different periods
    (another exam enters one of its rooms half-way).  For every (day, week) component in which a split
    sharing event meets different neighbours in different periods, check that one constant split fits every
    period (a tiny CP-SAT feasibility model, memoised)."""
    out: list[tuple[tuple[int, ...], tuple[int, ...], int, int, int]] = []
    by_dw: dict[tuple[int, int], dict[int, list[int]]] = defaultdict(dict)
    for (day, p, w), eids in slots.items():
        by_dw[(day, w)][p] = eids
    for (day, w), per_period in sorted(by_dw.items()):
        split = {
            e
            for eids in per_period.values()
            for e in eids
            if len([r for r in assignments[e].room_ids if r in rooms_by_id]) > 1
        }
        if not split:
            continue
        # components over (shared rooms) x (overlapping periods)
        parent: dict[int, int] = {}
        for eids in per_period.values():
            for comp in _components(eids, assignments):
                for other in comp:
                    _union(parent, comp[0], other)
        comps: dict[int, set[int]] = defaultdict(set)
        for e in list(parent):
            comps[_find(parent, e)].add(e)
        for comp_set in comps.values():
            if len(comp_set) < 2 or not comp_set & split:
                continue
            periods = sorted(p for p, eids in per_period.items() if set(eids) & comp_set)
            present = {p: sorted(set(per_period[p]) & comp_set) for p in periods}
            if all(present[p] == present[periods[0]] for p in periods):
                continue  # the same events in every period: the per-period flow already decides it
            events = [events_by_id[i] for i in sorted(comp_set)]
            room_ids = sorted({r for i in comp_set for r in assignments[i].room_ids if r in rooms_by_id})
            caps = {r: sharing_capacity(rooms_by_id[r], events) for r in room_ids}
            rooms_of = {i: tuple(r for r in assignments[i].room_ids if r in rooms_by_id) for i in sorted(comp_set)}
            demands = {i: seat_target(events_by_id[i], rooms_of[i], rooms_by_id) for i in sorted(comp_set)}
            sig = (
                tuple(sorted(demands.items())),
                tuple(sorted(rooms_of.items())),
                tuple(sorted(caps.items())),
                tuple((p, tuple(present[p])) for p in periods),
            )
            ok = _FIXED_SPLIT_CACHE.get(sig)
            if ok is None:
                ok = _constant_split_feasible(demands, rooms_of, caps, present)
                if len(_FIXED_SPLIT_CACHE) > 20000:
                    _FIXED_SPLIT_CACHE.clear()
                _FIXED_SPLIT_CACHE[sig] = ok
            if ok:
                continue
            key = (tuple(sorted(comp_set)), tuple(room_ids))
            if key in seen:
                continue
            seen.add(key)
            out.append((key[0], key[1], day, periods[0], w))
    return out


def _find(parent: dict[int, int], x: int) -> int:
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: dict[int, int], a: int, b: int) -> None:
    parent[_find(parent, b)] = _find(parent, a)


def _constant_split_feasible(
    demands: Mapping[int, int],
    rooms_of: Mapping[int, Iterable[int]],
    caps: Mapping[int, int],
    present: Mapping[int, list[int]],
) -> bool:
    """One seat split per event (``x[e, r]``, at least one seat per room of a split event) that fits the
    seats of every room in every period."""
    from ortools.sat.python import cp_model  # type: ignore[import-untyped]

    m = cp_model.CpModel()
    x: dict[tuple[int, int], object] = {}
    for e, rooms in rooms_of.items():
        rs = list(rooms)
        if len(rs) == 1:
            x[(e, rs[0])] = demands[e]
            continue
        for r in rs:
            x[(e, r)] = m.NewIntVar(1 if demands[e] >= len(rs) else 0, max(0, caps[r]), f"x{e}_{r}")
        m.Add(sum(x[(e, r)] for r in rs) == demands[e])  # type: ignore[misc]
    for _p, eids in present.items():
        for r, cap in caps.items():
            terms = [x[(e, r)] for e in eids if (e, r) in x]
            if terms:
                m.Add(sum(terms) <= cap)  # type: ignore[arg-type]
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.max_time_in_seconds = 5.0
    return bool(solver.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE))


def _components(eids: list[int], assignments: Mapping[int, Assignment]) -> list[list[int]]:
    """Events connected through shared rooms."""
    parent = {e: e for e in eids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_room: dict[int, list[int]] = defaultdict(list)
    for e in eids:
        for r in assignments[e].room_ids:
            by_room[r].append(e)
    for members in by_room.values():
        for other in members[1:]:
            parent[find(other)] = find(members[0])
    comps: dict[int, list[int]] = defaultdict(list)
    for e in eids:
        comps[find(e)].append(e)
    return [sorted(c) for c in comps.values()]


__all__ = ["proportional_allocation", "seat_conflicts", "seat_target", "seats_feasible"]
