"""Phase 19 moderation tab, backend (P19-M1..M3; docs/design/v2/phase19-moderation.md, review §3d).

Read models (M1):

* :func:`people` - one row per academician of a term: sections, requests, the match rate against the
  published run (or the planner's definitive rooms when the term has no published run), active preferences,
  learned priors (``app/services/learning.py``), accessibility as yes / no only and the
  "N dönemdir karşılanmadı" badge (academician needs Q6: shown, never an automatic boost).
* :func:`history` - a cross-term timeline per request: the raw cell and the parsed request, the definitive
  room, the published run's placement and verdict, the planner's edits (imported snapshot diff, audit events)
  and the bookings of the linked user (``Instructor.user_id``).
* :func:`matchings` - request -> assignment with satisfied flags for room / building / tags / day / period and
  one reason; the API adds ``calendar_views.classes`` issues and ``planner_check`` findings.

Visibility (Q11, KVKK data minimisation): :func:`visibility`.

Priorities (M2): :func:`set_section_priority`, :func:`set_request_priority` (audited); the bridge reads them
(``solver_bridge.stored_priorities``).

Re-solve (M3): :func:`create_resolve` + :func:`run_resolve` - a child run of a finished run with stability and
the carried locks, one CP-SAT worker, never activated; ``repair`` frees only the neighbourhood of the changed
requests (``app.solver.repair.repair``), ``full`` re-solves everything with stability. :func:`resolve_diff`
compares the child with its base: moved (from -> to, with the cause), unchanged, newly placed, unplaceable
(with the reason), hard / soft score, waived rules. Academician needs Q9: in ``repair`` mode no published class
outside the changed requests moves unless that places more (:func:`_minimal_change`).

Draft edits (M3): :func:`matching_action` writes a targeted pin / preference (``constraint_guard``) or an unlock
on a draft child run, never on the published run.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers import normalize as n
from app.models import (
    Assignment,
    AuditEvent,
    Booking,
    ConstraintRow,
    ImportedSnapshot,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
    User,
)
from app.services.bookings_perms import Access
from app.services.calendar_views import clock, tr_fold, when
from app.solver import model as sm

log = logging.getLogger(__name__)

FLAGS = ("room", "building", "tags", "day", "period")
ROOM_SIDE = ("room", "building", "tags")
#: verdicts (moderation spec §13: Karşılandı / Kısmen / Karşılanmadı / Yerleşmedi; plus the not-evaluated ones)
VERDICTS = ("satisfied", "partial", "not_as_requested", "unplaced", "not_evaluated", "pending")
UNSATISFIED = frozenset({"partial", "not_as_requested", "unplaced"})
VERDICT_TEXT: dict[str, tuple[str, str]] = {
    "satisfied": ("Karşılandı", "Satisfied"),
    "partial": ("Kısmen", "Partly"),
    "not_as_requested": ("Karşılanmadı", "Not as requested"),
    "unplaced": ("Yerleşmedi", "Not placed"),
    "not_evaluated": ("Değerlendirilmedi", "Not evaluated"),
    "pending": ("Karar yok", "No decision yet"),
}
#: run statuses whose timetable a re-solve may start from (a finished run with placements)
BASE_STATUSES = frozenset({"OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"})
#: the "N dönemdir karşılanmadı" badge is shown from this many terms in a row (Q6)
STREAK_BADGE_FROM = 2
#: priority tiers of the priority-policy spec (3 tiers, Normal = 0); any int in run_params.PRIORITY_RANGE works
PRIORITY_TIERS = {"high": 1, "normal": 0, "low": -1}
#: stability weight multiplier of a moderation re-solve: moving a published class costs more than any soft wish
RESOLVE_STABILITY_WEIGHT = 10
DEFAULT_RADIUS = 1
MAX_CHANGED = 500
#: policy step of a loss reason (``app.solver.policy.LOSS_REASONS``; priority-policy spec §5.4)
POLICY_STEP: dict[str, tuple[int, str, str]] = {
    "locked_row_kept": (1, "adım 1 · kilit", "step 1 · lock"),
    "lock_clash_tie": (1, "adım 1 · kilit", "step 1 · lock"),
    "lock_clash_more_locks": (1, "adım 1 · kilit", "step 1 · lock"),
    "lock_clash_priority": (2, "adım 2 · öncelik", "step 2 · priority"),
    "lower_priority": (2, "adım 2 · öncelik", "step 2 · priority"),
    "most_classes": (3, "adım 3 · en çok ders", "step 3 · most classes"),
}


class ModerationError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


# ------------------------------------------------------------------------------------------- visibility (Q11)


@dataclass(frozen=True)
class Scope:
    """Whose requests the caller may see: everyone (``all``) or the instructors linked to the caller."""

    all: bool
    instructor_ids: frozenset[int] = frozenset()
    basis: str = "planning.view"

    def allows(self, instructor_ids: Iterable[int]) -> bool:
        return self.all or bool(self.instructor_ids & set(instructor_ids))


async def visibility(session: AsyncSession, access: Access) -> Scope:
    """Q11: an academician sees only their own requests (``Instructor.user_id``); a coordinator / admin sees all.

    The department secretary ("sees their department") has no role or permission of its own in the user model:
    ``users.department_id`` names a programme, but nothing marks a user as that programme's secretary.
    TODO(Q11 department scope): once a department-scoped planning role exists, return the instructors of the
    sections of ``users.department_id`` here; until then ``planning.view`` sees all (the Viewer role is the
    institution's read-only plan role)."""
    if "planning.view" in access.perms:
        return Scope(True)
    linked = frozenset(
        int(i)
        for i in (await session.execute(select(Instructor.id).where(Instructor.user_id == access.user.id))).scalars()
    )
    if not linked:
        raise ModerationError(
            403, "requires permission planning.view, or an instructor record linked to your account (own requests)"
        )
    return Scope(False, linked, "own")


async def current_term_brief(session: AsyncSession) -> dict[str, Any] | None:
    """The current term (``terms.load_current_term``: active, else today's) in a form any signed-in user may read:
    no planning data beyond the published course run's id."""
    from app.services.terms import load_current_term

    term = await load_current_term(session)
    if term is None:
        return None
    pub = await published_run(session, term.id)
    return {
        "id": term.id,
        "code": term.code,
        "name": term.name,
        "kind": term.kind,
        "start_date": term.start_date.isoformat() if term.start_date else None,
        "end_date": term.end_date.isoformat() if term.end_date else None,
        "week_count": term.week_count,
        "published_run_id": pub.id if pub else None,
    }


async def me(session: AsyncSession, access: Access) -> dict[str, Any]:
    """``GET /moderation/me``: the caller's instructor link and visibility (Q11), plus the current term."""
    linked = list(
        (
            await session.execute(
                select(Instructor).where(Instructor.user_id == access.user.id).order_by(Instructor.id)
            )
        ).scalars()
    )
    sees_all = "planning.view" in access.perms
    from app.services import teacher_preferences as tp

    return {
        "user_id": access.user.id,
        "instructor_id": linked[0].id if linked else None,
        "instructor_ids": [i.id for i in linked],
        "instructor": (
            {"id": linked[0].id, "full_name": linked[0].full_name, "title": linked[0].title} if linked else None
        ),
        "visibility": "all" if sees_all else ("own" if linked else "none"),
        "can_edit": "planning.edit" in access.perms,
        # P19-T2 "Tercih ekle": a linked academician may add wishes for their own classes
        "can_add_preference": bool(linked),
        "preferences": await tp.counts_for_user(session, access.user),
        "current_term": await current_term_brief(session),
    }


# ------------------------------------------------------------------------------------------- matching core


@dataclass(frozen=True)
class Place:
    day: int
    start: int
    end: int
    room_ids: tuple[int, ...]
    weeks: tuple[int, ...]
    locked: bool = False
    origin: str = "SOLVER"


@dataclass
class Want:
    """What the department form asked for (Q12: the form is the official request)."""

    room_groups: list[frozenset[str]] = field(default_factory=list)  # canonical codes, alternatives
    avoid_rooms: frozenset[str] = frozenset()
    building: str | None = None
    buildings: frozenset[str] = frozenset()
    tags: frozenset[str] = frozenset()
    days: frozenset[int] = frozenset()
    start: int | None = None
    end: int | None = None


def _ints(values: Iterable[Any] | None) -> list[int]:
    out: list[int] = []
    for v in values or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def wanted(mr: MeetingRequest, rooms: Mapping[int, Room]) -> Want:
    """The request's wishes: room ids when the importer resolved them, else the codes in the cell text (a room
    outside the room master, e.g. PHY 102's ``D 204``), alternatives kept as groups."""
    vr = n.parse_venue_request(mr.requested_room_text) if mr.requested_room_text else None
    ids = [r for r in _ints(mr.requested_room_ids) if r in rooms]
    groups: list[frozenset[str]] = []
    if vr is not None and vr.room_groups:
        groups = [frozenset(g) for g in vr.room_groups if g]
    elif vr is not None and vr.room_codes:
        groups = [frozenset(vr.room_codes)]
    if ids and not groups:
        groups = [frozenset(rooms[r].code for r in ids)]
    days = frozenset(_ints(mr.days) or ([mr.day] if mr.day else []))
    return Want(
        room_groups=groups,
        avoid_rooms=frozenset(vr.avoid_room_codes) if vr is not None else frozenset(),
        building=mr.requested_building or (vr.building if vr is not None else None),
        buildings=frozenset(vr.buildings) if vr is not None else frozenset(),
        tags=frozenset(str(t).upper() for t in (mr.requested_tags or []) if str(t).upper() not in ("LAB",)),
        days=days,
        start=mr.start_period,
        end=mr.end_period,
    )


def _building(room: Room | None) -> str | None:
    return room.code[:1] if room is not None and room.code else None


def flags_for(want: Want, place: Place | None, rooms: Mapping[int, Room]) -> dict[str, bool | None]:
    """``True`` asked and got, ``False`` asked and not got, ``None`` nothing asked (or nothing placed)."""
    out: dict[str, bool | None] = dict.fromkeys(FLAGS)
    if place is None:
        return out
    codes = {rooms[r].code for r in place.room_ids if r in rooms}
    if want.room_groups:
        out["room"] = any(g <= codes for g in want.room_groups) and not (codes & want.avoid_rooms)
    elif want.avoid_rooms:
        out["room"] = not (codes & want.avoid_rooms)
    blds = {_building(rooms.get(r)) for r in place.room_ids if r in rooms}
    if want.building:
        out["building"] = bool(blds) and blds == {want.building}
    elif want.buildings:
        out["building"] = bool(blds) and blds <= set(want.buildings)
    if want.tags:
        have = {str(t).upper() for r in place.room_ids if r in rooms for t in (rooms[r].tags or [])}
        out["tags"] = want.tags <= have
    if want.days:
        out["day"] = place.day in want.days
    if want.start is not None and want.end is not None:
        out["period"] = (place.start, place.end) == (want.start, want.end)
    return out


def verdict_of(flags: Mapping[str, bool | None]) -> str:
    """``satisfied``: every evaluated wish holds; ``partial``: a room-side wish (room / building / tags) holds and
    another fails; ``not_as_requested``: otherwise (no room-side wish holds, or the day / period differ)."""
    evaluated = {k: v for k, v in flags.items() if v is not None}
    if all(evaluated.values()):
        return "satisfied"
    if flags.get("day") is False or flags.get("period") is False:
        return "not_as_requested"
    room_side = [flags.get(k) for k in ROOM_SIDE if flags.get(k) is not None]
    if any(room_side):
        return "partial"
    return "not_as_requested"


def place_of(rows: list[Assignment]) -> Place | None:
    """The request's placement in a run: the row covering most weeks gives day / time; rooms and weeks are the
    union (a week-segmented term run stores one row per room set)."""
    if not rows:
        return None
    first = sorted(rows, key=lambda a: (-len(a.weeks or []), a.id))[0]
    rids: list[int] = []
    for a in rows:
        for r in _ints(a.room_ids):
            if r not in rids:
                rids.append(r)
    weeks = sorted({int(w) for a in rows for w in (a.weeks or ([a.week] if a.week else []))})
    return Place(
        first.day,
        first.start_period,
        first.end_period,
        tuple(rids),
        tuple(weeks),
        all(a.is_locked for a in rows),
        str(first.origin or "SOLVER"),
    )


def _definitive_place(mr: MeetingRequest) -> Place | None:
    ids = tuple(_ints(mr.definitive_room_ids))
    if not ids or not mr.day or mr.start_period is None or mr.end_period is None:
        return None
    return Place(mr.day, mr.start_period, mr.end_period, ids, tuple(_ints(mr.weeks)), mr.status == "LOCKED", "IMPORT")


# ------------------------------------------------------------------------------------------- term context


@dataclass
class TermData:
    term: Term
    run: ScheduleRun | None
    rooms: dict[int, Room]
    meetings: list[MeetingRequest]
    rows_by_mr: dict[int, list[Assignment]]
    diag_by_request: dict[int, dict[str, Any]]
    occupancy: dict[tuple[int, int], list[tuple[int, int, frozenset[int], int]]]  # (room, day) -> spans
    labels: dict[int, str]
    member_of: dict[int, int]  # request -> its solver event (joint lecture head)
    #: person / programme priorities of the term (``priority_overrides``, P19-P-04)
    priorities: Any = None


def label_of(mr: MeetingRequest) -> str:
    sec = mr.section
    code = sec.course.display_code if sec.course else f"#{sec.course_id}"
    return f"{code}{f' §{sec.label}' if sec.label else ''}"


async def published_run(session: AsyncSession, term_id: int, kind: str = "COURSE") -> ScheduleRun | None:
    return (
        (
            await session.execute(
                select(ScheduleRun)
                .where(ScheduleRun.term_id == term_id, ScheduleRun.kind == kind, ScheduleRun.is_active.is_(True))
                .order_by(ScheduleRun.id.desc())
            )
        )
        .scalars()
        .first()
    )


async def all_rooms(session: AsyncSession) -> dict[int, Room]:
    return {r.id: r for r in (await session.execute(select(Room))).scalars()}


def _meeting_query() -> Any:
    return select(MeetingRequest).options(
        selectinload(MeetingRequest.section).selectinload(Section.course),
        selectinload(MeetingRequest.section).selectinload(Section.program).selectinload(Program.faculty),
        selectinload(MeetingRequest.section)
        .selectinload(Section.instructors)
        .selectinload(SectionInstructor.instructor),
    )


def _board_placements(meetings: list[MeetingRequest], rows: list[Assignment]) -> list[Assignment]:
    """Round-1 T-R1-39 part 2: an imported board's rows carry no request link (``meeting_request_id`` is None; the
    grid importer writes one row per period cell with the cell's course codes). For the match rate they are read
    against the term's requests the way the importer links them: the same course code (``normalize.course_key``),
    day and period (the row's period inside the request's range, its week among the request's weeks). Parallel
    sections of one course at one time take the room the planner wrote for them; the rest take the board's rooms
    in list order. Returns one transient row per request and room set (its period range and weeks merged; never
    added to the session), so :func:`place_of` reads it like a solver row."""
    by_course: dict[tuple[str, int], list[MeetingRequest]] = defaultdict(list)
    for mr in meetings:
        if mr.day is None or mr.start_period is None or mr.end_period is None or mr.section.course is None:
            continue
        by_course[(n.course_key(mr.section.course.code), mr.day)].append(mr)
    for ms in by_course.values():
        ms.sort(key=lambda m: (m.source_row_index if m.source_row_index is not None else 1 << 30, m.id))
    # (course key, day, rooms) -> the board's one-period rows of that course in that room on that day
    cells: dict[tuple[str, int, tuple[int, ...]], list[Assignment]] = defaultdict(list)
    for a in rows:
        rids = tuple(sorted(set(_ints(a.room_ids))))
        if a.meeting_request_id is not None or a.day is None or not rids:
            continue
        for code in a.course_codes or []:
            key = n.course_key(str(code))
            if (key, a.day) in by_course:
                cells[(key, a.day, rids)].append(a)
    # claims: (request, cell) with the rows inside the request's period range and weeks
    claims: list[tuple[int, int, MeetingRequest, tuple[str, int, tuple[int, ...]], list[Assignment]]] = []
    for ck, cell_rows in cells.items():
        key, day, rids = ck
        for mr in by_course[(key, day)]:
            lo, hi = int(mr.start_period or 0), int(mr.end_period or 0)
            weeks = set(_ints(mr.weeks))
            mine = [
                a
                for a in cell_rows
                if lo <= a.start_period and a.end_period <= hi and (not weeks or a.week is None or int(a.week) in weeks)
            ]
            if not mine:
                continue
            own_rooms = set(_ints(mr.definitive_room_ids)) | set(_ints(mr.requested_room_ids))
            # the planner's own room first, then the list order of the requests, then the room
            claims.append((0 if own_rooms & set(rids) else 1, mr.source_row_index or 0, mr, ck, mine))
    claims.sort(key=lambda c: (c[0], c[1], c[2].id, c[3][2]))
    taken_rows: set[int] = set()
    placed: set[int] = set()
    out: list[Assignment] = []
    for _rank, _row, mr, ck, mine in claims:
        if mr.id in placed or any(a.id in taken_rows for a in mine):
            continue
        placed.add(mr.id)
        taken_rows.update(a.id for a in mine)
        merged_weeks = sorted({int(w) for a in mine for w in (_ints(a.weeks) or ([a.week] if a.week else []))})
        out.append(
            Assignment(
                id=min(a.id for a in mine),
                run_id=mine[0].run_id,
                meeting_request_id=mr.id,
                week=None,
                weeks=merged_weeks,
                day=ck[1],
                start_period=min(a.start_period for a in mine),
                end_period=max(a.end_period for a in mine),
                room_ids=list(ck[2]),
                label=mine[0].label,
                course_codes=list(mine[0].course_codes or []),
                tags=[],
                is_locked=False,
                origin="IMPORT",
                archived=False,
            )
        )
    return out


async def load_term(
    session: AsyncSession,
    term: Term,
    run: ScheduleRun | None,
    *,
    rooms: dict[int, Room] | None = None,
    request_ids: Iterable[int] | None = None,
) -> TermData:
    rooms = rooms if rooms is not None else await all_rooms(session)
    q = (
        _meeting_query()
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(Section.term_id == term.id, MeetingRequest.archived.is_(False))
        .order_by(MeetingRequest.source_row_index, MeetingRequest.id)
    )
    if request_ids is not None:
        q = q.where(MeetingRequest.id.in_(list(request_ids)))
    meetings = list((await session.execute(q)).scalars())
    rows_by_mr: dict[int, list[Assignment]] = defaultdict(list)
    occupancy: dict[tuple[int, int], list[tuple[int, int, frozenset[int], int]]] = defaultdict(list)
    diag_by_request: dict[int, dict[str, Any]] = {}
    member_of: dict[int, int] = {}
    labels = {mr.id: label_of(mr) for mr in meetings}
    if run is not None:
        rows = list(
            (
                await session.execute(
                    select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False))
                )
            ).scalars()
        )
        if rows and all(a.meeting_request_id is None for a in rows):
            # an imported board (T-R1-39 part 2): its cells are read against the requests by course, day and period
            rows = _board_placements(meetings, rows)
        for a in rows:
            if a.meeting_request_id is None:
                continue
            rows_by_mr[a.meeting_request_id].append(a)
            weeks = frozenset(_ints(a.weeks) or ([a.week] if a.week else []))
            for r in _ints(a.room_ids):
                occupancy[(r, a.day)].append((a.start_period, a.end_period, weeks, a.meeting_request_id))
        members = {int(k): _ints(v) for k, v in ((run.stats or {}).get("event_members") or {}).items()}
        member_of = {m: h for h, ms in members.items() for m in ms}
        for d in run.diagnosis or []:
            if not isinstance(d, dict) or d.get("severity") != "error":
                continue
            for eid in _ints(d.get("event_ids")):
                for rid in members.get(eid, [eid]):
                    diag_by_request.setdefault(rid, d)
    from app.services.solver_bridge import priority_context

    prios = await priority_context(session, term.id)
    return TermData(term, run, rooms, meetings, rows_by_mr, diag_by_request, occupancy, labels, member_of, prios)


