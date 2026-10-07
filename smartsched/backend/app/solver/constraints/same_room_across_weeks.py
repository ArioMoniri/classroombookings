"""``same_room_across_weeks``: a meeting split into several week-pattern events (same label,
pairwise disjoint weeks — e.g. weeks 1–5 in a lab, 6–14 in a classroom) should keep one room.

Within one event the model already uses a single room for every week, so this kind only concerns
week-split events.  Implicit groups = identical label + pairwise disjoint weeks; explicit
``{"event_ids": [...]}`` / ``{"groups": [[...]]}``.  Soft by default."""

from __future__ import annotations

from collections import defaultdict

from app.solver.constraints import _groups
from app.solver.constraints._common import int_list, is_targeted, pairs
from app.solver.context import ModelContext
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event, SolverInput
from app.solver.weights import constraint_weight


def groups_for(inp: SolverInput, c: Constraint) -> dict[str, list[Event]]:
    by_id = {e.id: e for e in inp.events}
    raw = c.params.get("groups")
    if raw:
        return {f"#{c.id or 0}.{i}": [by_id[int(x)] for x in ids if int(x) in by_id] for i, ids in enumerate(raw)}
    if is_targeted(c):
        return {f"#{c.id or 0}": [by_id[i] for i in int_list(c.params, "event_ids") if i in by_id]}
    by_label: dict[str, list[Event]] = defaultdict(list)
    for e in inp.events:
        if e.needs_room:
            by_label[e.label].append(e)
    out: dict[str, list[Event]] = {}
    for label, events in by_label.items():
        if len(events) < 2:
            continue
        if all(a.weeks.isdisjoint(b.weeks) for a, b in pairs(events)):
            out[label] = events
    return out


def apply(ctx: ModelContext, c: Constraint) -> None:
    w = constraint_weight(ctx.inp.weights, "same_room_across_weeks", c.weight)
    for name, events in sorted(groups_for(ctx.inp, c).items()):
        _groups.apply_group(ctx, "same_room_across_weeks", name, events, c.hard, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "same_room_across_weeks", c.weight)
    for name, events in sorted(groups_for(ev.inp, c).items()):
        _groups.score_group(ev, "same_room_across_weeks", name, events, c.hard, w)


__all__ = ["apply", "groups_for", "score"]
