"""``building_preference``: prefer (soft) or require (hard, targeted) a building.

Implicit soft version from ``Event.preferred_building`` (penalty 1 per room outside).  Targeted
form ``{"event_ids"/"cohort"/"program"/..., "building": "A"}`` or ``{"buildings": ["B","C"]}``.
"""

from __future__ import annotations

from app.solver.constraints._common import is_targeted, select_events, str_list
from app.solver.context import ModelContext
from app.solver.domains import Domains
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event
from app.solver.weights import constraint_weight


def _wanted(c: Constraint, event: Event) -> frozenset[str]:
    if is_targeted(c):
        return frozenset(str_list(c.params, "building") + str_list(c.params, "buildings"))
    return frozenset([event.preferred_building]) if event.preferred_building else frozenset()


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard or not is_targeted(c):
        return
    for event in select_events(doms.inp, c.params):
        wanted = _wanted(c, event)
        if not wanted:
            continue
        dom = doms.domain(event.id)
        for rid in list(dom.rooms):
            if doms.rooms_by_id[rid].building not in wanted:
                dom.remove_room(rid, f"building not in {sorted(wanted)} (building_preference #{c.id})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if c.hard:
        return
    w = constraint_weight(ctx.inp.weights, "building_preference", c.weight)
    for event in select_events(ctx.inp, c.params):
        wanted = _wanted(c, event)
        if not wanted:
            continue
        for rid in ctx.domain(event.id).rooms:
            if ctx.rooms_by_id[rid].building not in wanted:
                ctx.add_penalty("building_preference", ctx.room_use(event.id, rid), 1, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "building_preference", c.weight)
    for event in select_events(ev.inp, c.params):
        wanted = _wanted(c, event)
        if not wanted or not event.needs_room:
            continue
        if not c.hard:
            ev.add_bound("building_preference", max(1, event.max_rooms) * w)
        for room in ev.rooms_of(event.id):
            if room.building in wanted:
                continue
            msg = f"{event.label} is in {room.code} (building {room.building}), wanted {sorted(wanted)}"
            if c.hard:
                ev.hard("building_preference", [event.id], msg, [room.id])
            else:
                ev.soft("building_preference", [event.id], msg, w, [room.id])


__all__ = ["apply", "prune", "score"]