def _in_horizon(mr: MeetingRequest, run: ScheduleRun) -> bool:
    if run.horizon != "WEEK":
        return True
    horizon = set(_ints((run.horizon_params or {}).get("weeks")))
    req = set(_ints(mr.weeks))
    return not horizon or not req or bool(horizon & req)


def _accessibility_phrases() -> tuple[str, ...]:
    return next((ph for key, ph, _t in n.FEATURE_LEXICON if key == "step_free"), ())


ACCESS_TAGS = frozenset({"STEP_FREE", "ACCESSIBLE"})


def mentions_accessibility(text: str | None) -> bool:
    """A free-text wish about step-free access ("Giriş kata yakın olsun"): never shown, only counted as yes."""
    if not text:
        return False
    f = n.fold(text)
    return any(p in f for p in _accessibility_phrases())


def needs_access(mr: MeetingRequest) -> bool:
    tags = {str(t).upper() for t in mr.requested_tags or []}
    return (
        bool(tags & ACCESS_TAGS) or mentions_accessibility(mr.notes) or mentions_accessibility(mr.requested_room_text)
    )


def _room_codes(ids: Iterable[int], rooms: Mapping[int, Room]) -> list[str]:
    return [rooms[r].display_name if r in rooms else f"#{r}" for r in ids]


def _holders(td: TermData, mr: MeetingRequest, place: Place, want: Want) -> list[dict[str, Any]]:
    """Requests of the run sitting in one of the requested rooms at the placed time (the "room taken" reason)."""
    code_to_id = {r.code: r.id for r in td.rooms.values()}
    wanted_ids = {code_to_id[c] for g in want.room_groups for c in g if c in code_to_id}
    weeks = set(place.weeks)
    out: list[dict[str, Any]] = []
    for rid in sorted(wanted_ids):
        for s, e, wk, other in td.occupancy.get((rid, place.day), []):
            if other == mr.id or td.member_of.get(other, other) == td.member_of.get(mr.id, mr.id):
                continue
            if s <= place.end and place.start <= e and (not weeks or not wk or weeks & wk):
                item = {
                    "request_id": other,
                    "label": td.labels.get(other, f"#{other}"),
                    "room": td.rooms[rid].display_name,
                }
                if item not in out:
                    out.append(item)
    return out[:5]


def reason_for(
    td: TermData, mr: MeetingRequest, want: Want, place: Place | None, flags: Mapping[str, bool | None], verdict: str
) -> dict[str, Any] | None:
    """One reason for a verdict that is not ``satisfied``: the run's diagnosis for an unplaced request (with the
    policy step), the planning office's decision when the planner's own room was kept (academician needs M2), the
    request that holds the wished room, the room's capacity, or the solver's trade-off."""
    if verdict == "satisfied":
        return None
    size = int(mr.section.enrolment or mr.requested_capacity or 0)
    if verdict == "unplaced":
        d = td.diag_by_request.get(mr.id)
        if d is None:
            return {
                "code": "unplaced",
                "text": _t("Bu çözümde yerleşmedi.", "Not placed in this run."),
                "culprits": [],
                "policy_step": None,
            }
        pol = ((d.get("params") or {}).get("policy") or {}) if isinstance(d.get("params"), dict) else {}
        step = POLICY_STEP.get(str(pol.get("reason") or ""))
        text = d.get("text") if isinstance(d.get("text"), dict) else None
        culprits = [{"request_id": w, "label": td.labels.get(int(w), f"#{w}")} for w in _ints(pol.get("winners"))[:5]]
        return {
            "code": str(d.get("code") or "unplaced"),
            "text": text or _t(str(d.get("message") or "Yerleşmedi"), str(d.get("message") or "Not placed")),
            "culprits": culprits,
            "policy_step": {"step": step[0], "text": _t(step[1], step[2])} if step else None,
            "policy_reason": pol.get("reason"),
        }
    if place is None:
        return None
    definitive = set(_ints(mr.definitive_room_ids))
    if flags.get("room") is False or flags.get("building") is False:
        if definitive and set(place.room_ids) == definitive:
            return {
                "code": "planner_decision",
                "text": _t(
                    "Karşılanmadı: planlama birimi kararı (gerekçe girilmemiş)",
                    "Not as requested: planning-office decision (no reason given)",
                ),
                "culprits": [],
                "policy_step": None,
            }
        holders = _holders(td, mr, place, want) if want.room_groups else []
        if holders:
            names = ", ".join(f"{h['label']} ({h['room']})" for h in holders)
            return {
                "code": "room_taken",
                "text": _t(
                    f"İstenen derslik bu saatte dolu: {names}", f"The wished room is taken at this time: {names}"
                ),
                "culprits": holders,
                "policy_step": None,
            }
        code_to = {r.code: r for r in td.rooms.values()}
        small = [
            code_to[c]
            for g in want.room_groups
            for c in sorted(g)
            if c in code_to and size and int(code_to[c].capacity or 0) < size
        ]
        if small:
            r = small[0]
            return {
                "code": "capacity",
                "text": _t(
                    f"{size} öğrenci {r.capacity} kişilik {r.display_name}'e sığmaz",
                    f"{size} students do not fit {r.display_name} ({r.capacity} seats)",
                ),
                "culprits": [],
                "policy_step": None,
            }
        missing = sorted(c for g in want.room_groups for c in g if c not in code_to or not code_to[c].is_bookable)
        if missing:
            return {
                "code": "room_unavailable",
                "text": _t(
                    f"İstenen derslik planlamada yok: {', '.join(missing)}",
                    f"The wished room is not in the planning pool: {', '.join(missing)}",
                ),
                "culprits": [],
                "policy_step": None,
            }
    if flags.get("tags") is False:
        return {
            "code": "tags",
            "text": _t("İstenen özellik atanan derslikte yok", "The assigned room lacks a wished feature"),
            "culprits": [],
            "policy_step": None,
        }
    if flags.get("day") is False or flags.get("period") is False:
        return {
            "code": "time_changed",
            "text": _t("Gün / saat istenenden farklı", "Day / time differ from the request"),
            "culprits": [],
            "policy_step": None,
        }
    return {
        "code": "solver_choice",
        "text": _t(
            "Çözücü başka bir tercihle dengeledi (yumuşak tercih)",
            "The solver traded this wish for another (soft preference)",
        ),
        "culprits": [],
        "policy_step": None,
    }


