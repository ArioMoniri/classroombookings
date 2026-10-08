"""Turn the solver's free-text diagnosis suggestions into structured, applicable fix options.

``app.solver.diagnose`` emits ``Diagnosis(event_ids, constraint_kinds, message, suggestions, severity)``
with plain-English suggestion strings.  A *subset* of those strings has a fixed shape and can be
applied mechanically (see :data:`PATTERNS`); everything else is returned with ``action="manual"`` and
``applicable=False`` and the apply endpoint answers 422 with a reason.

Applying never edits the source request rows' times or rooms.  Placements become planner-locked
``MANUAL`` assignments on the diagnosed run; :func:`app.services.solver_bridge.build_solver_input`
turns locked parent assignments into ``Event.locked`` when the child run is solved.  Unlocking resets
the request's ``LOCKED`` status (the bridge only pins definitive rooms of ``LOCKED`` requests).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, ConstraintRow, ExamRequest, MeetingRequest, Room, ScheduleRun, Term, Week
from app.services.calendar import week_index_for_date

# "use A101 at day 1 P4-P6"
_USE = re.compile(r"^use (?P<room>\S+) at day (?P<day>[1-7]) P(?P<start>\d+)-P(?P<end>\d+)$")
# "alternative periods on the same day: P5-P7 in A101, P8-P10 in B201"
_ALT = re.compile(r"^alternative periods on the same day: P(?P<start>\d+)-P(?P<end>\d+) in (?P<room>[^,\s]+)")
# "release A101 (58) at day 1 P4-P6 held by PSI 155 (#12), MAT 112 (#14)"
_RELEASE = re.compile(
    r"^release (?P<room>\S+) \((?P<cap>\d+)\) at day (?P<day>[1-7]) P(?P<start>\d+)-P(?P<end>\d+) held by (?P<who>.+)$"
)
# "unlock PSI 155 or MAT 112" / "unlock the event"
_UNLOCK = re.compile(r"^unlock\b")
# "make the building_preference rule soft or exempt this event"
_RELAX = re.compile(r"^make the (?P<kind>[a-z_]+) rule soft")
_SPLIT = re.compile(r"allow split(?:ting)?", re.IGNORECASE)
_HOLDER = re.compile(r"\(#(?P<id>\d+)\)")
_LABEL = re.compile(r"(?P<label>[^,:;|()]+?) \(#(?P<id>\d+)\)")
_DAY_IN_MSG = re.compile(r"\bday (?P<day>[1-7]) P\d+")


class FixError(Exception):
    """The option cannot be applied mechanically (-> HTTP 422 with ``str(exc)``)."""


@dataclass
class FixOption:
    index: int
    text: str
    action: str  # move | release_room | split | relax | unlock | manual
    applicable: bool
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": f"s{self.index}",
            "index": self.index,
            "text": self.text,
            "action": self.action,
            "applicable": self.applicable,
            "params": self.params,
        }


def parse_option(index: int, text: str, diag: dict[str, Any]) -> FixOption:
    """Classify one suggestion string of ``diag`` (a stored ``asdict(Diagnosis)``)."""
    t = " ".join(str(text).split())
    event_ids = [int(e) for e in diag.get("event_ids") or []]
    target = event_ids[0] if event_ids else None
    if m := _USE.match(t):
        return FixOption(
            index,
            t,
            "move",
            target is not None,
            {
                "event_id": target,
                "room_code": m["room"],
                "day": int(m["day"]),
                "start_period": int(m["start"]),
                "end_period": int(m["end"]),
            },
        )
    if m := _ALT.match(t):
        day = _DAY_IN_MSG.search(str(diag.get("message") or ""))
        return FixOption(
            index,
            t,
            "move",
            target is not None and day is not None,
            {
                "event_id": target,
                "room_code": m["room"],
                "day": int(day["day"]) if day else None,
                "start_period": int(m["start"]),
                "end_period": int(m["end"]),
            },
        )
    if m := _RELEASE.match(t):
        holders = [int(h["id"]) for h in _HOLDER.finditer(m["who"])]
        return FixOption(
            index,
            t,
            "release_room",
            target is not None,
            {
                "event_id": target,
                "room_code": m["room"],
                "day": int(m["day"]),
                "start_period": int(m["start"]),
                "end_period": int(m["end"]),
                "holder_event_ids": holders,
            },
        )
    if _UNLOCK.match(t):
        return FixOption(index, t, "unlock", bool(event_ids), {"event_ids": event_ids})
    if m := _RELAX.match(t):
        return FixOption(index, t, "relax", True, {"kind": m["kind"], "event_ids": event_ids})
    if _SPLIT.search(t):
        return FixOption(index, t, "split", bool(event_ids), {"event_ids": event_ids, "max_rooms": 3})
    return FixOption(index, t, "manual", False, {})


def structure_diagnosis(raw: Any, index: int) -> dict[str, Any]:
    """Stored diagnosis -> API shape: stable ``id``, ``event_labels`` and structured ``suggestions``."""
    if not isinstance(raw, dict):
        raw = {"event_ids": [], "constraint_kinds": [], "message": str(raw), "suggestions": [], "severity": "error"}
    labels = {int(m["id"]): m["label"].strip() for m in _LABEL.finditer(str(raw.get("message") or ""))}
    event_ids = [int(e) for e in raw.get("event_ids") or []]
    options = [
        parse_option(j, s, raw).as_dict() if isinstance(s, str) else s
        for j, s in enumerate(raw.get("suggestions") or [])
    ]
    return {
        **raw,
        "id": str(index),
        "index": index,
        "event_ids": event_ids,
        "event_labels": [labels.get(e, f"#{e}") for e in event_ids],
        "suggestions": options,
    }


# --------------------------------------------------------------------------- application


@dataclass
class FixResult:
    action: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    constraint_id: int | None = None


async def _room_by_code(session: AsyncSession, code: str) -> Room:
    norm = code.replace(" ", "").upper()
    room = (await session.execute(select(Room).where(Room.code == norm))).scalar_one_or_none()
    if room is None:
        raise FixError(f"room {code!r} not found")
    return room


async def _members(session: AsyncSession, run: ScheduleRun, event_id: int) -> list[int]:
    """Request ids behind a solver event (merged exam cohorts share the head's id)."""
    if run.kind != "EXAM":
        return [event_id]
    head = await session.get(ExamRequest, event_id)
    if head is None:
        raise FixError(f"exam request #{event_id} not found")
    if not head.merge_key:
        return [head.id]
    rows = (
        await session.execute(
            select(ExamRequest.id).where(
                ExamRequest.term_id == head.term_id,
                ExamRequest.merge_key == head.merge_key,
                ExamRequest.archived.is_(False),
            )
        )
    ).scalars()
    return sorted(set(rows) | {head.id})


async def _place(
    session: AsyncSession, run: ScheduleRun, event_id: int, room: Room, day: int, start: int, end: int
) -> list[int]:
    """Create/replace planner-locked MANUAL assignments of ``event_id`` on ``run``."""
    from app.services.solver_bridge import horizon_weeks

    term = await session.get(Term, run.term_id)
    assert term is not None
    exam = run.kind == "EXAM"
    out: list[int] = []
    for req_id in await _members(session, run, event_id):
        weeks: list[int]
        date = None
        if exam:
            ex = await session.get(ExamRequest, req_id)
            if ex is None:
                raise FixError(f"exam request #{req_id} not found")
            date = ex.date
            rows = list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())
            wk = week_index_for_date(term, ex.date, rows) if ex.date else None
            weeks = [wk] if wk is not None else []
        else:
            mr = await session.get(MeetingRequest, req_id)
            if mr is None:
                raise FixError(f"meeting request #{req_id} not found")
            horizon = horizon_weeks(run, term)
            weeks = [w for w in horizon if not mr.weeks or w in {int(x) for x in mr.weeks}]
        col = Assignment.exam_request_id if exam else Assignment.meeting_request_id
        existing = list(
            (
                await session.execute(
                    select(Assignment).where(Assignment.run_id == run.id, col == req_id, Assignment.archived.is_(False))
                )
            ).scalars()
        )
        a = existing[0] if existing else Assignment(run_id=run.id)
        for extra in existing[1:]:
            extra.archived = True
        if exam:
            a.exam_request_id = req_id
        else:
            a.meeting_request_id = req_id
        a.day, a.start_period, a.end_period = day, start, end
        a.room_ids = [room.id]
        a.weeks = weeks
        a.week = weeks[0] if len(weeks) == 1 else None
        a.date = date
        a.is_locked = True
        a.origin = "MANUAL"
        if not existing:
            session.add(a)
        await session.flush()
        out.append(a.id)
    return out


