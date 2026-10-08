"""Planner usability test 2026-10-08 regressions on the real Bahar 2026 import: U1 (programme/year rule
keys), U3 (pins / upload rules on members of merged joint lectures), U5 (exam scope weeks), U6 (Turkish
dotted İ in course codes), default term."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import ConstraintRow, MeetingRequest, Program, Section
from sqlalchemy import select

from tests import studio_support

bahar = studio_support.bahar


async def _hemsirelik_y1_sections(term_id: int) -> set[int]:
    async with get_session_factory()() as s:
        rows = (
            await s.execute(
                select(Section.id, Section.class_years, Section.class_year)
                .join(Program, Program.id == Section.program_id)
                .join(MeetingRequest, MeetingRequest.section_id == Section.id)
                .where(
                    Section.term_id == term_id,
                    Program.canonical_name == "hemşirelik",
                    MeetingRequest.needs_room.is_(True),
                    MeetingRequest.archived.is_(False),
                    MeetingRequest.start_period.is_not(None),
                )
            )
        ).all()
    return {sid for sid, years, year in rows if 1 in (years or [year])}


async def test_u1_programme_year_template_matches_the_real_nursing_sections(bahar):
    c, h = bahar.client, bahar.planner
    want = await _hemsirelik_y1_sections(bahar.term_id)
    assert len(want) >= 5  # nursing year-1 sections that need a room and have a time (7 sections in all)
    url = "/api/v1/studio/constraints/preview"
    for key in ("PROG:Hemşirelik:Y1", "PROG:HEMŞİRELİK:Y1", "PROG:hemşirelik:Y1"):
        body = {"term_id": bahar.term_id, "kind": "day_window", "params": {"cohorts": [key], "latest": 11}}
        p = (await c.post(url, json=body, headers=h)).json()
        assert p["affected_count"] > 0, (key, p)
    # stored through the CRUD as the studio dropdown sends it -> canonical, and the class list agrees
    r = await c.post(
        "/api/v1/constraints",
        json={"term_id": bahar.term_id, "kind": "day_window", "params": {"cohorts": ["PROG:Hemşirelik:Y1"], "latest": 11}, "hardness": "hard"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["params"]["cohorts"] == ["PROG:hemşirelik:Y1"]
    listed = (
        await c.get(f"/api/v1/terms/{bahar.term_id}/studio/classes", params={"rule_id": r.json()["id"], "limit": 2000}, headers=h)
    ).json()["items"]
    async with get_session_factory()() as s:
        got = {(await s.get(MeetingRequest, it["id"])).section_id for it in listed}
    assert want <= got  # + partners of merged joint lectures (BES 128 + HEM 106 is one lecture)
    # a row written before the fix (display-name key) still matches in the solver input
    async with get_session_factory()() as s:
        from sqlalchemy import update

        await s.execute(
            update(ConstraintRow).where(ConstraintRow.id == r.json()["id"]).values(params={"cohorts": ["PROG:Hemşirelik:Y1"], "latest": 11})
        )
        await s.commit()
        from app.models import ScheduleRun
        from app.services.solver_bridge import build_solver_input
        from app.solver.constraints._common import select_events

        inp, _ = await build_solver_input(s, ScheduleRun(id=-1, term_id=bahar.term_id, kind="COURSE", horizon="TERM", params={}, stats={}))
    rule = next(x for x in inp.constraints if x.id == r.json()["id"])
    assert select_events(inp, rule.params)


async def _merged_member(term_id: int) -> tuple[int, int, dict[int, list[int]]]:
    """(member request id, head event id) of a real merged joint lecture, preferring HEM 106."""
    from app.models import ScheduleRun
    from app.services.solver_bridge import build_solver_input

    from tests.studio_support import meeting_id

    async with get_session_factory()() as s:
        _inp, members = await build_solver_input(
            s, ScheduleRun(id=-1, term_id=term_id, kind="COURSE", horizon="TERM", params={}, stats={})
        )
    hem = await meeting_id("HEM 106")
    for head, ms in members.items():
        if hem in ms and hem != head:
            return hem, head, members
    head, ms = next((h, ms) for h, ms in members.items() if len(ms) > 1)
    return next(m for m in ms if m != head), head, members


async def test_u3_rules_and_pins_on_a_merged_member_reach_its_event(bahar):
    from tests.studio_support import room

    c, h = bahar.client, bahar.planner
    member, head, _members = await _merged_member(bahar.term_id)
    a206, a204 = (await room("A206")).id, (await room("A204")).id
    p = (
        await c.post(
            "/api/v1/studio/constraints/preview",
            json={"term_id": bahar.term_id, "kind": "room_preference", "params": {"event_ids": [member], "room_ids": [a206]}},
            headers=h,
        )
    ).json()
    assert p["affected_count"] >= 2 and member in p["sample"][0]["request_ids"], p  # was 0 ("matches none")
    r = await c.post(
        "/api/v1/constraints",
        json={"term_id": bahar.term_id, "kind": "room_preference", "params": {"event_ids": [member], "room_ids": [a206]}},
        headers=h,
    )
    assert r.status_code == 201, r.text
    d = (await c.get(f"/api/v1/terms/{bahar.term_id}/studio", headers=h)).json()
    r2 = await c.put(
        f"/api/v1/terms/{bahar.term_id}/studio",
        json={"version": d["version"], "pins": [{"event_id": member, "room_ids": [a204]}]},
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    from app.models import StudioDraft
    from app.services import studio as st

    async with get_session_factory()() as s:
        draft = await s.get(StudioDraft, d["draft_id"])
        din = await st.build_draft_input(s, draft)
    ev = next(e for e in din.inp.events if e.id == head)
    assert ev.required_room_ids == frozenset({a204})  # the pin landed on the joint lecture
    rule = next(x for x in din.inp.constraints if x.id == r.json()["id"])
    assert rule.params["event_ids"] == [head]
