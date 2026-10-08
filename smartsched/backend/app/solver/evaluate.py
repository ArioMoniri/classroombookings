"""Pure-Python evaluation of a set of assignments against a SolverInput.

Independent of CP-SAT: the API uses it after AI/manual edits, and the solver uses it on its own
output so that ``solve()`` and ``validate()`` report identical scores by construction.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.solver.domains import TimeOption, fixed_time_of, is_input_fixed, trusted_lock
from app.solver.model import Assignment, Event, Room, SolverInput


@dataclass
class Violation:
    kind: str
    hard: bool
    event_ids: list[int]
    message: str
    room_ids: list[int] = field(default_factory=list)
    penalty: int = 0  # weighted penalty for soft violations


@dataclass
class Evaluation:
    inp: SolverInput
    by_event: dict[int, Assignment]
    rooms_by_id: dict[int, Room]
    events_by_id: dict[int, Event]
    violations: list[Violation] = field(default_factory=list)
    penalties: dict[str, int] = field(default_factory=dict)  # term -> weighted penalty
    bounds: dict[str, int] = field(default_factory=dict)  # term -> weighted worst case (normalisation)
    soft_structural: frozenset[str] = frozenset()  # structural kinds an explicit constraint made soft

    # ------------------------------------------------------------------ helpers
    def assignment(self, event_id: int) -> Assignment | None:
        return self.by_event.get(event_id)

    def time_of(self, event_id: int) -> TimeOption | None:
        a = self.by_event.get(event_id)
        if a is None:
            return None
        return TimeOption(a.day, a.start, a.end - a.start + 1)

    def rooms_of(self, event_id: int) -> list[Room]:
        a = self.by_event.get(event_id)
        if a is None:
            return []
        return [self.rooms_by_id[r] for r in a.room_ids if r in self.rooms_by_id]

    def trusted(self, event_id: int) -> bool:
        """``trust_locked_rooms`` and the event sits exactly in its planner-locked rooms: capacity and
        tag mismatches of that room set are warnings (static check), not hard violations."""
        e = self.events_by_id.get(event_id)
        a = self.by_event.get(event_id)
        if e is None or a is None or not trusted_lock(self.inp, e) or e.locked is None:
            return False
        return set(a.room_ids) == set(e.locked.room_ids)

    def waived_pair(self, a: int, b: int) -> bool:
        """``fixed_conflicts_as_warnings``: both events are fixed by the input and sit at their fixed
        time, so their key overlap is an input conflict (reported as a warning), not a violation."""
        if not self.inp.fixed_conflicts_as_warnings:
            return False
        for eid in (a, b):
            e = self.events_by_id.get(eid)
            t = self.time_of(eid)
            if e is None or t is None or not is_input_fixed(e, self.soft_structural):
                return False
            ft = fixed_time_of(e)
            if ft is None or (ft.day, ft.start) != (t.day, t.start):
                return False
        return True

    def hard(self, kind: str, event_ids: list[int], message: str, room_ids: list[int] | None = None) -> None:
        self.violations.append(Violation(kind, True, list(event_ids), message, list(room_ids or [])))

    def soft(
        self, kind: str, event_ids: list[int], message: str, penalty: int, room_ids: list[int] | None = None
    ) -> None:
        if penalty <= 0:
            return
        self.violations.append(Violation(kind, False, list(event_ids), message, list(room_ids or []), penalty))
        self.penalties[kind] = self.penalties.get(kind, 0) + penalty

    def add_bound(self, kind: str, value: int) -> None:
        if value > 0:
            self.bounds[kind] = self.bounds.get(kind, 0) + value

    def add_penalty_only(self, kind: str, penalty: int) -> None:
        if penalty > 0:
            self.penalties[kind] = self.penalties.get(kind, 0) + penalty

    # ------------------------------------------------------------------ scores
    def hard_violations(self) -> list[Violation]:
        return [v for v in self.violations if v.hard]

    def hard_score(self) -> int:
        hard = self.hard_violations()
        if not hard:
            return 100
        touched: set[int] = set()
        for v in hard:
            touched.update(v.event_ids)
        n = max(1, len(self.inp.events))
        # each violated event costs its share; a violation without events costs one share
        bad = len(touched) + sum(1 for v in hard if not v.event_ids)
        return max(0, min(99, round(100 * (1 - bad / n))))

    def soft_score(self) -> int:
        total = sum(self.penalties.values())
        bound = sum(self.bounds.values())
        if bound <= 0:
            return 100
        return max(0, min(100, round(100 * (1 - total / bound))))

    def total_penalty(self) -> int:
        return sum(self.penalties.values())


def index_assignments(assignments: list[Assignment] | tuple[Assignment, ...]) -> dict[int, Assignment]:
    out: dict[int, Assignment] = {}
    for a in assignments:
        out[a.event_id] = a
    return out


def room_occupancy(ev: Evaluation) -> dict[tuple[int, int, int], list[int]]:
    """(room, day, period) -> event ids occupying it (weeks ignored here; callers intersect)."""
    occ: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for eid, a in ev.by_event.items():
        for r in a.room_ids:
            for p in range(a.start, a.end + 1):
                occ[(r, a.day, p)].append(eid)
    return occ
