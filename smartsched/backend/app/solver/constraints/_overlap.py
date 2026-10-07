"""Shared implementation for ``no_cohort_overlap`` and ``no_instructor_overlap``.

Per key (cohort or instructor) the events' intervals (fixed start for fixed-time events, the
``start[e]`` variable otherwise) go into one ``NoOverlap`` per week class.  Fixed-vs-fixed
collisions are detected statically in ``prune`` and recorded on ``doms.static_conflicts``;
fixed-vs-flexible collisions are removed from the flexible event's time options there as well.
"""

from __future__ import annotations

from app.solver.constraints._common import pairs, week_classes
from app.solver.context import ModelContext
from app.solver.domains import Domains, prune_fixed_key_conflicts, weeks_intersect
from app.solver.evaluate import Evaluation


def prune_keys(doms: Domains, groups: dict[str, list[int]], kind: str, label: str) -> None:
    for key, a, b in prune_fixed_key_conflicts(doms, groups, label):
        doms.static_conflicts.append((kind, key, a, b))


def apply_keys(ctx: ModelContext, groups: dict[str, list[int]], kind: str, guard_prefix: str) -> None:
    for key in sorted(groups):
        ids = groups[key]
        if len(ids) < 2:
            continue
        g = ctx.guard(f"{guard_prefix}:{key}")
        items: list[tuple[object, frozenset[int]]] = []
        for eid in ids:
            if not ctx.domain(eid).times:
                continue
            items.append((ctx.event_interval(eid, g), ctx.events_by_id[eid].weeks))
        for group in week_classes(items):
            ctx.add_no_overlap(group)


def score_keys(ev: Evaluation, groups: dict[str, list[int]], kind: str, noun: str) -> None:
    for key in sorted(groups):
        ids = [i for i in groups[key] if i in ev.by_event]
        for a, b in pairs(ids):
            ta, tb = ev.time_of(a), ev.time_of(b)
            if ta is None or tb is None or not ta.overlaps(tb):
                continue
            if not weeks_intersect(ev.events_by_id[a].weeks, ev.events_by_id[b].weeks):
                continue
            ev.hard(
                kind,
                [a, b],
                f"{noun} '{key}': {ev.events_by_id[a].label} and {ev.events_by_id[b].label} overlap on day {ta.day} (P{max(ta.start, tb.start)}-P{min(ta.end, tb.end)})",
            )
