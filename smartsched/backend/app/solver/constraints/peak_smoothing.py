"""``peak_smoothing``: keep *flexible* events out of busy (day, period, room group) cells (AS-08,
docs/research/2026-10-17-adaptive-scheduling.md §3.2 "Smooth").

A cell is a (day, period, room group) for one teaching week.  Its load is the number of rooms of the group
in use; its allowance is ``floor(rooms_in_group × threshold_pct / 100)`` (default 85 %, the profile's
``peak_threshold_pct``).  The penalty is one unit per room-period-week above the allowance, **counted only
over events whose day or start is flexible** (the request leaves the day or the start open and the planner
did not lock it): ``excess = max(0, min(flex, flex + fixed − allowance))``.  Fixed times are never moved and
a cell that only fixed classes overfill costs nothing (nothing could change it).

Always soft.  The base weight ``peak_smoothing`` defaults to **0 = off**: the implicit rule is then not even
added (``Handler.off_at_zero_weight``), so a run without a weight is byte-identical to one before AS-08.  A
season profile turns it on through ``SolverInput.weights`` (AS-01/AS-03).

Params (all optional): ``threshold_pct`` (50..100, default 85); ``groups`` (``"*"`` = every room,
``"tag:PC"``, ``"building:C"``, ``"building:*"`` = one group per building; default ``"*"`` plus one
``tag:<T>`` group per tag a flexible event requires); ``cells`` (``[{day, period, group?}]``: only these
cells, e.g. the peak cells of ``GET /analytics/peaks``); the usual event selector limits which flexible
events count.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from app.solver.constraints._common import is_targeted, select_events
from app.solver.context import HintView, Lit, ModelContext
from app.solver.domains import is_input_fixed
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event, Room, SolverInput
from app.solver.weights import base_weight, constraint_weight

KIND = "peak_smoothing"
DEFAULT_THRESHOLD_PCT = 85


# ------------------------------------------------------------------------------------------------ shared


def threshold_pct(params: Mapping[str, Any]) -> int:
    try:
        pct = int(params.get("threshold_pct", DEFAULT_THRESHOLD_PCT))
    except (TypeError, ValueError):
        pct = DEFAULT_THRESHOLD_PCT
    return max(1, min(100, pct))


def _flexible(inp: SolverInput, soft: Iterable[str]) -> list[Event]:
    return [e for e in inp.events if e.needs_room and not is_input_fixed(e, soft)]


def groups_of(inp: SolverInput, params: Mapping[str, Any], soft: Iterable[str] = ()) -> list[str]:
    """The room groups the rule watches, in a fixed order."""
    raw = params.get("groups")
    wanted: list[str]
    if raw:
        wanted = [str(g) for g in (raw if isinstance(raw, list | tuple) else [raw])]
    else:
        tags = sorted({t for e in _flexible(inp, soft) for t in e.required_tags})
        wanted = ["*", *(f"tag:{t}" for t in tags)]
    out: list[str] = []
    for g in wanted:
        if g == "building:*":
            out.extend(f"building:{b}" for b in sorted({r.building for r in inp.rooms}))
        else:
            out.append(g)
    seen: set[str] = set()
    return [g for g in out if not (g in seen or seen.add(g))]  # type: ignore[func-returns-value]


def in_group(room: Room, group: str) -> bool:
    if group == "*":
        return True
    kind, _, value = group.partition(":")
    if kind == "tag":
        return value in room.tags
    if kind == "building":
        return room.building == value
    if kind == "room":
        return room.code == value
    return False


def allowance(rooms: Iterable[Room], group: str, pct: int) -> tuple[int, frozenset[int]]:
    """``(allowed rooms in use, room ids of the group)``."""
    ids = frozenset(r.id for r in rooms if in_group(r, group))
    return (len(ids) * pct) // 100, ids


def _cells(params: Mapping[str, Any]) -> set[tuple[int, int, str | None]] | None:
    raw = params.get("cells")
    if not raw:
        return None
    out: set[tuple[int, int, str | None]] = set()
    for c in raw:
        try:
            out.add((int(c["day"]), int(c["period"]), (str(c["group"]) if c.get("group") else None)))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _cell_on(cells: set[tuple[int, int, str | None]] | None, day: int, period: int, group: str) -> bool:
    return cells is None or (day, period, group) in cells or (day, period, None) in cells


def _counted(inp: SolverInput, c: Constraint) -> set[int]:
    """Flexible events the rule counts (the selector, if any, narrows them)."""
    if is_targeted(c):
        return {e.id for e in select_events(inp, c.params)}
    return {e.id for e in inp.events}


def excess(flex: int, fixed: int, allowed: int) -> int:
    """Rooms above the allowance that flexible events account for."""
    return max(0, min(flex, flex + fixed - allowed))


def is_on(inp: SolverInput) -> bool:
    return base_weight(inp.weights, KIND) > 0


# ------------------------------------------------------------------------------------------------ CP-SAT


def _eval_cell(
    ctx: ModelContext, flex: list[Lit], fixed: list[Lit], allowed: int
) -> tuple[Callable[[HintView], int], Callable[[HintView], int]]:
    def counts(h: HintView) -> tuple[int, int]:
        return sum(ctx.lit_value(x, h) for x in flex), sum(ctx.lit_value(x, h) for x in fixed)

    def ex(h: HintView) -> int:
        f, x = counts(h)
        return excess(f, x, allowed)

    def pick(h: HintView) -> int:
        f, x = counts(h)
        return int(f + x - allowed <= f)

    return ex, pick


def _member(ctx: ModelContext, event: Event, ids: frozenset[int]) -> list[Lit]:
    """Literals 'the event uses a room of the group' (one per room for split events; ``True`` when every
    room option is in the group)."""
    if not event.needs_room:
        return []
    rooms = [r for r in ctx.domain(event.id).rooms if (event.id, r) in ctx.z]
    inside = [r for r in rooms if r in ids]
    if not inside:
        return []
    if event.max_rooms > 1:
        return [ctx.z[(event.id, r)] for r in inside]
    if len(inside) == len(rooms):
        return [True]
    if len(inside) == 1:
        return [ctx.z[(event.id, inside[0])]]
    v = ctx.new_bool(f"peak_in_{event.id}_{min(inside)}_{len(inside)}")
    ctx.model.Add(sum(ctx.z[(event.id, r)] for r in inside) == v)
    eid, ins = event.id, frozenset(inside)
    ctx.derive(v, lambda h: int(bool(h.rooms(eid) & ins)))
    return [v]


def apply(ctx: ModelContext, c: Constraint) -> None:
    w = constraint_weight(ctx.inp.weights, KIND, c.weight)
    if w <= 0:
        return
    inp = ctx.inp
    soft = ctx.doms.soft
    pct = threshold_pct(c.params)
    cells = _cells(c.params)
    counted = _counted(inp, c)
    flexible = {e.id for e in _flexible(inp, soft) if e.id in counted}
    if not flexible:
        return
    for group in groups_of(inp, c.params, soft):
        allowed, ids = allowance(inp.rooms, group, pct)
        if not ids:
            continue
        members: dict[int, list[Lit]] = {}
        for e in inp.events:
            m = _member(ctx, e, ids)
            if m:
                members[e.id] = m
        if not any(eid in flexible for eid in members):
            continue
        for day in inp.days:
            for period in range(1, inp.periods_per_day + 1):
                if not _cell_on(cells, day, period, group):
                    continue
                _cell(ctx, members, flexible, day, period, allowed, w, group)


def _cell(
    ctx: ModelContext,
    members: dict[int, list[Lit]],
    flexible: set[int],
    day: int,
    period: int,
    allowed: int,
    w: int,
    group: str,
) -> None:
    items: list[tuple[int, list[Lit]]] = []  # (event id, contribution literals)
    for eid, lits in members.items():
        occ = ctx.occupies(eid, day, period)
        if occ is None:
            continue
        items.append((eid, [ctx.and_lit(occ, m) for m in lits]))
    if not any(eid in flexible for eid, _ in items):
        return
    # per teaching week, deduplicated: weeks with the same candidate set share one excess term
    by_week: dict[int, list[int]] = defaultdict(list)
    for idx, (eid, _lits) in enumerate(items):
        for wk in ctx.events_by_id[eid].weeks:
            by_week[wk].append(idx)
    weeks_of: dict[tuple[int, ...], int] = defaultdict(int)
    for idxs in by_week.values():
        weeks_of[tuple(idxs)] += 1
    for n, (idxs, n_weeks) in enumerate(sorted(weeks_of.items())):
        flex = [x for i in idxs if items[i][0] in flexible for x in items[i][1]]
        fixed = [x for i in idxs if items[i][0] not in flexible for x in items[i][1]]
        if not flex:
            continue
        if len(flex) + len(fixed) <= allowed:
            continue  # can never exceed
        fixed_const = sum(1 for x in fixed if x is True)
        fixed_vars = [x for x in fixed if x is not True]
        flex_const = sum(1 for x in flex if x is True)
        flex_vars = [x for x in flex if x is not True]
        name = f"peak_{group}_{day}_{period}_{n}"
        if not flex_vars and not fixed_vars:
            units = excess(flex_const, fixed_const, allowed)
            ctx.add_penalty(KIND, True, units * n_weeks, w)
            continue
        hi = len(flex)
        ex = ctx.new_int(f"{name}_ex", 0, hi)
        flex_sum = flex_const + sum(flex_vars)
        ex_fn, pick_fn = _eval_cell(ctx, flex, fixed, allowed)
        if not fixed_vars:
            # allowance left by the fixed classes is a constant: excess >= flex - max(0, allowed - fixed)
            ctx.model.Add(ex >= flex_sum - max(0, allowed - fixed_const))
        else:
            # excess >= min(flex, flex + fixed - allowed): one choice literal per cell
            total = flex_sum + fixed_const + sum(fixed_vars)
            big = len(flex) + len(fixed) + allowed
            b = ctx.new_bool(f"{name}_b")
            ctx.model.Add(ex >= flex_sum - big * b)
            ctx.model.Add(ex >= total - allowed - big * (1 - b))
            ctx.derive(b, pick_fn)
        ctx.derive(ex, ex_fn)
        ctx.add_penalty(KIND, ex, n_weeks, w)


# ------------------------------------------------------------------------------------------------ evaluation


def score(ev: Evaluation, c: Constraint) -> None:
    inp = ev.inp
    w = constraint_weight(inp.weights, KIND, c.weight)
    if w <= 0:
        return
    soft = ev.soft_structural
    pct = threshold_pct(c.params)
    cells = _cells(c.params)
    counted = _counted(inp, c)
    flexible = {e.id for e in _flexible(inp, soft) if e.id in counted}
    if not flexible:
        return
    groups = groups_of(inp, c.params, soft)
    rooms = inp.rooms
    for eid in sorted(flexible):
        e = ev.events_by_id[eid]
        n_groups = sum(1 for g in groups if any(in_group(r, g) and e.required_tags <= r.tags for r in rooms))
        ev.add_bound(KIND, max(1, e.duration) * max(1, e.max_rooms) * len(e.weeks) * n_groups * w)
    # (group, day, period, week) -> [flex rooms, fixed rooms, flexible event ids]
    for group in groups:
        allowed, ids = allowance(rooms, group, pct)
        if not ids:
            continue
        load: dict[tuple[int, int, int], list[Any]] = defaultdict(lambda: [0, 0, []])
        for eid, a in ev.by_event.items():
            e = ev.events_by_id.get(eid)
            if e is None or not e.needs_room:
                continue
            n = sum(1 for r in a.room_ids if r in ids)
            if not n:
                continue
            for p in range(a.start, a.end + 1):
                for wk in e.weeks:
                    cell = load[(a.day, p, wk)]
                    if eid in flexible:
                        cell[0] += n
                        cell[2].append(eid)
                    else:
                        cell[1] += n
        per_cell: dict[tuple[int, int], list[Any]] = defaultdict(lambda: [0, set(), 0])
        for (day, p, _wk), (flex, fixed, eids) in load.items():
            if not _cell_on(cells, day, p, group):
                continue
            units = excess(flex, fixed, allowed)
            if units:
                agg = per_cell[(day, p)]
                agg[0] += units
                agg[1].update(eids)
                agg[2] = max(agg[2], flex + fixed)
        for (day, p), (units, eids, peak) in sorted(per_cell.items()):
            labels = ", ".join(ev.events_by_id[i].label for i in sorted(eids))
            ev.soft(
                KIND,
                sorted(eids),
                f"peak cell day {day} P{p} ({group}): {peak} rooms in use, allowance {allowed} "
                f"({pct} % of {len(ids)}); movable: {labels}",
                units * w,
            )


# ------------------------------------------------------------------------------------------------ greedy


class GreedyPeaks:
    """Peak cost of a time option during the greedy warm start (the same cells and allowance as the model,
    for the groups an event is sure to touch: ``*`` and its required tags)."""

    def __init__(self, inp: SolverInput, soft: Iterable[str]) -> None:
        self.inp = inp
        self.on = is_on(inp)
        cons = [c for c in inp.constraints if c.kind == KIND and not is_targeted(c)]
        params: Mapping[str, Any] = cons[-1].params if cons else {}
        self.pct = threshold_pct(params)
        self.cells = _cells(params)
        self.groups = groups_of(inp, params, soft)
        self.soft = frozenset(soft)
        self.allowed = {g: allowance(inp.rooms, g, self.pct)[0] for g in self.groups}
        self.load: dict[tuple[str, int, int, int], int] = defaultdict(int)
        self.rooms_by_id = {r.id: r for r in inp.rooms}

    def _sure_groups(self, e: Event) -> list[str]:
        out = []
        for g in self.groups:
            if g == "*" or (g.startswith("tag:") and g[4:] in e.required_tags):
                out.append(g)
        return out

    def flexible(self, e: Event) -> bool:
        return self.on and e.needs_room and not is_input_fixed(e, self.soft)

    def cost(self, e: Event, day: int, periods: Iterable[int]) -> int:
        total = 0
        for g in self._sure_groups(e):
            for p in periods:
                if not _cell_on(self.cells, day, p, g):
                    continue
                for wk in e.weeks:
                    total += int(self.load[(g, day, p, wk)] + 1 > self.allowed[g])
        return total

    def take(self, e: Event, day: int, periods: Iterable[int], room_ids: Iterable[int]) -> None:
        if not self.on or not e.needs_room:
            return
        rooms = [self.rooms_by_id[r] for r in room_ids if r in self.rooms_by_id]
        for g in self.groups:
            n = sum(1 for r in rooms if in_group(r, g))
            if not n:
                continue
            for p in periods:
                for wk in e.weeks:
                    self.load[(g, day, p, wk)] += n


__all__ = [
    "DEFAULT_THRESHOLD_PCT",
    "KIND",
    "GreedyPeaks",
    "allowance",
    "apply",
    "excess",
    "groups_of",
    "in_group",
    "is_on",
    "score",
    "threshold_pct",
]
