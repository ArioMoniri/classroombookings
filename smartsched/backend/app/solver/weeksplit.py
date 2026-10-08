"""Week segments for term runs (``split_blocked_weeks``).

The solver models a request as *one* event over all its weeks with *one* room set.  On a term run a
single blocked week (an ETKİNLİK cell or an exam in the planner's grid, a ``room_closed`` week, another
planner lock that holds the room only in some weeks) then excludes the room for the whole term: the
Bahar term lost 14 locked lectures (``locked_ineligible``) and 11 fixed-time ones (``no_room``) that way.

This preprocessing step splits such an event into **week segments**: the same day and periods in every
week, a room change only in the affected weeks.

* **Locked event** whose locked room is blocked (or held by another lock) in some of its weeks: the
  original event keeps the planner's lock for the unaffected weeks; the affected weeks become unlocked
  segments at the same time (the planner's rooms first in their preferences).  With
  ``trust_locked_rooms`` a segment needs no more seats than the planner's room offered.
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

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from app.solver.constraints import effective_constraints
from app.solver.constraints._common import int_list, week_runs
from app.solver.constraints.room_closed import _blocks as room_closed_blocks
from app.solver.domains import _room_options, normalize_input, shares_room
from app.solver.model import Assignment, Block, Constraint, Diagnosis, Event, SolverInput

#: the ``reason`` values of a ``week_split`` diagnosis
REASON_BLOCKED = "blocked"  # the planner's grid / a room_closed rule blocks the locked room
REASON_LOCK_CLASH = "locked_clash"  # another planner lock holds the room in those weeks
REASON_NO_COMMON_ROOM = "no_common_room"  # no eligible room is free in every week
REASON_ROOM_CHANGES = "room_availability_changes"  # the free rooms differ between weeks (blocks, locks)

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

    def origin_of(self, event_id: int) -> int:
        return self.origin.get(event_id, event_id)


def weeks_text(weeks: Iterable[int]) -> str:
    runs = week_runs(frozenset(weeks))
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)


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
    inp: SolverInput, *, unlocked_forbidden_tags: Mapping[int, frozenset[str]] | None = None
) -> WeekSplit:
    """Split term events around the weeks in which their room cannot be kept (see the module doc).

    ``unlocked_forbidden_tags``: forbidden tags an event would have without its lock (the bridge clears
    ``TIP`` for locked events); used for the unlocked segments.  Returns ``WeekSplit`` with ``inp``
    unchanged (same object) when nothing needs splitting."""
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

    def seg_label(e: Event, weeks: Iterable[int]) -> str:
        return f"{e.label} [w{weeks_text(weeks)}]"

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
        if len(groups) > MAX_PROFILE_SEGMENTS:
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
        cap = sum(rooms_by_id[r].exam_capacity if e.kind == "exam" else rooms_by_id[r].capacity for r in rooms)
        size = min(e.size, cap) if inp.trust_locked_rooms and cap else e.size
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
        segs = [replace(proto, id=new_id(), weeks=frozenset(g), label=seg_label(e, g)) for g in moved_groups]
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
                    **({"size_clipped_to": size} if size != e.size else {}),
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
        segs = [replace(e, id=new_id(), weeks=frozenset(g), label=seg_label(e, g)) for g in groups[1:]]
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
        return WeekSplit(inp=inp)

    events: list[Event] = []
    origin: dict[int, int] = {}
    segments: dict[int, list[int]] = {}
    for e in inp.events:
        parts = replaced.get(e.id)
        if parts is None:
            events.append(e)
            continue
        events.extend(parts)
        segments[e.id] = [p.id for p in parts]
        for p in parts[1:]:
            origin[p.id] = e.id

    def expand(ids: Iterable[int]) -> list[int]:
        return [x for i in ids for x in segments.get(int(i), [int(i)])]

    new_constraints: list[Constraint] = []
    for c in inp.constraints:
        params = dict(c.params)
        touched = False
        if "event_ids" in params and any(int(i) in segments for i in int_list(params, "event_ids")):
            params["event_ids"] = expand(int_list(params, "event_ids"))
            touched = True
        if params.get("groups") and any(int(i) in segments for g in params["groups"] for i in g):
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
        if a.event_id in segments:
            by_event_prev[a.event_id].append(a)
        else:
            previous.append(a)
    ev_by_id = {e.id: e for e in events}
    for orig, prevs in by_event_prev.items():
        for sid in segments[orig]:
            weeks = ev_by_id[sid].weeks
            best = max(prevs, key=lambda a: (len(a.weeks & weeks) if a.weeks else 0, -prevs.index(a)))
            previous.append(replace(best, event_id=sid, weeks=weeks))

    out = replace(inp, events=tuple(events), constraints=tuple(new_constraints), previous=tuple(previous))
    return WeekSplit(inp=out, origin=origin, segments=segments, diagnoses=diags)


def merge_segments(split: WeekSplit, assignments: Iterable[Assignment]) -> dict[int, list[Assignment]]:
    """Original event id -> its segment assignments (week order)."""
    out: dict[int, list[Assignment]] = defaultdict(list)
    for a in assignments:
        out[split.origin_of(a.event_id)].append(a)
    for v in out.values():
        v.sort(key=lambda a: min(a.weeks) if a.weeks else 0)
    return dict(out)


__all__ = [
    "REASON_BLOCKED",
    "REASON_LOCK_CLASH",
    "REASON_NO_COMMON_ROOM",
    "WeekSplit",
    "merge_segments",
    "split_blocked_weeks",
    "weeks_text",
]