def _place_out(place: Place | None, rooms: Mapping[int, Room]) -> dict[str, Any] | None:
    if place is None:
        return None
    return {
        "day": place.day,
        "start_period": place.start,
        "end_period": place.end,
        "time": f"{clock(place.start)}–{clock(place.end, True)}",
        "when": _t(when(place.day, place.start, place.end, "tr"), when(place.day, place.start, place.end, "en")),
        "room_ids": list(place.room_ids),
        "rooms": _room_codes(place.room_ids, rooms),
        "weeks": list(place.weeks),
        "locked": place.locked,
        "origin": place.origin,
    }


def effective_priority(mr: MeetingRequest, ctx: Any = None) -> dict[str, Any]:
    """``{value, source}``: request > section > person > programme > default (``solver_bridge.resolve_priority``,
    the bridge's own rule); ``ctx`` is the term's :class:`solver_bridge.PriorityContext` (none: request / section
    only)."""
    from app.services.solver_bridge import PriorityContext, resolve_priority

    sec = mr.section
    value, source = resolve_priority(
        mr.priority,
        sec.priority,
        [si.instructor_id for si in sec.instructors] if ctx is not None and ctx.person else [],
        sec.program_id,
        ctx or PriorityContext(),
    )
    return {"value": value, "source": source}


def match_one(td: TermData, mr: MeetingRequest) -> dict[str, Any]:
    """The request against the run's assignment (or the planner's definitive room without a run)."""
    sec = mr.section
    rooms = td.rooms
    want = wanted(mr, rooms)
    source = "run" if td.run is not None else "planner"
    place: Place | None
    verdict: str
    reason: dict[str, Any] | None = None
    # the bridge's rule: a meeting needs a room unless its row says otherwise (a section's ``mode`` is the mode of
    # one of its rows: PHAR 114 §2 has an online row and a classroom row)
    no_room = not mr.needs_room
    no_time = not mr.day or mr.start_period is None or mr.end_period is None
    if no_room or (td.run is not None and (no_time or not _in_horizon(mr, td.run))):
        place = place_of(td.rows_by_mr.get(mr.id, [])) if td.run is not None else None
        verdict = "not_evaluated"
        why = (
            _t("Derslik gerekmiyor", "No room needed")
            if no_room
            else _t("Gün / saat yok", "No day / time")
            if no_time
            else _t("Bu çözümün haftalarında değil", "Not in this run's weeks")
        )
        reason = {
            "code": "no_room" if no_room else "no_time" if no_time else "out_of_scope",
            "text": why,
            "culprits": [],
            "policy_step": None,
        }
        flags = dict.fromkeys(FLAGS)
    else:
        if td.run is not None:
            place = place_of(td.rows_by_mr.get(mr.id, []))
        else:
            place = _definitive_place(mr)
        flags = flags_for(want, place, rooms)
        if place is None:
            verdict = "unplaced" if td.run is not None else "pending"
        else:
            verdict = verdict_of(flags)
        reason = reason_for(td, mr, want, place, flags, verdict) if verdict != "pending" else None
    definitive_ids = _ints(mr.definitive_room_ids)
    return {
        "request_id": mr.id,
        "section_id": sec.id,
        "term_id": sec.term_id,
        "course_code": sec.course.display_code if sec.course else None,
        "course_name": sec.course.name if sec.course else None,
        "section": sec.label,
        "label": label_of(mr),
        "program": sec.program.name if sec.program else None,
        "faculty": sec.program.faculty.name if sec.program and sec.program.faculty else None,
        "enrolment": sec.enrolment,
        "instructors": [
            {"id": si.instructor_id, "name": si.instructor.full_name, "role": si.role} for si in sec.instructors
        ],
        "requested": {
            "day": mr.day,
            "days": _ints(mr.days),
            "start_period": mr.start_period,
            "end_period": mr.end_period,
            "time": (
                f"{clock(mr.start_period)}–{clock(mr.end_period, True)}"
                if mr.start_period is not None and mr.end_period is not None
                else None
            ),
            "weeks": _ints(mr.weeks),
            "room_text": (mr.requested_room_text or "").strip() or None,
            "rooms": [" + ".join(f"{c[:1]} {c[1:]}" for c in sorted(g)) for g in want.room_groups],
            "building": want.building,
            "tags": sorted(want.tags),
            "capacity": mr.requested_capacity,
            "status": mr.status,
        },
        "definitive": {
            "text": (mr.definitive_room_text or "").strip() or None,
            "room_ids": definitive_ids,
            "rooms": _room_codes(definitive_ids, rooms),
        },
        "assigned": _place_out(place, rooms) if verdict != "pending" else None,
        "satisfied": flags,
        "verdict": verdict,
        "verdict_text": _t(*VERDICT_TEXT[verdict]),
        "reason": reason,
        "priority": effective_priority(mr, td.priorities),
        "source": source,
        "provenance": {"row": mr.source_row_index, "source_key": mr.source_key},
    }


