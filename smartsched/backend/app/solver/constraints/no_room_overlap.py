"""``no_room_overlap``: at most one event per (room, day, period, week).

Modelled per room *without* per-week copies: every (event, room) option is an optional interval
(presence ``z[e,r]``) on the global period axis; the intervals of a room are grouped into "week
classes" (maximal sets of events whose week sets share a week) and one ``NoOverlap`` is posted per
class.  Two events in disjoint weeks (1–7 vs 8–14) never meet in a class, so they may share the
room.  Blocks are fixed intervals in the same ``NoOverlap`` (and pruned from fixed-time events'
domains beforehand).  Always hard.  Assumption guard per room: ``room:<code>``.
"""

from __future__ import annotations

import os
from collections import defaultdict

from app.solver.constraints._common import pairs, week_classes
from app.solver.context import ModelContext
from app.solver.domains import weeks_intersect
from app.solver.evaluate import Evaluation, room_occupancy
from app.solver.model import Constraint

#: "2d" = one NoOverlap2D per room (time × week runs); "classes" = one NoOverlap per week class
ROOM_ENCODING = os.environ.get("SMARTSCHED_ROOM_ENCODING", "2d")


def apply(ctx: ModelContext, c: Constraint) -> None:
    all_weeks = frozenset(ctx.inp.weeks)
    by_room: dict[int, list[tuple[object, frozenset[int]]]] = defaultdict(list)
    for eid, rid in sorted(ctx.z):
        g = ctx.guard(f"room:{ctx.rooms_by_id[rid].code}")
        iv = ctx.room_interval(eid, rid, g)
        if iv is not None:
            by_room[rid].append((iv, ctx.events_by_id[eid].weeks & all_weeks))
    for b in ctx.inp.blocks:
        if b.room_id not in by_room or b.day not in ctx.day_pos:
            continue
        weeks = all_weeks if b.week is None else frozenset([b.week]) & all_weeks
        by_room[b.room_id].append(
            (ctx.fixed_interval(b.day, b.start, b.end, f"block_{b.room_id}_{b.day}_{b.start}"), weeks)
        )
    for rid in sorted(by_room):
        items = [(iv, w) for iv, w in by_room[rid] if w]
        if ROOM_ENCODING == "classes" or all(w == all_weeks for _, w in items):
            for group in week_classes(items):
                ctx.add_no_overlap(group)
        else:
            ctx.add_no_overlap_2d(items)


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
                    f"{ev.events_by_id[a].label} and {ev.events_by_id[b].label} both "
                    f"use {code} on day {day} P{p} (weeks {shared[0]}..{shared[-1]})",
                    [rid],
                )
    # blocks
    blocks_by_room: dict[int, list[tuple[int | None, int, int, int]]] = defaultdict(list)
    for blk in ev.inp.blocks:
        blocks_by_room[blk.room_id].append((blk.week, blk.day, blk.start, blk.end))
    for eid, asg in ev.by_event.items():
        event = ev.events_by_id[eid]
        for rid in asg.room_ids:
            for week, day, start, end in blocks_by_room.get(rid, []):
                if day != asg.day or start > asg.end or asg.start > end:
                    continue
                if week is not None and week not in event.weeks:
                    continue
                room = ev.rooms_by_id.get(rid)
                code = room.code if room else str(rid)
                ev.hard(
                    "no_room_overlap",
                    [eid],
                    f"{event.label} uses {code} on day {day} P{start}-P{end} which is blocked",
                    [rid],
                )


__all__ = ["apply", "score"]
