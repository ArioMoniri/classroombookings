"""Synthetic instance generators (deterministic for a seed).

Instances are built by *planting* a conflict-free solution first (rooms, cohorts, instructors,
blocks), then deriving the events' requirements from it, so a generated instance is feasible by
construction.  ``generate`` returns the planted assignments too, which makes stability/repair
tests trivial.  ``from_fixture_like`` mirrors the Bahar 2026 data (room master buckets from
docs/DATA_ANALYSIS.md, 18 periods, 14 weeks, TIP rooms, PC labs, evening programmes).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.solver.model import Assignment, Block, Event, Room, SolverInput

#: (code, lecture capacity, tags) — union of the grid headers and the Bahar Sayfa2 bucket table
ROOM_MASTER: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("A204", 156, ("AMPHI",)), ("A203", 148, ("AMPHI", "TIP")), ("C201", 126, ("AMPHI",)), ("A207", 120, ("AMPHI",)),
    ("A102", 96, ()), ("A201", 96, ("TIP",)), ("A202", 96, ("TIP",)), ("A205", 94, ()), ("A206", 92, ()), ("D106", 82, ()),
    ("A307", 70, ()), ("C301", 72, ()), ("C302", 72, ()), ("C401", 72, ()), ("C402", 72, ()), ("C501", 72, ()), ("C502", 72, ()), ("C601", 72, ()), ("C602", 72, ()),
    ("A305", 64, ()), ("B202", 64, ()), ("B203", 64, ()), ("B204", 64, ()), ("B205", 64, ()), ("B206", 64, ()),
    ("A101", 58, ()), ("A106", 58, ()), ("A107", 58, ()), ("A108", 58, ()), ("A109", 58, ()),
    ("A306", 38, ()), ("A308", 42, ()), ("C303", 45, ()), ("C403", 45, ()), ("C503", 45, ()), ("C603", 45, ()), ("C304", 40, ()), ("C404", 40, ()), ("C504", 40, ()), ("C604", 40, ()),
    ("B201", 30, ()), ("B406", 30, ()), ("B407", 30, ()), ("CZ01", 30, ()), ("C205", 30, ()), ("C306", 30, ()), ("C406", 30, ()), ("C506", 30, ()), ("C606", 30, ()),
    ("C305", 32, ()), ("C405", 32, ()), ("C505", 32, ()), ("C605", 32, ()),
    ("A103", 47, ("PC", "LAB")), ("A104", 41, ("PC", "LAB")), ("A105", 60, ("PC", "LAB")), ("B207", 60, ("PC", "LAB")), ("BLAB", 40, ("PC", "LAB")),
    ("D107", 20, ()), ("D108", 24, ()),
)


def fixture_rooms(n: int | None = None) -> tuple[Room, ...]:
    """The real room master (60 rooms); exam capacity ≈ half, computer labs unchanged."""
    rooms: list[Room] = []
    for i, (code, cap, tags) in enumerate(ROOM_MASTER, start=1):
        exam_cap = cap if "PC" in tags else cap // 2
        rooms.append(Room(id=i, code=code, capacity=cap, exam_capacity=exam_cap, building=code[0], tags=frozenset(tags)))
    if n is not None:
        rooms = rooms[:n] if n <= len(rooms) else rooms + [Room(id=len(rooms) + k + 1, code=f"X{k + 1:03d}", capacity=40 + 8 * (k % 6), exam_capacity=20 + 4 * (k % 6), building="X") for k in range(n - len(rooms))]
    return tuple(rooms)


@dataclass
class GenParams:
    n_rooms: int = 20
    n_events: int = 100
    days: tuple[int, ...] = (1, 2, 3, 4, 5)
    weeks: tuple[int, ...] = tuple(range(1, 15))
    periods_per_day: int = 18
    tightness: float = 0.5  # 0 = plenty of spare rooms, 1 = planted on a minimal room subset
    fixed_ratio: float = 0.85  # share of events with a fixed day+start
    seed: int = 0
    exam: bool = False
    n_programs: int = 12
    n_instructors: int = 60
    use_fixture_rooms: bool = True
    evening_share: float = 0.12
    pc_share: float = 0.06
    medicine_share: float = 0.08
    block_share: float = 0.05  # share of (room, day) mornings blocked for HAZIRLIK
    week_split_share: float = 0.08
    preference_share: float = 0.5
    exam_split_share: float = 0.1


@dataclass
class _Planted:
    room: dict[tuple[int, int, int], set[int]] = field(default_factory=dict)  # (room, day, period) -> weeks
    key: dict[tuple[str, int, int], set[int]] = field(default_factory=dict)  # (key, day, period) -> weeks

    @staticmethod
    def _free(table: dict[tuple[object, int, int], set[int]], keys: list[tuple[object, int, int]], weeks: set[int]) -> bool:
        return all(table.get(k, set()).isdisjoint(weeks) for k in keys)

    def room_free(self, room: int, day: int, periods: range, weeks: set[int]) -> bool:
        return all(self.room.get((room, day, p), set()).isdisjoint(weeks) for p in periods)

    def key_free(self, key: str, day: int, periods: range, weeks: set[int]) -> bool:
        return all(self.key.get((key, day, p), set()).isdisjoint(weeks) for p in periods)

    def take_room(self, room: int, day: int, periods: range, weeks: set[int]) -> None:
        for p in periods:
            self.room.setdefault((room, day, p), set()).update(weeks)

    def take_key(self, key: str, day: int, periods: range, weeks: set[int]) -> None:
        for p in periods:
            self.key.setdefault((key, day, p), set()).update(weeks)


def _size(rng: random.Random, exam: bool) -> int:
    u = rng.random()
    if u < 0.35:
        return rng.randint(8, 30)
    if u < 0.70:
        return rng.randint(30, 60)
    if u < 0.90:
        return rng.randint(60, 100)
    return rng.randint(100, 200 if exam else 160)


def _weeks(rng: random.Random, all_weeks: Sequence[int], p: GenParams) -> list[frozenset[int]]:
    """One or two (week-split) patterns."""
    ws = list(all_weeks)
    u = rng.random()
    if u < p.week_split_share and len(ws) >= 4:
        cut = rng.randint(2, len(ws) - 2)
        return [frozenset(ws[:cut]), frozenset(ws[cut:])]
    if u < p.week_split_share + 0.08:
        return [frozenset(ws[::2])]
    if u < p.week_split_share + 0.12:
        return [frozenset(ws[: len(ws) // 2])]
    return [frozenset(ws)]


def generate(params: GenParams | None = None, **kw: object) -> tuple[SolverInput, list[Assignment]]:
    """Plant a feasible timetable and derive the events.  Returns ``(input, planted_assignments)``."""
    p = params or GenParams()
    for k, v in kw.items():
        setattr(p, k, v)
    rng = random.Random(p.seed)
    rooms = fixture_rooms(p.n_rooms) if p.use_fixture_rooms else tuple(Room(i + 1, f"R{i + 1:03d}", 30 + 10 * (i % 10), (30 + 10 * (i % 10)) // 2, "ABC"[i % 3], frozenset(["PC"] if i % 11 == 0 else [])) for i in range(p.n_rooms))
    n_core = max(1, round(len(rooms) * (1 - 0.7 * p.tightness)))
    core_rooms = list(rooms[:n_core])  # rooms used by the planted solution
    programs = [f"PROG:P{i + 1}" for i in range(p.n_programs)]
    evening = {programs[i] for i in range(p.n_programs) if rng.random() < p.evening_share}
    medicine = {programs[i] for i in range(p.n_programs) if programs[i] not in evening and rng.random() < p.medicine_share}
    instructors = [f"INS:I{i + 1}" for i in range(p.n_instructors)]
    planted = _Planted()
    blocks: list[Block] = []
    for r in core_rooms:
        for d in p.days:
            if rng.random() < p.block_share:
                end = rng.choice([3, 4, 6])
                blocks.append(Block(r.id, None, d, 1, end))  # HAZIRLIK morning block
                planted.take_room(r.id, d, range(1, end + 1), set(p.weeks))
    events: list[Event] = []
    assignments: list[Assignment] = []
    eid = 0
    attempts_total = 0
    while len(events) < p.n_events and attempts_total < p.n_events * 400:
        attempts_total += 1
        prog = rng.choice(programs)
        year = rng.randint(1, 4)
        cohort = f"{prog}:Y{year}" if prog not in evening else f"{prog} İÖ:Y{year}"
        instructor = rng.choice(instructors)
        exam = p.exam
        size = _size(rng, exam)
        duration = rng.choice([2, 2, 3, 3, 3, 4, 1]) if not exam else rng.choice([2, 2, 3])
        wsets = [frozenset([rng.choice(p.weeks)])] if exam else _weeks(rng, p.weeks, p)
        split_exam = exam and rng.random() < p.exam_split_share
        if prog in evening:
            period_lo, period_hi = 13, p.periods_per_day
            room_pool = [r for r in core_rooms if r.building in ("B", "C") and "TIP" not in r.tags] or core_rooms
        else:
            period_lo, period_hi = 1, 12
            room_pool = [r for r in core_rooms if "TIP" not in r.tags or prog in medicine]
        needs_pc = rng.random() < p.pc_share and any("PC" in r.tags for r in room_pool)
        if needs_pc:
            room_pool = [r for r in room_pool if "PC" in r.tags]
        placed_ok = False
        for _ in range(60):
            day = rng.choice(p.days)
            start = rng.randint(period_lo, max(period_lo, period_hi - duration + 1))
            periods = range(start, start + duration)
            if periods[-1] > p.periods_per_day:
                continue
            allw: set[int] = set().union(*wsets)
            if not planted.key_free(cohort, day, periods, allw) or not planted.key_free(instructor, day, periods, allw):
                continue
            cap_of = (lambda r: r.exam_capacity) if exam else (lambda r: r.capacity)
            if split_exam:
                cands = [r for r in room_pool if planted.room_free(r.id, day, periods, allw)]
                rng.shuffle(cands)
                chosen: list[Room] = []
                for r in cands:
                    chosen.append(r)
                    if sum(cap_of(x) for x in chosen) >= size or len(chosen) == 3:
                        break
                if sum(cap_of(x) for x in chosen) < size or len(chosen) < 2:
                    continue
            else:
                fitting = [r for r in room_pool if cap_of(r) >= size and planted.room_free(r.id, day, periods, allw)]
                if not fitting:
                    smaller = [r for r in room_pool if planted.room_free(r.id, day, periods, allw)]
                    if not smaller:
                        continue
                    r0 = max(smaller, key=cap_of)
                    size = min(size, cap_of(r0))
                    fitting = [r0]
                # prefer a tight fit most of the time (like the human planner)
                fitting.sort(key=cap_of)
                chosen = [fitting[0] if rng.random() < 0.6 else rng.choice(fitting)]
            room_ids = tuple(sorted(r.id for r in chosen))
            base_id = eid + 1
            for wset in wsets:
                eid += 1
                fixed = rng.random() < p.fixed_ratio
                label = f"{'EXM' if exam else 'CRS'} {base_id:04d}"
                prefs: tuple[int, ...] = ()
                pref_b: str | None = None
                if rng.random() < p.preference_share:
                    prefs = room_ids if rng.random() < 0.6 else (chosen[0].id, rng.choice(rooms).id)
                elif rng.random() < 0.3:
                    pref_b = chosen[0].building
                events.append(
                    Event(
                        id=eid,
                        kind="exam" if exam else "course",
                        label=label,
                        size=size,
                        duration=duration,
                        weeks=wset,
                        fixed_day=day if fixed else None,
                        fixed_start=start if fixed else None,
                        allowed_days=frozenset() if fixed else frozenset(p.days),
                        earliest_start=period_lo,
                        latest_end=period_hi,
                        required_tags=frozenset(["PC"]) if needs_pc else frozenset(),
                        forbidden_tags=frozenset() if prog in medicine else frozenset(["TIP"]),
                        preferred_room_ids=prefs,
                        preferred_building=pref_b,
                        min_rooms=1,
                        max_rooms=3 if split_exam else 1,
                        cohort_keys=frozenset([cohort]),
                        instructor_keys=frozenset([instructor]),
                    )
                )
                assignments.append(Assignment(eid, day, start, start + duration - 1, room_ids, wset))
                for r in chosen:
                    planted.take_room(r.id, day, periods, set(wset))
                planted.take_key(cohort, day, periods, set(wset))
                planted.take_key(instructor, day, periods, set(wset))
            placed_ok = True
            break
        if not placed_ok:
            continue
    inp = SolverInput(
        rooms=rooms,
        events=tuple(events),
        constraints=(),
        days=p.days,
        periods_per_day=p.periods_per_day,
        weeks=p.weeks,
        blocks=tuple(blocks),
        seed=p.seed,
    )
    return inp, assignments


def from_fixture_like(n_events: int = 1300, weeks: int = 14, seed: int = 0, days: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7), exam: bool = False, tightness: float = 0.35, fixed_ratio: float = 0.85) -> tuple[SolverInput, list[Assignment]]:
    """A Bahar-2026-like instance: 60 real rooms, 18 periods, ``weeks`` weeks, TIP rooms reserved
    for medicine, PC labs, evening programmes after P13 in B/C, HAZIRLIK morning blocks."""
    params = GenParams(
        n_rooms=len(ROOM_MASTER),
        n_events=n_events,
        days=days,
        weeks=tuple(range(1, weeks + 1)),
        tightness=tightness,
        fixed_ratio=fixed_ratio,
        seed=seed,
        exam=exam,
        n_programs=40 if not exam else 60,
        n_instructors=350,
        use_fixture_rooms=True,
    )
    return generate(params)


__all__ = ["ROOM_MASTER", "GenParams", "fixture_rooms", "from_fixture_like", "generate"]
