"""Studio drafts that leave part of a joint lecture out keep the bridge's fallback sizes (comparison follow-up 3).

Bahar rows 1090 (SYS 19, Tıbbi Laboratuvar Teknikleri, 57 students), 1292 and 1293 (SYS 019, Patoloji
Laboratuvar Teknikleri, day and evening programme, no enrolment): all three LOCKED to A 207 on Tuesday
16:00-17:30, i.e. one joint lecture.  The missing enrolments get the course's median (57)."""

from __future__ import annotations

from app.models import MeetingRequest, Room, ScheduleRun, Term
from app.services.studio import _build_for
from sqlalchemy import select

from tests.conftest import BAHAR_LIST
from tests.test_importer_followups import subset


async def _setup(session, tmp_path):  # type: ignore[no-untyped-def]
    from app.importers.planning_list import import_planning_list

    await import_planning_list(session, subset(BAHAR_LIST, [1090, 1292, 1293], tmp_path / "sys.xlsx"), "T-SYS19")
    room = (await session.execute(select(Room).where(Room.code == "A207"))).scalar_one()
    room.capacity, room.is_bookable = 120, True  # the room master's A 207
    await session.flush()
    term = (await session.execute(select(Term))).scalar_one()
    ids = [m.id for m in (await session.execute(select(MeetingRequest).order_by(MeetingRequest.id))).scalars()]
    return term, ids


def _run(term: Term) -> ScheduleRun:
    return ScheduleRun(term_id=term.id, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]}, params={})


async def test_joint_lecture_without_enrolments_keeps_fallback_sizes(session, tmp_path) -> None:
    term, (r1090, r1292, r1293) = await _setup(session, tmp_path)
    full = await _build_for(session, _run(term), {})
    [ev] = full.inp.events
    assert full.members[ev.id] == [r1090, r1292, r1293] and ev.size == 57 * 3
    # leave the 57-student row out: the two Patoloji rows still count 57 each (their fallback), not 0
    out = await _build_for(session, _run(term), {"excluded_event_ids": [r1090]})
    [ev2] = out.inp.events
    assert out.members[ev2.id] == [r1292, r1293] and ev2.size == 114
    # leave one Patoloji row out: 57 + 57, not 57 + 0
    out = await _build_for(session, _run(term), {"excluded_event_ids": [r1292]})
    [ev3] = out.inp.events
    assert ev3.size == 114
