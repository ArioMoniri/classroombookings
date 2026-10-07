"""Shared "events in a group should share a room" machinery for ``same_room_group`` and
``same_room_across_weeks``.

Soft: ``used[g, r] ≥ room_use(e, r)`` for every event in the group; penalty = Σ_r used − 1
(number of extra distinct rooms).  Hard: all events of the group use the same room set
(pairwise equality of the ``room_use`` literals under the guard ``<kind>:<group>``)."""

from __future__ import annotations

from app.solver.context import ModelContext
from app.solver.evaluate import Evaluation
from app.solver.model import Event


def apply_group(ctx: ModelContext, kind: str, name: str, events: list[Event], hard: bool, weight: int) -> None:
    events = [e for e in events if e.needs_room]
    if len(events) < 2:
        return
    room_ids = sorted({r for e in events for r in ctx.domain(e.id).rooms})
    if hard:
        g = ctx.guard(f"{kind}:{name}")
        for rid in room_ids:
            lits = [ctx.room_use(e.id, rid) for e in events]
            # all equal: lit_i == lit_0 (None = this event cannot use the room -> others must not)
            first = lits[0]
            for lit in lits[1:]:
                if lit is None and first is None:
                    continue
                if lit is None:
                    ctx.add_lit_false(first, g)
                elif first is None:
                    ctx.add_lit_false(lit, g)
                elif g is None:
                    ctx.model.Add(lit == first)
                else:
                    ctx.model.Add(lit == first).OnlyEnforceIf(g)
        return
    used_vars = []
    for rid in room_ids:
        u = ctx.new_bool(f"used_{kind}_{name}_{rid}")
        for e in events:
            lit = ctx.room_use(e.id, rid)
            if lit is None:
                continue
            ctx.model.AddImplication(lit, u)
        used_vars.append(u)
    if len(used_vars) < 2:
        return
    extra = ctx.new_int(f"extra_{kind}_{name}", 0, len(used_vars))
    ctx.model.Add(extra >= sum(used_vars) - 1)
    ctx.add_penalty(kind, extra, 1, weight)


def score_group(ev: Evaluation, kind: str, name: str, events: list[Event], hard: bool, weight: int) -> None:
    events = [e for e in events if e.needs_room and ev.assignment(e.id) is not None]
    if len(events) < 2:
        return
    if not hard:
        ev.add_bound(kind, (len(events) - 1) * weight)
    used: set[int] = set()
    for e in events:
        used.update(ev.by_event[e.id].room_ids)
    distinct_sets = {tuple(sorted(ev.by_event[e.id].room_ids)) for e in events}
    if hard:
        if len(distinct_sets) > 1:
            ev.hard(kind, [e.id for e in events], f"group '{name}' uses different rooms: {sorted(distinct_sets)}", sorted(used))
        return
    extra = max(0, len(used) - 1)
    if extra:
        names = ", ".join(ev.rooms_by_id[r].code for r in sorted(used) if r in ev.rooms_by_id)
        ev.soft(kind, [e.id for e in events], f"group '{name}' is spread over {len(used)} rooms ({names})", extra * weight, sorted(used))
