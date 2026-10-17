"""Flow loop round 1, lane F (docs/ROADMAP.md "Flow loop tickets — round 1", ``rounds/round-1-tickets.json``):
the dashboard and the learning memory, on the real 2026 Bahar / Güz fixtures.

* T-R1-39: with the imported Güz board published (weeks 1-2 of the weekly grid), the dashboard's room use is the
  heatmap's "Genel doluluk" of the same week, never 0 % because today's week lies outside the board.
* T-R1-40: the F-06 academician's A-block habit (8/8 over Bahar + Güz) is a suggestible prior that Güz hides
  because every one of their Güz classes already holds its room (plan drift, not a product bug), and becomes an
  open card where their classes still need rooms; cross-season evidence never yields a room-level preference.
* T-R1-41: the learning memory names people by title + initials, never ``#<id>``.
"""

from __future__ import annotations

from datetime import date

from app.core.db import get_session_factory
from app.models import ConstraintRow, Course, Instructor, ScheduleRun, Section, SectionInstructor, Term
from app.services import learning
from app.services.dashboard import build_dashboard
from sqlalchemy import select

from tests.api_fixtures import login
from tests.test_api_runs import _import_guz, publish_directly
from tests.test_p19_learning import API, _next_bahar, _pick, _suggestions, env  # noqa: F401

TODAY = date(2026, 10, 16)  # Güz 2026-27 week 4: the imported board covers weeks 1 and 2 only


async def _publish_board(term_id: int) -> int:
    async with get_session_factory()() as s:
        board = (
            await s.execute(select(ScheduleRun).where(ScheduleRun.term_id == term_id, ScheduleRun.kind == "COURSE"))
        ).scalar_one()
    await publish_directly(board.id)
    return board.id


# --------------------------------------------------------------------------------------------------
# T-R1-39: the dashboard reads the published board like the heatmap does
# --------------------------------------------------------------------------------------------------


async def test_t_r1_39_dashboard_room_use_equals_the_heatmap_on_a_published_board(client):
    h = await login(client)
    term_id = await _import_guz()
    board = await _publish_board(term_id)

    # default week: today is week 4, the board covers 1-2 -> the closest week the board occupies, not 0 %
    async with get_session_factory()() as s:
        term = await s.get(Term, term_id)
        assert term is not None
        d = await build_dashboard(s, term, today=TODAY)
    assert d["current_week"] == 4 and d["utilisation_week"] == 2
    assert d["active_run_id"] == board and d["utilisation_run_id"] == board
    assert d["utilisation"] > 0.15

    for week in (1, 2):
        dash = (await client.get("/api/v1/dashboard", params={"term_id": term_id, "week": week}, headers=h)).json()
        heat = (
            await client.get("/api/v1/analytics/heatmap/rooms", params={"term_id": term_id, "week": week}, headers=h)
        ).json()
        assert heat["source"] == "board" and [r["run_id"] for r in heat["runs"]] == [board]
        overall = heat["overall"]["total"]["pct"]  # "Genel doluluk %24,1"
        assert overall > 15
        assert abs(100 * dash["utilisation"] - overall) <= 0.5, (week, dash["utilisation"], overall)
        # the building bars use the same definition: every building row is the heatmap's row
        rows = {r["key"]: r["total"]["pct"] for r in heat["rows"]}
        for b in dash["utilisation_by_building"]:
            assert abs(100 * b["utilisation"] - rows[b["building"]]) <= 0.5, (b, rows)
        assert dash["blocks_week"] == heat["counted"]["blocks"] > 0

    # a week the board does not cover reads 0 % honestly (the user picked it), still with the board's id
    d4 = (await client.get("/api/v1/dashboard", params={"term_id": term_id, "week": 4}, headers=h)).json()
    assert d4["utilisation_week"] == 4 and d4["utilisation"] == 0 and d4["active_run_id"] == board


# --------------------------------------------------------------------------------------------------
# T-R1-40: the linked academician's A-block habit, and cross-season evidence never names rooms
# --------------------------------------------------------------------------------------------------


async def _primary_of(term_id: int, course: str) -> int:
    async with get_session_factory()() as s:
        q = (
            select(SectionInstructor.instructor_id)
            .join(Section, Section.id == SectionInstructor.section_id)
            .join(Course, Course.id == Section.course_id)
            .where(Section.term_id == term_id, Course.display_code == course, SectionInstructor.role == "PRIMARY")
        )
        return int((await s.execute(q)).scalars().first())


