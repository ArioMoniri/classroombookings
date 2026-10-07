"""``max_exams_per_day(cohort, n)``: at most ``n`` exams per day for a cohort (per week).

Params: ``n`` (default 2), optional ``cohort``/``cohorts``, ``kinds`` (default ``["exam"]``).
Hard: ``Σ on_day ≤ n`` per (cohort, day, week class), guard ``max_exams_per_day:<cohort>``.
Soft: one penalty per exam above ``n``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.solver.constraints._common import select_events, str_list, week_classes
from app.solver.context import HintView, ModelContext
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event, SolverInput
from app.solver.weights import constraint_weight


def _limit(c: Constraint) -> int:
    return max(0, int(c.params.get("n", c.params.get("max", 2))))


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
    return {k: v for k, v in groups.items() if len(v) > _limit(c)}


def _eval_excess(ctx: ModelContext, group: list[Any], n: int) -> Callable[[HintView], int]:
    return lambda h: max(0, sum(ctx.lit_value(x, h) for x in group) - n)


def apply(ctx: ModelContext, c: Constraint) -> None:
    n = _limit(c)
    w = constraint_weight(ctx.inp.weights, "max_exams_per_day", c.weight)
    for key, events in sorted(_cohorts(ctx.inp, c).items()):
        g = ctx.guard(f"max_exams_per_day:{key}")
        for day in ctx.inp.days:
            items = []
            for e in events:
                lit = ctx.on_day(e.id, day)
                if lit is not None:
                    items.append((lit, e.weeks))
            for group in week_classes(items):
                consts = sum(1 for lit in group if lit is True)
                vars_ = [lit for lit in group if lit is not True]
                if c.hard:
                    if consts > n:
                        ctx.add_false(g)
                    elif vars_:
                        ctx.add_linear_le(sum(vars_), n - consts, g)
                    continue
                excess = ctx.new_int(f"excess_{key}_{day}_{len(ctx.terms)}", 0, len(group))
                ctx.model.Add(excess >= sum(vars_) + consts - n)
                ctx.derive(excess, _eval_excess(ctx, list(group), n))
                ctx.add_penalty("max_exams_per_day", excess, 1, w)


def score(ev: Evaluation, c: Constraint) -> None:
    n = _limit(c)
    w = constraint_weight(ev.inp.weights, "max_exams_per_day", c.weight)
    for key, events in sorted(_cohorts(ev.inp, c).items()):
        if not c.hard:
            ev.add_bound("max_exams_per_day", (len(events) - n) * w)
        per: dict[tuple[int, int], list[int]] = defaultdict(list)
        for e in events:
            a = ev.assignment(e.id)
            if a is None:
                continue
            for wk in e.weeks:
                per[(wk, a.day)].append(e.id)
        reported: set[tuple[int, ...]] = set()
        for (wk, day), ids in sorted(per.items()):
            if len(ids) <= n:
                continue
            sig = tuple(sorted(ids))
            if sig in reported:
                continue
            reported.add(sig)
            labels = ", ".join(ev.events_by_id[i].label for i in ids)
            msg = f"cohort '{key}' has {len(ids)} exams on day {day} of week {wk} (max {n}): {labels}"
            if c.hard:
                ev.hard("max_exams_per_day", list(ids), msg)
            else:
                ev.soft("max_exams_per_day", list(ids), msg, (len(ids) - n) * w)


__all__ = ["apply", "score"]
