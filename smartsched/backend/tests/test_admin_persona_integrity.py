"""Admin persona test 2026-10-15 (docs/testing/2026-10-15-persona-admin.md), hard-rule integrity ("100/100 or
explained"):

* M-02: a forced bulk move that creates a room clash kept hard 100 and could be published. Every mutation path
  re-scores the run; forcing needs ``planning.admin`` and a written ``reason``; each forced move is recorded as an
  override (``stats.forced_overrides``, audited) and the publish guard refuses a run whose current evaluation
  breaks a hard rule that no recorded override explains.
* M-09: a manual move put 80 students into a 30-seat room without force: capacity is now a hard move rule.
* M-04: a one-week run replaced the term-wide published timetable: activation of a narrower run answers 409 with
  the weeks it would drop unless ``confirm_scope_reduction``.
* Q8: a request edit pinning more students than the room seats is refused at the edit, unless an administrator
  overrides it with a reason.
* M-07: the imported board's summary said "Sorunlar 0" while the data-issues report listed its too-small locked
  rooms; the summary counts them.

Real Bahar 2026 import (``tests/crbs_env``): the board (one row per week) has parallel Monday classes in different
rooms; MAT 112 is a real planning-list course; B 201 seats 30.
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import Assignment, AuditEvent, Course, MeetingRequest, Room, ScheduleRun, Section
from sqlalchemy import select, update

from tests.crbs_env import env  # noqa: F401


async def _pair(run_id: int) -> tuple[Assignment, Assignment]:
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
                and (a.start_period, a.end_period) == (b.start_period, b.end_period)
                and set(a.weeks or []) & set(b.weeks or [])
            ):
                return a, b
    raise AssertionError("the Bahar board has parallel Monday classes")


async def _unpublish(env) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(ScheduleRun).where(ScheduleRun.id == env.run_id).values(is_active=False))
        await s.commit()


async def test_forced_clash_needs_a_reason_lowers_the_score_and_is_listed_when_published(env):  # noqa: F811
    await _unpublish(env)
    a, b = await _pair(env.run_id)
    base = f"/api/v1/runs/{env.run_id}/assignments"
    move = {"moves": [{"aid": a.id, "room_ids": list(b.room_ids), "scope": "week", "week": 3}], "force": True}
    r = await env.client.post(f"{base}/bulk-move", json=move, headers=env.admin)
    assert r.status_code == 422, r.text
    assert "room_overlap" in str(r.json()["detail"])  # names the rule
    reason = "Bölüm başkanlığı onayı: ortak sınav provası"
    r = await env.client.post(f"{base}/bulk-move", json={**move, "reason": reason}, headers=env.admin)
    assert r.status_code == 200 and r.json()["applied"] is True, r.text
    run = (await env.client.get(f"/api/v1/runs/{env.run_id}", headers=env.admin)).json()
    assert run["hard_score"] < 100
    (ov,) = run["stats"]["forced_overrides"]
    assert ov["reason"] == reason and "room_overlap" in ov["rules"] and a.id in ov["assignment_ids"]
    # explained by a recorded override: publishable only once the planner confirms the listed break (round-1
    # R1-S-01), and the override stays in the report
    r = await env.client.post(f"/api/v1/runs/{env.run_id}/activate", headers=env.admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "forced_breaks", r.text
    assert r.json()["detail"]["breaks"][0]["reason"] == reason
    r = await env.client.post(
        f"/api/v1/runs/{env.run_id}/activate", json={"confirm_forced_breaks": True}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["forced_overrides"][0]["reason"] == reason


async def test_an_unexplained_manual_clash_blocks_publishing(env):  # noqa: F811
    """A clash between planning-list classes that no override explains (e.g. made before overrides existed)."""
    await _unpublish(env)
    async with dbmod.get_session_factory()() as s:
        mrs = list(
            (
                await s.execute(
                    select(MeetingRequest)
                    .join(Section, Section.id == MeetingRequest.section_id)
                    .where(Section.term_id == env.term_id, MeetingRequest.day == 1, MeetingRequest.start_period == 1)
                    .order_by(MeetingRequest.id)
                    .limit(2)
                )
            ).scalars()
        )
        assert len(mrs) == 2
        a101 = env.rooms["A101"]
        run = ScheduleRun(
            term_id=env.term_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"week": 3, "weeks": [3]},
            status="FEASIBLE",
            hard_score=100,
            stats={"manual_edits": 1},
        )
        s.add(run)
        await s.flush()
        for mr in mrs:  # both in A 101 at the same time, the second one moved there by hand
            s.add(
                Assignment(
                    run_id=run.id,
                    meeting_request_id=mr.id,
                    week=3,
                    weeks=[3],
                    day=1,
                    start_period=1,
                    end_period=mr.end_period or 1,
                    room_ids=[a101],
                    origin="MANUAL",
                    is_locked=True,
                )
            )
        await s.commit()
        rid = run.id
    r = await env.client.post(f"/api/v1/runs/{rid}/activate", headers=env.admin)
    assert r.status_code == 409, r.text
    assert any("room" in i for i in r.json()["detail"]["issues"]), r.json()


async def test_manual_move_into_a_too_small_room_is_refused(env):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        b201 = (await s.execute(select(Room).where(Room.code == "B201"))).scalar_one()
        rows = list((await s.execute(select(Assignment).where(Assignment.run_id == env.run_id))).scalars())
    assert b201.capacity == 30
    # a board class with a known enrolment > 30: through its label's course
    big = await _big_class(env, rows, 30)
    url = f"/api/v1/runs/{env.run_id}/assignments/{big.id}/move-preview"
    r = await env.client.post(url, json={"room_ids": [b201.id]}, headers=env.admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is False
    issue = next(i for i in out["items"][0]["hard"] if i["code"] == "capacity")
    assert "sığmaz" in issue["text"]["tr"] and "B 201" in issue["text"]["tr"]


async def _big_class(env, rows, seats):  # type: ignore[no-untyped-def]  # noqa: F811
    from app.services import calendar_views as cv

    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, env.run_id)
        ctx = await cv.load_run_context(s, run)
        for a in rows:
            if a.day == 1 and ctx.size_of(a) > seats:
                return a
    raise AssertionError("the board has Monday classes above 30 students")


async def test_a_week_run_cannot_silently_replace_the_term_timetable(env):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        week = ScheduleRun(
            term_id=env.term_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"week": 3, "weeks": [3]},
            status="OPTIMAL",
            hard_score=100,
            label="Hafta 3",
        )
        s.add(week)
        await s.commit()
        wid = week.id
    r = await env.client.post(f"/api/v1/runs/{wid}/activate", headers=env.planner)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "scope_reduction" and d["new"]["weeks"] == [3] and d["active"]["run_id"] == env.run_id
    assert 4 in d["weeks_lost"] and 3 not in d["weeks_lost"]
    r = await env.client.post(
        f"/api/v1/runs/{wid}/activate", json={"confirm_scope_reduction": True}, headers=env.planner
    )
    assert r.status_code == 200 and r.json()["is_active"] is True, r.text


async def test_request_edit_pinning_too_many_students_is_refused(env):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        b201 = (await s.execute(select(Room).where(Room.code == "B201"))).scalar_one()
        mr, size = (
            await s.execute(
                select(MeetingRequest, Section.enrolment)
                .join(Section, Section.id == MeetingRequest.section_id)
                .join(Course, Course.id == Section.course_id)
                .where(Section.term_id == env.term_id, Course.code == "MAT112", Section.enrolment > 30)
                .order_by(MeetingRequest.id)
            )
        ).first()
    url = f"/api/v1/requests/meetings/{mr.id}"
    r = await env.client.put(url, json={"definitive_room_ids": [b201.id], "status": "LOCKED"}, headers=env.planner)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["message_tr"] == f"{size} öğrenci 30 kişilik B 201'e sığmaz"
    body = {"definitive_room_ids": [b201.id], "status": "LOCKED", "override_reason": "Dönem sonu, yarısı uzaktan"}
    assert (await env.client.put(url, json=body, headers=env.planner)).status_code == 422  # admins only
    r = await env.client.put(url, json=body, headers=env.admin)
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        ev = (
            await s.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "meeting_request.update", AuditEvent.entity_id == str(mr.id)
                )
            )
        ).scalar_one()
    assert ev.reason and "yarısı uzaktan" in ev.reason


async def test_board_summary_counts_its_data_issues(env):  # noqa: F811
    s = (await env.client.get(f"/api/v1/runs/{env.run_id}/summary", headers=env.planner)).json()
    report = (await env.client.get(f"/api/v1/runs/{env.run_id}/data-issues", headers=env.planner)).json()
    assert s["data_issues"]["issues"] == report["totals"]["issues"] > 0
    assert s["data_issues"]["by_group"] == report["totals"]["by_group"]
