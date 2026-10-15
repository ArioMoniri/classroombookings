"""Idempotent observation extractors for learned suggestions (P19-L2; review 2026-10-15 §3b).

Every extractor reads tables that already exist, so learning needs nothing new from the planning side:

==========================  ======================================================  =========  ==================
kind                        source                                                  weight     subjects
==========================  ======================================================  =========  ==================
``definitive_room``         ``meeting_requests.definitive_room_ids`` (every term)   +3         course, section,
                                                                                               instructor, program
``correction_to/away``      ``imported_snapshots`` (meeting) vs the current row     +2 / -2    same
``move_to/away``            ``assignments`` origin MANUAL / AI_EDIT (vs parent run) +2 / -2    same
``lock``                    ``assignments.is_locked`` (not an import, not the       +2         same
                            definitive rooms again)
``request_text``            requested rooms / building / tags of a request          +1         course, section,
                                                                                               instructor
``request_time``            the request's day and period band                       +1         course, instructor
``booking_series``          ``booking_series`` (BOOKED)                             +1         user (+ instructor)
``approval_approved/        ``approval_requests`` APPROVED / REJECTED               +1 / -2    user (+ instructor)
rejected``
==========================  ======================================================  =========  ==================

Attributes: ``room`` (room id), ``building`` (building code), ``day`` (1..7), ``period`` (band: morning P1-P6,
afternoon P7-P12, evening P13-P18), ``day_period`` (``"<day>:<band>"``), ``tag`` (``PC``, ``LAB`` ...).

Never learned (docs/testing/2026-10-15-academician-needs.md §3.4):

* the planner's **locked double bookings**: two LOCKED rows of different lectures holding one room at overlapping
  times in common weeks (rows of one lecture listed twice, same room set and same start or same course, are one
  lecture, as in ``solver_bridge.merge_joint_lectures``). Bahar has 7 such incidents (MAT 112 §1 / HEM 236 in A 204
  ...): their room evidence is dropped;
* **over-capacity locks**: a row whose enrolment exceeds the known seats of its rooms (MBG 034 §1, 80 students in
  B 407 with 30 seats); every positive room observation is checked the same way;
* rows without a room need (online, UZEM, hospital ...), one-week segments, placeholder instructors.

Idempotence: ``learned_observations`` is unique on (source table, source id, kind, subject, attribute, value), and
the extractor skips keys it already holds, so a re-run adds 0 rows. A memory reset leaves a watermark: evidence
dated up to it is not learned again for the reset's scope, even after the purge deleted the rows.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import (
    ApprovalRequest,
    Assignment,
    BookingSeries,
    Building,
    Course,
    ImportedSnapshot,
    Instructor,
    LearnedObservation,
    LearningReset,
    MeetingRequest,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
)
from app.models.base import utcnow

#: (sign, weight) per observation kind (review §3b weights)
SIGNALS: dict[str, tuple[int, int]] = {
    "definitive_room": (1, 3),
    "correction_to": (1, 2),
    "correction_away": (-1, 2),
    "move_to": (1, 2),
    "move_away": (-1, 2),
    "lock": (1, 2),
    "request_text": (1, 1),
    "request_time": (1, 1),
    "booking_series": (1, 1),
    "approval_approved": (1, 1),
    "approval_rejected": (-1, 2),
    "suggestion_accepted": (1, 2),
    "suggestion_rejected": (-1, 3),
}
#: delivery modes whose room is evidence of a preference (rule 5: online / UZEM / hospital rooms are not)
ROOM_MODES = frozenset({"F2F", "HYBRID", "SIMULATION"})
#: period bands of the 18-period grid (docs/DATA_ANALYSIS.md "Time grid")
BANDS: tuple[tuple[str, int, int], ...] = (("morning", 1, 6), ("afternoon", 7, 12), ("evening", 13, 18))
BOOKED = "BOOKED"


def band_of(period: int | None) -> str | None:
    if period is None:
        return None
    for name, lo, hi in BANDS:
        if lo <= period <= hi:
            return name
    return None


def band_range(name: str) -> tuple[int, int] | None:
    for b, lo, hi in BANDS:
        if b == name:
            return lo, hi
    return None


@dataclass(frozen=True)
class Obs:
    ts: datetime
    term_id: int | None
    kind: str
    subject_type: str
    subject_key: str
    attribute: str
    value: str
    source_table: str
    source_id: int
    actor_id: int | None = None
    detail: dict[str, Any] | None = field(default=None, compare=False, hash=False)

    @property
    def key(self) -> tuple[str, int, str, str, str, str, str]:
        return (
            self.source_table,
            self.source_id,
            self.kind,
            self.subject_type,
            self.subject_key,
            self.attribute,
            self.value,
        )

    def row(self) -> dict[str, Any]:
        sign, weight = SIGNALS[self.kind]
        return {
            "ts": self.ts,
            "created_at": utcnow(),
            "term_id": self.term_id,
            "kind": self.kind,
            "subject_type": self.subject_type,
            "subject_key": self.subject_key,
            "attribute": self.attribute,
            "value": self.value,
            "sign": sign,
            "weight": weight,
            "source_table": self.source_table,
            "source_id": self.source_id,
            "actor_id": self.actor_id,
            "detail": self.detail,
        }


@dataclass
class _Req:
    """One meeting request with what the extractors need (no names)."""

    id: int
    term_id: int
    section_id: int
    course_id: int
    program_id: int | None
    course_code: str
    label: str | None
    enrolment: int
    mode: str
    needs_room: bool
    day: int | None
    start: int | None
    end: int | None
    weeks: frozenset[int]
    flexible: bool
    status: str
    definitive: tuple[int, ...]
    requested: tuple[int, ...]
    requested_building: str | None
    requested_tags: tuple[str, ...]
    ts: datetime
    instructors: tuple[int, ...] = ()


@dataclass
class Report:
    """Rows added per kind and what was left out (and why)."""

    added: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    excluded_requests: dict[str, list[int]] = field(default_factory=dict)

    def skip(self, why: str, k: int = 1) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + k

    def as_dict(self) -> dict[str, Any]:
        return {
            "added": dict(sorted(self.added.items())),
            "added_total": sum(self.added.values()),
            "skipped": dict(sorted(self.skipped.items())),
            "excluded": {k: len(v) for k, v in self.excluded_requests.items()},
        }


def _ints(values: Iterable[Any] | None) -> tuple[int, ...]:
    out: list[int] = []
    for v in values or ():
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return tuple(dict.fromkeys(out))


class _Ctx:
    def __init__(self) -> None:
        self.rooms: dict[int, Room] = {}
        self.building: dict[int, str] = {}  # room id -> building code
        self.reqs: dict[int, _Req] = {}
        self.double_booked: set[int] = set()
        self.instructor_user: dict[int, int] = {}  # instructor id -> user id
        self.user_instructor: dict[int, int] = {}
        self.resets: list[LearningReset] = []

    # -- room evidence rules ------------------------------------------------------------------------------
    def seats(self, room_ids: Iterable[int]) -> int | None:
        """Known seats of a room set, or None when a room's capacity is unknown (0) or the room is missing."""
        total = 0
        for rid in room_ids:
            room = self.rooms.get(rid)
            if room is None or not room.capacity:
                return None
            total += int(room.capacity)
        return total

    def over_capacity(self, r: _Req, room_ids: Iterable[int]) -> bool:
        seats = self.seats(room_ids)
        return seats is not None and r.enrolment > seats

    def room_evidence(self, r: _Req) -> bool:
        return r.needs_room and r.mode in ROOM_MODES and len(r.weeks) != 1

    def subjects(self, r: _Req, *, section: bool = True, program: bool = True) -> list[tuple[str, str]]:
        out = [("course", str(r.course_id))]
        if section:
            out.append(("section", str(r.section_id)))
        if program and r.program_id is not None:
            out.append(("program", str(r.program_id)))
        out.extend(("instructor", str(i)) for i in r.instructors)
        return out

    def room_values(self, room_ids: Iterable[int]) -> list[tuple[str, str]]:
        ids = [rid for rid in room_ids if rid in self.rooms]
        out = [("room", str(rid)) for rid in ids]
        out.extend(("building", b) for b in dict.fromkeys(self.building[rid] for rid in ids if rid in self.building))
        return out

    def detail(self, r: _Req, rooms: Iterable[int] = ()) -> dict[str, Any]:
        return {
            "request_id": r.id,
            "course": r.course_code,
            "section": r.label,
            "day": r.day,
            "periods": [r.start, r.end] if r.start is not None else None,
            "rooms": [self.rooms[x].display_name for x in rooms if x in self.rooms],
        }

    # -- watermark ------------------------------------------------------------------------------------------
    def blocked(self, o: Obs) -> bool:
        """Evidence a (not undone) reset covers: dated up to its watermark and inside its scope."""
        for rs in self.resets:
            if o.ts > rs.watermark:
                continue
            if rs.scope_type == "all":
                return True
            if rs.scope_type == "term" and o.term_id is not None and str(o.term_id) == rs.scope_value:
                return True
            if rs.scope_type == "person" and rs.scope_value is not None:
                if o.subject_type == "instructor" and o.subject_key == rs.scope_value:
                    return True
                uid = self.instructor_user.get(int(rs.scope_value)) if rs.scope_value.isdigit() else None
                if o.subject_type == "user" and uid is not None and o.subject_key == str(uid):
                    return True
        return False


