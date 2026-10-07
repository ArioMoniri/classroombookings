"""``capacity``: room capacity (lecture) / exam capacity (exam) must cover the event size.

Implicit hard version: pruned in :mod:`app.solver.domains` (single-room events) or enforced by the
split-room linking (``Σ_r x·cap_r ≥ size``).  Explicit ``Constraint("capacity", {}, hard=False)``
makes it soft: shortage in seats is penalised.  Targeted form ``{"event_ids": [...], "size": n}``
overrides the required seats for those events (e.g. a merged exam).
"""

from __future__ import annotations

from app.solver.constraints._common import int_list, is_targeted, select_events
from app.solver.context import ModelContext
from app.solver.domains import Domains, effective_capacity
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event
from app.solver.weights import constraint_weight


def _required(c: Constraint, event: Event) -> int:
    size = c.params.get("size")
    return int(size) if size is not None else event.size


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard or not is_targeted(c):
        return
    for event in select_events(doms.inp, c.params):
        dom = doms.domain(event.id)
        need = _required(c, event)
        if event.max_rooms > 1:
            continue
        for rid in list(dom.rooms):
            cap = effective_capacity(doms.rooms_by_id[rid], event)
            if cap < need:
                dom.remove_room(rid, f"capacity {cap} < required {need} (capacity #{c.id})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    targeted = is_targeted(c)
    events = select_events(ctx.inp, c.params) if targeted else list(ctx.inp.events)
    if c.hard and targeted:
        # split events: Σ cap·x ≥ required size at every time option
        for event in events:
            if event.max_rooms <= 1 or not event.needs_room:
                continue
            need = _required(c, event)
            dom = ctx.domain(event.id)
            g = ctx.guard(f"capacity:{event.id}")
            zs = [(ctx.z[(event.id, r)], effective_capacity(ctx.rooms_by_id[r], event)) for r in dom.rooms if (event.id, r) in ctx.z]
            if not zs:
                continue
            expr = sum(cap * v for v, cap in zs)
            placed = ctx.placed.get(event.id, True)
            if placed is True:
                ctx.add_linear_le(-expr, -need, g)
            elif g is None:
                ctx.model.Add(expr >= need).OnlyEnforceIf(placed)
            else:
                ctx.model.Add(expr >= need).OnlyEnforceIf([placed, g])
        return
    if c.hard:
        return  # implicit hard: handled by domain pruning / split linking
    w = constraint_weight(ctx.inp.weights, "capacity", c.weight)
    for event in events:
        if not event.needs_room or event.max_rooms > 1:
            continue
        need = _required(c, event)
        dom = ctx.domain(event.id)
        for rid in dom.rooms:
            short = need - effective_capacity(ctx.rooms_by_id[rid], event)
            if short <= 0:
                continue
            lit = ctx.room_use(event.id, rid)
            ctx.add_penalty("capacity", lit, short, w)


def score(ev: Evaluation, c: Constraint) -> None:
    targeted = is_targeted(c)
    events = select_events(ev.inp, c.params) if targeted else list(ev.inp.events)
    w = constraint_weight(ev.inp.weights, "capacity", c.weight)
    for event in events:
        a = ev.assignment(event.id)
        if a is None or not event.needs_room:
            continue
        rooms = ev.rooms_of(event.id)
        n = len(rooms)
        if not targeted:
            if n < max(1, event.min_rooms) or n > max(1, event.max_rooms):
                ev.hard("capacity", [event.id], f"{event.label} uses {n} room(s); allowed {max(1, event.min_rooms)}..{max(1, event.max_rooms)}", list(a.room_ids))
                continue
        need = _required(c, event)
        total = sum(effective_capacity(r, event) for r in rooms)
        if total >= need:
            continue
        msg = f"{event.label} needs {need} seats but {', '.join(r.code for r in rooms) or 'no room'} offers {total}"
        if c.hard:
            ev.hard("capacity", [event.id], msg, list(a.room_ids))
        else:
            ev.soft("capacity", [event.id], msg, (need - total) * w, list(a.room_ids))
    if not c.hard:
        for event in events:
            if event.needs_room and event.max_rooms <= 1:
                ev.add_bound("capacity", _required(c, event) * w)


__all__ = ["apply", "prune", "score"]
