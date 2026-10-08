"""Shared implementation for ``no_cohort_overlap`` and ``no_instructor_overlap``.

Per key (cohort or instructor) the events' intervals (fixed start for fixed-time events, the
``start[e]`` variable otherwise) go into one ``NoOverlap`` per week class.  Fixed-vs-fixed
collisions are detected statically in ``prune`` and recorded on ``doms.static_conflicts``;
fixed-vs-flexible collisions are removed from the flexible event's time options there as well.
"""

from __future__ import annotations

from app.solver.constraints._common import pairs, week_classes
from app.solver.context import ModelContext
from app.solver.domains import Domains, is_input_fixed, prune_fixed_key_conflicts, weeks_intersect
from app.solver.evaluate import Evaluation


def prune_keys(doms: Domains, groups: dict[str, list[int]], kind: str, label: str) -> None:
    waive = doms.inp.fixed_conflicts_as_warnings
    seen = set(doms.static_conflicts) | set(doms.waived_conflicts)
    for key, a, b in prune_fixed_key_conflicts(doms, groups, label, record_as=kind):
        item = (kind, key, a, b)
        if item in seen:
            continue  # the same key configured twice (default + targeted constraint)
        seen.add(item)
        ea, eb = doms.events_by_id[a], doms.events_by_id[b]
        if waive and is_input_fixed(ea, doms.soft) and is_input_fixed(eb, doms.soft):
            doms.waived_conflicts.append(item)
        else:
            doms.static_conflicts.append(item)


def apply_keys(ctx: ModelContext, groups: dict[str, list[int]], kind: str, guard_prefix: str) -> None:
    """One NoOverlap per (key, week class) over the key's *flexible* events.  Events that were fixed
    when the key was pruned are left out: fixed-vs-flexible overlaps were removed from the flexible
    domains, and fixed-vs-fixed overlaps are known pairs — each gets an explicit "not both placed"
    clause, unless ``fixed_conflicts_as_warnings`` waived it (then the pair is simply not related)."""
    clashes: dict[str, list[tuple[int, int]]] = {}
    for k, key, a, b in ctx.doms.static_conflicts:
        if k == kind:
            clashes.setdefault(key, []).append((a, b))
    for key in sorted(groups):
        ids = groups[key]
        if len(ids) < 2:
            continue
        g = ctx.guard(f"{guard_prefix}:{key}")
        fixed = ctx.doms.key_fixed.get((kind, key), frozenset())
        items: list[tuple[object, frozenset[int]]] = []
        for eid in ids:
            if eid in fixed or not ctx.domain(eid).times:
                continue
            items.append((ctx.event_interval(eid, g), ctx.events_by_id[eid].weeks))
        for group in week_classes(items):
            ctx.add_no_overlap(group)
        for a, b in clashes.get(key, []):
            ctx.add_not_both(ctx.placed.get(a, True), ctx.placed.get(b, True), g)


def score_keys(ev: Evaluation, groups: dict[str, list[int]], kind: str, noun: str) -> None:
    for key in sorted(groups):
        ids = [i for i in groups[key] if i in ev.by_event]
        for a, b in pairs(ids):
            ta, tb = ev.time_of(a), ev.time_of(b)
            if ta is None or tb is None or not ta.overlaps(tb):
                continue
            if not weeks_intersect(ev.events_by_id[a].weeks, ev.events_by_id[b].weeks):
                continue
            if ev.waived_pair(a, b):
                continue  # fixed_conflicts_as_warnings: an input conflict, reported by the static check
            ev.hard(
                kind,
                [a, b],
                f"{noun} '{key}': {ev.events_by_id[a].label} and {ev.events_by_id[b].label} "
                f"overlap on day {ta.day} (P{max(ta.start, tb.start)}-P{min(ta.end, tb.end)})",
            )