async def test_t_r1_40_a_block_habit_is_a_hidden_prior_in_roomed_guz_and_a_card_where_rooms_are_open(env):  # noqa: F811
    # P1 of F-06 (ACADEMICIAN_INSTRUCTOR_ID 157 on the full stack): the PSY 277 instructor, A block in every
    # roomed class of Bahar and Güz. In Güz every one of their classes already holds its definitive room (the
    # planning list's "kesinleşen derslik"), so the habit is suggestible but has no class left to target.
    p1 = await _primary_of(env.guz, "PSY 277")
    guz = await _suggestions(env, env.guz, person_id=p1, state="all", limit=1000)
    a = _pick(guz, "instructor", "building")
    assert a["value"] == "A" and a["proposal"]["kind"] == "building_preference"
    assert a["support"]["seen_terms"] == 2 and a["support"]["rows"] == a["support"]["total"] >= 6, a["support"]
    assert a["confidence"] >= 0.8 and a["cross_season"] is True
    assert a["state"] == "hidden" and a["hidden_reason"] == "room_already_set"
    assert a["impact"]["request_ids"] == [] and len(a["impact"]["covered_request_ids"]) >= 4

    # the same person's classes in a new Bahar without rooms: an open building card with 2-term evidence, and no
    # card that names a room (L2: a building at most from other-season data)
    term, _ = await _next_bahar(["PSI 214", "PSY 214", "PSY 278"])
    nxt = await _suggestions(env, term, person_id=p1, state="all", limit=1000)
    card = _pick(nxt, "instructor", "building")
    assert card["value"] == "A" and card["state"] == "open" and card["support"]["seen_terms"] == 2
    assert "2 dönemdir" in card["explanation"]["tr"] and "A Blok'ta" in card["explanation"]["tr"]
    assert not [i for i in nxt if i["proposal"]["kind"] == "room_preference" and i["cross_season"]]


async def test_t_r1_40_cross_season_evidence_never_yields_a_room_preference(env):  # noqa: F811
    r = await env.client.post(f"{API}/learning/refresh", json={"term_id": env.guz}, headers=env.admin)
    assert r.status_code in (200, 202), r.text
    for term in (env.guz, env.bahar):
        items = await _suggestions(env, term, state="all", limit=1000)
        assert items, term
        bad = [
            (i["subject"]["label"], i["attribute"], i["value"])
            for i in items
            if i["cross_season"] and i["proposal"]["kind"] not in ("building_preference",)
        ]
        assert bad == [], bad
        # a room-feature (PC lab) card rests on same-season evidence only: its proposal names the tagged rooms
        for i in items:
            if i["attribute"] == "tag":
                assert {t["term_id"] for t in i["evidence"]["terms"]} == {term}, i["evidence"]["terms"]


# --------------------------------------------------------------------------------------------------
# T-R1-41: people are named by title + initials in the reset rows and in the stored rule text
# --------------------------------------------------------------------------------------------------


async def test_t_r1_41_reset_rows_and_stored_explanations_name_the_person_by_initials(env):  # noqa: F811
    term, _ = await _next_bahar(["PSI 214", "PSY 214", "PSY 278"])
    p1 = await _primary_of(env.guz, "PSY 277")
    async with get_session_factory()() as s:
        ins = await s.get(Instructor, p1)
        assert ins is not None
        masked = learning.masked_person(ins.title, ins.full_name)
    assert masked and ins.full_name not in masked and masked.endswith(".") and "#" not in masked

    # accept the building card: the stored rule explanation uses the initials, not "öğretim elemanı #<id>"
    card = _pick(await _suggestions(env, term, person_id=p1), "instructor", "building")
    r = await env.client.post(f"{API}/learning/suggestions/{card['id']}/accept", json={}, headers=env.planner)
    assert r.status_code == 201, r.text
    async with get_session_factory()() as s:
        row = await s.get(ConstraintRow, r.json()["constraint_id"])
        assert row is not None
        stored = f"{row.nl_text} {row.source_ref}"
    assert masked in stored and f"#{p1}" not in stored and ins.full_name not in stored

    # the reset row says who it was about, as initials
    body = {"scope": "person", "value": p1, "reason": "görev değişikliği"}
    r = await env.client.post(f"{API}/learning/reset", json=body, headers=env.admin)
    assert r.status_code == 201, r.text
    assert r.json()["subject_label"] == masked
    rows = (await env.client.get(f"{API}/learning/resets", headers=env.admin)).json()
    assert rows[0]["scope"] == "person" and rows[0]["subject_label"] == masked
    undone = (await env.client.post(f"{API}/learning/resets/{rows[0]['id']}/undo", headers=env.admin)).json()
    assert undone["subject_label"] == masked
    # scopes without a person carry no label
    r = await env.client.post(f"{API}/learning/reset", json={"scope": "all", "reason": "yeni yıl"}, headers=env.admin)
    assert r.status_code == 201, r.text
    assert r.json()["subject_label"] is None