def counts_of(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    out = dict.fromkeys(VERDICTS, 0)
    for it in items:
        out[str(it["verdict"])] = out.get(str(it["verdict"]), 0) + 1
    return out


def match_rate(counts: Mapping[str, int]) -> float | None:
    evaluated = sum(counts.get(v, 0) for v in ("satisfied", *UNSATISFIED))
    return round(counts.get("satisfied", 0) / evaluated, 3) if evaluated else None


async def term_matchings(
    session: AsyncSession, term: Term, run: ScheduleRun | None, scope: Scope, *, rooms: dict[int, Room] | None = None
) -> tuple[TermData, list[dict[str, Any]]]:
    td = await load_term(session, term, run, rooms=rooms)
    items = []
    for mr in td.meetings:
        if not scope.allows(si.instructor_id for si in mr.section.instructors):
            continue
        items.append(match_one(td, mr))
    return td, items


async def run_for(session: AsyncSession, term: Term, run_id: int | None) -> ScheduleRun | None:
    if run_id is None:
        return await published_run(session, term.id)
    run = await session.get(ScheduleRun, run_id)
    if run is None or run.term_id != term.id:
        raise ModerationError(404, f"run {run_id} is not a run of term {term.code}")
    if run.kind != "COURSE":
        raise ModerationError(422, "matchings cover course runs (meeting requests)")
    return run


# ------------------------------------------------------------------------------------------- learning seam


async def learned_priors(
    session: AsyncSession, term_id: int, instructor_id: int | None = None
) -> list[dict[str, Any]] | None:
    """Learned priors of the term's instructors (``learning.priors_for``); ``None`` when the learning lane cannot
    answer (its tables or code are not there): the moderation views never fail because of it."""
    try:
        from app.services import learning
    except ImportError:  # pragma: no cover - the learning lane is part of the tree since 0023
        return None
    fn = getattr(learning, "priors_for", None)
    if fn is None:
        return None
    try:
        async with session.begin_nested():
            return list(await fn(session, term_id, "instructor", str(instructor_id) if instructor_id else None))
    except Exception:  # noqa: BLE001 - a seam to a lane still in progress; logged, the view degrades
        log.warning("learning priors for term %s unavailable", term_id, exc_info=True)
        return None


# ------------------------------------------------------------------------------------------- people (M1)


async def _terms_by_date(session: AsyncSession) -> list[Term]:
    from app.services.learning import term_date

    terms = list((await session.execute(select(Term))).scalars())
    return sorted(terms, key=lambda t: (term_date(t), t.id), reverse=True)


async def _preferences(session: AsyncSession, term_id: int) -> list[ConstraintRow]:
    return list(
        (
            await session.execute(
                select(ConstraintRow).where(
                    ConstraintRow.term_id == term_id,
                    ConstraintRow.enabled.is_(True),
                    ConstraintRow.hardness == "soft",
                    ConstraintRow.source != "BUILTIN",
                )
            )
        ).scalars()
    )


def _rule_targets(c: ConstraintRow, request_ids: set[int], names: set[str]) -> bool:
    params = c.params or {}
    if request_ids & set(_ints(params.get("event_ids"))):
        return True
    ins = params.get("instructor") or params.get("instructors")
    vals = ins if isinstance(ins, list) else [ins] if ins else []
    return any(tr_fold(str(v)) in names for v in vals)


def _streak(verdicts_by_term: list[list[str]]) -> int:
    """Terms in a row (newest first, from the asked term back) with at least one unsatisfied request; a term
    without requests of the person neither counts nor breaks the run (moderation spec "3 of 4 terms" rule)."""
    streak = 0
    for vs in verdicts_by_term:
        if not vs:
            continue
        if any(v in UNSATISFIED for v in vs):
            streak += 1
        else:
            break
    return streak


def streak_badge(streak: int) -> dict[str, str] | None:
    if streak < STREAK_BADGE_FROM:
        return None
    return _t(f"{streak} dönemdir karşılanmadı", f"not satisfied for {streak} terms")


async def _verdicts_per_term(
    session: AsyncSession, terms: list[Term], rooms: dict[int, Room]
) -> dict[int, dict[int, list[str]]]:
    """term id -> instructor id -> verdicts of their requests (published run, else the planner's rooms)."""
    out: dict[int, dict[int, list[str]]] = {}
    for t in terms:
        run = await published_run(session, t.id)
        td = await load_term(session, t, run, rooms=rooms)
        per: dict[int, list[str]] = defaultdict(list)
        for mr in td.meetings:
            v = match_one(td, mr)["verdict"]
            for si in mr.section.instructors:
                per[si.instructor_id].append(v)
        out[t.id] = per
    return out


async def people(session: AsyncSession, term: Term, scope: Scope, q: str | None = None) -> dict[str, Any]:
    rooms = await all_rooms(session)
    run = await published_run(session, term.id)
    td, items = await term_matchings(session, term, run, Scope(True), rooms=rooms)
    terms = await _terms_by_date(session)
    from app.services.learning import term_date

    older = [t for t in terms if t.id != term.id and term_date(t) <= term_date(term)]
    past = await _verdicts_per_term(session, older, rooms)
    prefs = await _preferences(session, term.id)
    priors = await learned_priors(session, term.id)
    priors_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in priors or []:
        subj = p.get("subject") or {}
        if subj.get("type") == "instructor":
            priors_by[str(subj.get("id"))].append(p)
    by_mr = {mr.id: mr for mr in td.meetings}
    person: dict[int, dict[str, Any]] = {}
    for it in items:
        mr = by_mr[it["request_id"]]
        for si in mr.section.instructors:
            row = person.setdefault(
                si.instructor_id,
                {
                    "instructor": si.instructor,
                    "sections": set(),
                    "requests": [],
                    "roles": set(),
                    "units": defaultdict(int),
                    "access": False,
                },
            )
            row["sections"].add(mr.section_id)
            row["requests"].append(it)
            row["roles"].add(si.role)
            if it["faculty"] or it["program"]:
                row["units"][it["faculty"] or it["program"]] += 1
            row["access"] = row["access"] or needs_access(mr)
    needle = tr_fold(q) if q and q.strip() else None
    out: list[dict[str, Any]] = []
    for iid, row in person.items():
        ins: Instructor = row["instructor"]
        if not scope.allows([iid]):
            continue
        codes = {str(r["course_code"] or "") for r in row["requests"]}
        if needle and needle not in tr_fold(ins.full_name) and not any(needle in tr_fold(c) for c in codes):
            continue
        counts = counts_of(row["requests"])
        req_ids = {int(r["request_id"]) for r in row["requests"]}
        names = {tr_fold(ins.full_name), tr_fold(ins.canonical_name)}
        n_prefs = sum(1 for c in prefs if _rule_targets(c, req_ids, names))
        history = [[str(r["verdict"]) for r in row["requests"]]] + [past.get(t.id, {}).get(iid, []) for t in older]
        streak = _streak(history)
        unit = max(row["units"].items(), key=lambda kv: (kv[1], kv[0]))[0] if row["units"] else None
        prios = [r["priority"]["value"] for r in row["requests"]]
        out.append(
            {
                "id": iid,
                "name": ins.full_name,
                "title": ins.title,
                "unit": unit,
                "roles": sorted(row["roles"]),
                "sections": len(row["sections"]),
                "requests": len(row["requests"]),
                "counts": counts,
                "match_rate": match_rate(counts),
                "active_preferences": n_prefs,
                "learned_priors": len(priors_by.get(str(iid), [])) if priors is not None else None,
                "priority_max": max(prios) if prios else 0,
                "accessibility": "yes" if row["access"] else "no",
                "unsatisfied_streak": streak,
                "badge": streak_badge(streak),
                "linked_user": ins.user_id is not None,
            }
        )

    def unmet(r: Mapping[str, Any]) -> int:
        c = r["counts"]
        return int(c["unplaced"]) + int(c["not_as_requested"]) + int(c["partial"])

    out.sort(key=lambda r: (-unmet(r), tr_fold(str(r["name"]))))
    return {
        "term_id": term.id,
        "term_code": term.code,
        "run_id": run.id if run else None,
        "source": "run" if run else "planner",
        "visibility": "all" if scope.all else "own",
        "learning_available": priors is not None,
        "total": len(out),
        "items": out,
    }


# ------------------------------------------------------------------------------------------- history (M1)

#: imported fields a planner edit may change (ImportedSnapshot ``meeting`` / ``section`` values)
_SNAPSHOT_FIELDS = {
    "meeting": (
        "day",
        "days",
        "start_period",
        "end_period",
        "weeks",
        "requested_room_text",
        "requested_room_ids",
        "requested_building",
        "requested_tags",
        "requested_capacity",
        "definitive_room_ids",
        "needs_room",
        "status",
    ),
    "section": ("enrolment", "mode", "label", "class_years"),
}


def _json(v: Any) -> Any:
    from app.services.audit import jsonable

    return jsonable(v)


async def planner_edits(session: AsyncSession, mr: MeetingRequest) -> list[dict[str, Any]]:
    """The planner's edits of a request: the diff against the imported values (``imported_snapshots``) and the
    audit events on the request and its section. TODO(P19-02): when the backend lane records assignment moves
    and locks with the request id, add them here (``audit_events`` of entity ``assignment``)."""
    out: list[dict[str, Any]] = []
    snaps = {
        (s.entity, s.entity_id): s
        for s in (
            await session.execute(
                select(ImportedSnapshot).where(
                    ((ImportedSnapshot.entity == "meeting") & (ImportedSnapshot.entity_id == mr.id))
                    | ((ImportedSnapshot.entity == "section") & (ImportedSnapshot.entity_id == mr.section_id))
                )
            )
        ).scalars()
    }
    for (entity, _eid), snap in sorted(snaps.items()):
        obj: Any = mr if entity == "meeting" else mr.section
        changes = {}
        for k, imported in (snap.values or {}).items():
            if k not in _SNAPSHOT_FIELDS.get(entity, ()):
                continue
            cur = _json(getattr(obj, k, None))
            if cur != imported:
                changes[k] = {"imported": imported, "current": cur}
        if changes:
            out.append({"kind": "snapshot", "entity": entity, "at": snap.created_at.isoformat(), "changes": changes})
    events = list(
        (
            await session.execute(
                select(AuditEvent)
                .where(
                    ((AuditEvent.entity_type == "meeting_request") & (AuditEvent.entity_id == str(mr.id)))
                    | ((AuditEvent.entity_type == "section") & (AuditEvent.entity_id == str(mr.section_id)))
                )
                .order_by(AuditEvent.id)
                .limit(50)
            )
        ).scalars()
    )
    for ev in events:
        out.append(
            {
                "kind": "audit",
                "id": ev.id,
                "action": ev.action,
                "at": ev.ts.isoformat() if ev.ts else None,
                "actor": ev.actor_label,
                "before": ev.before,
                "after": ev.after,
                "reason": ev.reason,
            }
        )
    return out


async def _bookings(
    session: AsyncSession, user_id: int, term_ids: list[int], rooms: Mapping[int, Room]
) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    rows = (
        await session.execute(
            select(Booking)
            .where(Booking.user_id == user_id, Booking.term_id.in_(term_ids))
            .order_by(Booking.date, Booking.start_period, Booking.id)
            .limit(500)
        )
    ).scalars()
    for b in rows:
        out[b.term_id].append(
            {
                "id": b.id,
                "date": b.date.isoformat(),
                "start_period": b.start_period,
                "end_period": b.end_period,
                "time": f"{clock(b.start_period)}–{clock(b.end_period, True)}",
                "room": rooms[b.room_id].display_name if b.room_id in rooms else f"#{b.room_id}",
                "status": b.status,
            }
        )
    return out


async def _resolve_terms(session: AsyncSession, terms: str | None) -> list[Term]:
    ordered = await _terms_by_date(session)
    if not terms or not terms.strip():
        return ordered
    want: list[Term] = []
    for part in [p.strip() for p in terms.split(",") if p.strip()]:
        key = tr_fold(part)
        hit = next((t for t in ordered if str(t.id) == part or tr_fold(t.code) == key), None)
        if hit is None:
            raise ModerationError(404, f"term {part!r} not found")
        if hit not in want:
            want.append(hit)
    return [t for t in ordered if t in want]


async def history(session: AsyncSession, instructor_id: int, scope: Scope, terms: str | None = None) -> dict[str, Any]:
    ins = await session.get(Instructor, instructor_id)
    if ins is None:
        raise ModerationError(404, "instructor not found")
    if not scope.allows([instructor_id]):
        raise ModerationError(403, "you can see only your own requests")
    rooms = await all_rooms(session)
    chosen = await _resolve_terms(session, terms)
    mr_ids = {
        int(i)
        for i in (
            await session.execute(
                select(MeetingRequest.id)
                .join(SectionInstructor, SectionInstructor.section_id == MeetingRequest.section_id)
                .where(SectionInstructor.instructor_id == instructor_id, MeetingRequest.archived.is_(False))
            )
        ).scalars()
    }
    bookings = await _bookings(session, ins.user_id, [t.id for t in chosen], rooms) if ins.user_id else {}
    groups = []
    access = False
    for t in chosen:
        run = await published_run(session, t.id)
        td = await load_term(session, t, run, rooms=rooms, request_ids=mr_ids)
        if not td.meetings and not bookings.get(t.id):
            continue
        items = []
        for mr in td.meetings:
            m = match_one(td, mr)
            access = access or needs_access(mr)
            role = next((si.role for si in mr.section.instructors if si.instructor_id == instructor_id), None)
            notes = mr.notes
            items.append(
                {
                    **m,
                    "role": role,
                    "raw": {
                        "room_text": mr.requested_room_text
                        if not mentions_accessibility(mr.requested_room_text)
                        else None,
                        # Q11: an accessibility wish is shown as yes / no only, never its words
                        "notes": None if mentions_accessibility(notes) else notes,
                        "row": mr.source_row_index,
                        "source_row": _raw_cells(mr.section.source_row),
                    },
                    "parsed": {
                        "day": mr.day,
                        "days": _ints(mr.days),
                        "start_period": mr.start_period,
                        "end_period": mr.end_period,
                        "start_time": mr.start_time.isoformat() if mr.start_time else None,
                        "end_time": mr.end_time.isoformat() if mr.end_time else None,
                        "weeks": _ints(mr.weeks),
                        "rooms": _room_codes(_ints(mr.requested_room_ids), rooms),
                        "building": mr.requested_building,
                        "tags": [str(x) for x in mr.requested_tags or []],
                        "capacity": mr.requested_capacity,
                        "status": mr.status,
                        "warnings": [
                            str(w.get("message") if isinstance(w, dict) else w) for w in mr.parse_warnings or []
                        ],
                    },
                    "planner_edits": await planner_edits(session, mr),
                }
            )
        groups.append(
            {
                "term_id": t.id,
                "term_code": t.code,
                "term_name": t.name,
                "run": (
                    {"id": run.id, "label": run.label, "status": run.status, "published": bool(run.is_active)}
                    if run
                    else None
                ),
                "source": "run" if run else "planner",
                "counts": counts_of(items),
                "match_rate": match_rate(counts_of(items)),
                "items": items,
                "bookings": bookings.get(t.id, []),
                "learned": await learned_priors(session, t.id, instructor_id) if items else [],
            }
        )
    return {
        "instructor": {
            "id": ins.id,
            "name": ins.full_name,
            "title": ins.title,
            "linked_user": ins.user_id is not None,
        },
        "accessibility": "yes" if access else "no",
        "terms": groups,
    }


def _raw_cells(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The planning-list cells of the section row, minus free-text notes that mention accessibility."""
    if not row:
        return None
    return {str(k): (None if isinstance(v, str) and mentions_accessibility(v) else v) for k, v in row.items()}


# ------------------------------------------------------------------------------------------- priorities (M2)


def parse_priority(value: Any) -> int | None:
    """An int within ``run_params.PRIORITY_RANGE`` or a tier name (high / normal / low); ``None`` clears."""
    from app.services.run_params import PRIORITY_RANGE

    if value is None:
        return None
    if isinstance(value, str):
        key = n.fold(value).strip()
        tiers = {**PRIORITY_TIERS, "yuksek": 1, "dusuk": -1}
        if key in tiers:
            return tiers[key]
        raise ModerationError(422, f"priority must be an integer or one of {sorted(PRIORITY_TIERS)}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModerationError(422, "priority must be an integer")
    lo, hi = PRIORITY_RANGE
    if not lo <= value <= hi:
        raise ModerationError(422, f"priority must be within {lo}..{hi}")
    return value


async def set_section_priority(
    session: AsyncSession, section_id: int, value: Any, actor: User, note: str | None = None
) -> dict[str, Any]:
    from app.services.events import publish_event

    sec = await session.get(Section, section_id)
    if sec is None or sec.archived:
        raise ModerationError(404, "section not found")
    new = parse_priority(value) or 0
    before = int(sec.priority or 0)
    if new != before:
        sec.priority = new
        await publish_event(
            session,
            "section.priority",
            "section",
            sec.id,
            before={"priority": before},
            after={"priority": new},
            actor=actor,
            reason=(note or "").strip() or None,
            term_id=sec.term_id,
        )
    await session.commit()
    return {"section_id": sec.id, "priority": new, "previous": before}


async def set_request_priority(
    session: AsyncSession, request_id: int, value: Any, actor: User, note: str | None = None
) -> dict[str, Any]:
    from app.services.events import publish_event

    mr = (
        await session.execute(
            select(MeetingRequest).where(MeetingRequest.id == request_id).options(selectinload(MeetingRequest.section))
        )
    ).scalar_one_or_none()
    if mr is None or mr.archived:
        raise ModerationError(404, "meeting request not found")
    new = parse_priority(value)
    before = mr.priority
    if new != before:
        mr.priority = new
        await publish_event(
            session,
            "meeting_request.priority",
            "meeting_request",
            mr.id,
            before={"priority": before},
            after={"priority": new},
            actor=actor,
            reason=(note or "").strip() or None,
            term_id=mr.section.term_id,
        )
    await session.commit()
    return {"request_id": mr.id, "priority": new, "previous": before, "effective": effective_priority(mr)}


SUBJECTS = {"person": ("instructor", "person.priority"), "program": ("program", "program.priority")}


def _override_out(o: Any) -> dict[str, Any]:
    return {
        "subject_type": o.subject_type,
        "subject_id": o.subject_id,
        "term_id": o.term_id,
        "priority": int(o.priority),
        "note": o.note,
        "updated_by": o.updated_by,
        "updated_at": o.updated_at.isoformat() if o.updated_at else None,
    }


async def set_subject_priority(
    session: AsyncSession,
    subject_type: str,
    subject_id: int,
    term_id: int,
    value: Any,
    actor: User,
    note: str | None = None,
) -> dict[str, Any]:
    """P19-P-04: a person's (instructor) or a programme's default priority for one term; ``null`` / normal clears
    it. Every request of the subject without a more specific value inherits it (request > section > person >
    programme). Audited as ``person.priority`` / ``program.priority`` with the term, so it shows in
    ``changes-since-publish``."""
    from app.models import PriorityOverride
    from app.services.events import publish_event

    if subject_type not in SUBJECTS:
        raise ModerationError(422, f"subject must be one of {sorted(SUBJECTS)}")
    term = await session.get(Term, term_id)
    if term is None:
        raise ModerationError(404, "term not found")
    model = Instructor if subject_type == "person" else Program
    subject = await session.get(model, subject_id)
    if subject is None:
        raise ModerationError(404, f"{SUBJECTS[subject_type][0]} not found")
    new = parse_priority(value)
    if new == 0:
        new = None  # Normal at person / programme level is "nothing set"
    row = (
        await session.execute(
            select(PriorityOverride).where(
                PriorityOverride.term_id == term_id,
                PriorityOverride.subject_type == subject_type,
                PriorityOverride.subject_id == subject_id,
            )
        )
    ).scalar_one_or_none()
    before = int(row.priority) if row is not None else None
    text = (note or "").strip() or None
    if new is None and row is not None:
        await session.delete(row)
    elif new is not None:
        if row is None:
            row = PriorityOverride(term_id=term_id, subject_type=subject_type, subject_id=subject_id, priority=new)
            session.add(row)
        row.priority, row.note, row.updated_by = new, text, actor.id
    if new != before:
        await publish_event(
            session,
            SUBJECTS[subject_type][1],
            SUBJECTS[subject_type][0],
            subject_id,
            before={"priority": before, "term_id": term_id},
            after={"priority": new, "term_id": term_id},
            actor=actor,
            reason=text,
            term_id=term_id,
        )
    await session.commit()
    affected = await subject_request_ids(session, subject_type, subject_id, term_id)
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "term_id": term_id,
        "priority": new,
        "previous": before,
        "source": subject_type if new is not None else None,
        "request_ids": affected,
    }


async def subject_request_ids(session: AsyncSession, subject_type: str, subject_id: int, term_id: int) -> list[int]:
    """The term's live meeting requests of a person (their sections) or a programme."""
    q = (
        select(MeetingRequest.id)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(Section.term_id == term_id, MeetingRequest.archived.is_(False), Section.archived.is_(False))
    )
    if subject_type == "person":
        q = q.join(SectionInstructor, SectionInstructor.section_id == Section.id).where(
            SectionInstructor.instructor_id == subject_id
        )
    else:
        q = q.where(Section.program_id == subject_id)
    return sorted({int(i) for i in (await session.execute(q)).scalars()})


async def list_overrides(session: AsyncSession, term_id: int, subject_type: str | None = None) -> list[dict[str, Any]]:
    from app.models import PriorityOverride

    q = select(PriorityOverride).where(PriorityOverride.term_id == term_id)
    if subject_type:
        q = q.where(PriorityOverride.subject_type == subject_type)
    rows = list(
        (await session.execute(q.order_by(PriorityOverride.subject_type, PriorityOverride.subject_id))).scalars()
    )
    names: dict[tuple[str, int], str] = {}
    people = [r.subject_id for r in rows if r.subject_type == "person"]
    progs = [r.subject_id for r in rows if r.subject_type == "program"]
    if people:
        for i in (await session.execute(select(Instructor).where(Instructor.id.in_(people)))).scalars():
            names[("person", i.id)] = i.full_name
    if progs:
        for p in (await session.execute(select(Program).where(Program.id.in_(progs)))).scalars():
            names[("program", p.id)] = p.name
    return [{**_override_out(r), "name": names.get((r.subject_type, r.subject_id))} for r in rows]


# ------------------------------------------------------------------------------------------- staged changes (P19-M-07)

#: audit actions that change what the next solve sees, by kind (moderation spec §5.1 "N değişiklik yayında değil")
SOLVING_ACTIONS: dict[str, str] = {
    "meeting_request.priority": "priority",
    "section.priority": "priority",
    "person.priority": "priority",
    "program.priority": "priority",
    "moderation.pin": "pin",
    "moderation.prefer": "prefer",
    "moderation.unlock": "unlock",
    "meeting_request.update": "request",
    "meeting.create": "request",
    "meeting.archive": "request",
    "meeting.delete": "request",
    "section.create": "request",
    "section.update": "request",
    "section.archive": "request",
    "section.delete": "request",
    "section.pattern": "request",
    "constraint.create": "preference",
    "constraint.update": "preference",
    "constraint.delete": "preference",
    "constraint.waive": "preference",
    # P19-T2: an academician's wish acts once a coordinator accepts it
    "preference.accept": "preference",
}
CHANGE_KINDS = ("priority", "pin", "prefer", "unlock", "request", "preference")


async def published_since(session: AsyncSession, run: ScheduleRun | None) -> datetime | None:
    """When ``run`` became the published timetable: its latest ``run.activate`` audit event, else its finish."""
    if run is None:
        return None
    ts = (
        await session.execute(
            select(AuditEvent.ts)
            .where(AuditEvent.action == "run.activate", AuditEvent.entity_id == str(run.id))
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return ts or run.finished_at or run.created_at


def _int_or_none(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


async def changes_since_publish(
    session: AsyncSession, term: Term, *, kinds: Iterable[str] | None = None, limit: int = 500
) -> dict[str, Any]:
    """Draft edits not yet in the published plan (P19-M-07), from the audit log: priority changes (request,
    section, person, programme), pins / prefers / unlocks on draft child runs, request edits (meetings, sections,
    patterns) and rule changes of the term, recorded after the published run was activated. Every item names
    the requests it touches, and ``changed_request_ids`` seeds the next re-solve, so the staged-changes popover
    and the recreate sheet no longer keep them per browser. Without a published run everything since the term's
    first edit is listed (``since`` null)."""
    run = await published_run(session, term.id)
    since = await published_since(session, run)
    wanted = {k for k in (kinds or CHANGE_KINDS) if k in CHANGE_KINDS}
    actions = [a for a, k in SOLVING_ACTIONS.items() if k in wanted]
    q = select(AuditEvent).where(
        AuditEvent.term_id == term.id, AuditEvent.action.in_(actions), AuditEvent.parent_id.is_(None)
    )
    if since is not None:
        q = q.where(AuditEvent.ts >= since)
    if run is not None:  # the activation itself is the cut: anything audited before its row is published
        act_id = (
            await session.execute(
                select(AuditEvent.id)
                .where(AuditEvent.action == "run.activate", AuditEvent.entity_id == str(run.id))
                .order_by(AuditEvent.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if act_id is not None:
            q = q.where(AuditEvent.id > act_id)
    rows = list((await session.execute(q.order_by(AuditEvent.id))).scalars())
    pattern_ids = [r.id for r in rows if r.action == "section.pattern"]
    children: dict[int, list[int]] = defaultdict(list)
    if pattern_ids:
        for pid, child_eid in (
            await session.execute(
                select(AuditEvent.parent_id, AuditEvent.entity_id).where(AuditEvent.parent_id.in_(pattern_ids))
            )
        ).all():
            if pid is not None and (v := _int_or_none(child_eid)) is not None:
                children[int(pid)].append(v)
    section_ids = {v for r in rows if r.entity_type == "section" and (v := _int_or_none(r.entity_id)) is not None}
    by_section: dict[int, list[int]] = defaultdict(list)
    if section_ids:
        for mid, sid in (
            await session.execute(
                select(MeetingRequest.id, MeetingRequest.section_id).where(
                    MeetingRequest.section_id.in_(sorted(section_ids))
                )
            )
        ).all():
            by_section[int(sid)].append(int(mid))
    subject_cache: dict[tuple[str, int], list[int]] = {}
    items: list[dict[str, Any]] = []
    for r in rows:
        kind = SOLVING_ACTIONS[r.action]
        eid = _int_or_none(r.entity_id)
        after = r.after if isinstance(r.after, dict) else {}
        before = r.before if isinstance(r.before, dict) else {}
        rids: list[int] = []
        if r.entity_type in ("meeting_request", "meeting") and eid is not None:
            rids = [eid]
        elif r.entity_type == "section" and eid is not None:
            rids = sorted(
                {*by_section.get(eid, []), *children.get(r.id, []), *_ints(after.get("archived_meeting_ids"))}
            )
        elif r.action in ("person.priority", "program.priority") and eid is not None:
            key = ("person" if r.action == "person.priority" else "program", eid)
            if key not in subject_cache:
                subject_cache[key] = await subject_request_ids(session, key[0], eid, term.id)
            rids = subject_cache[key]
        elif r.entity_type == "constraint":
            params = (after.get("params") or before.get("params") or {}) if isinstance(after, dict) else {}
            rids = _ints(params.get("event_ids")) if isinstance(params, dict) else []
        items.append(
            {
                "audit_id": r.id,
                "ts": r.ts.isoformat() if r.ts else None,
                "action": r.action,
                "kind": kind,
                "entity_type": r.entity_type,
                "entity_id": eid if eid is not None else r.entity_id,
                "run_id": _int_or_none(after.get("run_id")),
                "request_ids": rids,
                "actor_id": r.actor_id,
                "actor": r.actor_label,
                "reason": r.reason,
                "before": before or None,
                "after": after or None,
            }
        )
    every = sorted({i for it in items for i in it["request_ids"]})
    labels: dict[int, str] = {}
    if every:
        for mr in (await session.execute(_meeting_query().where(MeetingRequest.id.in_(every[:5000])))).scalars():
            labels[mr.id] = label_of(mr)
    for it in items:
        it["labels"] = [labels[i] for i in it["request_ids"][:20] if i in labels]
    counts = {k: sum(1 for it in items if it["kind"] == k) for k in CHANGE_KINDS}
    total = len(items)
    return {
        "term_id": term.id,
        "published_run_id": run.id if run else None,
        "since": since.isoformat() if since else None,
        "total": total,
        "counts": counts,
        "changed_request_ids": [i for i in every if i in labels],
        "items": items[-limit:][::-1],  # newest first
    }


# ------------------------------------------------------------------------------------------- publish digest (P19-M-09)

_DAY_TR = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
_DAY_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _cell_text(place: Place | None, rooms: Mapping[int, Room], lang: str) -> str:
    if place is None:
        return "yerleşmedi" if lang == "tr" else "not placed"
    days = _DAY_TR if lang == "tr" else _DAY_EN
    start = n.PERIODS[place.start - 1].start if 1 <= place.start <= len(n.PERIODS) else None
    end = n.PERIODS[place.end - 1].end if 1 <= place.end <= len(n.PERIODS) else None
    clock_ = f"{start:%H:%M}-{end:%H:%M}" if start and end else f"P{place.start}-P{place.end}"
    day = days[place.day - 1] if 1 <= place.day <= 7 else str(place.day)
    return f"{day} {clock_} {' + '.join(_room_codes(place.room_ids, rooms))}".strip()


async def publish_changes(
    session: AsyncSession, run: ScheduleRun, previous: ScheduleRun | None
) -> dict[int, list[dict[str, Any]]]:
    """Per instructor: the classes whose cell differs between the previously published run and ``run`` (moved,
    newly placed, no longer placed). Without a previous run every placed class is new."""
    term = await session.get(Term, run.term_id)
    assert term is not None
    rooms = await all_rooms(session)
    after = await load_term(session, term, run, rooms=rooms)
    before = await load_term(session, term, previous, rooms=rooms) if previous is not None else None
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for mr in after.meetings:
        new_rows = after.rows_by_mr.get(mr.id, [])
        old_rows = before.rows_by_mr.get(mr.id, []) if before is not None else []
        if before is not None and _cell_set(new_rows) == _cell_set(old_rows):
            continue
        np_, op = place_of(new_rows), place_of(old_rows)
        if np_ is None and op is None:
            continue
        change = "moved" if np_ is not None and op is not None else "new" if np_ is not None else "unplaced"
        item = {"request_id": mr.id, "label": label_of(mr), "change": change, "from": op, "to": np_}
        for si in mr.section.instructors:
            out[si.instructor_id].append(item)
    return out


async def publish_digest(session: AsyncSession, run: ScheduleRun, previous_id: int | None) -> dict[str, Any]:
    """``POST /runs/{id}/activate {"notify_people": true}``: one ``timetable.published`` notice per affected
    academician (``Instructor.user_id``), listing only their changed classes, through ``notify_dispatch`` (the
    user's channel switches; in-app + e-mail by default, e-mail opt-out per user). Idempotent per run and person
    (``timetable:<run>:published``): publishing the same run again sends nothing twice. Unlinked instructors are
    counted, never contacted."""
    from app.services import notify_dispatch as nd
    from app.services.bookings_notify import _language

    previous = await session.get(ScheduleRun, previous_id) if previous_id else None
    changes = await publish_changes(session, run, previous)
    term = await session.get(Term, run.term_id)
    rooms = await all_rooms(session)
    linked = {
        i.id: i
        for i in (
            await session.execute(
                select(Instructor).where(Instructor.id.in_(list(changes)), Instructor.user_id.is_not(None))
            )
        ).scalars()
    }
    per_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for iid, items in changes.items():
        ins = linked.get(iid)
        if ins is not None and ins.user_id is not None:
            per_user[int(ins.user_id)].extend(items)
    notified, deliveries = 0, 0
    for uid, items in sorted(per_user.items()):
        user = await session.get(User, uid)
        if user is None or not user.is_active:
            continue
        uniq = list({it["request_id"]: it for it in items}.values())
        lang = "tr" if (await _language(session, user)) == "tr" else "en"
        code = term.code if term else str(run.term_id)
        if lang == "tr":
            title = f"{code} planı yayınlandı: {len(uniq)} dersinizde değişiklik"
        else:
            title = f"{code} timetable published: {len(uniq)} of your classes changed"
        lines = []
        for it in sorted(uniq, key=lambda x: x["label"]):
            lines.append(f"{it['label']}: {_cell_text(it['from'], rooms, lang)} → {_cell_text(it['to'], rooms, lang)}")
        notice = nd.Notice(
            event="timetable.published",
            key=f"timetable:{run.id}:published",
            title=title,
            body="\n".join(lines),
            link="/moderation",
            data={
                "run_id": run.id,
                "term_id": run.term_id,
                "previous_run_id": previous_id,
                "classes": [
                    {
                        "request_id": it["request_id"],
                        "label": it["label"],
                        "change": it["change"],
                        "from": _place_out(it["from"], rooms),
                        "to": _place_out(it["to"], rooms),
                    }
                    for it in uniq
                ],
            },
        )
        res = await nd.dispatch(session, user, notice)
        sent = [d for d in res if d.status in ("sent", "skipped")]
        if sent:
            notified += 1
            deliveries += len(sent)
    return {
        "notified": notified,
        "deliveries": deliveries,
        "affected_people": len(changes),
        "unlinked_people": len([i for i in changes if i not in linked]),
        "changed_classes": len({it["request_id"] for items in changes.values() for it in items}),
    }


# ------------------------------------------------------------------------------------------- re-solve (M3)


def _members_of(run: ScheduleRun) -> dict[int, list[int]]:
    return {int(k): _ints(v) for k, v in ((run.stats or {}).get("event_members") or {}).items()}


async def create_resolve(
    session: AsyncSession,
    term: Term,
    base: ScheduleRun,
    changed_request_ids: list[int],
    mode: str,
    actor: User,
    *,
    radius: int = DEFAULT_RADIUS,
    time_limit_s: float | None = None,
    compare_to: int | None = None,
) -> ScheduleRun:
    """A QUEUED child run of ``base`` for a moderation re-solve (the caller enqueues :func:`run_resolve`).

    The preview's baseline is fixed here (``params.moderation.compare_to_run_id``): ``compare_to`` when given,
    else the published run that started the chain (:func:`chain_baseline`), so a re-solve of a draft child
    still shows every change against what is published, not only the last step."""
    from app.services import run_params as rp
    from app.services.events import publish_event

    if base.term_id != term.id:
        raise ModerationError(422, f"run {base.id} is not a run of term {term.code}")
    if base.status not in BASE_STATUSES:
        raise ModerationError(
            409,
            f"run {base.id} is {base.status}; a re-solve starts from a finished run "
            f"({', '.join(sorted(BASE_STATUSES))})",
        )
    if mode not in ("repair", "full"):
        raise ModerationError(422, "mode must be repair or full")
    ids = sorted({int(i) for i in changed_request_ids})
    if len(ids) > MAX_CHANGED:
        raise ModerationError(422, f"at most {MAX_CHANGED} changed requests per re-solve")
    if mode == "repair" and not ids:
        raise ModerationError(422, "a repair names the changed requests (changed_request_ids); use mode full otherwise")
    if ids:
        if base.kind == "EXAM":
            from app.models import ExamRequest

            found = set(
                (
                    await session.execute(
                        select(ExamRequest.id).where(ExamRequest.id.in_(ids), ExamRequest.term_id == term.id)
                    )
                ).scalars()
            )
        else:
            found = set(
                (
                    await session.execute(
                        select(MeetingRequest.id)
                        .join(Section, Section.id == MeetingRequest.section_id)
                        .where(MeetingRequest.id.in_(ids), Section.term_id == term.id)
                    )
                ).scalars()
            )
        missing = sorted(set(ids) - found)
        if missing:
            raise ModerationError(422, f"requests not in term {term.code}: {missing[:20]}")
    if compare_to is not None:
        baseline = await comparable_run(session, term, base, compare_to)
        basis = "explicit"
    else:
        baseline, basis = await chain_baseline(session, base, include_self=True)
    params = {k: v for k, v in dict(base.params or {}).items() if k not in ("moderation",)}
    weights = dict(params.get("weights") or {})
    weights["stability"] = max(int(weights.get("stability", 1) or 1), RESOLVE_STABILITY_WEIGHT)
    lo, hi = rp.bounds()["time_limit_s"]
    limit = float(time_limit_s) if time_limit_s is not None else float(params.get("time_limit_s", 60.0))
    params.update(
        {
            "stability": True,
            rp.PUBLISH_CANDIDATE: True,
            "workers": 1,
            "weights": weights,
            "time_limit_s": min(max(limit, lo), hi),
            "moderation": {
                "base_run_id": base.id,
                "changed_request_ids": ids,
                "mode": mode,
                "radius": max(0, min(int(radius), 3)),
                "compare_to_run_id": baseline.id,
                "compare_basis": basis,
            },
        }
    )
    child = ScheduleRun(
        term_id=term.id,
        kind=base.kind,
        horizon=base.horizon,
        horizon_params=dict(base.horizon_params or {}),
        params=params,
        status="QUEUED",
        parent_run_id=base.id,
        label=f"Moderasyon yeniden çözüm #{base.id} ({'en az değişiklik' if mode == 'repair' else 'baştan'})"[:255],
        stats={"progress": 0, "phase": "queued", "moderation": {"base_run_id": base.id, "mode": mode}},
        created_by=actor.id,
    )
    session.add(child)
    await session.flush()
    await publish_event(
        session,
        "moderation.resolve",
        "run",
        child.id,
        after={
            "base_run_id": base.id,
            "mode": mode,
            "changed_request_ids": ids,
            "radius": params["moderation"]["radius"],
            "compare_to_run_id": baseline.id,
        },
        actor=actor,
        term_id=term.id,
    )
    await session.commit()
    await session.refresh(child)
    return child


#: how far :func:`run_chain` walks up ``parent_run_id`` (cycle-safe; a moderation chain is a few steps)
MAX_CHAIN = 64


async def run_chain(session: AsyncSession, run: ScheduleRun) -> list[ScheduleRun]:
    """``run`` and its ancestors, nearest first (``parent_run_id``; stops at a cycle or :data:`MAX_CHAIN`)."""
    out = [run]
    seen = {run.id}
    cur = run
    while cur.parent_run_id is not None and len(out) < MAX_CHAIN:
        nxt = await session.get(ScheduleRun, int(cur.parent_run_id))
        if nxt is None or nxt.id in seen:
            break
        out.append(nxt)
        seen.add(nxt.id)
        cur = nxt
    return out


async def _ever_published(session: AsyncSession, run_ids: Iterable[int]) -> set[int]:
    """Runs that were published at some point (``run.activate`` audit events), active now or not."""
    ids = [str(i) for i in run_ids]
    if not ids:
        return set()
    rows = await session.execute(
        select(AuditEvent.entity_id).where(AuditEvent.action == "run.activate", AuditEvent.entity_id.in_(ids))
    )
    return {int(e) for e in rows.scalars() if e and str(e).isdigit()}


async def chain_baseline(
    session: AsyncSession, run: ScheduleRun, *, include_self: bool = False
) -> tuple[ScheduleRun, str]:
    """The published run that started ``run``'s chain of re-solves, and why it was chosen:

    * ``published``: the nearest ancestor that is the term's published run now (``is_active``);
    * ``was_published``: else the nearest ancestor that was published once (``run.activate`` in the audit);
    * ``root``: else the run the chain started from (a chain that never had a published run).

    ``include_self`` counts ``run`` itself (the base of a new re-solve); the diff of a stored child starts at its
    parent."""
    chain = await run_chain(session, run)
    cands = chain if include_self else chain[1:]
    if not cands:
        return run, "base"
    for r in cands:
        if r.is_active:
            return r, "published"
    once = await _ever_published(session, (r.id for r in cands))
    for r in cands:
        if r.id in once:
            return r, "was_published"
    return cands[-1], "root"


async def comparable_run(session: AsyncSession, term: Term, run: ScheduleRun, other_id: int) -> ScheduleRun:
    """``compare_to``: a finished run of the same term and kind (404 / 422 / 409 otherwise)."""
    other = await session.get(ScheduleRun, int(other_id))
    if other is None:
        raise ModerationError(404, f"run {other_id} (compare_to) not found")
    if other.term_id != term.id or other.kind != run.kind:
        raise ModerationError(422, f"run {other.id} is not a {run.kind} run of term {term.code}")
    if other.status not in BASE_STATUSES:
        raise ModerationError(409, f"run {other.id} is {other.status}; compare against a finished run")
    return other


async def chain_edits(session: AsyncSession, chain: list[ScheduleRun]) -> set[int]:
    """The requests edited along a chain of draft runs: each step's ``changed_request_ids``, its unlocks and the
    targets of its pin / prefer rules (:func:`matching_action`)."""
    from app.services.solver_bridge import UNLOCK_PARAM

    out: set[int] = set()
    ids = [r.id for r in chain]
    for r in chain:
        p = r.params or {}
        out |= set(_ints((p.get("moderation") or {}).get("changed_request_ids")))
        out |= set(_ints(p.get(UNLOCK_PARAM)))
    if ids:
        for c in (await session.execute(select(ConstraintRow).where(ConstraintRow.run_id.in_(ids)))).scalars():
            rid = _moderation_ref(c).get("request_id")
            if isinstance(rid, int):
                out.add(rid)
    return out


async def _input_for(session: AsyncSession, run: ScheduleRun) -> tuple[sm.SolverInput, dict[int, list[int]]]:
    """The bridge input, keeping a studio draft's snapshot when the run descends from one (B3 seal)."""
    from app.services import solver_bridge

    if solver_bridge._studio_run(run):  # noqa: SLF001 - the bridge's own predicate, one definition
        from app.services.studio import build_solver_input_for_run

        return await build_solver_input_for_run(session, run)
    return await solver_bridge.build_solver_input(session, run)


def _overlaps(a: sm.Assignment, b: sm.Assignment) -> bool:
    if a.day != b.day or a.start > b.end or b.start > a.end:
        return False
    return not a.weeks or not b.weeks or bool(a.weeks & b.weeks)


def _slot_of(e: sm.Event) -> sm.Assignment | None:
    """The cell an event asks for (its lock, else its fixed day + start), for finding who blocks it."""
    if e.locked is not None:
        return e.locked
    if e.fixed_day is None or e.fixed_start is None:
        return None
    return sm.Assignment(e.id, e.fixed_day, e.fixed_start, e.fixed_start + e.duration - 1, (), e.weeks)


def _fits(e: sm.Event, r: sm.Room) -> bool:
    cap = r.exam_capacity if e.kind == "exam" else r.capacity
    return cap >= e.size and e.required_tags <= r.tags and not (e.forbidden_tags & r.tags)


def slot_blockers(inp: sm.SolverInput, current: Iterable[sm.Assignment], seeds: Iterable[int]) -> set[int]:
    """Events placed in the requested cell of a changed event (a shared room it could use, its cohort or its
    instructor at that time): the repair frees them too, so an edited or re-prioritised request that is not placed
    (or asks for a new cell) gets its chance (``repair.neighbours`` only looks at current placements)."""
    events = {e.id: e for e in inp.events}
    cur = list(current)
    out: set[int] = set()
    for sid in seeds:
        e = events.get(sid)
        if e is None:
            continue
        slot = _slot_of(e)
        if slot is None:
            continue
        slot = replace(slot, weeks=e.weeks)
        cand = set(slot.room_ids) or set(e.required_room_ids) or set(e.preferred_room_ids)
        if not cand:
            cand = {r.id for r in inp.rooms if _fits(e, r)}
        for a in cur:
            other = events.get(a.event_id)
            if other is None or a.event_id == sid or not _overlaps(slot, a):
                continue
            if set(a.room_ids) & cand or e.cohort_keys & other.cohort_keys or e.instructor_keys & other.instructor_keys:
                out.add(a.event_id)
    return out


def base_assignments(inp: sm.SolverInput, base: ScheduleRun | None) -> list[sm.Assignment]:
    """The base run's placements per solver event: the solver's own (``stats.solver_assignments``), else the
    bridge's ``previous`` (rebuilt from the stored rows) cleaned of rooms outside the pool."""
    from app.services.solver_bridge import solver_assignments_of

    events = {e.id: e for e in inp.events}
    stored = solver_assignments_of(base) if base is not None else None
    if stored is not None:
        seen: set[int] = set()
        out = []
        for a in stored:
            if a.event_id in events and a.event_id not in seen:
                seen.add(a.event_id)
                out.append(a)
        return out
    pool = {r.id for r in inp.rooms}
    out = []
    for a in inp.previous:
        e = events.get(a.event_id)
        if e is None:
            continue
        rooms = tuple(r for r in a.room_ids if r in pool) if e.needs_room else ()
        out.append(replace(a, room_ids=rooms, weeks=a.weeks or e.weeks))
    return out


def violating(inp: sm.SolverInput, assignments: list[sm.Assignment]) -> set[int]:
    """Events of ``assignments`` in a hard violation of ``inp`` (the base placements against the child's rules:
    a pin written on the draft, a request edited since). The repair frees them instead of locking them there."""
    from app.solver.repair import validate

    placed = {a.event_id for a in assignments}
    sub = replace(inp, events=tuple(e for e in inp.events if e.id in placed), best_effort=False)
    return {int(i) for v in validate(sub, assignments) if v.hard for i in v.event_ids}


def _rescore(inp: sm.SolverInput, assignments: list[sm.Assignment]) -> tuple[int, int, dict[str, int], int]:
    """(hard, soft, breakdown, hard violations) of the placed events (a partial result's unplaced events are
    reported apart, as in ``repair``)."""
    from app.solver.repair import score, validate

    placed = {a.event_id for a in assignments}
    sub = replace(inp, events=tuple(e for e in inp.events if e.id in placed), best_effort=False)
    hard, soft, breakdown = score(sub, assignments)
    return hard, soft, breakdown, sum(1 for v in validate(sub, assignments) if v.hard)


def _minimal_change(
    inp: sm.SolverInput, current: list[sm.Assignment], result: sm.SolverResult, scope: set[int]
) -> list[int]:
    """Academician needs Q9: a published class outside the changed requests keeps its cell unless moving it was
    needed. Every moved or dropped event outside ``scope`` whose old cell is still free (reverting it keeps every
    hard rule) is put back; deterministic (sorted order, repeated until nothing changes). Returns the reverted event
    ids and rewrites ``result`` in place (assignments, scores, ``stats.repair.moved``)."""
    from app.solver.repair import moved_diff

    before = {a.event_id: a for a in current}
    after = {a.event_id: a for a in result.assignments}
    _hard0, _s0, _b0, viol0 = _rescore(inp, list(after.values()))
    reverted: list[int] = []
    changed = True
    while changed:
        changed = False
        for m in moved_diff(list(before.values()), list(after.values())):
            eid = int(m["event_id"])
            # a class the repair dropped (``to`` None) is put back too when its old cell still keeps every hard rule:
            # a minimal re-solve never unplaces a placed class for a soft wish (round-1 R1-S-04)
            if eid in scope or m["from"] is None or eid in reverted or eid not in before:
                continue
            trial = dict(after)
            trial[eid] = before[eid]
            if _rescore(inp, list(trial.values()))[3] <= viol0:
                after = trial
                reverted.append(eid)
                changed = True
    if reverted:
        final = [after[k] for k in sorted(after)]
        hard, soft, breakdown, _v = _rescore(inp, final)
        restored = {eid for eid in reverted if eid not in {a.event_id for a in result.assignments}}
        if restored:
            # classes put back in their published cell are placed again: their "cannot be placed" lines go
            result.diagnoses = [
                d
                for d in result.diagnoses
                if not (len(d.event_ids) == 1 and d.event_ids[0] in restored and d.severity == "error")
            ]
            for d in result.diagnoses:
                if d.code == "unplaced_summary":
                    d.event_ids = [i for i in d.event_ids if i not in restored]
            total = int(result.stats.get("events_total") or len(inp.events))
            result.stats["placed"] = len(final)
            result.stats["unplaced"] = max(0, total - len(final))
            result.stats["restored_to_published"] = sorted(restored)
        result.assignments = final
        result.hard_score, result.soft_score = hard, soft
        result.objective_breakdown = breakdown
        rep = dict(result.stats.get("repair") or {})
        moved = moved_diff(current, final)
        rep.update(
            {
                "moved": moved,
                "moved_count": sum(1 for x in moved if x["to"] is not None and x["from"] is not None),
                "reverted": sorted(reverted),
            }
        )
        result.stats["repair"] = rep
    return sorted(reverted)


async def run_resolve(session_factory: Any, run_id: int, progress: Any = None) -> dict[str, Any]:
    """Queue job of a moderation re-solve: the bridge input of the child (previous = the base run's placements,
    the base's locks carried, stability on, one worker), then ``repair`` on the neighbourhood of the changed
    requests or a full solve. Infeasible stays INFEASIBLE with its diagnosis (nothing is relaxed silently)."""
    from app.services import solver_bridge
    from app.solver.repair import repair
    from app.workers import run_jobs

    def report(phase: str, pct: int) -> None:
        if progress:
            progress(phase, pct)

    async with session_factory() as session:
        run = await session.get(ScheduleRun, run_id)
        if run is None:
            raise ValueError(f"run {run_id} not found")
        if not await run_jobs.start_run(session, run):
            return await run_jobs.finish_cancelled(session_factory, run_id)
        run.stats = {**(run.stats or {}), "progress": 5, "phase": "loading"}
        await session.commit()
        report("loading", 5)
        inp, members = await _input_for(session, run)
        mod = dict((run.params or {}).get("moderation") or {})
        base = await session.get(ScheduleRun, int(mod.get("base_run_id") or run.parent_run_id or 0))
        if not inp.events:
            await solver_bridge._finish_empty_scope(session, run)  # noqa: SLF001
            return {"status": "FAILED", "assignments": 0}
        await session.commit()
    head_of = {m: h for h, ms in members.items() for m in ms}
    ids = {e.id for e in inp.events}
    changed = {head_of.get(int(r), int(r)) for r in mod.get("changed_request_ids") or []} & ids
    current = base_assignments(inp, base)
    mode = str(mod.get("mode") or "repair")
    limit = float(inp.time_limit_s)
    report("solving", 20)
    seeds: set[int] = set()
    broken: set[int] = set()
    reverted: list[int] = []
    try:
        if mode == "repair":
            broken = violating(inp, current) - changed
            seeds = changed | broken | slot_blockers(inp, current, changed)
            result = await run_jobs.solve_off_loop(
                run_id,
                limit,
                repair,
                inp,
                current,
                sorted(seeds),
                limit,
                keep_changed=False,
                radius=int(mod.get("radius", DEFAULT_RADIUS)),
            )
            if result.assignments and current and result.status != "ERROR":  # best effort: INFEASIBLE + placements
                reverted = _minimal_change(inp, current, result, changed)
        else:
            result = await run_jobs.solve_off_loop(
                run_id,
                limit,
                solver_bridge._call_solver,  # noqa: SLF001 - the bridge's solve entry (week splitting included)
                inp,
                None,
                str((run.params or {}).get("solver", "auto")),
                split_weeks=solver_bridge.run_mode(dict(run.params or {}), "split_blocked_weeks"),
            )
    except run_jobs.RunCancelled:
        return await run_jobs.finish_cancelled(session_factory, run_id)
    report("persisting", 90)
    result.stats = {
        **result.stats,
        "solver": "app.solver.repair" if mode == "repair" else solver_bridge.CPSAT_MODULE,
        "mode": mode,
        "moderation": {
            **mod,
            "changed_events": sorted(changed),
            "seeds": sorted(seeds),
            "base_violations": sorted(broken),
            "reverted": reverted,
            "workers": inp.workers,
        },
    }
    async with session_factory() as session:
        run = await session.get(ScheduleRun, run_id)
        if run is None:
            raise ValueError(f"run {run_id} was deleted while solving")
        if run.status == "CANCELLED":
            return {"status": "CANCELLED"}
        count = await solver_bridge.persist_result(session, run, result, members)
        if count < 0:
            return {"status": "CANCELLED"}
    report("done", 100)
    return {"status": solver_bridge.run_status(result), "assignments": count}


def enqueue_resolve(run_id: int) -> None:
    from app.core.db import get_session_factory
    from app.workers.queue import JobState, get_queue

    factory = get_session_factory()

    async def body(progress: Any) -> dict[str, Any]:
        return await run_resolve(factory, run_id, progress)

    async def on_status(st: JobState) -> None:
        async with factory() as s:
            row = await s.get(ScheduleRun, run_id)
            if row is None:
                return
            if st.status == "FAILED":
                row.status = "FAILED"
                row.error = (st.error or "")[:4000]
                row.finished_at = datetime.now(UTC).replace(tzinfo=None)
            row.stats = {**(row.stats or {}), "progress": st.progress, "phase": st.phase}
            await s.commit()

    get_queue().enqueue(f"run:{run_id}", body, on_status=on_status)


# ------------------------------------------------------------------------------------------- diff (M3)


def _cell_set(rows: list[Assignment]) -> frozenset[tuple[int, int, int, tuple[int, ...], tuple[int, ...]]]:
    return frozenset(
        (a.day, a.start_period, a.end_period, tuple(sorted(_ints(a.room_ids))), tuple(sorted(_ints(a.weeks))))
        for a in rows
    )


def _touch(a: Place, b: Place, ma: MeetingRequest, mb: MeetingRequest) -> str | None:
    """Why ``b``'s new cell displaces ``a``'s old one: a shared room, the same cohort or the same instructor."""
    if a.day != b.day or a.start > b.end or b.start > a.end:
        return None
    if a.weeks and b.weeks and not set(a.weeks) & set(b.weeks):
        return None
    if set(a.room_ids) & set(b.room_ids):
        return "room"
    sa, sb = ma.section, mb.section
    if sa.program_id and sa.program_id == sb.program_id:
        ya = set(_ints(sa.class_years) or ([sa.class_year] if sa.class_year else []))
        yb = set(_ints(sb.class_years) or ([sb.class_year] if sb.class_year else []))
        if ya & yb:
            return "cohort"
    if {si.instructor_id for si in sa.instructors} & {si.instructor_id for si in sb.instructors}:
        return "instructor"
    return None


async def resolve_diff(session: AsyncSession, child: ScheduleRun, compare_to: int | None = None) -> dict[str, Any]:
    """The re-solve against its baseline, request by request (moderation spec §5.4 preview, needs §5.3):
    moved (from -> to, with the cause), unchanged (count), newly placed, unplaceable (with the reason), the hard /
    soft score before and after and the waived rules. Pure read of the stored rows: re-running the same re-solve
    gives the identical diff (one worker, deterministic time).

    Baseline (P19 gap 1): ``compare_to`` when given; else the one fixed when the re-solve was created
    (``params.moderation.compare_to_run_id``: the published run that started the chain); else
    :func:`chain_baseline`. A re-solve of a draft child therefore diffs against the published run, and the
    edits of every draft step in between count as "changed" (``in_scope``)."""
    mod = (child.params or {}).get("moderation") or {}
    base_id = mod.get("base_run_id") or child.parent_run_id
    parent = await session.get(ScheduleRun, int(base_id)) if base_id else None
    if parent is None:
        raise ModerationError(404, f"run {child.id} has no base run")
    term = await session.get(Term, child.term_id)
    assert term is not None
    if compare_to is not None:
        base = await comparable_run(session, term, child, compare_to)
        basis = "explicit"
    elif mod.get("compare_to_run_id"):
        stored = await session.get(ScheduleRun, int(mod["compare_to_run_id"]))
        base, basis = (stored, str(mod.get("compare_basis") or "published")) if stored else (parent, "base")
    else:
        base, basis = await chain_baseline(session, child)
    chain = await run_chain(session, child)
    between = []
    for r in chain:  # child .. up to (not including) the baseline
        if r.id == base.id:
            break
        between.append(r)
    status = child.status
    out: dict[str, Any] = {
        "run_id": child.id,
        "base_run_id": parent.id,
        "compare_to_run_id": base.id,
        "compared_to": basis,
        "chain": [r.id for r in between[1:]] + [base.id],  # ancestors up to the baseline (not the run itself)
        "status": status,
        "mode": mod.get("mode"),
        "changed_request_ids": _ints(mod.get("changed_request_ids")),
        "is_active": bool(child.is_active),
    }
    if status in ("QUEUED", "RUNNING"):
        return {**out, "ready": False}
    rooms = await all_rooms(session)
    before = await load_term(session, term, base, rooms=rooms)
    after = await load_term(session, term, child, rooms=rooms)
    by_mr = {mr.id: mr for mr in after.meetings}
    changed = set(_ints(mod.get("changed_request_ids")))
    if len(between) > 1 or base.id != parent.id:  # several draft steps: every step's edits are in scope
        changed |= await chain_edits(session, between)
    out["changed_request_ids"] = sorted(changed)
    st = child.stats or {}
    bst = base.stats or {}
    in_scope = [mr for mr in after.meetings if mr.needs_room and _in_horizon(mr, child)]
    moved: list[dict[str, Any]] = []
    newly: list[dict[str, Any]] = []
    unplaceable: list[dict[str, Any]] = []
    unchanged = 0
    # requests whose published cell already broke a hard rule of the child (``run_resolve`` frees them)
    cst = child.stats or {}
    members_of = {int(k): [int(x) for x in v] for k, v in (cst.get("event_members") or {}).items()}
    base_conflict = {
        int(m)
        for e in ((cst.get("moderation") or {}).get("base_violations") or [])
        for m in members_of.get(int(e), [int(e)])
    }
    old_place: dict[int, Place | None] = {}
    new_place: dict[int, Place | None] = {}
    for mr in in_scope:
        b_rows, a_rows = before.rows_by_mr.get(mr.id, []), after.rows_by_mr.get(mr.id, [])
        old_place[mr.id], new_place[mr.id] = place_of(b_rows), place_of(a_rows)
    for mr in in_scope:
        b_rows, a_rows = before.rows_by_mr.get(mr.id, []), after.rows_by_mr.get(mr.id, [])
        op, np_ = old_place[mr.id], new_place[mr.id]
        people_ids = [si.instructor_id for si in mr.section.instructors]
        base_item = {
            "request_id": mr.id,
            "label": label_of(mr),
            "in_scope": mr.id in changed,
            "instructor_ids": people_ids,
        }
        if op is None and np_ is None:
            if mr.start_period is None or not mr.day:
                continue
            d = after.diag_by_request.get(mr.id)
            unplaceable.append({**base_item, "was_placed": False, "reason": _diag_reason(after, mr, d)})
            continue
        if np_ is None:
            d = after.diag_by_request.get(mr.id)
            reason = _diag_reason(after, mr, d)
            if mr.id in base_conflict:
                # round-1 R1-S-04: the loss is a hard conflict of the published cell itself (a booking or a block
                # added since, a rule written on the draft), never a price paid for a soft wish
                reason = {
                    **reason,
                    "code": "base_conflict",
                    "text": _t(
                        "Yayımdaki hücresi artık kesin bir kuralı bozuyor (sonradan eklenen rezervasyon / blok ya da "
                        "taslak kuralı); orada kalamaz. " + str((reason.get("text") or {}).get("tr") or ""),
                        "Its published cell now breaks a hard rule (a booking or block added since, or a draft rule); "
                        "it cannot stay there. " + str((reason.get("text") or {}).get("en") or ""),
                    ),
                }
            unplaceable.append(
                {
                    **base_item,
                    "was_placed": True,
                    "from": _place_out(op, rooms),
                    "reason": reason,
                    "base_conflict": mr.id in base_conflict,
                }
            )
            continue
        if op is None:
            newly.append({**base_item, "to": _place_out(np_, rooms)})
            continue
        if _cell_set(b_rows) == _cell_set(a_rows):
            unchanged += 1
            continue
        causes: list[dict[str, Any]] = []
        if mr.id in changed:
            causes.append({"code": "changed", "text": _t("Değiştirilen talep", "Edited request")})
        else:
            for oid, other_new in new_place.items():
                if oid == mr.id or other_new is None:
                    continue
                if old_place.get(oid) == other_new:
                    continue  # the other class did not move: it is no cause
                why = _touch(op, other_new, mr, by_mr[oid])
                if why:
                    lbl = label_of(by_mr[oid])
                    tr_why = {"room": "dersliği", "cohort": "aynı sınıfın saatini", "instructor": "hocanın saatini"}[
                        why
                    ]
                    en_why = {"room": "the room", "cohort": "the cohort's slot", "instructor": "the instructor's slot"}[
                        why
                    ]
                    causes.append(
                        {
                            "code": f"displaced_{why}",
                            "request_id": oid,
                            "label": lbl,
                            "text": _t(
                                f"{lbl} {tr_why} aldığı için {label_of(mr)} taşındı",
                                f"{label_of(mr)} moved because {lbl} took {en_why}",
                            ),
                        }
                    )
            causes = causes[:5]
            if not causes:
                # no class took its old cell: Q9 counts it (repair mode reverts such moves, _minimal_change)
                causes.append(
                    {
                        "code": "unexplained",
                        "text": _t(
                            "Taşındı; eski yerini başka bir ders almadı",
                            "Moved although no other class took its old cell",
                        ),
                    }
                )
        moved.append({**base_item, "from": _place_out(op, rooms), "to": _place_out(np_, rooms), "causes": causes})
    outside = [m for m in moved if not m["in_scope"]]
    touched = [*moved, *newly, *(u for u in unplaceable if u["was_placed"])]
    affected = sorted({i for m in touched for i in m["instructor_ids"]})
    rep = st.get("repair") or {}
    diags = [
        {"code": d.get("code"), "text": d.get("text"), "message": d.get("message"), "event_ids": d.get("event_ids")}
        for d in child.diagnosis or []
        if isinstance(d, dict) and d.get("severity") == "error"
    ][:50]
    return {
        **out,
        "ready": True,
        "counts": {
            "moved": len(moved),
            "moved_outside_scope": len(outside),
            "moved_unexplained": sum(1 for m in outside if m["causes"][0]["code"] == "unexplained"),
            "unchanged": unchanged,
            "newly_placed": len(newly),
            "unplaceable": len(unplaceable),
            "newly_unplaced": sum(1 for u in unplaceable if u["was_placed"]),
            "newly_unplaced_base_conflict": sum(1 for u in unplaceable if u.get("base_conflict")),
            "affected_people": len(affected),
        },
        "moved": moved,
        "newly_placed": newly,
        "unplaceable": unplaceable,
        "affected_instructor_ids": affected,
        "scores": {
            "hard": {"before": base.hard_score, "after": child.hard_score},
            "soft": {"before": base.soft_score, "after": child.soft_score},
            "placed": {"before": bst.get("placed"), "after": st.get("placed"), "total": st.get("events_total")},
        },
        "waived_rules": list(st.get("waived_rules") or []),
        "neighbourhood": {
            "seeds": len((st.get("moderation") or {}).get("seeds") or []),
            "freed": len(rep.get("freed") or []),
            "reverted": len((st.get("moderation") or {}).get("reverted") or []),
            "radius": (st.get("moderation") or {}).get("radius"),
        },
        "workers": (st.get("moderation") or {}).get("workers"),
        "diagnosis": diags,
    }


def _diag_reason(td: TermData, mr: MeetingRequest, d: Mapping[str, Any] | None) -> dict[str, Any]:
    if d is None:
        return {"code": "unplaced", "text": _t("Yerleşmedi", "Not placed"), "policy_step": None, "culprits": []}
    r = reason_for(td, mr, wanted(mr, td.rooms), None, dict.fromkeys(FLAGS), "unplaced")
    assert r is not None
    return r


# ------------------------------------------------------------------------------------------- draft edits (M3)

ACTIONS = ("pin", "prefer", "unlock")
#: the explicit soft weight of a coordinator wish (academician needs Q7: explicit 10 > learned 5)
PREFER_WEIGHT = 10


def _moderation_ref(c: ConstraintRow) -> dict[str, Any]:
    ref = c.source_ref if isinstance(c.source_ref, dict) else {}
    mod = ref.get("moderation")
    return mod if isinstance(mod, dict) else {}


def _draft_child(run: ScheduleRun) -> None:
    if run.is_active:
        raise ModerationError(409, "the published run is never edited; re-solve it and edit the draft child run")
    if run.parent_run_id is None:
        raise ModerationError(409, "edits go to a draft child run (POST /terms/{id}/moderation/resolve first)")


async def matching_action(
    session: AsyncSession,
    request_id: int,
    *,
    run_id: int,
    action: str,
    actor: User,
    may_override: bool,
    room_ids: list[int] | None = None,
    day: int | None = None,
    start_period: int | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """``pin``: the class keeps a cell (default: its cell in the base run, "Bu taşımayı engelle"), written as hard
    targeted ``room_pin`` + ``fixed_time`` rules of the draft child run; ``prefer``: a soft targeted
    ``room_preference``; ``unlock``: the child's pins / preferences of the class are switched off and its lock is
    released for the next re-solve (``solver_bridge.UNLOCK_PARAM``). Rules go through ``constraint_guard`` and the
    constraint catalogue; a pin that seats more students than the rooms hold is refused unless a planning
    administrator gives a reason (Q8). The rule takes effect at the next re-solve from this run (rules are
    inherited by child runs)."""
    from sqlalchemy.orm.attributes import flag_modified

    from app.ai.catalog import validate_params
    from app.services.constraint_guard import guard_rule
    from app.services.events import publish_event
    from app.services.solver_bridge import UNLOCK_PARAM

    if action not in ACTIONS:
        raise ModerationError(422, f"action must be one of {ACTIONS}")
    run = await session.get(ScheduleRun, run_id)
    if run is None:
        raise ModerationError(404, "run not found")
    _draft_child(run)
    if run.kind != "COURSE":
        raise ModerationError(422, "matchings cover course runs (meeting requests)")
    mr = (await session.execute(_meeting_query().where(MeetingRequest.id == request_id))).scalar_one_or_none()
    if mr is None or mr.archived or mr.section.term_id != run.term_id:
        raise ModerationError(404, "meeting request not found in this run's term")
    term_id = run.term_id
    existing = list(
        (
            await session.execute(
                select(ConstraintRow).where(ConstraintRow.run_id == run.id, ConstraintRow.enabled.is_(True))
            )
        ).scalars()
    )
    mine = [c for c in existing if _moderation_ref(c).get("request_id") == mr.id]
    created: list[int] = []
    disabled: list[int] = []
    if action == "unlock":
        for c in mine:
            c.enabled = False
            disabled.append(c.id)
        params = dict(run.params or {})
        cur = _ints(params.get(UNLOCK_PARAM))
        if mr.id not in cur:
            params[UNLOCK_PARAM] = sorted([*cur, mr.id])
            run.params = params
            flag_modified(run, "params")
        detail: dict[str, Any] = {"unlocked": True}
    else:
        parent = await session.get(ScheduleRun, run.parent_run_id) if run.parent_run_id else None
        ref_place = None
        if parent is not None:
            rows = list(
                (
                    await session.execute(
                        select(Assignment).where(
                            Assignment.run_id == parent.id,
                            Assignment.meeting_request_id == mr.id,
                            Assignment.archived.is_(False),
                        )
                    )
                ).scalars()
            )
            ref_place = place_of(rows)
        rooms = await all_rooms(session)
        rids = [int(r) for r in room_ids] if room_ids else list(ref_place.room_ids) if ref_place else []
        unknown = [r for r in rids if r not in rooms]
        if unknown:
            raise ModerationError(422, f"unknown room ids {unknown}")
        if not rids:
            raise ModerationError(422, "name the rooms (room_ids): the class has no cell in the base run")
        specs: list[tuple[str, dict[str, Any], str, int]] = []
        if action == "pin":
            d = day if day is not None else ref_place.day if ref_place else mr.day
            s = start_period if start_period is not None else ref_place.start if ref_place else mr.start_period
            if d is None or s is None:
                raise ModerationError(422, "name the day and start_period of the pin")
            size = int(mr.section.enrolment or 0)
            seats = sum(int(rooms[r].capacity or 0) for r in rids)
            if size and seats < size and not (may_override and len((reason or "").strip()) >= 3):
                from app.services.pin_guard import capacity_message

                names = " + ".join(rooms[r].display_name for r in rids)
                msg = capacity_message(size, seats, names)
                raise ModerationError(
                    422,
                    {
                        "code": "capacity",
                        "message": f"{msg['tr']} / {msg['en']}",
                        "message_tr": msg["tr"],
                        "message_en": msg["en"],
                        "issues": ["capacity"],
                        "override": "planning.admin with a reason",
                    },
                )
            specs.append(("room_pin", {"event_ids": [mr.id], "room_ids": rids}, "hard", 1))
            specs.append(("fixed_time", {"event_ids": [mr.id], "day": int(d), "start": int(s)}, "hard", 1))
        else:
            specs.append(("room_preference", {"event_ids": [mr.id], "room_ids": rids}, "soft", PREFER_WEIGHT))
        for c in mine:  # one wish per class and draft: the new one replaces the old
            c.enabled = False
            disabled.append(c.id)
        for kind, params_, hardness, weight in specs:
            issues = validate_params(kind, dict(params_), hardness) + guard_rule(
                kind, params_, hardness, source="ADMIN", may_waive=False, reason=None
            )
            if issues:
                raise ModerationError(422, {"message": "invalid rule", "issues": issues[:10]})
            row = ConstraintRow(
                term_id=None,
                run_id=run.id,
                kind=kind,
                params=params_,
                hardness=hardness,
                weight=weight,
                source="ADMIN",
                nl_text=f"{label_of(mr)}: {action} " + " + ".join(rooms[r].display_name for r in rids),
                enabled=True,
                created_by=actor.id,
                source_ref={
                    "moderation": {"request_id": mr.id, "action": action, "reason": (reason or "").strip() or None}
                },
            )
            session.add(row)
            await session.flush()
            created.append(row.id)
        detail = {"room_ids": rids}
    await publish_event(
        session,
        f"moderation.{action}",
        "meeting_request",
        mr.id,
        after={"run_id": run.id, "action": action, "constraints": created, "disabled": disabled, **detail},
        actor=actor,
        reason=(reason or "").strip() or None,
        term_id=term_id,
    )
    await session.commit()
    return {
        "request_id": mr.id,
        "run_id": run.id,
        "action": action,
        "constraint_ids": created,
        "disabled_constraint_ids": disabled,
        "effective": _t("Bir sonraki yeniden çözümde etkili olur", "Takes effect at the next re-solve"),
        **detail,
    }


__all__ = [
    "FLAGS",
    "ModerationError",
    "Scope",
    "chain_baseline",
    "create_resolve",
    "enqueue_resolve",
    "flags_for",
    "history",
    "match_one",
    "matching_action",
    "people",
    "resolve_diff",
    "run_resolve",
    "set_request_priority",
    "set_section_priority",
    "set_subject_priority",
    "term_matchings",
    "verdict_of",
    "visibility",
    "wanted",
]
