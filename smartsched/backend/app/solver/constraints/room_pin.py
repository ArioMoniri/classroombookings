"""``room_pin``: the event must use one of the listed rooms (``required_room_ids``).

Soft default: penalty 1 per assigned room outside the set.  Targeted form
``{"event_ids"/..., "room_ids": [...]}``.
"""

from __future__ import annotations

from app.solver.constraints._common import int_list, is_targeted, select_events
from app.solver.context import ModelContext
from app.solver.domains import Domains
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event
from app.solver.weights import constraint_weight


def _allowed(c: Constraint, event: Event) -> frozenset[int]:
    return frozenset(int_list(c.params, "room_ids")) if is_targeted(c) else event.required_room_ids


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard or not is_targeted(c):
        return
    for event in select_events(doms.inp, c.params):
        allowed = _allowed(c, event)
        if not allowed:
            continue
        dom = doms.domain(event.id)
        for rid in list(dom.rooms):
            if rid not in allowed:
                dom.remove_room(rid, f"not in the pinned room set (room_pin #{c.id})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if c.hard:
        return
    w = constraint_weight(ctx.inp.weights, "room_pin", c.weight)
    for event in select_events(ctx.inp, c.params):
        allowed = _allowed(c, event)
        if not allowed:
            continue
        for rid in ctx.domain(event.id).rooms:
            if rid not in allowed:
                ctx.add_penalty("room_pin", ctx.room_use(event.id, rid), 1, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "room_pin", c.weight)
    for event in select_events(ev.inp, c.params):
        allowed = _allowed(c, event)
        if not allowed:
            continue
        if not c.hard:
            ev.add_bound("room_pin", max(1, event.max_rooms) * w)
        for room in ev.rooms_of(event.id):
            if room.id in allowed:
                continue
            names = ", ".join(ev.rooms_by_id[r].code for r in sorted(allowed) if r in ev.rooms_by_id) or str(sorted(allowed))
            msg = f"{event.label} is in {room.code} but is pinned to {names}"
            if c.hard:
                ev.hard("room_pin", [event.id], msg, [room.id])
            else:
                ev.soft("room_pin", [event.id], msg, w, [room.id])


__all__ = ["apply", "prune", "score"]
