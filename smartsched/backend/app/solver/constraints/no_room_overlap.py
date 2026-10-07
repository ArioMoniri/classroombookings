"""``no_room_overlap``: at most one event per (room, day, period, week).

Modelled per (room, day, period) *without* per-week copies: the room literals ``x[e,t,r]`` whose
time option covers the period are grouped into "week classes" (maximal sets of events whose
week sets share a week) and one ``AtMostOne`` is posted per class.  Two events in disjoint weeks
(1–7 vs 8–14) never meet in a class, so they may share the room.  Blocks are enforced by pruning
in :mod:`app.solver.domains`; here they are only *scored*.
Always hard.  Assumption guard per room: ``room:<code>``.
"""

from __future__ import annotations

from collections import defaultdict

from app.solver.constraints._common import pairs, week_classes
from app.solver.context import ModelContext
from app.solver.domains import weeks_intersect
from app.solver.evaluate import Evaluation, room_occupancy
from app.solver.model import Constraint


def apply(ctx: ModelContext, c: Constraint) -> None:
    cells: dict[tuple[int, int, int], list[tuple[object, frozenset[int]]]] = defaultdict(list)
    for (eid, ti, rid), lit in ctx.x.items():
        t = ctx.domain(eid).times[ti]
        weeks = ctx.events_by_id[eid].weeks
        for p in t.periods:
            cells[(rid, t.day, p)].append((lit, weeks))
    for (rid, _day, _p), items in sorted(cells.items(), key=lambda kv: kv[0]):
        if len(items) < 2:
            continue
        g = ctx.guard(f"room:{ctx.rooms_by_id[rid].code}")
        for group in week_classes(items):
            ctx.add_at_most_one(group, g)


def score(ev: Evaluation, c: Constraint) -> None:
    occ = room_occupancy(ev)
    seen: set[tuple[int, int, int]] = set()
    for (rid, day, p), eids in occ.items():
        if len(eids) < 2:
            continue
        for a, b in pairs(sorted(eids)):
            if (rid, a, b) in seen:
                continue
            wa, wb = ev.events_by_id[a].weeks, ev.events_by_id[b].weeks
            if weeks_intersect(wa, wb):
                seen.add((rid, a, b))
                room = ev.rooms_by_id.get(rid)
                code = room.code if room else str(rid)
                shared = sorted(wa & wb)
                ev.hard(
                    "no_room_overlap",
                    [a, b],
                    f"{ev.events_by_id[a].label} and {ev.events_by_id[b].label} both use {code} on day {day} P{p} (weeks {shared[0]}..{shared[-1]})",
                    [rid],
                )
    # blocks
    blocks_by_room: dict[int, list[tuple[int | None, int, int, int, str]]] = defaultdict(list)
    for b in ev.inp.blocks:
        blocks_by_room[b.room_id].append((b.week, b.day, b.start, b.end, b.label))
    for eid, a in ev.by_event.items():
        event = ev.events_by_id[eid]
        for rid in a.room_ids:
            for week, day, start, end, label in blocks_by_room.get(rid, []):
                if day != a.day or start > a.end or a.start > end:
                    continue
                if week is not None and week not in event.weeks:
                    continue
                room = ev.rooms_by_id.get(rid)
                code = room.code if room else str(rid)
                ev.hard("no_room_overlap", [eid], f"{event.label} uses {code} on day {day} P{start}-P{end} which is blocked ({label or 'block'})", [rid])


__all__ = ["apply", "score"]
