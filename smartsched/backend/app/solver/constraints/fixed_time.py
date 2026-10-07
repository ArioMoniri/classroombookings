"""``fixed_time``: honour ``fixed_day`` / ``fixed_start`` / ``locked`` / allowed days / window.

Implicit hard version: domain enumeration only produces matching time options; locked assignments
are fixed on the model (guard ``locked:<event>``).  ``Constraint("fixed_time", {}, hard=False)``
turns fixed day/start into preferences (penalty 1 per event not at its requested time).  Targeted
form ``{"event_ids": [...], "day": d, "start": s}`` pins (hard) or prefers (soft) that time.
"""

from __future__ import annotations

from app.solver.constraints._common import is_targeted, select_events
from app.solver.context import ModelContext
from app.solver.domains import Domains, TimeOption
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, Event
from app.solver.weights import constraint_weight


def _wanted(c: Constraint, event: Event) -> tuple[int | None, int | None]:
    if is_targeted(c):
        day = c.params.get("day")
        start = c.params.get("start")
        return (int(day) if day is not None else None, int(start) if start is not None else None)
    return event.fixed_day, event.fixed_start


def _matches(t: TimeOption, day: int | None, start: int | None) -> bool:
    return (day is None or t.day == day) and (start is None or t.start == start)


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard or not is_targeted(c):
        return
    for event in select_events(doms.inp, c.params):
        day, start = _wanted(c, event)
        dom = doms.domain(event.id)
        for t in list(dom.times):
            if not _matches(t, day, start):
                dom.remove_time(t, f"outside the required time (fixed_time #{c.id})")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if not is_targeted(c):
        for event in ctx.inp.events:
            if event.locked is not None:
                ctx.fix_assignment(event.locked, ctx.guard(f"locked:{event.id}"))
    if c.hard:
        return
    w = constraint_weight(ctx.inp.weights, "fixed_time", c.weight)
    for event in select_events(ctx.inp, c.params):
        day, start = _wanted(c, event)
        if day is None and start is None:
            continue
        dom = ctx.domain(event.id)
        for ti, t in enumerate(dom.times):
            if not _matches(t, day, start):
                ctx.add_penalty("fixed_time", ctx.time_lit(event.id, ti), 1, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "fixed_time", c.weight)
    targeted = is_targeted(c)
    events = select_events(ev.inp, c.params) if targeted else list(ev.inp.events)
    for event in events:
        a = ev.assignment(event.id)
        if a is None:
            continue
        t = TimeOption(a.day, a.start, a.end - a.start + 1)
        if not targeted:
            # structural checks that are always hard
            if a.end - a.start + 1 != max(1, event.duration):
                ev.hard("fixed_time", [event.id], f"{event.label} spans {a.end - a.start + 1} periods, expected {event.duration}")
            if a.day not in ev.inp.days or a.start < 1 or a.end > ev.inp.periods_per_day:
                ev.hard("fixed_time", [event.id], f"{event.label} is outside the grid (day {a.day}, P{a.start}-P{a.end})")
            if event.locked is not None and (event.locked.day, event.locked.start, tuple(sorted(event.locked.room_ids))) != (a.day, a.start, tuple(sorted(a.room_ids))):
                ev.hard("fixed_time", [event.id], f"{event.label} is locked to day {event.locked.day} P{event.locked.start} rooms {list(event.locked.room_ids)}")
            if c.hard:
                if event.allowed_days and event.fixed_day is None and a.day not in event.allowed_days:
                    ev.hard("fixed_time", [event.id], f"{event.label} is on day {a.day}, allowed {sorted(event.allowed_days)}")
                if a.start < event.earliest_start or a.end > event.latest_end:
                    ev.hard("fixed_time", [event.id], f"{event.label} at P{a.start}-P{a.end} is outside its window P{event.earliest_start}-P{event.latest_end}")
        day, start = _wanted(c, event)
        if day is None and start is None:
            continue
        if _matches(t, day, start):
            continue
        msg = f"{event.label} is at day {a.day} P{a.start}, requested day {day or '*'} P{start or '*'}"
        if c.hard:
            ev.hard("fixed_time", [event.id], msg)
        else:
            ev.soft("fixed_time", [event.id], msg, w)
    if not c.hard:
        for event in events:
            day, start = _wanted(c, event)
            if day is not None or start is not None:
                ev.add_bound("fixed_time", w)


__all__ = ["apply", "prune", "score"]
