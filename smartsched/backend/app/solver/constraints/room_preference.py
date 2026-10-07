"""``room_preference``: ordered list of preferred rooms.

Penalty units = rank of the chosen room in the list (0 for the first choice), or ``len(list)``
when the room is not listed.  Implicit from ``Event.preferred_room_ids``; targeted form
``{"event_ids"/..., "room_ids": [ordered]}``; hard + targeted = restrict to the list.
"""

from __future__ import annotations

from app.solver.constraints._common import int_list, is_targeted, select_events
from app.solver.context import ModelContext
from app.solver.domains import Domains
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event
from app.solver.weights import constraint_weight


def _prefs(c: Constraint, event: Event) -> tuple[int, ...]:
    return tuple(int_list(c.params, "room_ids")) if is_targeted(c) else event.preferred_room_ids


def rank(prefs: tuple[int, ...], room_id: int) -> int:
    return prefs.index(room_id) if room_id in prefs else len(prefs)


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard or not is_targeted(c):
        return
    for event in select_events(doms.inp, c.params):
        prefs = _prefs(c, event)
        if not prefs:
            continue
        dom = doms.domain(event.id)
        for rid in list(dom.rooms):
            if rid not in prefs:
                dom.remove_room(rid, f"not in the required room list (room_preference #{c.id})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if c.hard:
        return
    w = constraint_weight(ctx.inp.weights, "room_preference", c.weight)
    for event in select_events(ctx.inp, c.params):
        prefs = _prefs(c, event)
        if not prefs:
            continue
        for rid in ctx.domain(event.id).rooms:
            units = rank(prefs, rid)
            if units:
                ctx.add_penalty("room_preference", ctx.room_use(event.id, rid), units, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "room_preference", c.weight)
    for event in select_events(ev.inp, c.params):
        prefs = _prefs(c, event)
        if not prefs or not event.needs_room:
            continue
        if not c.hard:
            ev.add_bound("room_preference", len(prefs) * max(1, event.max_rooms) * w)
        for room in ev.rooms_of(event.id):
            units = rank(prefs, room.id)
            if not units:
                continue
            names = ", ".join(ev.rooms_by_id[r].code for r in prefs if r in ev.rooms_by_id)
            msg = f"{event.label} is in {room.code}; preferred order: {names}"
            if c.hard:
                ev.hard("room_preference", [event.id], msg, [room.id])
            else:
                ev.soft("room_preference", [event.id], msg, units * w, [room.id])


__all__ = ["apply", "prune", "rank", "score"]
