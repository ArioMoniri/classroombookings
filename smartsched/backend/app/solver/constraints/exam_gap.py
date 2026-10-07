"""``exam_gap(cohort, min_periods)``: two exams of the same cohort on the same day must be at
least ``min_periods`` free periods apart.

Params: ``min_periods`` (default 2), optional ``cohort``/``cohorts`` (default: every cohort key),
``kinds`` (default ``["exam"]``).  Encoding: for each event *a* we take its *extended* occupancy
literal ``ext[a, d, p]`` (true when *a* occupies a period within ``min_periods`` of *p*); for every
other event *b* of the cohort and every period *p* we forbid ``ext[a,d,p] ∧ occ[b,d,p]`` (hard, guard
``exam_gap:<cohort>``) or charge one penalty per (pair, day) (soft).  Only pairs with intersecting
weeks are considered.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.solver.constraints._common import pairs, select_events, str_list
from app.solver.context import HintView, Lit, ModelContext
from app.solver.domains import weeks_intersect
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event, SolverInput
from app.solver.weights import constraint_weight


def _min_gap(c: Constraint) -> int:
    return max(0, int(c.params.get("min_periods", 2)))


def _cohorts(inp: SolverInput, c: Constraint) -> dict[str, list[Event]]:
    params = dict(c.params)
    params.setdefault("kinds", ["exam"])
    wanted = set(str_list(params, "cohort") + str_list(params, "cohorts"))
    params.pop("cohort", None)
    params.pop("cohorts", None)
    groups: dict[str, list[Event]] = defaultdict(list)
    for e in select_events(inp, params):
        for k in e.cohort_keys:
            if not wanted or k in wanted:
                groups[k].append(e)
    return {k: v for k, v in groups.items() if len(v) >= 2}


def _ext(
    ctx: ModelContext, cache: dict[tuple[int, int, int], Lit | None], eid: int, day: int, p: int, margin: int
) -> Lit | None:
    key = (eid, day, p)
    if key in cache:
        return cache[key]
    dom = ctx.domain(eid)
    lits = [
        ctx.time_lit(eid, ti)
        for ti, t in enumerate(dom.times)
        if t.day == day and t.start - margin <= p <= t.end + margin
    ]
    res: Lit | None
    if not lits:
        res = None
    elif any(lit is True for lit in lits):
        res = True
    elif len(lits) == 1:
        res = lits[0]
    else:
        v = ctx.new_bool(f"ext_{eid}_{day}_{p}")
        ctx.model.AddMaxEquality(v, lits)
        ctx.derive(v, _eval_max(ctx, list(lits)))
        res = v
    cache[key] = res
    return res


def _eval_gap(a: Event, b: Event, day: int, gap: int) -> Callable[[HintView], int]:
    def fn(h: HintView) -> int:
        ta, tb = h.time(a.id), h.time(b.id)
        if ta is None or tb is None or ta.day != day or tb.day != day:
            return 0
        return int(max(tb.start - ta.end - 1, ta.start - tb.end - 1) < gap)

    return fn


def _eval_max(ctx: ModelContext, lits: list[Any]) -> Callable[[HintView], int]:
    return lambda h: max(ctx.lit_value(x, h) for x in lits)


def apply(ctx: ModelContext, c: Constraint) -> None:
    gap = _min_gap(c)
    w = constraint_weight(ctx.inp.weights, "exam_gap", c.weight)
    cache: dict[tuple[int, int, int], Lit | None] = {}
    for key, events in sorted(_cohorts(ctx.inp, c).items()):
        g = ctx.guard(f"exam_gap:{key}")
        for a, b in pairs(events):
            if not weeks_intersect(a.weeks, b.weeks):
                continue
            days = {t.day for t in ctx.domain(a.id).times} & {t.day for t in ctx.domain(b.id).times}
            for day in sorted(days):
                pen = None
                for p in range(1, ctx.inp.periods_per_day + 1):
                    occ_b = ctx.occupies(b.id, day, p)
                    if occ_b is None:
                        continue
                    ext_a = _ext(ctx, cache, a.id, day, p, gap)
                    if ext_a is None:
                        continue
                    if c.hard:
                        ctx.add_not_both(ext_a, occ_b, g)
                        continue
                    if pen is None:
                        pen = ctx.new_bool(f"gap_{a.id}_{b.id}_{day}")
                        ctx.add_penalty("exam_gap", pen, 1, w)
                        ctx.derive(pen, _eval_gap(a, b, day, gap))
                    if ext_a is True and occ_b is True:
                        ctx.model.Add(pen == 1)
                    elif ext_a is True:
                        ctx.model.AddImplication(occ_b, pen)
                    elif occ_b is True:
                        ctx.model.AddImplication(ext_a, pen)
                    else:
                        ctx.model.AddBoolOr([ext_a.Not(), occ_b.Not(), pen])


def score(ev: Evaluation, c: Constraint) -> None:
    gap = _min_gap(c)
    w = constraint_weight(ev.inp.weights, "exam_gap", c.weight)
    for key, events in sorted(_cohorts(ev.inp, c).items()):
        for a, b in pairs(events):
            if not weeks_intersect(a.weeks, b.weeks):
                continue
            if not c.hard:
                ev.add_bound("exam_gap", w)
            ta, tb = ev.time_of(a.id), ev.time_of(b.id)
            if ta is None or tb is None or ta.day != tb.day:
                continue
            free = max(tb.start - ta.end - 1, ta.start - tb.end - 1)
            if free >= gap:
                continue
            msg = (
                f"cohort '{key}': {a.label} and {b.label} are {max(0, free)} "
                f"period(s) apart on day {ta.day} (minimum {gap})"
            )
            if c.hard:
                ev.hard("exam_gap", [a.id, b.id], msg)
            else:
                ev.soft("exam_gap", [a.id, b.id], msg, w)


__all__ = ["apply", "score"]
