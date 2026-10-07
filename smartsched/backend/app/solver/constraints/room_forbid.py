"""``room_forbid``: the event must not use the listed rooms (``forbidden_room_ids``).
Targeted form ``{"event_ids"/..., "room_ids": [...]}``; soft = penalty 1 per forbidden room used."""

from __future__ import annotations

from app.solver.constraints._common import int_list, is_targeted, select_events
from app.solver.context import ModelContext
from app.solver.domains import Domains
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event
from app.solver.weights import constraint_weight


def _forbidden(c: Constraint, event: Event) -> frozenset[int]:
    return frozenset(int_list(c.params, "room_ids")) if is_targeted(c) else event.forbidden_room_ids


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard or not is_targeted(c):
        return
    for event in select_events(doms.inp, c.params):
        for rid in _forbidden(c, event):
            doms.domain(event.id).remove_room(rid, f"room is forbidden (room_forbid #{c.id})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if c.hard:
        return
    w = constraint_weight(ctx.inp.weights, "room_forbid", c.weight)
    for event in select_events(ctx.inp, c.params):
        for rid in _forbidden(c, event):
            lit = ctx.room_use(event.id, rid)
            if lit is not None:
                ctx.add_penalty("room_forbid", lit, 1, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "room_forbid", c.weight)
    for event in select_events(ev.inp, c.params):
        forb = _forbidden(c, event)
        if not forb:
            continue
        if not c.hard:
            ev.add_bound("room_forbid", max(1, event.max_rooms) * w)
        for room in ev.rooms_of(event.id):
            if room.id not in forb:
                continue
            msg = f"{event.label} uses forbidden room {room.code}"
            if c.hard:
                ev.hard("room_forbid", [event.id], msg, [room.id])
            else:
                ev.soft("room_forbid", [event.id], msg, w, [room.id])


__all__ = ["apply", "prune", "score"]
