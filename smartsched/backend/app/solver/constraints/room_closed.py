"""``room_closed(room, day, periods, weeks)``: a room is unavailable in the given slots.

Params: ``room_id`` (or ``room`` = code), ``day`` (int or list), ``periods`` (list) or
``start``/``end``, ``weeks`` (list; absent = every week), ``label``.  Hard = converted into
:class:`~app.solver.model.Block` objects and pruned; soft = penalty 1 per event using the room
in a closed slot.
"""

from __future__ import annotations

from app.solver.constraints._common import int_list
from app.solver.context import ModelContext
from app.solver.domains import Domains, TimeOption
from app.solver.evaluate import Evaluation
from app.solver.model import Block, Constraint, SolverInput
from app.solver.weights import constraint_weight


def _blocks(inp: SolverInput, c: Constraint) -> list[Block]:
    rid = c.params.get("room_id")
    if rid is None:
        code = str(c.params.get("room", ""))
        for r in inp.rooms:
            if r.code == code:
                rid = r.id
    if rid is None:
        return []
    days = int_list(c.params, "day") or int_list(c.params, "days") or list(inp.days)
    periods = int_list(c.params, "periods")
    if not periods:
        start = int(c.params.get("start", 1))
        end = int(c.params.get("end", inp.periods_per_day))
        periods = list(range(start, end + 1))
    weeks: list[int | None] = list(int_list(c.params, "weeks")) or [None]
    out: list[Block] = []
    for day in days:
        for w in weeks:
            out.append(Block(int(rid), w, day, min(periods), max(periods)))
    return out


def prune(doms: Domains, c: Constraint) -> None:
    if not c.hard:
        return
    for b in _blocks(doms.inp, c):
        doms.add_block(b, f"room_closed #{c.id}")


def apply(ctx: ModelContext, c: Constraint) -> None:
    if c.hard:
        return
    w = constraint_weight(ctx.inp.weights, "room_closed", c.weight)
    blocks = _blocks(ctx.inp, c)
    for (eid, rid), z in ctx.z.items():
        dom = ctx.domain(eid)
        weeks = ctx.events_by_id[eid].weeks
        for ti, t in enumerate(dom.times):
            if any(
                b.room_id == rid
                and b.day == t.day
                and t.start <= b.end
                and b.start <= t.end
                and (b.week is None or b.week in weeks)
                for b in blocks
            ):
                ctx.add_penalty("room_closed", ctx.and_lit(ctx.time_lit(eid, ti), z), 1, w)


def score(ev: Evaluation, c: Constraint) -> None:
    w = constraint_weight(ev.inp.weights, "room_closed", c.weight)
    blocks = _blocks(ev.inp, c)
    if not blocks:
        return
    if not c.hard:
        ev.add_bound("room_closed", len(ev.inp.events) * w)
    for eid, a in ev.by_event.items():
        event = ev.events_by_id[eid]
        t = TimeOption(a.day, a.start, a.end - a.start + 1)
        for b in blocks:
            if (
                b.room_id in a.room_ids
                and b.day == t.day
                and t.start <= b.end
                and b.start <= t.end
                and (b.week is None or b.week in event.weeks)
            ):
                code = ev.rooms_by_id[b.room_id].code if b.room_id in ev.rooms_by_id else str(b.room_id)
                msg = (
                    f"{event.label} uses {code} on day {b.day} P{b.start}-P{b.end} "
                    f"while it is closed ({c.params.get('label', 'room_closed')})"
                )
                if c.hard:
                    ev.hard("room_closed", [eid], msg, [b.room_id])
                else:
                    ev.soft("room_closed", [eid], msg, w, [b.room_id])
                break


__all__ = ["apply", "prune", "score"]
