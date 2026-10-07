"""Shared implementation for ``no_cohort_overlap`` and ``no_instructor_overlap``.

Per key (cohort or instructor) and per (day, period) we collect the "event occupies this period"
literals (``True`` for fixed-time events) and post one ``AtMostOne`` per week class.  Fixed-vs-
fixed collisions are detected statically in ``prune`` and recorded on ``doms.static_conflicts``;
fixed-vs-flexible collisions are removed from the flexible event's time options there as well.
"""

from __future__ import annotations

from collections import defaultdict

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
        cells: dict[tuple[int, int], list[tuple[object, frozenset[int]]]] = defaultdict(list)
        for eid in ids:
            dom = ctx.domain(eid)
            weeks = ctx.events_by_id[eid].weeks
            covered: set[tuple[int, int]] = set()
            for t in dom.times:
                for p in t.periods:
                    covered.add((t.day, p))
            for day, p in covered:
                lit = ctx.occupies(eid, day, p)
                if lit is not None:
                    cells[(day, p)].append((lit, weeks))
        g = ctx.guard(f"{guard_prefix}:{key}")
        for (_day, _p), items in sorted(cells.items(), key=lambda kv: kv[0]):
            if len(items) < 2:
                continue
            for group in week_classes(items):
                ctx.add_at_most_one(group, g)


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
