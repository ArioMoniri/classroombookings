"""``evening_programs_in_buildings(list)``: evening (İÖ) programmes stay in the given buildings.

Params: ``buildings`` (list of codes), selector (default ``match: "İÖ"`` on cohort keys/labels;
``cohorts``/``program``/``event_ids`` also work).  Hard = rooms outside are pruned; soft = penalty
1 per room outside the list.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.solver.constraints._common import select_events, str_list
from app.solver.context import ModelContext
from app.solver.domains import Domains
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint
from app.solver.weights import constraint_weight

DEFAULT_MATCH = "İÖ"


def _params(c: Constraint) -> tuple[frozenset[str], Mapping[str, Any]]:
    params = dict(c.params)
    buildings = frozenset(str_list(params, "buildings") + str_list(params, "building"))
    if not any(k in params for k in ("event_ids", "cohort", "cohorts", "program", "programs", "match")):
        params["match"] = DEFAULT_MATCH
    return buildings, params


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard:
        return
    buildings, params = _params(c)
    if not buildings:
        return
    for event in select_events(doms.inp, params):
        dom = doms.domain(event.id)
        for rid in list(dom.rooms):
            if doms.rooms_by_id[rid].building not in buildings:
                dom.remove_room(rid, f"evening programmes must use buildings {sorted(buildings)} (evening_programs_in_buildings #{c.id})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if c.hard:
        return
    buildings, params = _params(c)
    if not buildings:
        return
    w = constraint_weight(ctx.inp.weights, "evening_programs_in_buildings", c.weight)
    for event in select_events(ctx.inp, params):
        for rid in ctx.domain(event.id).rooms:
            if ctx.rooms_by_id[rid].building not in buildings:
                ctx.add_penalty("evening_programs_in_buildings", ctx.room_use(event.id, rid), 1, w)


def score(ev: Evaluation, c: Constraint) -> None:
    buildings, params = _params(c)
    if not buildings:
        return
    w = constraint_weight(ev.inp.weights, "evening_programs_in_buildings", c.weight)
    for event in select_events(ev.inp, params):
        if not event.needs_room:
            continue
        if not c.hard:
            ev.add_bound("evening_programs_in_buildings", max(1, event.max_rooms) * w)
        for room in ev.rooms_of(event.id):
            if room.building in buildings:
                continue
            msg = f"evening programme event {event.label} is in {room.code} (building {room.building}); allowed {sorted(buildings)}"
            if c.hard:
                ev.hard("evening_programs_in_buildings", [event.id], msg, [room.id])
            else:
                ev.soft("evening_programs_in_buildings", [event.id], msg, w, [room.id])


__all__ = ["apply", "prune", "score"]
