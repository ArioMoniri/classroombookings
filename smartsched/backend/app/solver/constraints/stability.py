"""``stability``: stay close to ``SolverInput.previous`` (minimum-perturbation re-solve).

Per event with a previous assignment: ``stability_time`` weight when its (day, start) changes,
``stability_room`` weight when its room changes (single-room events) or per previous room dropped
(split events).  Both are multiplied by ``base_weight("stability") * Constraint.weight``.
Hard + targeted (``{"event_ids": [...]}``) pins those events to their previous assignment.
"""

from __future__ import annotations

from app.solver.constraints._common import int_list, is_targeted
from app.solver.context import ModelContext
from app.solver.evaluate import Evaluation
from app.solver.model import Assignment, Constraint, SolverInput
from app.solver.weights import base_weight, constraint_weight


def _previous(inp: SolverInput, c: Constraint) -> list[Assignment]:
    ids = set(int_list(c.params, "event_ids")) if is_targeted(c) else None
    by_id = {e.id for e in inp.events}
    return [a for a in inp.previous if a.event_id in by_id and (ids is None or a.event_id in ids)]


def _weights(inp: SolverInput, c: Constraint) -> tuple[int, int]:
    base = constraint_weight(inp.weights, "stability", c.weight)
    return base * base_weight(inp.weights, "stability_room"), base * base_weight(inp.weights, "stability_time")


def apply(ctx: ModelContext, c: Constraint) -> None:
    prev = _previous(ctx.inp, c)
    if c.hard:
        if is_targeted(c):
            for a in prev:
                ctx.fix_assignment(a, ctx.guard(f"stability:{a.event_id}"))
        return
    w_room, w_time = _weights(ctx.inp, c)
    for a in prev:
        event = ctx.events_by_id[a.event_id]
        dom = ctx.domain(a.event_id)
        ti = dom.time_index(a.day, a.start)
        if ti is None:
            ctx.add_penalty("stability_time", True, 1, w_time)  # time must change
        else:
            lit = ctx.time_lit(a.event_id, ti)
            if lit is not True:
                ctx.add_penalty("stability_time", lit.Not(), 1, w_time)
        if not event.needs_room:
            continue
        for rid in a.room_ids:
            use = ctx.room_use(a.event_id, rid)
            if use is None:
                ctx.add_penalty("stability_room", True, 1, w_room)
            else:
                ctx.add_penalty("stability_room", use.Not(), 1, w_room)


def score(ev: Evaluation, c: Constraint) -> None:
    prev = _previous(ev.inp, c)
    w_room, w_time = _weights(ev.inp, c)
    for a in prev:
        cur = ev.assignment(a.event_id)
        event = ev.events_by_id[a.event_id]
        if cur is None:
            continue
        time_changed = (cur.day, cur.start) != (a.day, a.start)
        dropped = [r for r in a.room_ids if r not in cur.room_ids] if event.needs_room else []
        if c.hard:
            if time_changed or dropped:
                ev.hard("stability", [a.event_id], f"{event.label} moved from day {a.day} P{a.start} rooms {list(a.room_ids)}")
            continue
        ev.add_bound("stability_time", w_time)
        ev.add_bound("stability_room", len(a.room_ids) * w_room)
        if time_changed:
            ev.soft("stability_time", [a.event_id], f"{event.label} moved from day {a.day} P{a.start} to day {cur.day} P{cur.start}", w_time)
        if dropped:
            names = ", ".join(ev.rooms_by_id[r].code for r in dropped if r in ev.rooms_by_id)
            ev.soft("stability_room", [a.event_id], f"{event.label} left room(s) {names}", len(dropped) * w_room, dropped)


__all__ = ["apply", "score"]