async def _load(session: AsyncSession) -> _Ctx:
    ctx = _Ctx()
    codes = {b.id: b.code for b in (await session.execute(select(Building))).scalars()}
    for room in (await session.execute(select(Room))).scalars():
        ctx.rooms[room.id] = room
        if room.building_id in codes:
            ctx.building[room.id] = n.tr_upper(codes[room.building_id]).strip()
    for ins in (await session.execute(select(Instructor))).scalars():
        if ins.user_id is not None:
            ctx.instructor_user[ins.id] = ins.user_id
            ctx.user_instructor[ins.user_id] = ins.id
    people: dict[int, list[int]] = defaultdict(list)
    names = {i.id: i.full_name for i in (await session.execute(select(Instructor))).scalars()}
    for si in (await session.execute(select(SectionInstructor).where(SectionInstructor.role == "PRIMARY"))).scalars():
        if n.non_person_reason(names.get(si.instructor_id)) is None:  # "Yabancı Diller", "Yüz yüze" ...
            people[si.section_id].append(si.instructor_id)
    q = (
        select(MeetingRequest, Section, Course.display_code)
        .join(Section, Section.id == MeetingRequest.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(MeetingRequest.archived.is_(False), Section.archived.is_(False))
    )
    for mr, sec, code in (await session.execute(q)).all():
        ctx.reqs[mr.id] = _Req(
            id=mr.id,
            term_id=sec.term_id,
            section_id=sec.id,
            course_id=sec.course_id,
            program_id=sec.program_id,
            course_code=code,
            label=sec.label,
            enrolment=int(sec.enrolment or 0),
            mode=(sec.mode or "F2F").upper(),
            needs_room=bool(mr.needs_room),
            day=mr.day,
            start=mr.start_period,
            end=mr.end_period if mr.end_period is not None else mr.start_period,
            weeks=frozenset(_ints(mr.weeks)),
            flexible=bool(mr.flexible_day),
            status=(mr.status or "").upper(),
            definitive=_ints(mr.definitive_room_ids),
            requested=_ints(mr.requested_room_ids),
            requested_building=n.tr_upper(mr.requested_building).strip() if mr.requested_building else None,
            requested_tags=tuple(str(t).upper() for t in (mr.requested_tags or []) if t),
            ts=mr.updated_at or mr.created_at or utcnow(),
            instructors=tuple(sorted(people.get(sec.id, []))),
        )
    ctx.double_booked = locked_double_bookings(ctx.reqs.values())
    ctx.resets = list((await session.execute(select(LearningReset).where(LearningReset.undone_at.is_(None)))).scalars())
    return ctx


def _same_lecture(a: _Req, b: _Req) -> bool:
    """Rows of one lecture listed twice: the same room set and the same start, or the same course."""
    if set(a.definitive) != set(b.definitive):
        return False
    return a.start == b.start or a.course_id == b.course_id


def locked_double_bookings(reqs: Iterable[_Req]) -> set[int]:
    """Ids of LOCKED requests that share a room with another lecture at overlapping periods of common weeks."""
    by_slot: dict[tuple[int, int], list[_Req]] = defaultdict(list)
    for r in reqs:
        if r.status != "LOCKED" or not r.definitive or r.day is None or r.start is None:
            continue
        for rid in r.definitive:
            by_slot[(r.term_id, r.day * 1000 + rid)].append(r)
    out: set[int] = set()
    for rows in by_slot.values():
        for a, b in itertools.combinations(rows, 2):
            assert a.start is not None and b.start is not None and a.end is not None and b.end is not None
            if a.start > b.end or b.start > a.end:
                continue
            if a.weeks and b.weeks and not a.weeks & b.weeks:
                continue
            if _same_lecture(a, b):
                continue
            out.update((a.id, b.id))
    return out


# --------------------------------------------------------------------------------------------- extractors


def _definitive(ctx: _Ctx, rep: Report) -> Iterator[Obs]:
    for r in ctx.reqs.values():
        if not r.definitive:
            continue
        if not ctx.room_evidence(r):
            rep.skip("definitive_no_room_need")
            continue
        if r.id in ctx.double_booked:
            rep.excluded_requests.setdefault("locked_double_booking", []).append(r.id)
            continue
        if ctx.over_capacity(r, r.definitive):
            rep.excluded_requests.setdefault("over_capacity_lock", []).append(r.id)
            continue
        detail = ctx.detail(r, r.definitive)
        for (st, sk), (attr, val) in itertools.product(ctx.subjects(r), ctx.room_values(r.definitive)):
            yield Obs(r.ts, r.term_id, "definitive_room", st, sk, attr, val, "meeting_requests", r.id, None, detail)


def _requests(ctx: _Ctx, rep: Report) -> Iterator[Obs]:
    for r in ctx.reqs.values():
        values: list[tuple[str, str]] = []
        if ctx.room_evidence(r):
            rooms = [x for x in r.requested if not ctx.over_capacity(r, [x])]
            if len(rooms) < len(r.requested):
                rep.skip("request_room_over_capacity", len(r.requested) - len(rooms))
            values.extend(ctx.room_values(rooms))
            if r.requested_building and ("building", r.requested_building) not in values:
                values.append(("building", r.requested_building))
            values.extend(("tag", t) for t in dict.fromkeys(r.requested_tags))
        detail = ctx.detail(r, r.requested)
        for (st, sk), (attr, val) in itertools.product(ctx.subjects(r, program=False), values):
            yield Obs(r.ts, r.term_id, "request_text", st, sk, attr, val, "meeting_requests", r.id, None, detail)
        if r.day is None or r.start is None or r.flexible:
            continue
        band = band_of(r.start)
        times = [("day", str(r.day))]
        if band:
            times += [("period", band), ("day_period", f"{r.day}:{band}")]
        for (st, sk), (attr, val) in itertools.product(ctx.subjects(r, section=False, program=False), times):
            yield Obs(r.ts, r.term_id, "request_time", st, sk, attr, val, "meeting_requests", r.id, None, detail)


async def _corrections(session: AsyncSession, ctx: _Ctx, rep: Report) -> list[Obs]:
    """A planner edit after import (studio snapshot of the imported values vs the current row)."""
    out: list[Obs] = []
    snaps = (await session.execute(select(ImportedSnapshot).where(ImportedSnapshot.entity == "meeting"))).scalars()
    for snap in snaps:
        r = ctx.reqs.get(snap.entity_id)
        if r is None or not snap.values:
            continue
        before = set(_ints(snap.values.get("definitive_room_ids")))
        after = set(r.definitive)
        if before == after or not ctx.room_evidence(r):
            continue
        detail = {
            **ctx.detail(r, r.definitive),
            "before": [ctx.rooms[x].display_name for x in before if x in ctx.rooms],
        }
        gained = [x for x in r.definitive if x not in before]
        if gained and ctx.over_capacity(r, r.definitive):
            rep.skip("correction_over_capacity")
            gained = []
        lost = [x for x in before if x not in after]
        ts = snap.created_at or r.ts
        gained_vals = ctx.room_values(gained)
        # a building is "left" only when the new rooms are not in it
        kept_buildings = {v for a, v in ctx.room_values(after) if a == "building"}
        lost_vals = [(a, v) for a, v in ctx.room_values(lost) if a == "room" or v not in kept_buildings]
        for st, sk in ctx.subjects(r):
            for attr, val in gained_vals:
                out.append(
                    Obs(ts, r.term_id, "correction_to", st, sk, attr, val, "imported_snapshots", snap.id, None, detail)
                )
            for attr, val in lost_vals:
                out.append(
                    Obs(
                        ts, r.term_id, "correction_away", st, sk, attr, val, "imported_snapshots", snap.id, None, detail
                    )
                )
    return out


async def _assignments(session: AsyncSession, ctx: _Ctx, rep: Report) -> list[Obs]:
    """Manual / AI moves (+2 to the new rooms, -2 away from the parent run's rooms) and locks (+2)."""
    runs = {r.id: r for r in (await session.execute(select(ScheduleRun))).scalars()}
    q = select(Assignment).where(
        Assignment.meeting_request_id.is_not(None),
        Assignment.archived.is_(False),
        (Assignment.origin.in_(("MANUAL", "AI_EDIT"))) | (Assignment.is_locked.is_(True)),
    )
    rows = list((await session.execute(q.order_by(Assignment.id))).scalars())
    parents: dict[tuple[int, int], set[int]] = {}
    parent_ids = {runs[a.run_id].parent_run_id for a in rows if a.run_id in runs and runs[a.run_id].parent_run_id}
    if parent_ids:
        pq = select(Assignment).where(Assignment.run_id.in_(parent_ids), Assignment.meeting_request_id.is_not(None))
        for pa in (await session.execute(pq)).scalars():
            assert pa.meeting_request_id is not None
            parents.setdefault((pa.run_id, pa.meeting_request_id), set()).update(_ints(pa.room_ids))
    seen: set[tuple[str, int, tuple[int, ...]]] = set()
    out: list[Obs] = []
    for a in rows:
        assert a.meeting_request_id is not None
        r = ctx.reqs.get(a.meeting_request_id)
        run = runs.get(a.run_id)
        if r is None or run is None or not ctx.room_evidence(r):
            continue
        rooms = _ints(a.room_ids)
        if not rooms:
            continue
        ts = run.created_at or r.ts
        moved = a.origin in ("MANUAL", "AI_EDIT")
        kind = "move_to" if moved else "lock"
        if not moved and (a.origin == "IMPORT" or set(rooms) == set(r.definitive)):
            continue  # a lock that only repeats the planning list (already learned as definitive_room)
        once = (kind, r.id, tuple(sorted(rooms)))  # per-week rows and carried locks count once
        if once in seen:
            continue
        seen.add(once)
        if ctx.over_capacity(r, rooms):
            rep.skip(f"{kind}_over_capacity")
            continue
        detail = {**ctx.detail(r, rooms), "run_id": a.run_id, "origin": a.origin}
        before = parents.get((run.parent_run_id or 0, r.id), set())
        lost = [x for x in before if x not in rooms] if moved else []
        kept_buildings = {v for at, v in ctx.room_values(rooms) if at == "building"}
        for st, sk in ctx.subjects(r):
            for attr, val in ctx.room_values(rooms):
                out.append(Obs(ts, r.term_id, kind, st, sk, attr, val, "assignments", a.id, run.created_by, detail))
            for attr, val in ctx.room_values(lost):
                if attr == "building" and val in kept_buildings:
                    continue
                out.append(
                    Obs(ts, r.term_id, "move_away", st, sk, attr, val, "assignments", a.id, run.created_by, detail)
                )
    return out


async def _bookings(session: AsyncSession, ctx: _Ctx) -> list[Obs]:
    out: list[Obs] = []
    for s in (await session.execute(select(BookingSeries).where(BookingSeries.status == BOOKED))).scalars():
        if s.user_id is None:
            continue
        subjects = [("user", str(s.user_id))]
        if s.user_id in ctx.user_instructor:
            subjects.append(("instructor", str(ctx.user_instructor[s.user_id])))
        values = [*ctx.room_values([s.room_id]), ("day", str(s.weekday))]
        detail = {"series_id": s.id, "rooms": [ctx.rooms[s.room_id].display_name] if s.room_id in ctx.rooms else []}
        ts = s.created_at or utcnow()
        for (st, sk), (attr, val) in itertools.product(subjects, values):
            out.append(
                Obs(ts, s.term_id, "booking_series", st, sk, attr, val, "booking_series", s.id, s.created_by, detail)
            )
    q = select(ApprovalRequest).where(ApprovalRequest.status.in_(("APPROVED", "REJECTED")))
    for ar in (await session.execute(q)).scalars():
        if ar.requested_by is None:
            continue
        kind = "approval_approved" if ar.status == "APPROVED" else "approval_rejected"
        subjects = [("user", str(ar.requested_by))]
        if ar.requested_by in ctx.user_instructor:
            subjects.append(("instructor", str(ctx.user_instructor[ar.requested_by])))
        detail = {
            "approval_id": ar.id,
            "rooms": [ctx.rooms[ar.room_id].display_name] if ar.room_id in ctx.rooms else [],
        }
        ts = ar.decided_at or ar.requested_at or utcnow()
        for (st, sk), (attr, val) in itertools.product(subjects, ctx.room_values([ar.room_id])):
            out.append(Obs(ts, ar.term_id, kind, st, sk, attr, val, "approval_requests", ar.id, None, detail))
    return out


async def _planning_audit(session: AsyncSession, ctx: _Ctx) -> list[Obs]:  # noqa: ARG001
    """Hook for the planning audit (P19-02: ``audit_events`` rows of entity ``assignment`` / ``meeting_request``
    written by ``services/planning_audit.py``).

    TODO(P19-02): once the planning audit has run for a term, read its ``assignment.move`` / ``.lock`` /
    ``meeting_request.update`` rows (before -> after rooms) as ``move_to`` / ``move_away`` / ``correction_*``
    observations with ``source_table="audit_events"``, and drop the parent-run comparison in
    :func:`_assignments` for runs the audit covers (one source per edit, never both)."""
    return []


async def extract(session: AsyncSession) -> Report:
    """Run every extractor and insert the observations not stored yet. Idempotent: a re-run adds 0 rows."""
    rep = Report()
    ctx = await _load(session)
    candidates: list[Obs] = [*_definitive(ctx, rep), *_requests(ctx, rep)]
    candidates += await _corrections(session, ctx, rep)
    candidates += await _assignments(session, ctx, rep)
    candidates += await _bookings(session, ctx)
    candidates += await _planning_audit(session, ctx)

    cols = (
        LearnedObservation.source_table,
        LearnedObservation.source_id,
        LearnedObservation.kind,
        LearnedObservation.subject_type,
        LearnedObservation.subject_key,
        LearnedObservation.attribute,
        LearnedObservation.value,
    )
    existing = {tuple(row) for row in (await session.execute(select(*cols))).all()}
    fresh: dict[tuple[str, int, str, str, str, str, str], Obs] = {}
    for o in candidates:
        if o.key in existing or o.key in fresh:
            continue
        if ctx.blocked(o):
            rep.skip("reset_watermark")
            continue
        fresh[o.key] = o
    rows = [o.row() for o in fresh.values()]
    for chunk in range(0, len(rows), 2000):
        await session.execute(insert(LearnedObservation), rows[chunk : chunk + 2000])
    for o in fresh.values():
        rep.added[o.kind] = rep.added.get(o.kind, 0) + 1
    await session.flush()
    return rep


__all__ = [
    "BANDS",
    "ROOM_MODES",
    "SIGNALS",
    "Obs",
    "Report",
    "band_of",
    "band_range",
    "extract",
    "locked_double_bookings",
]
