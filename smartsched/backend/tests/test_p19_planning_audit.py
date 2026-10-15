"""P19-02 / review 2026-10-15 D5: planning edits leave an audit row with before/after -- request edits, single and
bulk moves (forced ones flagged with their conflicts), locks, restores. (Run activate/delete and constraint CRUD
are covered in test_p19_publish_guard.py / test_p19_hard_rules.py.)

Real Bahar 2026 import (``tests/crbs_env``): the published weekly-grid run and the planning-list requests.
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import Assignment, AuditEvent, Course, MeetingRequest, Section
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401


async def _events(action: str) -> list[AuditEvent]:
    async with dbmod.get_session_factory()() as s:
        q = select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        return list((await s.execute(q)).scalars())


async def _two_overlapping(run_id: int) -> tuple[Assignment, Assignment]:
    """Two Monday classes of the board in different rooms whose periods overlap (a move of one into the other's
    room is a room clash)."""
    async with dbmod.get_session_factory()() as s:
        rows = list(
            (
                await s.execute(
                    select(Assignment).where(Assignment.run_id == run_id, Assignment.day == 1).order_by(Assignment.id)
                )
            ).scalars()
        )
    for a in rows:
        for b in rows:
            if (
                a.id != b.id
                and a.room_ids
                and b.room_ids
                and set(a.room_ids).isdisjoint(b.room_ids)
                and a.start_period == b.start_period
                and a.end_period == b.end_period
                and set(a.weeks or []) & set(b.weeks or [])
            ):
                return a, b
    raise AssertionError("the Bahar board has parallel Monday classes")


async def test_meeting_request_edit_is_audited_with_before_and_after(env):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        mr = (
            (
                await s.execute(
                    select(MeetingRequest)
                    .join(Section, Section.id == MeetingRequest.section_id)
                    .join(Course, Course.id == Section.course_id)
                    .where(Section.term_id == env.term_id, Course.code == "MAT112")
                    .order_by(MeetingRequest.id)
                )
            )
            .scalars()
            .first()
        )
        assert mr is not None
        old_notes, old_status = mr.notes, mr.status
    note = "Bilgisayar laboratuvarı zorunlu (İÖ şubesi)"
    new_status = "NEEDS_REVIEW" if old_status != "NEEDS_REVIEW" else "PARSED"
    r = await env.client.put(
        f"/api/v1/requests/meetings/{mr.id}", json={"notes": note, "status": new_status}, headers=env.planner
    )
    assert r.status_code == 200, r.text
    (ev,) = await _events("meeting_request.update")
    assert ev.entity_id == str(mr.id) and ev.term_id == env.term_id
    assert ev.before == {"notes": old_notes, "status": old_status}
    assert ev.after == {"notes": note, "status": new_status}


async def test_single_move_and_lock_are_audited(env):  # noqa: F811
    a, b = await _two_overlapping(env.run_id)
    url = f"/api/v1/runs/{env.run_id}/assignments/{a.id}"
    r = await env.client.post(f"{url}/move", json={"room_ids": list(b.room_ids), "force": True}, headers=env.admin)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    (ev,) = await _events("assignment.move")
    assert ev.entity_id == str(a.id) and ev.term_id == env.term_id
    assert ev.before["room_ids"] == list(a.room_ids) and ev.after["room_ids"] == list(b.room_ids)
    assert ev.after["origin"] == "MANUAL" and ev.after["forced"] is True and ev.after["conflicts"]
    assert ev.reason and "forced" in ev.reason
    r = await env.client.post(f"{url}/lock", params={"locked": False}, headers=env.planner)
    assert r.status_code == 200, r.text
    (lk,) = await _events("assignment.unlock")
    assert lk.before == {"is_locked": True} and lk.after == {"is_locked": False}


async def test_forced_bulk_move_restore_and_bulk_lock_are_audited(env):  # noqa: F811
    a, b = await _two_overlapping(env.run_id)
    base = f"/api/v1/runs/{env.run_id}/assignments"
    body = {"moves": [{"aid": a.id, "room_ids": list(b.room_ids)}], "force": True}
    r = await env.client.post(f"{base}/bulk-move", json=body, headers=env.planner)
    assert r.status_code == 403  # forcing is admin-only
    r = await env.client.post(f"{base}/bulk-move", json=body, headers=env.admin)
    assert r.status_code == 200 and r.json()["applied"] is True, r.text
    assert r.json()["conflict_count"] == 1
    (ev,) = await _events("assignment.bulk_move")
    assert ev.entity_type == "assignment" and ev.entity_id == str(a.id)  # one row: no parent
    assert ev.before["room_ids"] == list(a.room_ids) and ev.after["room_ids"] == list(b.room_ids)
    assert ev.reason and "forced" in ev.reason and "1 conflict" in ev.reason
    undo = r.json()["undo"]
    r = await env.client.post(f"{base}/restore", json=undo, headers=env.planner)
    assert r.status_code == 200, r.text
    (rs,) = await _events("assignment.restore")
    assert rs.before["room_ids"] == list(b.room_ids) and rs.after["room_ids"] == list(a.room_ids)
    r = await env.client.post(f"{base}/bulk-lock", json={"ids": [a.id, b.id], "locked": False}, headers=env.planner)
    assert r.status_code == 200, r.text
    r = await env.client.post(f"{base}/bulk-lock", json={"ids": [a.id, b.id], "locked": True}, headers=env.planner)
    assert r.status_code == 200, r.text
    locks = await _events("assignment.lock")
    parent = next(e for e in locks if e.parent_id is None)
    assert parent.entity_type == "run" and parent.after["count"] == 2
    assert {e.entity_id for e in locks if e.parent_id == parent.id} == {str(a.id), str(b.id)}
