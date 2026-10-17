"""Hard room pins that cannot seat their class (persona Q8, round-1 R1-M-03).

"100 öğrenci 30 kişilik B 201'e sığmaz": a Must rule (``room_pin``, hard) that puts a class into rooms whose seats
cannot hold it is impossible: the solver prunes every other room, the capacity rule then refuses the pinned ones,
and the class is left out. Every write path refuses such a rule with the same TR/EN sentence (422 ``capacity``);
only a planning administrator may keep it, with a written reason (audited by the caller):

* ``POST /constraints`` / ``PUT /constraints/{id}`` (the Studio templates such as "Her zaman bu derslikte" and the
  rule editor write through them);
* AI / upload / import approval (``app.ai.elicit.accept_proposals``: Studio review tray, chat, council commit),
  never overridable there;
* Studio copy-from-term and presets (``app.services.studio_rules``);
* moderation pins and programme-wizard rules; the meeting edit (``PUT /requests/meetings/{id}``, definitive rooms).

The check is an upper bound (the pinned rooms' seats added up, as if the class could split over all of them): it
refuses only what can never fit. The exact solver semantics (single-room classes, ``max_rooms``) are the static
checker's (``app.solver.diagnose`` ``no_room`` / ``reason: capacity`` with ``pin_constraint_ids``), which the
Studio pre-check and the run report show for rules written before this guard.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ExamRequest, MeetingRequest, Room, Section
from app.services.tr_grammar import dative

REASON_MIN = 3


@dataclass(frozen=True)
class Shortfall:
    request_id: int
    label: str
    size: int
    seats: int
    rooms: str  # "B 201" / "A 101 + A 106"

    @property
    def tr(self) -> str:
        return f"{self.size} öğrenci {self.seats} kişilik {dative(self.rooms)} sığmaz"

    @property
    def en(self) -> str:
        return f"{self.size} students do not fit {self.rooms} ({self.seats} seats)"


def capacity_message(size: int, seats: int, rooms: str) -> dict[str, str]:
    """The one sentence of every refusal: ``{"tr": "100 öğrenci 30 kişilik B 201'e sığmaz", "en": ...}``."""
    s = Shortfall(0, "", size, seats, rooms)
    return {"tr": s.tr, "en": s.en}


def _ints(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, int | str):
        value = [value]
    out = []
    for v in value:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def is_hard_pin(kind: str, params: Mapping[str, Any] | None, hardness: str | None) -> bool:
    return kind == "room_pin" and (hardness or "hard") == "hard" and bool(_ints((params or {}).get("room_ids")))


async def shortfalls(
    session: AsyncSession,
    kind: str,
    params: Mapping[str, Any] | None,
    hardness: str | None,
    *,
    term_id: int | None = None,
) -> list[Shortfall]:
    """The classes a hard ``room_pin`` with explicit ``event_ids`` puts into rooms that cannot seat them."""
    p = dict(params or {})
    if not is_hard_pin(kind, p, hardness):
        return []
    event_ids = _ints(p.get("event_ids"))
    room_ids = _ints(p.get("room_ids"))
    if not event_ids or not room_ids:
        return []
    exam = "exam" in [str(k) for k in (p.get("kinds") or p.get("kind") or [])]
    rooms = {r.id: r for r in (await session.execute(select(Room).where(Room.id.in_(room_ids)))).scalars()}
    if not rooms:
        return []
    names = " + ".join(rooms[r].display_name or rooms[r].code for r in room_ids if r in rooms)
    seats = sum(int((rooms[r].exam_capacity if exam else rooms[r].capacity) or 0) for r in rooms)
    if seats <= 0:
        return []  # rooms without a known capacity (outside the pool): nothing to compare with
    out: list[Shortfall] = []
    if exam:
        qe = select(ExamRequest).where(ExamRequest.id.in_(event_ids))
        if term_id is not None:
            qe = qe.where(ExamRequest.term_id == term_id)
        for ex in (await session.execute(qe)).scalars():
            size = int(ex.enrolment or 0)
            if size > seats:
                out.append(Shortfall(ex.id, ex.course_code, size, seats, names))
        return out
    q = (
        select(MeetingRequest)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(MeetingRequest.id.in_(event_ids))
        .options(selectinload(MeetingRequest.section).selectinload(Section.course))
    )
    if term_id is not None:
        q = q.where(Section.term_id == term_id)
    for mr in (await session.execute(q)).scalars():
        sec = mr.section
        size = int((sec.enrolment if sec is not None else 0) or mr.requested_capacity or 0)
        if size > seats:
            label = f"{sec.course.display_code}{' §' + sec.label if sec.label else ''}" if sec is not None else ""
            out.append(Shortfall(mr.id, label, size, seats, names))
    return sorted(out, key=lambda s: s.request_id)


def refusal(found: list[Shortfall], *, overridable: bool) -> dict[str, Any]:
    """The 422 body (``code: capacity``) naming every class that does not fit."""
    one = len(found) == 1
    tr = found[0].tr if one else "; ".join(f"{s.label}: {s.tr}" for s in found[:5])
    en = found[0].en if one else "; ".join(f"{s.label}: {s.en}" for s in found[:5])
    if len(found) > 5:
        tr += f" (+{len(found) - 5} ders)"
        en += f" (+{len(found) - 5} classes)"
    body: dict[str, Any] = {
        "code": "capacity",
        "message": en,
        "message_tr": tr,
        "message_en": en,
        "classes": [
            {"request_id": s.request_id, "label": s.label, "size": s.size, "seats": s.seats, "rooms": s.rooms}
            for s in found[:50]
        ],
    }
    if overridable:
        body["override"] = "a planning administrator may keep it with a written reason (reason)"
    return body


def valid_reason(reason: str | None) -> bool:
    return len((reason or "").strip()) >= REASON_MIN


async def check(
    session: AsyncSession,
    kind: str,
    params: Mapping[str, Any] | None,
    hardness: str | None,
    *,
    term_id: int | None,
    may_override: bool,
    reason: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """``(refusal, None)`` when the pin is impossible and not overridden; ``(None, override_text)`` when a planning
    administrator keeps it with a reason; ``(None, None)`` when it fits."""
    found = await shortfalls(session, kind, params, hardness, term_id=term_id)
    if not found:
        return None, None
    if may_override and valid_reason(reason):
        what = "; ".join(f"{s.label}: {s.en}" for s in found[:5])
        return None, f"{(reason or '').strip()} (override: {what})"
    return refusal(found, overridable=True), None


__all__ = ["Shortfall", "capacity_message", "check", "is_hard_pin", "refusal", "shortfalls", "valid_reason"]
