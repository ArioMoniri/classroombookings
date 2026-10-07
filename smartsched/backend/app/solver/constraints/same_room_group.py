"""``same_room_group``: events sharing ``Event.same_room_group`` (e.g. "same room as OPT 126")
should use the same room.  Soft by default (penalty per extra distinct room); hard = identical
room sets.  Explicit form ``{"event_ids": [...]}`` or ``{"groups": [[ids], [ids]]}``."""

from __future__ import annotations

from collections import defaultdict

from app.solver.constraints import _groups
from app.solver.constraints._common import int_list, is_targeted
from app.solver.context import ModelContext
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event, SolverInput
from app.solver.weights import constraint_weight


def groups_for(inp: SolverInput, c: Constraint) -> dict[str, list[Event]]:
    by_id = {e.id: e for e in inp.events}
    out: dict[str, list[Event]] = {}
    raw = c.params.get("groups")
    if raw:
        for i, ids in enumerate(raw):
            out[f"#{c.id or 0}.{i}"] = [by_id[int(x)] for x in ids if int(x) in by_id]
        return out
    if is_targeted(c):
        out[f"#{c.id or 0}"] = [by_id[i] for i in int_list(c.params, "event_ids") if i in by_id]
        return out
    tmp: dict[str, list[Event]] = defaultdict(list)
    for e in inp.events:
        if e.same_room_group:
            tmp[e.same_room_group].append(e)
    return dict(tmp)


def apply(ctx: ModelContext, c: Constraint) -> None:
    w = constraint_weight(ctx.inp.weights, "same_room_group", c.weight)
    for name, events in sorted(groups_for(ctx.inp, c).items()):
        _groups.apply_group(ctx, "same_room_group", name, events, c.hard, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "same_room_group", c.weight)
    for name, events in sorted(groups_for(ev.inp, c).items()):
        _groups.score_group(ev, "same_room_group", name, events, c.hard, w)


__all__ = ["apply", "groups_for", "score"]