async def _unlock(session: AsyncSession, run: ScheduleRun, event_ids: list[int]) -> list[int]:
    unlocked: list[int] = []
    for ev in event_ids:
        for req_id in await _members(session, run, ev):
            row: MeetingRequest | ExamRequest | None = (
                await session.get(ExamRequest, req_id)
                if run.kind == "EXAM"
                else await session.get(MeetingRequest, req_id)
            )
            if row is None:
                continue
            if row.status == "LOCKED":
                row.status = "PARSED"
                unlocked.append(req_id)
            col = Assignment.exam_request_id if run.kind == "EXAM" else Assignment.meeting_request_id
            for a in (
                await session.execute(select(Assignment).where(Assignment.run_id == run.id, col == req_id))
            ).scalars():
                if a.is_locked:
                    a.is_locked = False
                    unlocked.append(req_id)
    return sorted(set(unlocked))


async def apply_option(session: AsyncSession, run: ScheduleRun, diag: dict[str, Any], option_index: int) -> FixResult:
    """Apply suggestion ``option_index`` of ``diag`` to ``run``'s inputs.  Caller commits."""
    suggestions = list(diag.get("suggestions") or [])
    if not 0 <= option_index < len(suggestions):
        raise FixError(f"option_index {option_index} out of range (0..{len(suggestions) - 1})")
    raw = suggestions[option_index]
    opt = parse_option(option_index, raw if isinstance(raw, str) else str(raw.get("text", "")), diag)
    if not opt.applicable:
        raise FixError(f"suggestion {opt.text!r} has no structured fix; apply it by hand")
    p = opt.params
    if opt.action in {"move", "release_room"}:
        room = await _room_by_code(session, str(p["room_code"]))
        details: dict[str, Any] = {}
        if opt.action == "release_room":
            details["unlocked_request_ids"] = await _unlock(session, run, list(p["holder_event_ids"]))
        ids = await _place(
            session, run, int(p["event_id"]), room, int(p["day"]), int(p["start_period"]), int(p["end_period"])
        )
        details |= {
            "assignment_ids": ids,
            "room_id": room.id,
            **{k: p[k] for k in ("day", "start_period", "end_period")},
        }
        return FixResult(
            opt.action,
            f"#{p['event_id']} placed in {room.display_name} on day {p['day']} P{p['start_period']}-P{p['end_period']}"
            " and locked",
            details,
        )
    if opt.action == "unlock":
        ids = await _unlock(session, run, list(p["event_ids"]))
        if not ids:
            raise FixError("nothing to unlock: the events' requests are not LOCKED and have no locked assignment")
        return FixResult("unlock", f"unlocked request(s) {ids}", {"unlocked_request_ids": ids})
    if opt.action == "relax":
        kind = str(p["kind"])
        rows = list(
            (
                await session.execute(
                    select(ConstraintRow).where(
                        ConstraintRow.kind == kind,
                        ConstraintRow.enabled.is_(True),
                        ConstraintRow.hardness == "hard",
                        (ConstraintRow.term_id == run.term_id) | (ConstraintRow.run_id == run.id),
                    )
                )
            ).scalars()
        )
        if not rows:
            raise FixError(f"no enabled hard '{kind}' constraint to soften (built-in rule); edit the request instead")
        for c in rows:
            c.hardness = "soft"
        return FixResult(
            "relax", f"'{kind}' made soft ({len(rows)} rule(s))", {"constraint_ids": [c.id for c in rows]}, rows[0].id
        )
    if opt.action == "split":
        if run.kind != "EXAM":
            raise FixError("course sections are never split across rooms; reduce the group or pick a larger room")
        changed: list[int] = []
        for ev in p["event_ids"]:
            for req_id in await _members(session, run, int(ev)):
                ex = await session.get(ExamRequest, req_id)
                if ex is not None and int(ex.requested_room_count or 0) < int(p["max_rooms"]):
                    ex.requested_room_count = int(p["max_rooms"])
                    changed.append(req_id)
        return FixResult("split", f"exam(s) may now use up to {p['max_rooms']} rooms", {"exam_request_ids": changed})
    raise FixError(f"unsupported action {opt.action}")
