"""``room_tags``: required / forbidden room tags (``PC``, ``TIP`` ...).

Implicit hard version pruned in domains.  Soft default: penalty 1 per missing/forbidden tag.
Targeted form ``{"event_ids"/"cohort"/..., "required_tags": [...], "forbidden_tags": [...]}``.
"""

from __future__ import annotations

from app.solver.constraints._common import is_targeted, select_events, str_list
from app.solver.context import ModelContext
from app.solver.domains import Domains
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event, Room
from app.solver.weights import constraint_weight


def _tags(c: Constraint, event: Event) -> tuple[frozenset[str], frozenset[str]]:
    if is_targeted(c):
        return frozenset(str_list(c.params, "required_tags")), frozenset(str_list(c.params, "forbidden_tags"))
    return event.required_tags, event.forbidden_tags


def _bad(room: Room, req: frozenset[str], forb: frozenset[str]) -> int:
    return len(req - room.tags) + len(forb & room.tags)


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard or not is_targeted(c):
        return
    for event in select_events(doms.inp, c.params):
        req, forb = _tags(c, event)
        dom = doms.domain(event.id)
        for rid in list(dom.rooms):
            if _bad(doms.rooms_by_id[rid], req, forb):
                dom.remove_room(rid, f"tags mismatch (room_tags #{c.id}: need {sorted(req)}, avoid {sorted(forb)})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if c.hard:
        return
    w = constraint_weight(ctx.inp.weights, "room_tags", c.weight)
    for event in select_events(ctx.inp, c.params):
        req, forb = _tags(c, event)
        if not req and not forb:
            continue
        for rid in ctx.domain(event.id).rooms:
            units = _bad(ctx.rooms_by_id[rid], req, forb)
            if units:
                ctx.add_penalty("room_tags", ctx.room_use(event.id, rid), units, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "room_tags", c.weight)
    for event in select_events(ev.inp, c.params):
        req, forb = _tags(c, event)
        if not req and not forb:
            continue
        if not c.hard:
            ev.add_bound("room_tags", (len(req) + len(forb)) * max(1, event.max_rooms) * w)
        for room in ev.rooms_of(event.id):
            units = _bad(room, req, forb)
            if not units:
                continue
            msg = f"{event.label} in {room.code} (tags {sorted(room.tags)}) needs {sorted(req)} and must avoid {sorted(forb)}"
            if c.hard:
                ev.hard("room_tags", [event.id], msg, [room.id])
            else:
                ev.soft("room_tags", [event.id], msg, units * w, [room.id])


__all__ = ["apply", "prune", "score"]
