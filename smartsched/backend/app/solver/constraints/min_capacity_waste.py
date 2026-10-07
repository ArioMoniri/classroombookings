"""``min_capacity_waste``: avoid 20 students in a 156-seat hall.

Penalty units = ``(Σ capacity of chosen rooms − size) // unit`` (unit = 10 seats by default,
param ``unit``).  Always soft.
"""

from __future__ import annotations

from app.solver.constraints._common import select_events
from app.solver.context import ModelContext
from app.solver.domains import effective_capacity
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint
from app.solver.weights import CAPACITY_WASTE_UNIT, constraint_weight


def _unit(c: Constraint) -> int:
    return max(1, int(c.params.get("unit", CAPACITY_WASTE_UNIT)))


def apply(ctx: ModelContext, c: Constraint) -> None:
    w = constraint_weight(ctx.inp.weights, "min_capacity_waste", c.weight)
    unit = _unit(c)
    for event in select_events(ctx.inp, c.params):
        if not event.needs_room:
            continue
        dom = ctx.domain(event.id)
        if event.max_rooms <= 1:
            for rid in dom.rooms:
                units = (effective_capacity(ctx.rooms_by_id[rid], event) - event.size) // unit
                if units > 0:
                    ctx.add_penalty("min_capacity_waste", ctx.room_use(event.id, rid), units, w)
        else:
            # split events: penalise total capacity in unit steps (size offset is a constant)
            for rid in dom.rooms:
                units = effective_capacity(ctx.rooms_by_id[rid], event) // unit
                if units > 0:
                    ctx.add_penalty("min_capacity_waste", ctx.room_use(event.id, rid), units, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "min_capacity_waste", c.weight)
    unit = _unit(c)
    for event in select_events(ev.inp, c.params):
        if not event.needs_room:
            continue
        rooms = ev.rooms_of(event.id)
        if not rooms:
            continue
        if event.max_rooms <= 1:
            waste = (effective_capacity(rooms[0], event) - event.size) // unit
            biggest = max((effective_capacity(r, event) for r in ev.inp.rooms), default=0)
            ev.add_bound("min_capacity_waste", max(0, (biggest - event.size) // unit) * w)
        else:
            waste = sum(effective_capacity(r, event) // unit for r in rooms)
            caps = sorted((effective_capacity(r, event) // unit for r in ev.inp.rooms), reverse=True)
            ev.add_bound("min_capacity_waste", sum(caps[: max(1, event.max_rooms)]) * w)
        if waste > 0:
            ev.soft(
                "min_capacity_waste",
                [event.id],
                f"{event.label} ({event.size}) in {'+'.join(r.code for r in rooms)} ({sum(effective_capacity(r, event) for r in rooms)} seats)",
                waste * w,
                [r.id for r in rooms],
            )


__all__ = ["apply", "score"]
