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
        json={
            "term_id": bahar.term_id,
            "kind": "day_window",
            "params": {"cohorts": ["PROG:Hemşirelik:Y1"], "latest": 11},
            "hardness": "hard",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["params"]["cohorts"] == ["PROG:hemşirelik:Y1"]
    listed = (
        await c.get(
            f"/api/v1/terms/{bahar.term_id}/studio/classes",
            params={"rule_id": r.json()["id"], "limit": 2000},
            headers=h,
        )
    ).json()["items"]
    async with get_session_factory()() as s:
        got = {(await s.get(MeetingRequest, it["id"])).section_id for it in listed}
    assert want <= got  # + partners of merged joint lectures (BES 128 + HEM 106 is one lecture)
    # a row written before the fix (display-name key) still matches in the solver input
    async with get_session_factory()() as s:
        from sqlalchemy import update

        await s.execute(
            update(ConstraintRow)
            .where(ConstraintRow.id == r.json()["id"])
            .values(params={"cohorts": ["PROG:Hemşirelik:Y1"], "latest": 11})
        )
        await s.commit()
        from app.models import ScheduleRun
        from app.services.solver_bridge import build_solver_input
        from app.solver.constraints._common import select_events

        inp, _ = await build_solver_input(
            s, ScheduleRun(id=-1, term_id=bahar.term_id, kind="COURSE", horizon="TERM", params={}, stats={})
        )
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
            json={
                "term_id": bahar.term_id,
                "kind": "room_preference",
                "params": {"event_ids": [member], "room_ids": [a206]},
            },
            headers=h,
        )
    ).json()
    assert p["affected_count"] >= 2 and member in p["sample"][0]["request_ids"], p  # was 0 ("matches none")
    r = await c.post(
        "/api/v1/constraints",
        json={
            "term_id": bahar.term_id,
            "kind": "room_preference",
            "params": {"event_ids": [member], "room_ids": [a206]},
        },
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


def test_u6_course_codes_fold_the_dotted_capital_i():
    from app.importers.normalize import canon_course_code, extract_course_codes

    assert canon_course_code("BİF111") == canon_course_code("BIF111") == canon_course_code("bif 111") == "BIF111"
    assert extract_course_codes("ATA112, TUR112, İNG112") == ["ATA112", "TUR112", "ING112"]  # real Final row 67
    assert canon_course_code("MİK 502") == "MIK502" and canon_course_code("ÇEV 101") == "ÇEV101"


async def test_u5_u6_final_term_scope_and_codes(client):
    from app.importers.exam_list import import_exam_list
    from app.importers.weekly_grid import import_weekly_grid
    from app.models import Course, ExamRequest, Term

    from tests.api_fixtures import login
    from tests.conftest import EXAM_LIST, FINAL_GRID

    async with get_session_factory()() as s:
        await import_weekly_grid(s, FINAL_GRID, "2026-FINAL", year=2026, term_kind="FINAL")
        await import_exam_list(s, EXAM_LIST, "2026-FINAL")
    async with get_session_factory()() as s:
        term = (await s.execute(select(Term).where(Term.code == "2026-FINAL"))).scalar_one()
        assert term.week_count == 3
        codes = list((await s.execute(select(Course.code))).scalars())
        assert codes and not [c for c in codes if "İ" in c]  # U6
        ing212 = (await s.execute(select(ExamRequest).where(ExamRequest.source_row_index == 68))).scalar_one()
        assert ing212.course_code == "ING212"
    h = await login(client)
    url = f"/api/v1/terms/{term.id}/studio"
    d = (await client.get(url, params={"kind": "EXAM"}, headers=h)).json()
    assert d["scope"]["weeks"] == [1, 2, 3]  # was 1..14
    sm = (await client.get(f"{url}/summary", params={"kind": "EXAM"}, headers=h)).json()
    assert sm["weeks"] == [1, 2, 3] and sm["counts"]["weeks"] == 3  # was [-2, 1, ..., 14]
    assert "-2" not in sm["human_summary"]["tr"] and "1-3. sınav haftalarında" in sm["human_summary"]["tr"]
    events, requests = sm["counts"]["events"], sm["counts"]["classes_in"]
    assert f"{events:,}".replace(",", ".") + " sınavı" in sm["human_summary"]["tr"] and events < requests
    assert any(w["code"] == "exams_outside_term" for w in sm["warnings"])  # the 13 May exams are reported


async def test_default_term_is_todays_term_not_the_last_imported(client, monkeypatch):
    from datetime import date

    from app.services import terms as terms_svc

    from tests.api_fixtures import login

    h = await login(client)
    for code, start, weeks in (
        ("2026-BAHAR", "2026-02-02", 14),
        ("2026-FINAL", "2026-06-01", 3),
        ("2026-2027-GUZ", "2026-09-28", 14),
    ):
        r = await client.post("/api/v1/terms", json={"code": code, "start_date": start, "week_count": weeks}, headers=h)
        assert r.status_code == 201, r.text
    for today, want in (
        (date(2026, 3, 10), "2026-BAHAR"),
        (date(2026, 6, 3), "2026-FINAL"),
        (date(2026, 10, 8), "2026-2027-GUZ"),
        (date(2026, 5, 20), "2026-FINAL"),
    ):
        monkeypatch.setattr(terms_svc, "today", lambda d=today: d)
        listed = (await client.get("/api/v1/terms", headers=h)).json()
        assert listed[0]["code"] == want and listed[0]["is_current"], (today, [t["code"] for t in listed])
        assert sum(t["is_current"] for t in listed) == 1
        assert (await client.get("/api/v1/terms/current", headers=h)).json()["code"] == want
        assert (await client.get("/api/v1/dashboard", headers=h)).json()["term"]["code"] == want
