"""``room_preference``: ordered list of preferred rooms.

Penalty units = rank of the chosen room in the list (0 for the first choice), or ``len(list)``
when the room is not listed; a multi-room event uses its first ``max_rooms`` listed rooms for free
(see :func:`units`).  Implicit from ``Event.preferred_room_ids``; targeted form
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


def units(prefs: tuple[int, ...], room_id: int, max_rooms: int = 1) -> int:
    """Penalty units of one used room.  A multi-room event (split exam, a lecture the planner seats in
    ``A 101 / A 106``) may use its first ``max_rooms`` preferred rooms at no cost — the planner's room
    *set* is the first choice, not just its first room; a room outside the list costs at least 1."""
    k = max(1, max_rooms) - 1
    if room_id in prefs:
        return max(0, prefs.index(room_id) - k)
    return max(1, len(prefs) - k)


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
            n = units(prefs, rid, event.max_rooms)
            if n:
                ctx.add_penalty("room_preference", ctx.room_use(event.id, rid), n, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "room_preference", c.weight)
    for event in select_events(ev.inp, c.params):
        prefs = _prefs(c, event)
        if not prefs or not event.needs_room:
            continue
        if not c.hard:
            ev.add_bound("room_preference", len(prefs) * max(1, event.max_rooms) * w)
        for room in ev.rooms_of(event.id):
            n = units(prefs, room.id, event.max_rooms)
            if not n:
                continue
            names = ", ".join(ev.rooms_by_id[r].code for r in prefs if r in ev.rooms_by_id)
            msg = f"{event.label} is in {room.code}; preferred order: {names}"
            if c.hard:
                ev.hard("room_preference", [event.id], msg, [room.id])
            else:
                ev.soft("room_preference", [event.id], msg, n * w, [room.id])


__all__ = ["apply", "prune", "rank", "score", "units"]
