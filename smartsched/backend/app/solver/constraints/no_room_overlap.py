"""``no_room_overlap``: at most one event per (room, day, period, week).

Modelled per room *without* per-week copies: every (event, room) option is an optional interval
(presence ``z[e,r]``) on the global period axis.  Exclusive events go into one ``NoOverlap2D`` per
room (time × week runs; ``SMARTSCHED_ROOM_ENCODING=classes`` uses one ``NoOverlap`` per week class
instead).  Two events in disjoint weeks (1–7 vs 8–14) never meet, so they may share the room.
Blocks are fixed intervals in the same constraint (and pruned from fixed-time events' domains).

``Event.share_room`` (small exams invigilated together): sharing events in a room are limited by a
``Cumulative`` per (room, week class) — demand = event size, capacity = the room's exam capacity
(lecture capacity if no sharing event is an exam); exclusive events and blocks enter it with demand
= capacity, so a non-sharing event in a room-period excludes everything else.
Always hard.  Assumption guard per room: ``room:<code>``.
"""

from __future__ import annotations

import os
from collections import defaultdict

from app.solver.constraints._common import pairs, week_classes
from app.solver.context import ModelContext
from app.solver.domains import effective_capacity, shares_room, sharing_capacity, weeks_intersect
from app.solver.evaluate import Evaluation, room_occupancy
from app.solver.model import Constraint, Event

#: "2d" = one NoOverlap2D per room (time × week runs); "classes" = one NoOverlap per week class
ROOM_ENCODING = os.environ.get("SMARTSCHED_ROOM_ENCODING", "2d")


def apply(ctx: ModelContext, c: Constraint) -> None:
    all_weeks = frozenset(ctx.inp.weeks)
    exclusive: dict[int, list[tuple[object, frozenset[int]]]] = defaultdict(list)
    sharing: dict[int, list[tuple[object, frozenset[int], Event]]] = defaultdict(list)
    for eid, rid in sorted(ctx.z):
        g = ctx.guard(f"room:{ctx.rooms_by_id[rid].code}")
        iv = ctx.room_interval(eid, rid, g)
        event = ctx.events_by_id[eid]
        if iv is None:
            continue
        if shares_room(event):
            sharing[rid].append((iv, event.weeks & all_weeks, event))
        else:
            exclusive[rid].append((iv, event.weeks & all_weeks))
    for b in ctx.inp.blocks:
        if b.room_id not in ctx.rooms_by_id or b.day not in ctx.day_pos:
            continue
        weeks = all_weeks if b.week is None else frozenset([b.week]) & all_weeks
        exclusive[b.room_id].append(
            (ctx.fixed_interval(b.day, b.start, b.end, f"block_{b.room_id}_{b.day}_{b.start}"), weeks)
        )
    for rid in sorted(set(exclusive) | set(sharing)):
        items = [(iv, w) for iv, w in exclusive.get(rid, []) if w]
        if ROOM_ENCODING == "classes" or all(w == all_weeks for _, w in items):
            for group in week_classes(items):
                ctx.add_no_overlap(group)
        else:
            ctx.add_no_overlap_2d(items)
        shared = [(iv, w, e) for iv, w, e in sharing.get(rid, []) if w]
        if not shared:
            continue
        room = ctx.rooms_by_id[rid]
        cap = sharing_capacity(room, [e for _, _, e in shared])
        entries: list[tuple[tuple[object, int], frozenset[int]]] = [((iv, e.size), w) for iv, w, e in shared]
        entries += [((iv, cap), w) for iv, w in items]
        for group in week_classes(entries):
            ctx.model.AddCumulative([iv for iv, _ in group], [d for _, d in group], cap)


def score(ev: Evaluation, c: Constraint) -> None:
    occ = room_occupancy(ev)
    seen: set[tuple[int, int, int]] = set()
    seen_share: set[tuple[int, int, int, tuple[int, ...]]] = set()
    for (rid, day, p), eids in occ.items():
        if len(eids) < 2:
            continue
        sharers = [i for i in eids if shares_room(ev.events_by_id[i])]
        if len(sharers) >= 2 and rid in ev.rooms_by_id:
            # seat budget per week among sharing events
            room = ev.rooms_by_id[rid]
            cap = sharing_capacity(room, [ev.events_by_id[i] for i in sharers])
            for wk in ev.inp.weeks:
                ids = tuple(sorted(i for i in sharers if wk in ev.events_by_id[i].weeks))
                total = sum(ev.events_by_id[i].size for i in ids)
                if len(ids) >= 2 and total > cap and (rid, day, p, ids) not in seen_share:
                    seen_share.add((rid, day, p, ids))
                    labels = ", ".join(f"{ev.events_by_id[i].label} ({ev.events_by_id[i].size})" for i in ids)
                    ev.hard(
                        "no_room_overlap",
                        list(ids),
                        f"shared room {room.code} on day {day} P{p} (week {wk}) seats {cap} but holds {total}: {labels}",
                        [rid],
                    )
        for a, b in pairs(sorted(eids)):
            if shares_room(ev.events_by_id[a]) and shares_room(ev.events_by_id[b]):
                continue
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
