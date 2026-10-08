"""Week segments for term runs (``split_blocked_weeks``).

The solver models a request as *one* event over all its weeks with *one* room set.  On a term run a
single blocked week (an ETKİNLİK cell or an exam in the planner's grid, a ``room_closed`` week, another
planner lock that holds the room only in some weeks) then excludes the room for the whole term: the
Bahar term lost 14 locked lectures (``locked_ineligible``) and 11 fixed-time ones (``no_room``) that way.

This preprocessing step splits such an event into **week segments**: the same day and periods in every
week, a room change only in the affected weeks.

* **Locked event** whose locked room is blocked (or held by another lock) in some of its weeks: the
  original event keeps the planner's lock for the unaffected weeks; the affected weeks become unlocked
  segments at the same time (the planner's rooms first in their preferences).  A segment needs seats
  for the full size: the planner's room is not available in those weeks, so the trust in the planner's
  (too small) room does not carry over to another room (review MINOR: clip only for the planner's room).
* **Fixed-time event without a lock** for which no eligible room is free in *every* week: the weeks
  are partitioned by a greedy maximum cover (the room free in most weeks takes them, then the next), so
  the room changes only where it must.  The largest segment keeps the event id.

Segments get new (negative) ids, labels ``"<label> [w9]"`` and inherit every key, tag and group of the
event; explicit constraints naming the event (``event_ids`` / ``groups``) name its segments too, and
``previous`` assignments are re-keyed by weeks.  All segments of one event form a soft
``same_room_across_weeks`` group, so the solver still prefers one room for all weeks.  Every split is
reported (``week_split`` warning with the kept / moved weeks and the reason), never silent.

Flexible events (no fixed time), exams and single-week events are left alone: the solver moves their
time instead.  Pure function, deterministic; idempotent on its own output.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from app.solver.constraints import effective_constraints
from app.solver.constraints._common import int_list, week_runs
from app.solver.constraints.room_closed import _blocks as room_closed_blocks
from app.solver.domains import _room_options, effective_capacity, normalize_input, shares_room
from app.solver.model import Assignment, Block, Constraint, Diagnosis, Event, SolverInput, SolverResult

#: the ``reason`` values of a ``week_split`` diagnosis
REASON_BLOCKED = "blocked"  # the planner's grid / a room_closed rule blocks the locked room
REASON_LOCK_CLASH = "locked_clash"  # another planner lock holds the room in those weeks
REASON_NO_COMMON_ROOM = "no_common_room"  # no eligible room is free in every week
REASON_ROOM_CHANGES = "room_availability_changes"  # the free rooms differ between weeks (blocks, locks)
REASON_RESIDUAL = "no_room_all_weeks"  # unplaced by the solve: no room free in all weeks given the rest

#: an unlocked event is split by week "profile" (the set of unavailable eligible rooms) up to this many
#: segments; beyond, the greedy cover gives the fewest segments that each keep one free room
MAX_PROFILE_SEGMENTS = 4


@dataclass
class WeekSplit:
    inp: SolverInput
    #: segment id -> original event id (new segment ids only; the original id stays its own origin)
    origin: dict[int, int] = field(default_factory=dict)
    #: original event id -> all its event ids, the original first
    segments: dict[int, list[int]] = field(default_factory=dict)
    diagnoses: list[Diagnosis] = field(default_factory=list)
    #: event id -> forbidden tags without its lock (the bridge clears ``TIP`` for locked events)
    forbid: dict[int, frozenset[str]] = field(default_factory=dict)

    def origin_of(self, event_id: int) -> int:
        return self.origin.get(event_id, event_id)


def weeks_text(weeks: Iterable[int]) -> str:
    runs = week_runs(frozenset(weeks))
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)


_SEG_SUFFIX = re.compile(r" \[w[0-9, -]+\]$")


def _base_label(label: str) -> str:
    return _SEG_SUFFIX.sub("", label)


def seg_label(label: str, weeks: Iterable[int]) -> str:
    """``"MAT 112 §1 [w9]"`` — the label of a week segment."""
    return f"{_base_label(label)} [w{weeks_text(weeks)}]"


@dataclass(frozen=True)
class _Slot:
    day: int
    start: int
    end: int

    def overlaps(self, day: int, start: int, end: int) -> bool:
        return self.day == day and self.start <= end and start <= self.end


def _fixed_slot(e: Event, fixed_soft: bool) -> _Slot | None:
    if e.locked is not None:
        return _Slot(e.locked.day, e.locked.start, e.locked.start + max(1, e.duration) - 1)
    if fixed_soft or e.fixed_day is None or e.fixed_start is None:
        return None
    return _Slot(e.fixed_day, e.fixed_start, e.fixed_start + max(1, e.duration) - 1)


class _Occupancy:
    """Static room occupation per week: blocks + the rooms of locked (non-sharing) events."""

    def __init__(self, inp: SolverInput, blocks: list[Block]) -> None:
        self.weeks = tuple(inp.weeks)
        self.blocks: dict[int, list[Block]] = defaultdict(list)
        for b in blocks:
            self.blocks[b.room_id].append(b)
        #: room -> event id -> (slot, weeks)
        self.locks: dict[int, dict[int, tuple[_Slot, frozenset[int]]]] = defaultdict(dict)

    def add_lock(self, e: Event, slot: _Slot, weeks: frozenset[int]) -> None:
        assert e.locked is not None
        for r in e.locked.room_ids:
            self.locks[r][e.id] = (slot, weeks)

    def blocked_weeks(self, room: int, slot: _Slot, weeks: frozenset[int]) -> set[int]:
        out: set[int] = set()
        for b in self.blocks.get(room, ()):
            if slot.overlaps(b.day, b.start, b.end):
                out |= set(weeks) if b.week is None else ({b.week} & weeks)
        return out

    def held_weeks(self, room: int, slot: _Slot, weeks: frozenset[int], skip: int) -> dict[int, set[int]]:
        """week -> ids of other locked events holding ``room`` at ``slot``."""
        out: dict[int, set[int]] = defaultdict(set)
        for eid, (s, w) in self.locks.get(room, {}).items():
            if eid != skip and s.overlaps(slot.day, slot.start, slot.end):
                for wk in w & weeks:
                    out[wk].add(eid)
        return out

    def free(self, room: int, slot: _Slot, weeks: frozenset[int], skip: int) -> set[int]:
        busy = self.blocked_weeks(room, slot, weeks) | set(self.held_weeks(room, slot, weeks, skip))
        return set(weeks) - busy


def _cover(weeks: frozenset[int], free: dict[int, set[int]], order: list[int]) -> tuple[list[set[int]], set[int]]:
    """Greedy maximum cover of ``weeks`` by rooms (``free[room]`` = weeks the room is free); ties go to
    the earlier room in ``order``.  Returns (week groups, weeks no room covers)."""
    left = set(weeks)
    groups: list[set[int]] = []
    while left:
        best, best_cover = None, set()
        for r in order:
            c = free.get(r, set()) & left
            if len(c) > len(best_cover):
                best, best_cover = r, c
        if best is None:
            break
        groups.append(best_cover)
        left -= best_cover
    return groups, left


def split_blocked_weeks(
    inp: SolverInput,
    *,
    unlocked_forbidden_tags: Mapping[int, frozenset[str]] | None = None,
    profile_split: bool = False,
) -> WeekSplit:
    """Split term events around the weeks in which their room cannot be kept (see the module doc).

    ``unlocked_forbidden_tags``: forbidden tags an event would have without its lock (the bridge clears
    ``TIP`` for locked events); used for the unlocked segments.  ``profile_split`` also splits unlocked
    fixed-time events whose set of free rooms merely *changes* between weeks (more freedom, a larger
    model; off by default — :func:`solve_segmented` splits the events that actually end up unplaced).
    Returns ``WeekSplit`` with ``inp`` unchanged when nothing needs splitting."""
    inp = normalize_input(inp)
    constraints, _w, soft = effective_constraints(inp)
    fixed_soft = "fixed_time" in soft
    blocks = list(inp.blocks)
    for c in constraints:
        if c.kind == "room_closed" and c.hard:
            blocks.extend(room_closed_blocks(inp, c))
    occ = _Occupancy(inp, blocks)
    rooms_by_id = {r.id: r for r in inp.rooms}
    room_order = [r.id for r in inp.rooms]
    forbid = dict(unlocked_forbidden_tags or {})

    for e in inp.events:
        if e.locked is not None and e.needs_room and not shares_room(e):
            slot = _fixed_slot(e, fixed_soft)
            assert slot is not None
            occ.add_lock(e, slot, e.weeks)

    next_id = min([0, *(e.id for e in inp.events)]) - 1
    replaced: dict[int, list[Event]] = {}
    diags: list[Diagnosis] = []

    def new_id() -> int:
        nonlocal next_id
        nid = next_id
        next_id -= 1
        return nid

    def free_by_room(proto: Event, slot: _Slot, weeks: frozenset[int]) -> tuple[dict[int, set[int]], list[int]]:
        eligible, _reasons = _room_options(proto, inp, soft)
        pref = [r for r in proto.preferred_room_ids if r in eligible]
        order = pref + [r for r in room_order if r in eligible and r not in pref]
        return {r: occ.free(r, slot, weeks, proto.id) for r in order}, order

    def unlocked_segments(proto: Event, slot: _Slot, weeks: frozenset[int]) -> tuple[list[set[int]], set[int]]:
        """Partition ``weeks`` for an unlocked fixed-time event: weeks with the same set of unavailable
        eligible rooms form one segment (so the solver may change the room exactly where the room
        situation changes); more than ``MAX_PROFILE_SEGMENTS`` profiles fall back to the greedy cover
        (fewest segments that each have a common free room).  Returns (segments, weeks without any
        free eligible room)."""
        free, order = free_by_room(proto, slot, weeks)
        uncovered = {w for w in weeks if not any(w in f for f in free.values())}
        profile: dict[frozenset[int], set[int]] = defaultdict(set)
        for w in sorted(weeks - uncovered):
            profile[frozenset(r for r in order if w not in free[r])].add(w)
        groups = list(profile.values())
        if not profile_split or len(groups) > MAX_PROFILE_SEGMENTS:
            groups, _left = _cover(frozenset(weeks - uncovered), free, order)
        if uncovered:
            groups.append(set(uncovered))  # no room at all in these weeks: kept together, reported unplaced
        groups.sort(key=lambda g: (-len(g), min(g)))
        return groups, uncovered

    # 1) locked events whose room is blocked / held by another lock in some weeks (most weeks first:
    #    the longer lock yields, so a one-week special event keeps the room it was locked to)
    locked = sorted(
        (e for e in inp.events if e.locked is not None and e.needs_room and not shares_room(e) and len(e.weeks) > 1),
        key=lambda e: (-len(e.weeks), e.id),
    )
    for e in locked:
        assert e.locked is not None
        slot = _fixed_slot(e, fixed_soft)
        assert slot is not None
        rooms = [r for r in e.locked.room_ids if r in rooms_by_id]
        if not rooms:
            continue
        blocked: set[int] = set()
        clash: dict[int, set[int]] = defaultdict(set)
        hit: list[int] = []  # the locked rooms that are not free in some week
        for r in rooms:
            b = occ.blocked_weeks(r, slot, e.weeks)
            held = occ.held_weeks(r, slot, e.weeks, e.id)
            blocked |= b
            for wk, ids in held.items():
                clash[wk] |= ids
            if b or held:
                hit.append(r)
        bad = blocked | set(clash)
        if not bad or bad >= e.weeks:
            continue  # nothing to split, or the room is never free (the static checker explains it)
        kept = frozenset(e.weeks - bad)
        moved = frozenset(bad)
        main = replace(e, weeks=kept, locked=replace(e.locked, weeks=kept))
        occ.add_lock(main, slot, kept)
        size = e.size  # another room in the moved weeks must seat everyone (no trust outside the planner's room)
        proto = replace(
            e,
            locked=None,
            fixed_day=slot.day,
            fixed_start=slot.start,
            allowed_days=frozenset({slot.day}),
            weeks=moved,
            size=size,
            forbidden_tags=forbid.get(e.id, e.forbidden_tags),
            preferred_room_ids=tuple(dict.fromkeys([*rooms, *e.preferred_room_ids])),
        )
        moved_groups, moved_uncovered = unlocked_segments(proto, slot, moved)
        segs = [replace(proto, id=new_id(), weeks=frozenset(g), label=seg_label(e.label, g)) for g in moved_groups]
        replaced[e.id] = [main, *segs]
        reason = REASON_BLOCKED if blocked else REASON_LOCK_CLASH
        codes = ", ".join(rooms_by_id[r].code for r in rooms)
        hit_codes = ", ".join(rooms_by_id[r].code for r in hit)
        why = []
        if blocked:
            why.append(f"blocked by the grid in week(s) {weeks_text(blocked)}")
        if clash:
            others = sorted({i for ids in clash.values() for i in ids})
            labels = ", ".join(next((x.label for x in inp.events if x.id == i), f"#{i}") for i in others[:3])
            why.append(f"held by another locked request ({labels}) in week(s) {weeks_text(clash)}")
        diags.append(
            Diagnosis(
                [e.id],
                ["same_room_across_weeks"],
                f"{e.label} keeps {codes} in week(s) {weeks_text(kept)}; {hit_codes} "
                + ("is " if len(hit) == 1 else "are ")
                + " and ".join(why)
                + f", so week(s) {weeks_text(moved)} get another room at the same time",
                [
                    f"release the block on {hit_codes} in week(s) {weeks_text(moved)} to keep one room all term",
                    "accept the room change for those weeks",
                ],
                "warning",
                "week_split",
                {
                    "reason": reason,
                    "rooms": rooms,
                    "room_codes": [rooms_by_id[r].code for r in rooms],
                    "affected_rooms": hit,
                    "kept_weeks": sorted(kept),
                    "moved_weeks": sorted(moved),
                    "blocked_weeks": sorted(blocked),
                    "clash_weeks": sorted(clash),
                    "clash_ids": sorted({i for ids in clash.values() for i in ids}),
                    "uncovered_weeks": sorted(moved_uncovered),
                    "segments": [s.id for s in segs],
                },
            )
        )

    # 2) fixed-time events without a lock whose free rooms differ between weeks
    for e in inp.events:
        if e.locked is not None or e.id in replaced or not e.needs_room or shares_room(e) or len(e.weeks) < 2:
            continue
        slot = _fixed_slot(e, fixed_soft)
        if slot is None:
            continue
        groups, uncovered = unlocked_segments(e, slot, e.weeks)
        if len(groups) < 2:
            continue  # the same rooms are free in every week (or none ever is: the static checker explains it)
        _free, order = free_by_room(e, slot, e.weeks)
        common = bool(order) and any(e.weeks <= f for f in _free.values())
        main = replace(e, weeks=frozenset(groups[0]))
        segs = [replace(e, id=new_id(), weeks=frozenset(g), label=seg_label(e.label, g)) for g in groups[1:]]
        replaced[e.id] = [main, *segs]
        reason = REASON_ROOM_CHANGES if common else REASON_NO_COMMON_ROOM
        diags.append(
            Diagnosis(
                [e.id],
                ["same_room_across_weeks"],
                f"{e.label}: "
                + (
                    "the free rooms differ between weeks"
                    if common
                    else f"no eligible room is free at day {slot.day} P{slot.start}-P{slot.end} in every week"
                )
                + " (blocks / locked rooms), so it is scheduled in week segments "
                + "; ".join(f"w{weeks_text(g)}" for g in groups)
                + " at the same time, preferably in one room"
                + (f"; no room at all in week(s) {weeks_text(uncovered)}" if uncovered else ""),
                ["release a block in the affected weeks to keep one room all term", "accept the room change"],
                "warning",
                "week_split",
                {
                    "reason": reason,
                    "kept_weeks": sorted(groups[0]),
                    "moved_weeks": sorted(set().union(*groups[1:])),
                    "uncovered_weeks": sorted(uncovered),
                    "segments": [s.id for s in segs],
                },
            )
        )

    if not replaced:
        return WeekSplit(inp=inp, forbid=forbid)
    return _apply(WeekSplit(inp=inp, forbid=forbid), replaced, diags)


def _apply(base: WeekSplit, replaced: dict[int, list[Event]], diags: list[Diagnosis]) -> WeekSplit:
    """Replace events of ``base.inp`` by their parts (first part keeps the id) and keep the bookkeeping
    consistent: origins, segment lists per original, constraints naming the events, the
    ``week_segments`` group constraint, ``previous`` re-keyed by weeks."""
    inp = base.inp
    origin = dict(base.origin)
    segments = {k: list(v) for k, v in base.segments.items()}
    events: list[Event] = []
    expand_map: dict[int, list[int]] = {}
    for e in inp.events:
        parts = replaced.get(e.id)
        if parts is None:
            events.append(e)
            continue
        events.extend(parts)
        expand_map[e.id] = [p.id for p in parts]
        root = origin.get(e.id, e.id)
        seg = segments.setdefault(root, [root])
        for p in parts[1:]:
            origin[p.id] = root
            seg.append(p.id)

    def expand(ids: Iterable[int]) -> list[int]:
        return [x for i in ids for x in expand_map.get(int(i), [int(i)])]

    new_constraints: list[Constraint] = []
    for c in inp.constraints:
        if c.kind == "same_room_across_weeks" and c.params.get("week_segments"):
            continue  # rebuilt below
        params = dict(c.params)
        touched = False
        for key in ("event_ids", "exclude_event_ids"):
            if key in params and any(int(i) in expand_map for i in int_list(params, key)):
                params[key] = expand(int_list(params, key))
                touched = True
        if params.get("groups") and any(int(i) in expand_map for g in params["groups"] for i in g):
            params["groups"] = [expand(g) for g in params["groups"]]
            touched = True
        new_constraints.append(replace(c, params=params) if touched else c)
    groups = [ids for ids in segments.values() if len(ids) > 1]
    new_constraints.append(
        Constraint(
            "same_room_across_weeks",
            {"event_ids": [i for g in groups for i in g], "groups": groups, "week_segments": True},
            False,
        )
    )

    by_event_prev: dict[int, list[Assignment]] = defaultdict(list)
    previous: list[Assignment] = []
    for a in inp.previous:
        if a.event_id in expand_map:
            by_event_prev[a.event_id].append(a)
        else:
            previous.append(a)
    ev_by_id = {e.id: e for e in events}
    for eid, prevs in by_event_prev.items():
        for sid in expand_map[eid]:
            weeks = ev_by_id[sid].weeks
            best = max(prevs, key=lambda a: (len(a.weeks & weeks) if a.weeks else 0, -prevs.index(a)))
            previous.append(replace(best, event_id=sid, weeks=weeks))

    out = replace(inp, events=tuple(events), constraints=tuple(new_constraints), previous=tuple(previous))
    return WeekSplit(
        inp=out, origin=origin, segments=segments, diagnoses=[*base.diagnoses, *diags], forbid=dict(base.forbid)
    )


def residual_split(split: WeekSplit, assignments: Iterable[Assignment]) -> tuple[WeekSplit, list[Assignment]] | None:
    """Second chance for fixed-time events a (partial) solve left unplaced: with everything else where
    the solve put it, cover the event's weeks by rooms that are free *in those weeks* (greedy maximum
    cover) and split it accordingly.  Returns the new split and a hint (the given assignments + the
    covering segments), or ``None`` when no unplaced event gains a week."""
    inp = split.inp
    placed = {a.event_id: a for a in assignments}
    constraints, _w, soft = effective_constraints(inp)
    fixed_soft = "fixed_time" in soft
    blocks = list(inp.blocks)
    for c in constraints:
        if c.kind == "room_closed" and c.hard:
            blocks.extend(room_closed_blocks(inp, c))
    occ = _Occupancy(inp, blocks)
    ev_by_id = {e.id: e for e in inp.events}
    for a in placed.values():
        e = ev_by_id.get(a.event_id)
        if e is None or not e.needs_room:
            continue
        slot = _Slot(a.day, a.start, a.end)
        for r in a.room_ids:
            occ.locks[r][a.event_id] = (slot, a.weeks or e.weeks)
    room_order = [r.id for r in inp.rooms]
    rooms_by_id = {r.id: r for r in inp.rooms}
    next_id = min([0, *(e.id for e in inp.events)]) - 1
    replaced: dict[int, list[Event]] = {}
    diags: list[Diagnosis] = []
    hints = list(placed.values())
    codes = {r.id: r.code for r in inp.rooms}
    # locked events the solve left unplaced because their room is taken in *some* weeks by what it placed
    # (another request's moved week segment, orchestrator R3): keep the planner's lock in the free weeks and
    # give only the taken weeks another room at the same time (full size: the trust stays with the lock)
    for e in inp.events:
        if e.id in placed or e.locked is None or not e.needs_room or shares_room(e) or len(e.weeks) < 2:
            continue
        slot = _fixed_slot(e, fixed_soft)
        lrooms = [r for r in e.locked.room_ids if r in rooms_by_id]
        if slot is None or not lrooms:
            continue
        kept = set(e.weeks)
        for r in lrooms:
            kept &= occ.free(r, slot, e.weeks, e.id)
        moved_weeks = set(e.weeks) - kept
        if not kept or not moved_weeks:
            continue  # never free (the static checker explains it) or free all term (unplaced for another reason)
        proto = replace(
            e,
            locked=None,
            fixed_day=slot.day,
            fixed_start=slot.start,
            allowed_days=frozenset({slot.day}),
            weeks=frozenset(moved_weeks),
            forbidden_tags=split.forbid.get(e.id, e.forbidden_tags),
            preferred_room_ids=tuple(dict.fromkeys([*lrooms, *e.preferred_room_ids])),
        )
        eligible, _r = _room_options(proto, inp, soft)
        if proto.max_rooms > 1 and "capacity" not in soft:
            eligible = [r for r in eligible if effective_capacity(rooms_by_id[r], proto) >= proto.size]
        free = {r: occ.free(r, slot, proto.weeks, e.id) for r in eligible}
        left = set(moved_weeks)
        cover: list[tuple[int, set[int]]] = []
        while left:
            best = max(eligible, key=lambda r: len(free[r] & left), default=None)
            if best is None or not free[best] & left:
                break
            cover.append((best, free[best] & left))
            left -= free[best] & left
        main = replace(e, weeks=frozenset(kept), locked=replace(e.locked, weeks=frozenset(kept)))
        parts: list[Event] = [main]
        hints.append(replace(e.locked, weeks=frozenset(kept)))
        for r in lrooms:
            occ.locks[r][e.id] = (slot, frozenset(kept))
        for room, weeks in cover:
            sid = next_id
            next_id -= 1
            parts.append(replace(proto, id=sid, weeks=frozenset(weeks), label=seg_label(e.label, weeks)))
            hints.append(Assignment(sid, slot.day, slot.start, slot.end, (room,), frozenset(weeks), e.fixed_date))
            occ.locks[room][sid] = (slot, frozenset(weeks))
        if left:
            parts.append(replace(proto, id=next_id, weeks=frozenset(left), label=seg_label(e.label, left)))
            next_id -= 1
        replaced[e.id] = parts
        diags.append(
            Diagnosis(
                [split.origin_of(e.id)],
                ["same_room_across_weeks"],
                f"{e.label} keeps {', '.join(codes.get(r, str(r)) for r in lrooms)} in week(s) {weeks_text(kept)}; the "
                f"room is taken in week(s) {weeks_text(moved_weeks)} once the rest of the timetable is placed, so "
                "those weeks move to "
                + ("; ".join(f"{codes.get(r, r)} (w{weeks_text(w)})" for r, w in cover) or "no free room")
                + " at the same time"
                + (f"; no room at all in week(s) {weeks_text(left)}" if left else ""),
                ["move the class that takes the room in those weeks to keep one room all term"],
                "warning",
                "week_split",
                {
                    "reason": REASON_LOCK_CLASH,
                    "rooms": lrooms,
                    "room_codes": [codes.get(r, str(r)) for r in lrooms],
                    "kept_weeks": sorted(kept),
                    "moved_weeks": sorted(moved_weeks),
                    "uncovered_weeks": sorted(left),
                    "segments": [p.id for p in parts[1:]],
                },
            )
        )
    for e in inp.events:
        if e.id in placed or e.locked is not None or not e.needs_room or shares_room(e) or len(e.weeks) < 2:
            continue
        slot = _fixed_slot(e, fixed_soft)
        if slot is None:
            continue
        eligible, _r = _room_options(e, inp, soft)
        if e.max_rooms > 1 and "capacity" not in soft:  # the hint seats the event in one room
            eligible = [r for r in eligible if effective_capacity(rooms_by_id[r], e) >= e.size]
        pref = [r for r in e.preferred_room_ids if r in eligible]
        order = pref + [r for r in room_order if r in eligible and r not in pref]
        free = {r: occ.free(r, slot, e.weeks, e.id) for r in order}
        left = set(e.weeks)
        cover: list[tuple[int, set[int]]] = []
        while left:
            best = max(order, key=lambda r: len(free[r] & left), default=None)
            if best is None or not free[best] & left:
                break
            cover.append((best, free[best] & left))
            left -= free[best] & left
        if not cover:
            continue
        base = _base_label(e.label)
        parts: list[Event] = []
        for i, (room, weeks) in enumerate(cover):
            sid = e.id if i == 0 else next_id
            if i:
                next_id -= 1
            whole = i == 0 and not left and len(cover) == 1
            label = e.label if whole else seg_label(base, weeks)
            if i == 0 and split.origin_of(e.id) == e.id and not whole:
                label = base  # the original id keeps the original label
            parts.append(replace(e, id=sid, weeks=frozenset(weeks), label=label))
            hints.append(Assignment(sid, slot.day, slot.start, slot.end, (room,), frozenset(weeks), e.fixed_date))
            occ.locks[room][sid] = (slot, frozenset(weeks))
        if left:
            parts.append(replace(e, id=next_id, weeks=frozenset(left), label=seg_label(base, left)))
            next_id -= 1
        if len(parts) < 2:
            continue  # one free room in every week: no split needed, the hint alone places it
        replaced[e.id] = parts
        diags.append(
            Diagnosis(
                [split.origin_of(e.id)],
                ["same_room_across_weeks"],
                f"{e.label}: no room is free at day {slot.day} P{slot.start}-P{slot.end} in all of its weeks once the "
                "rest of the timetable is placed, so it is scheduled in week segments "
                + "; ".join(f"w{weeks_text(w)} in {codes.get(r, r)}" for r, w in cover)
                + (f"; no room at all in week(s) {weeks_text(left)}" if left else ""),
                ["release a block or move a lecture in the affected weeks to keep one room all term"],
                "warning",
                "week_split",
                {
                    "reason": REASON_RESIDUAL,
                    "kept_weeks": sorted(cover[0][1]),
                    "moved_weeks": sorted(set().union(*(w for _r, w in cover[1:]))) if len(cover) > 1 else [],
                    "uncovered_weeks": sorted(left),
                    "segments": [p.id for p in parts[1:]],
                },
            )
        )
    if not replaced and len(hints) == len(placed):
        return None
    return _apply(split, replaced, diags), hints


def residual_gain(split: WeekSplit, assignments: Iterable[Assignment], cand: WeekSplit, hints: list[Assignment]) -> int:
    """How many more original events the residual round's hint places completely, counting only the
    covering segments that keep every hard rule next to the current timetable (validated)."""
    from app.solver.scoring import evaluate

    current = list(assignments)
    known = {e.id: e for e in cand.inp.events}
    hint = [a for a in hints if a.event_id in known]
    old_ids = {a.event_id for a in current}
    sub = replace(cand.inp, events=tuple(known[a.event_id] for a in hint), best_effort=False)
    bad = {i for v in evaluate(sub, hint).hard_violations() for i in v.event_ids} - old_ids
    valid = [a for a in hint if a.event_id not in bad]
    return len(fully_placed(cand, valid)) - len(fully_placed(split, current))


def fully_placed(split: WeekSplit, assignments: Iterable[Assignment]) -> set[int]:
    """Original event ids all of whose segments are placed."""
    have = {a.event_id for a in assignments}
    out = set()
    for e in split.inp.events:
        root = split.origin_of(e.id)
        if root in out:
            continue
        if all(i in have for i in split.segments.get(root, [root])):
            out.add(root)
    return out


def merge_back(split: WeekSplit, assignments: Iterable[Assignment]) -> list[Assignment]:
    """Assignments keyed by the *original* event ids: segments that ended up at the same time in the
    same rooms are merged into one assignment (union of weeks); a real room change gives one
    assignment per room set, in week order."""
    by_root: dict[int, list[Assignment]] = defaultdict(list)
    order: list[int] = []
    for a in assignments:
        root = split.origin_of(a.event_id)
        if root not in by_root:
            order.append(root)
        by_root[root].append(a)
    out: list[Assignment] = []
    for root in order:
        parts = by_root[root]
        groups: dict[tuple[int, int, int, tuple[int, ...]], list[Assignment]] = {}
        for a in sorted(parts, key=lambda x: min(x.weeks) if x.weeks else 0):
            groups.setdefault((a.day, a.start, a.end, tuple(sorted(a.room_ids))), []).append(a)
        for (day, start, end, _rooms), items in groups.items():
            weeks = frozenset().union(*(x.weeks for x in items))
            first = items[0]
            out.append(replace(first, event_id=root, day=day, start=start, end=end, weeks=weeks))
    return out


def to_original(split: WeekSplit, result: SolverResult) -> SolverResult:
    """Translate a result on ``split.inp`` back to the original events: merged assignments, diagnosis
    event ids mapped to the originals, placement stats counted per original (``placed`` = every
    week placed; ``partially_placed`` = some weeks), plus the ``week_split`` warnings of the events
    whose room really changes (or which lose weeks)."""
    if not split.origin and not split.diagnoses:
        return result
    merged = merge_back(split, result.assignments)
    rows_per_root: dict[int, int] = defaultdict(int)
    for a in merged:
        rows_per_root[a.event_id] += 1
    full = fully_placed(split, result.assignments)
    roots = list(dict.fromkeys(split.origin_of(e.id) for e in split.inp.events))
    have = {split.origin_of(a.event_id) for a in result.assignments}
    partial_ids = [r for r in roots if r in have and r not in full]
    unplaced_ids = [r for r in roots if r not in full]

    def map_ids(ids: Iterable[int]) -> list[int]:
        return list(dict.fromkeys(split.origin_of(i) for i in ids))

    def map_params(params: dict[str, Any]) -> dict[str, Any]:
        out = dict(params)
        for key in ("busy", "clashes"):  # explain_event: the events holding a room / a key
            if isinstance(out.get(key), list):
                out[key] = [
                    {**x, "holders": map_ids(x.get("holders") or [])} if isinstance(x, dict) else x for x in out[key]
                ]
        if isinstance(out.get("clash_ids"), list):
            out["clash_ids"] = map_ids(out["clash_ids"])
        return out

    diags = [replace(d, event_ids=map_ids(d.event_ids), params=map_params(d.params)) for d in result.diagnoses]
    kept_notes: list[Diagnosis] = []
    for d in split.diagnoses:
        root = d.event_ids[0] if d.event_ids else None
        if root is None:
            continue
        if d.params.get("reason") in (REASON_ROOM_CHANGES,) and rows_per_root.get(root, 0) <= 1 and root in full:
            continue  # split for freedom only, and every week ended up in one room: nothing to report
        kept_notes.append(d)
    stats = dict(result.stats)
    if stats.get("partial") or unplaced_ids:
        stats.update(
            placed=len(full),
            unplaced=len(unplaced_ids),
            events_total=len(roots),
            unplaced_ids=unplaced_ids[:500],
            partially_placed=len(partial_ids),
            partially_placed_ids=partial_ids[:500],
        )
    else:
        stats.update(placed=len(full), unplaced=0, events_total=len(roots))
    stats["week_split"] = {
        "events_split": len(split.segments),
        "segments": sum(len(v) for v in split.segments.values()),
        "room_changes": sum(1 for v in rows_per_root.values() if v > 1),
        "rounds": stats.get("week_split_rounds", 0),
    }
    if split.segments and not stats.get("partial") and partial_ids:
        stats["partial"] = True
    return replace(result, assignments=merged, diagnoses=[*diags, *kept_notes], stats=stats)


def solve_segmented(
    inp: SolverInput,
    *,
    unlocked_forbidden_tags: Mapping[int, frozenset[str]] | None = None,
    rounds: int = 2,
    profile_split: bool = False,
) -> tuple[SolverResult, WeekSplit]:
    """``cpsat.solve`` with week segments: split blocked weeks up front, solve, then (best effort, up to
    ``rounds`` times, within the time limit) give the fixed-time events left unplaced a week-segmented
    second chance hinted with the previous timetable; a round is kept only if it places more original
    events completely without losing hard score.  Returns the result on ``split.inp`` (segment ids)
    and the split; :func:`to_original` translates it back."""
    from app.solver.cpsat import solve

    t0 = time.perf_counter()
    split = split_blocked_weeks(inp, unlocked_forbidden_tags=unlocked_forbidden_tags, profile_split=profile_split)
    res = solve(split.inp)
    done = 0
    for _ in range(max(0, rounds)):
        if not res.stats.get("partial") or not res.assignments:
            break
        remaining = inp.time_limit_s - (time.perf_counter() - t0)
        if remaining < 5.0:
            break
        nxt = residual_split(split, res.assignments)
        if nxt is None:
            break
        cand_split, hints = nxt
        if residual_gain(split, res.assignments, cand_split, hints) <= 0:
            # the covering segments clash with the placed timetable (cohort / instructor / seats) for every
            # event they would complete: a round could not place more (review M5: one wasted 112 s)
            res.stats["week_split_residual_skipped"] = True
            break
        cand = solve(replace(cand_split.inp, time_limit_s=remaining), _hints=hints)
        before = len(fully_placed(split, res.assignments))
        after = len(fully_placed(cand_split, cand.assignments))
        if after <= before or cand.hard_score < res.hard_score:
            break
        split, res = cand_split, cand
        done += 1
    res.stats["week_split_rounds"] = done
    res.stats["wall_s_total"] = round(time.perf_counter() - t0, 3)
    return res, split


__all__ = [
    "REASON_BLOCKED",
    "REASON_RESIDUAL",
    "REASON_ROOM_CHANGES",
    "fully_placed",
    "merge_back",
    "residual_split",
    "seg_label",
    "solve_segmented",
    "to_original",
    "REASON_LOCK_CLASH",
    "REASON_NO_COMMON_ROOM",
    "WeekSplit",
    "split_blocked_weeks",
    "weeks_text",
]
