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
        e0 = events[0]
        for e in events[1:]:
            # enforced only when both events are placed (assume/relax modes) and the guard holds
            enforce = [lit for lit in (g, ctx.placed.get(e0.id), ctx.placed.get(e.id)) if lit is not None]
            for rid in room_ids:
                first, lit = ctx.room_use(e0.id, rid), ctx.room_use(e.id, rid)
                if lit is None and first is None:
                    continue
                if lit is None or first is None:
                    target = first if lit is None else lit
                    assert target is not None
                    if enforce:
                        ctx.model.AddBoolOr([x.Not() for x in enforce] + [target.Not()])
                    else:
                        ctx.model.Add(target == 0)
                elif enforce:
                    ctx.model.Add(lit == first).OnlyEnforceIf(enforce)
                else:
                    ctx.model.Add(lit == first)
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
            ev.hard(
                kind,
                [e.id for e in events],
                f"group '{name}' uses different rooms: {sorted(distinct_sets)}",
                sorted(used),
            )
        return
    extra = max(0, len(used) - 1)
    if extra:
        names = ", ".join(ev.rooms_by_id[r].code for r in sorted(used) if r in ev.rooms_by_id)
        ev.soft(
            kind,
            [e.id for e in events],
            f"group '{name}' is spread over {len(used)} rooms ({names})",
            extra * weight,
            sorted(used),
        )
