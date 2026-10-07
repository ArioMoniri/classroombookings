"""``day_window(program, allowed periods)``: events of a programme/cohort must (hard) or should
(soft) lie inside a period window, e.g. "no lectures after 17:30 for first-year nursing".

Params: selector (``program``/``cohort``/``cohorts``/``match``/``event_ids``; none = all events),
and either ``periods`` (list of allowed periods) or ``earliest``/``latest`` (inclusive), optional
``days`` (restrict to those days).  Soft penalty = number of periods outside the window.
"""

from __future__ import annotations

from app.solver.constraints._common import int_list, select_events
from app.solver.context import ModelContext
from app.solver.domains import Domains, TimeOption
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, SolverInput
from app.solver.weights import constraint_weight


def _allowed(inp: SolverInput, c: Constraint) -> tuple[frozenset[int], frozenset[int]]:
    periods = int_list(c.params, "periods")
    if not periods:
        lo = int(c.params.get("earliest", 1))
        hi = int(c.params.get("latest", inp.periods_per_day))
        periods = list(range(lo, hi + 1))
    days = int_list(c.params, "days") or list(inp.days)
    return frozenset(periods), frozenset(days)


def _outside(t: TimeOption, allowed: frozenset[int], days: frozenset[int]) -> int:
    if t.day not in days:
        return 0
    return sum(1 for p in t.periods if p not in allowed)


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard:
        return
    allowed, days = _allowed(doms.inp, c)
    for event in select_events(doms.inp, c.params):
        dom = doms.domain(event.id)
        for t in list(dom.times):
            if _outside(t, allowed, days):
                dom.remove_time(t, f"outside the allowed day window (day_window #{c.id})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if c.hard:
        return
    allowed, days = _allowed(ctx.inp, c)
    w = constraint_weight(ctx.inp.weights, "day_window", c.weight)
    for event in select_events(ctx.inp, c.params):
        dom = ctx.domain(event.id)
        for ti, t in enumerate(dom.times):
            units = _outside(t, allowed, days)
            if units:
                ctx.add_penalty("day_window", ctx.time_lit(event.id, ti), units, w)


def score(ev: Evaluation, c: Constraint) -> None:
    allowed, days = _allowed(ev.inp, c)
    w = constraint_weight(ev.inp.weights, "day_window", c.weight)
    for event in select_events(ev.inp, c.params):
        if not c.hard:
            ev.add_bound("day_window", max(1, event.duration) * w)
        t = ev.time_of(event.id)
        if t is None:
            continue
        units = _outside(t, allowed, days)
        if not units:
            continue
        msg = f"{event.label} at day {t.day} P{t.start}-P{t.end} leaves the allowed window ({units} period(s))"
        if c.hard:
            ev.hard("day_window", [event.id], msg)
        else:
            ev.soft("day_window", [event.id], msg, units * w)


__all__ = ["apply", "prune", "score"]
