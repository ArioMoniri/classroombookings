"""Candidate enumeration ("domains") for every event, computed before any CP-SAT variable exists.

Per event we enumerate the *time options* ``(day, start)`` inside its allowed window and the
*room options* that satisfy the hard room rules (capacity / exam capacity, tags, pins, forbids,
blocks and ``room_closed``).  Events with a fixed day and start get exactly one time option, so
the full Bahar instance (≈1 300 mostly fixed events × 60 rooms) stays near 10⁵ Booleans instead
of the ~10⁷ of a naive ``x[event, day, period, room]`` grid.

Pruning here is only ever done for *hard* rules.  Each pruned option is recorded with a reason so
the diagnoser can explain "why not room A 204?" without re-running the solver.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.solver.model import Block, Event, Room, SolverInput


@dataclass(frozen=True)
class TimeOption:
    day: int
    start: int
    duration: int

    @property
    def end(self) -> int:
        return self.start + self.duration - 1

    @property
    def periods(self) -> range:
        return range(self.start, self.start + self.duration)

    def overlaps(self, other: TimeOption) -> bool:
        return self.day == other.day and self.start <= other.end and other.start <= self.end

    def covers(self, day: int, period: int) -> bool:
        return self.day == day and self.start <= period <= self.end


def weeks_intersect(a: frozenset[int], b: frozenset[int]) -> bool:
    return not a.isdisjoint(b)


def effective_capacity(room: Room, event: Event) -> int:
    return room.exam_capacity if event.kind == "exam" else room.capacity


def room_fits_alone(room: Room, event: Event) -> bool:
    return effective_capacity(room, event) >= event.size


@dataclass
class EventDomain:
    """All options still open for one event plus the reasons for pruned ones."""

    event: Event
    times: list[TimeOption] = field(default_factory=list)
    rooms: list[int] = field(default_factory=list)  # room ids (ordered as inp.rooms)
    #: (time, room) pairs removed because of blocks / room_closed; everything else is the product
    excluded_pairs: set[tuple[TimeOption, int]] = field(default_factory=set)
    room_reasons: dict[int, str] = field(default_factory=dict)  # room id -> why pruned
    time_reasons: dict[TimeOption, str] = field(default_factory=dict)
    pair_reasons: dict[tuple[TimeOption, int], str] = field(default_factory=dict)

    @property
    def fixed_time(self) -> bool:
        return len(self.times) == 1

    def time_index(self, day: int, start: int) -> int | None:
        for i, t in enumerate(self.times):
            if t.day == day and t.start == start:
                return i
        return None

    def option_count(self) -> int:
        if not self.event.needs_room:
            return len(self.times)
        return len(self.times) * len(self.rooms) - len(self.excluded_pairs)

    def is_pair_allowed(self, t: TimeOption, room_id: int) -> bool:
        return (t, room_id) not in self.excluded_pairs

    def remove_room(self, room_id: int, reason: str) -> None:
        if room_id in self.rooms:
            self.rooms.remove(room_id)
            self.room_reasons.setdefault(room_id, reason)

    def remove_time(self, t: TimeOption, reason: str) -> None:
        if t in self.times:
            self.times.remove(t)
            self.time_reasons.setdefault(t, reason)

    def exclude_pair(self, t: TimeOption, room_id: int, reason: str) -> None:
        if t in self.times and room_id in self.rooms:
            self.excluded_pairs.add((t, room_id))
            self.pair_reasons.setdefault((t, room_id), reason)


@dataclass
class Domains:
    inp: SolverInput
    rooms_by_id: dict[int, Room]
    events_by_id: dict[int, Event]
    by_event: dict[int, EventDomain]
    blocks_by_room: dict[int, list[Block]]
    soft: frozenset[str] = frozenset()  # structural kinds that are soft (not pruned)
    static_conflicts: list[tuple[str, str, int, int]] = field(default_factory=list)  # (kind, key, a, b)

    def event_ids(self) -> list[int]:
        return [e.id for e in self.inp.events]

    def domain(self, event_id: int) -> EventDomain:
        return self.by_event[event_id]

    def add_block(self, block: Block) -> None:
        """Register an extra block (e.g. from ``room_closed``) and prune affected pairs."""
        self.blocks_by_room[block.room_id].append(block)
        for dom in self.by_event.values():
            _prune_block(dom, block, self.inp)


def _time_options(event: Event, inp: SolverInput, soft: frozenset[str]) -> tuple[list[TimeOption], dict[TimeOption, str]]:
    """Enumerate (day, start) options from the event's window; locked > fixed > window.
    When ``fixed_time`` is soft, fixed day/start become preferences and the window is enumerated."""
    reasons: dict[TimeOption, str] = {}
    dur = max(1, event.duration)
    if event.locked is not None:
        return [TimeOption(event.locked.day, event.locked.start, dur)], reasons
    fixed_hard = "fixed_time" not in soft
    days: list[int]
    if event.fixed_day is not None and fixed_hard:
        days = [event.fixed_day]
    elif event.allowed_days:
        days = [d for d in inp.days if d in event.allowed_days]
    else:
        days = list(inp.days)
    lo = max(1, event.earliest_start)
    hi = min(inp.periods_per_day, event.latest_end) - dur + 1
    starts: list[int]
    if event.fixed_start is not None and fixed_hard:
        starts = [event.fixed_start]
    else:
        starts = list(range(lo, hi + 1))
    options = [TimeOption(d, s, dur) for d in days for s in starts]
    return options, reasons


def _room_options(event: Event, inp: SolverInput, soft: frozenset[str]) -> tuple[list[int], dict[int, str]]:
    """Rooms passing the hard room rules.  Kinds listed in ``soft`` are not pruned here; the
    corresponding constraint module turns them into penalties instead."""
    reasons: dict[int, str] = {}
    chosen: list[int] = []
    if not event.needs_room:
        return chosen, reasons
    split = event.max_rooms > 1
    for room in inp.rooms:
        cap = effective_capacity(room, event)
        if event.locked is not None and event.locked.room_ids:
            if room.id not in event.locked.room_ids:
                reasons[room.id] = "locked to another room"
                continue
        if "room_pin" not in soft and event.required_room_ids and room.id not in event.required_room_ids:
            reasons[room.id] = "not in the pinned room set (room_pin)"
            continue
        if "room_forbid" not in soft and room.id in event.forbidden_room_ids:
            reasons[room.id] = "room is forbidden for this event (room_forbid)"
            continue
        missing = event.required_tags - room.tags
        if "room_tags" not in soft and missing:
            reasons[room.id] = f"room lacks required tag(s) {sorted(missing)} (room_tags)"
            continue
        clash = event.forbidden_tags & room.tags
        if "room_tags" not in soft and clash:
            reasons[room.id] = f"room carries forbidden tag(s) {sorted(clash)} (room_tags)"
            continue
        if cap <= 0:
            reasons[room.id] = "room has no usable capacity (capacity)"
            continue
        if "capacity" not in soft and not split and cap < event.size:
            reasons[room.id] = f"capacity {cap} < {event.size} (capacity)"
            continue
        chosen.append(room.id)
    return chosen, reasons


def _prune_block(dom: EventDomain, block: Block, inp: SolverInput) -> None:
    event = dom.event
    if block.room_id not in dom.rooms:
        return
    if block.week is not None and block.week not in event.weeks:
        return
    for t in list(dom.times):
        if t.day == block.day and t.start <= block.end and block.start <= t.end:
            label = f" ({block.label})" if block.label else ""
            dom.exclude_pair(t, block.room_id, f"room blocked{label} on day {block.day} P{block.start}-P{block.end}")
    # a room that is blocked at every time option is useless for this event
    if all(not dom.is_pair_allowed(t, block.room_id) for t in dom.times):
        for t in dom.times:
            dom.excluded_pairs.discard((t, block.room_id))
            dom.pair_reasons.pop((t, block.room_id), None)
        dom.remove_room(block.room_id, f"room blocked at every allowed time ({block.label or 'block'})")


def build_domains(inp: SolverInput, soft_structural: Iterable[str] = ()) -> Domains:
    """Enumerate options for every event.  ``soft_structural`` names structural kinds
    (``capacity``, ``room_tags``, ``room_pin``, ``room_forbid``, ``fixed_time``) that an explicit
    Constraint turned into soft rules; they are then not pruned."""
    soft = frozenset(soft_structural)
    rooms_by_id = {r.id: r for r in inp.rooms}
    events_by_id = {e.id: e for e in inp.events}
    blocks_by_room: dict[int, list[Block]] = defaultdict(list)
    for b in inp.blocks:
        blocks_by_room[b.room_id].append(b)
    by_event: dict[int, EventDomain] = {}
    for event in inp.events:
        times, treasons = _time_options(event, inp, soft)
        rooms, rreasons = _room_options(event, inp, soft)
        dom = EventDomain(event=event, times=times, rooms=rooms, room_reasons=rreasons, time_reasons=treasons)
        by_event[event.id] = dom
    doms = Domains(inp=inp, rooms_by_id=rooms_by_id, events_by_id=events_by_id, by_event=by_event, blocks_by_room=blocks_by_room, soft=soft)
    for room_id, blocks in list(blocks_by_room.items()):
        if room_id not in rooms_by_id:
            continue
        for block in blocks:
            for dom in by_event.values():
                _prune_block(dom, block, inp)
    return doms


def cohort_groups(inp: SolverInput) -> dict[str, list[int]]:
    """cohort key -> event ids."""
    groups: dict[str, list[int]] = defaultdict(list)
    for e in inp.events:
        for k in e.cohort_keys:
            groups[k].append(e.id)
    return dict(groups)


def instructor_groups(inp: SolverInput) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for e in inp.events:
        for k in e.instructor_keys:
            groups[k].append(e.id)
    return dict(groups)


def prune_fixed_key_conflicts(doms: Domains, groups: dict[str, list[int]], kind: str) -> list[tuple[str, int, int]]:
    """For cohort/instructor keys: remove time options of flexible events that collide with
    fixed-time events of the same key (weeks intersecting).  Returns the list of fixed-vs-fixed
    collisions ``(key, event_a, event_b)`` which make the instance statically infeasible."""
    collisions: list[tuple[str, int, int]] = []
    for key, ids in groups.items():
        fixed = [doms.domain(i) for i in ids if doms.domain(i).fixed_time]
        flexible = [doms.domain(i) for i in ids if not doms.domain(i).fixed_time]
        for i, a in enumerate(fixed):
            ta = a.times[0]
            for b in fixed[i + 1 :]:
                if weeks_intersect(a.event.weeks, b.event.weeks) and ta.overlaps(b.times[0]):
                    collisions.append((key, a.event.id, b.event.id))
        for dom in flexible:
            for t in list(dom.times):
                for a in fixed:
                    if weeks_intersect(a.event.weeks, dom.event.weeks) and t.overlaps(a.times[0]):
                        dom.remove_time(t, f"{kind} '{key}' busy with {a.event.label} (#{a.event.id})")
                        break
    return collisions
