"""Phase 19 moderation backend (P19-M1..M3) on the real 2026 Bahar + 2026-27 Güz planning lists.

The module builds one database (Güz and Bahar lists + room master, the importers' own path) and one published
Bahar week-3 run solved like ``POST /runs`` with ``publish_candidate`` (one CP-SAT worker, deterministic); every
test works on a copy. Real rows (1-based ``Sayfa1`` rows of ``bahar_derslik_planlama_listesi_v5.xlsx``):

* R545 PHAR 240 §1, Mon 08:30-10:50, 80 students, definitive A 206 (LOCKED);
* R49 PHY 102 §1, Fri P3-P4, request "D 204", definitive D 202 (academician needs M2: a planner decision with no
  reason);
* R381 ENG 106 §2, Wed P1-P2, definitive B 203 / B 205;
* R1156 PHAR 114 §2, Tue P4-P5, definitive A 306 / C 602;
* R2 + R1001 MAT 112 §1 (one lecture listed twice) and R1022 HEM 236, both locked to A 204 on Thursday at
  overlapping times (13:30-16:00 vs 15:10-16:40): only one can hold the room (priority-policy spec §4).
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.models import (
    AuditEvent,
    Base,
    ConstraintRow,
    Instructor,
    MeetingRequest,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
)
from app.services.seed import seed_admin
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.api_fixtures import login
from tests.conftest import BAHAR_LIST, FIXTURES, GUZ_LIST
from tests.crbs_support import make_user

ROWS = {"phar240": 545, "phy102": 49, "eng106_2": 381, "eng106": 279, "phar114_2": 1156, "hem236": 1022, "mat112": 2}
_CACHE: dict[str, Any] = {}


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("p19_moderation")


async def _build(workdir: Path) -> tuple[Path, dict[str, Any]]:
    if "db" in _CACHE:
        return _CACHE["db"], _CACHE["ids"]
    from app.importers.planning_list import import_planning_list
    from app.importers.room_master import import_room_master
    from app.services.solver_bridge import run_schedule

    db = workdir / "bahar_guz.db"
    eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{db}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = dbmod.get_session_factory()
    async with factory() as s:
        await import_planning_list(s, GUZ_LIST, "2026-GUZ")
        await import_planning_list(s, BAHAR_LIST, "2026-BAHAR")
        await import_room_master(s, FIXTURES / "room_master.csv")
        await s.commit()
    async with factory() as s:
        bahar = (await s.execute(select(Term).where(Term.code == "2026-BAHAR"))).scalar_one()
        run = ScheduleRun(
            term_id=bahar.id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"weeks": [3]},
            params={"time_limit_s": 30.0, "seed": 0, "solver": "cpsat", "publish_candidate": True, "workers": 8},
            label="Bahar week 3 (published)",
        )
        s.add(run)
        await s.commit()
        run_id, term_id = run.id, bahar.id
    await run_schedule(factory, run_id)
    async with factory() as s:
        run = await s.get(ScheduleRun, run_id)
        assert run is not None and run.status in ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"), run.status
        run.is_active = True
        rows = (
            await s.execute(
                select(MeetingRequest.source_row_index, MeetingRequest.id)
                .join(Section, Section.id == MeetingRequest.section_id)
                .where(Section.term_id == term_id, MeetingRequest.source_row_index.in_(list(ROWS.values())))
            )
        ).all()
        by_row = {int(r): int(i) for r, i in rows}
        ids: dict[str, Any] = {k: by_row[v] for k, v in ROWS.items()}
        ids["mat112_twin"] = (
            await s.execute(
                select(MeetingRequest.id)
                .join(Section, Section.id == MeetingRequest.section_id)
                .where(Section.term_id == term_id, MeetingRequest.source_row_index == 1001)
            )
        ).scalar_one()
        # the A 204 lock clash: exactly one of the two keeps the room in the published run (which one depends on
        # the policy's tie-break: more classes / weeks, then the larger class); the tests follow the data
        unplaced = set(run.stats.get("unplaced_ids") or [])
        mat_out = bool({ids["mat112"], ids["mat112_twin"]} & unplaced)
        assert mat_out != (ids["hem236"] in unplaced), unplaced
        ids["loser"], ids["winner"] = (ids["mat112"], ids["hem236"]) if mat_out else (ids["hem236"], ids["mat112"])
        ids["loser_label"], ids["winner_label"] = ("MAT 112 §1", "HEM 236") if mat_out else ("HEM 236", "MAT 112 §1")
        for key in ("phar240", "phy102", "hem236", "loser"):
            ids[f"ins_{key}"] = (
                await s.execute(
                    select(SectionInstructor.instructor_id)
                    .join(MeetingRequest, MeetingRequest.section_id == SectionInstructor.section_id)
                    .where(MeetingRequest.id == ids[key], SectionInstructor.role == "PRIMARY")
                )
            ).scalar_one()
        ids.update(run_id=run_id, term_id=term_id, base_stats=dict(run.stats or {}), base_hard=run.hard_score)
        ids["guz_id"] = (await s.execute(select(Term.id).where(Term.code == "2026-GUZ"))).scalar_one()
        await s.commit()
    await dbmod.dispose_engine()
    _CACHE["db"], _CACHE["ids"] = db, ids
    return db, ids


@pytest.fixture
async def real(workdir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    """An API client on a private copy of the real database, plus the ids of the rows above."""
    base, ids = await _build(workdir)
    path = tmp_path / "api.db"
    shutil.copyfile(base, path)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
    qmod.reset_queue()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        admin = await login(c)
        yield {"client": c, "admin": admin, **ids}
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


def _item(items: list[dict[str, Any]], rid: int) -> dict[str, Any]:
    return next(it for it in items if it["request_id"] == rid)


# ------------------------------------------------------------------------------------------- M1 read models


async def test_history_lists_requested_definitive_and_assigned_across_terms(real: dict[str, Any]) -> None:
    c, h = real["client"], real["admin"]
    r = await c.get(f"/api/v1/moderation/people/{real['ins_phar240']}/history", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    groups = {g["term_code"]: g for g in body["terms"]}
    # the person teaches in both terms; the newest term comes first (Güz 2026-27 after Bahar 2026)
    assert [g["term_code"] for g in body["terms"]] == ["2026-GUZ", "2026-BAHAR"]
    bahar, guz = groups["2026-BAHAR"], groups["2026-GUZ"]
    assert bahar["source"] == "run" and bahar["run"]["id"] == real["run_id"] and bahar["run"]["published"]
    assert guz["source"] == "planner" and guz["run"] is None
    it = _item(bahar["items"], real["phar240"])
    assert it["course_code"] == "PHAR 240" and it["section"] == "1" and it["role"] == "PRIMARY"
    # requested (raw cell + parsed), definitive, assigned
    assert it["raw"]["room_text"] == "Derslik" and it["raw"]["row"] == 545
    assert (it["parsed"]["day"], it["parsed"]["start_period"], it["parsed"]["end_period"]) == (1, 1, 3)
    assert it["parsed"]["start_time"] == "08:30:00"
    assert it["definitive"]["rooms"] == ["A 206"]
    assert it["assigned"]["rooms"] == ["A 206"] and it["assigned"]["day"] == 1
    assert it["assigned"]["time"] == "08:30–10:50" and 3 in it["assigned"]["weeks"]
    assert it["verdict"] == "satisfied" and it["satisfied"]["day"] is True and it["satisfied"]["period"] is True
    assert it["satisfied"]["room"] is None  # "Derslik" names no room
    assert it["planner_edits"] == []
    # Güz: no published run, the planner's definitive rooms stand in, labelled as such
    assert guz["items"] and all(x["source"] == "planner" for x in guz["items"])
    assert any(x["definitive"]["rooms"] and x["assigned"] for x in guz["items"])
    assert body["accessibility"] in ("yes", "no")
    # term filter by code (Turkish-insensitive) and by id
    r = await c.get(f"/api/v1/moderation/people/{real['ins_phar240']}/history?terms=2026-bahar", headers=h)
    assert [g["term_code"] for g in r.json()["terms"]] == ["2026-BAHAR"]
    r = await c.get(f"/api/v1/moderation/people/{real['ins_phar240']}/history?terms={real['guz_id']}", headers=h)
    assert [g["term_code"] for g in r.json()["terms"]] == ["2026-GUZ"]


async def test_history_shows_planner_edits_and_linked_bookings(real: dict[str, Any]) -> None:
    """A request edited through PUT /requests/meetings (snapshot of the imported values + audit event) and a
    booking of the linked user both appear in the person's history."""
    c, h = real["client"], real["admin"]
    rid = real["phy102"]
    r = await c.put(f"/api/v1/requests/meetings/{rid}", json={"requested_capacity": 90}, headers=h)
    assert r.status_code == 200, r.text
    r = await c.get(f"/api/v1/moderation/people/{real['ins_phy102']}/history?terms=2026-BAHAR", headers=h)
    it = _item(r.json()["terms"][0]["items"], rid)
    kinds = {e["kind"] for e in it["planner_edits"]}
    assert "audit" in kinds, it["planner_edits"]
    assert any(e.get("action") == "meeting_request.update" for e in it["planner_edits"])


async def test_people_rows_rate_badge_and_search(real: dict[str, Any]) -> None:
    c, h = real["client"], real["admin"]
    r = await c.get(f"/api/v1/terms/{real['term_id']}/moderation/people", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == real["run_id"] and body["visibility"] == "all" and body["total"] > 300
    row = next(p for p in body["items"] if p["id"] == real["ins_phar240"])
    assert row["sections"] >= 1 and row["requests"] >= row["sections"]
    assert 0 <= (row["match_rate"] or 0) <= 1
    assert row["accessibility"] in ("yes", "no") and set(row) >= {
        "active_preferences",
        "learned_priors",
        "unsatisfied_streak",
        "badge",
        "counts",
    }
    # the lecturer of the class that lost the A 204 lock clash: at least one unplaced request
    lost = next(p for p in body["items"] if p["id"] == real["ins_loser"])
    assert lost["counts"]["unplaced"] >= 1 and lost["unsatisfied_streak"] >= 1
    # sorted by unmet requests first
    unmet = [p["counts"]["unplaced"] + p["counts"]["not_as_requested"] + p["counts"]["partial"] for p in body["items"]]
    assert unmet == sorted(unmet, reverse=True)
    # search by course code, Turkish-insensitive
    r = await c.get(f"/api/v1/terms/{real['term_id']}/moderation/people?q=phar 240", headers=h)
    assert real["ins_phar240"] in {p["id"] for p in r.json()["items"]}


async def test_matchings_flags_on_known_rows(real: dict[str, Any]) -> None:
    c, h = real["client"], real["admin"]
    r = await c.get(f"/api/v1/terms/{real['term_id']}/moderation/matchings", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == real["run_id"] and body["planner_check"]["violations"] == 0
    items = body["items"]
    phar = _item(items, real["phar240"])
    assert phar["verdict"] == "satisfied" and phar["assigned"]["rooms"] == ["A 206"]
    assert phar["findings"] == [] and phar["placement_status"] == "placed"
    eng2 = _item(items, real["eng106_2"])
    assert sorted(eng2["assigned"]["rooms"]) == ["B 203", "B 205"] and eng2["verdict"] == "satisfied"
    phar114 = _item(items, real["phar114_2"])
    assert sorted(phar114["assigned"]["rooms"]) == ["A 306", "C 602"] and phar114["verdict"] == "satisfied"
    # PHY 102 asked for D 204 and the planner gave D 202: building kept, room not; no reason was recorded
    phy = _item(items, real["phy102"])
    assert phy["requested"]["rooms"] == ["D 204"] and phy["assigned"]["rooms"] == ["D 202"]
    assert phy["satisfied"]["room"] is False and phy["satisfied"]["building"] is True
    assert phy["verdict"] == "partial" and phy["reason"]["code"] == "planner_decision"
    assert phy["reason"]["text"]["tr"] == "Karşılanmadı: planlama birimi kararı (gerekçe girilmemiş)"
    # MAT 112 §1 and HEM 236 hold A 204 at once (two locks, one room): step 1 of the policy, the winner named
    lost = _item(items, real["loser"])
    assert lost["verdict"] == "unplaced" and lost["assigned"] is None
    assert lost["reason"]["policy_step"]["step"] == 1
    assert any(x["label"] == real["winner_label"] for x in lost["reason"]["culprits"])
    assert lost["reason"]["text"]["tr"] and lost["reason"]["text"]["en"]
    assert _item(items, real["winner"])["verdict"] == "satisfied"
    assert body["counts"]["satisfied"] > 400 and body["counts"]["unplaced"] >= 1
    # filters
    r = await c.get(f"/api/v1/terms/{real['term_id']}/moderation/matchings?verdict=unplaced&check=false", headers=h)
    assert {it["verdict"] for it in r.json()["items"]} == {"unplaced"}
    r = await c.get(f"/api/v1/terms/{real['term_id']}/moderation/matchings?q=PHY 102&check=false", headers=h)
    assert {it["course_code"] for it in r.json()["items"]} == {"PHY 102"}
    # detail = the matching + calendar_views.class_detail (raw planning-list row, checks, run history)
    r = await c.get(f"/api/v1/terms/{real['term_id']}/moderation/matchings/{real['phar240']}", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["verdict"] == "satisfied" and d["detail"]["raw_row"] and d["detail"]["history"]


async def test_visibility_academician_own_viewer_all_unlinked_403(real: dict[str, Any]) -> None:
    c, admin = real["client"], real["admin"]
    tid, own, other = real["term_id"], real["ins_phar240"], real["ins_phy102"]
    uid, teacher = await make_user(c, admin, "akademisyen@uni.edu.tr", role="TEACHER")
    async with dbmod.get_session_factory()() as s:
        ins = await s.get(Instructor, own)
        assert ins is not None
        ins.user_id = uid
        await s.commit()
    r = await c.get(f"/api/v1/terms/{tid}/moderation/people", headers=teacher)
    assert r.status_code == 200, r.text
    assert [p["id"] for p in r.json()["items"]] == [own] and r.json()["visibility"] == "own"
    assert r.json()["items"][0]["linked_user"] is True
    assert (await c.get(f"/api/v1/moderation/people/{own}/history", headers=teacher)).status_code == 200
    assert (await c.get(f"/api/v1/moderation/people/{other}/history", headers=teacher)).status_code == 403
    r = await c.get(f"/api/v1/terms/{tid}/moderation/matchings?check=false", headers=teacher)
    assert r.status_code == 200 and r.json()["items"]
    assert all(own in {i["id"] for i in it["instructors"]} for it in r.json()["items"])
    r = await c.get(f"/api/v1/terms/{tid}/moderation/matchings/{real['phy102']}", headers=teacher)
    assert r.status_code == 403
    # the academician cannot edit priorities or re-solve
    r = await c.put(f"/api/v1/moderation/requests/{real['phar240']}/priority", json={"priority": 1}, headers=teacher)
    assert r.status_code == 403
    # a TEACHER without a linked instructor record sees nothing
    _uid2, stranger = await make_user(c, admin, "misafir@uni.edu.tr", role="TEACHER")
    assert (await c.get(f"/api/v1/terms/{tid}/moderation/people", headers=stranger)).status_code == 403
    assert (await c.get(f"/api/v1/moderation/people/{own}/history", headers=stranger)).status_code == 403
    # a Viewer (planning.view) sees every person (department scope: TODO in moderation.visibility)
    _uid3, viewer = await make_user(c, admin, "izleyici@uni.edu.tr", role="VIEWER")
    r = await c.get(f"/api/v1/terms/{tid}/moderation/people", headers=viewer)
    assert r.status_code == 200 and r.json()["total"] > 300 and r.json()["visibility"] == "all"
    assert (
        await c.post(
            f"/api/v1/terms/{tid}/moderation/resolve",
            json={"base_run_id": real["run_id"], "changed_request_ids": [real["loser"]]},
            headers=viewer,
        )
    ).status_code == 403


# ------------------------------------------------------------------------------------------- M2 priorities


async def test_priority_is_persisted_audited_and_decides_the_real_lock_clash(real: dict[str, Any]) -> None:
    from app.services.solver_bridge import build_solver_input
    from app.solver.cpsat import solve

    c, h = real["client"], real["admin"]
    loser, winner, mat, twin = real["loser"], real["winner"], real["mat112"], real["mat112_twin"]
    r = await c.put(
        f"/api/v1/moderation/requests/{loser}/priority", json={"priority": "yüksek", "note": "Q5"}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.json()["priority"] == 1 and r.json()["effective"] == {"value": 1, "source": "request"}
    bad = await c.put(f"/api/v1/moderation/requests/{loser}/priority", json={"priority": 500}, headers=h)
    assert bad.status_code == 422
    async with dbmod.get_session_factory()() as s:
        mr = await s.get(MeetingRequest, winner)
        assert mr is not None
        winner_section = mr.section_id
    r = await c.put(f"/api/v1/moderation/sections/{winner_section}/priority", json={"priority": -1}, headers=h)
    assert r.status_code == 200 and r.json() == {"section_id": winner_section, "priority": -1, "previous": 0}
    async with dbmod.get_session_factory()() as s:
        acts = [(a, b) for a, b in (await s.execute(select(AuditEvent.action, AuditEvent.after))).all()]
        assert ("meeting_request.priority", {"priority": 1}) in acts
        assert ("section.priority", {"priority": -1}) in acts
        probe = ScheduleRun(term_id=real["term_id"], kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]})
        inp, members = await build_solver_input(s, probe)
        head_of = {m: hd for hd, ms in members.items() for m in ms}
        assert head_of[mat] == head_of[twin]  # MAT 112 §1 listed twice (two programmes) is one event
        lev, wev = head_of.get(loser, loser), head_of.get(winner, winner)
        prio = {e.id: e.priority for e in inp.events}
        # the joint MAT 112 event takes the highest of its two sections' priorities
        assert prio[lev] == 1 and prio[wev] == (0 if winner == mat else -1)
        assert probe.stats["relaxation_policy"]["stored_priorities"] >= 2
        # the run param still overrides the stored value per request (experiments, counterfactual runs)
        probe2 = ScheduleRun(
            term_id=real["term_id"],
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"weeks": [3]},
            params={"priorities": {str(loser): -5, **({str(twin): -5} if loser == mat else {})}},
        )
        inp2, _m = await build_solver_input(s, probe2)
        assert {e.id: e.priority for e in inp2.events}[lev] == -5
        a204 = (await s.execute(select(Room.id).where(Room.code == "A204"))).scalar_one()
    # the two real locks alone on A 204: the higher priority is placed (lock_first, priority decides the clash)
    by_id = {e.id: e for e in inp.events}
    sub = replace(
        inp,
        events=(by_id[lev], by_id[wev]),
        rooms=tuple(r for r in inp.rooms if r.id == a204),
        constraints=(),
        blocks=(),
        previous=(),
        time_limit_s=20.0,
    )
    won = solve(sub)
    assert [a.event_id for a in won.assignments] == [lev] and won.hard_score == 100
    # and the other way round: the priority, not the data order, decides
    flipped = solve(replace(sub, events=(replace(by_id[lev], priority=-1), replace(by_id[wev], priority=1))))
    assert [a.event_id for a in flipped.assignments] == [wev] and flipped.hard_score == 100


# ------------------------------------------------------------------------------------------- M3 re-solve


async def _resolve(c: AsyncClient, h: dict[str, str], tid: int, body: dict[str, Any]) -> dict[str, Any]:
    r = await c.post(f"/api/v1/terms/{tid}/moderation/resolve", json={"wait": True, **body}, headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _stable(diff: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in diff.items() if k not in ("run_id",)}


async def test_resolve_after_one_edit_moves_only_the_neighbourhood_and_is_deterministic(real: dict[str, Any]) -> None:
    c, h, tid, base = real["client"], real["admin"], real["term_id"], real["run_id"]
    loser, winner = real["loser"], real["winner"]
    r = await c.put(f"/api/v1/moderation/requests/{loser}/priority", json={"priority": "high"}, headers=h)
    assert r.status_code == 200
    body = {"base_run_id": base, "changed_request_ids": [loser], "mode": "repair", "time_limit_s": 30}
    d1 = await _resolve(c, h, tid, body)
    assert d1["ready"] and d1["base_run_id"] == base and d1["workers"] == 1 and not d1["is_active"]
    assert d1["status"] in ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL") or d1["diagnosis"]
    assert d1["scores"]["hard"]["after"] == 100, d1["diagnosis"]
    # the class that lost A 204 (now high priority) takes it; the other gives way, the reason names the step
    assert loser in {x["request_id"] for x in d1["newly_placed"]}
    lost = {x["request_id"]: x for x in d1["unplaceable"] if x["was_placed"]}
    assert winner in lost and lost[winner]["reason"]["policy_step"]["step"] == 2
    assert lost[winner]["reason"]["policy_reason"] == "lock_clash_priority"
    # Q9: nothing outside the edit moves unless it had to; every move names its cause
    assert d1["counts"]["moved_unexplained"] == 0
    for m in d1["moved"]:
        assert m["causes"] and (m["in_scope"] or m["causes"][0].get("request_id")), m
    assert d1["counts"]["unchanged"] > 600 and d1["counts"]["moved"] <= 10
    assert d1["neighbourhood"]["freed"] < 100
    assert d1["waived_rules"] == list(real["base_stats"].get("waived_rules") or [])
    # never activated: the published run is still the base
    async with dbmod.get_session_factory()() as s:
        child = await s.get(ScheduleRun, d1["run_id"])
        assert child is not None and not child.is_active and child.parent_run_id == base
        assert child.params["workers"] == 1 and child.params["moderation"]["mode"] == "repair"
        assert (await s.get(ScheduleRun, base)).is_active  # type: ignore[union-attr]
    # the same edit again: the identical diff
    d2 = await _resolve(c, h, tid, body)
    assert _stable(d2) == _stable(d1)
    r = await c.get(f"/api/v1/moderation/runs/{d1['run_id']}/diff", headers=h)
    assert _stable(r.json()) == _stable(d1)
    # publishing goes through the existing activate guard
    r = await c.post(f"/api/v1/runs/{d1['run_id']}/activate", headers=h)
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        assert not (await s.get(ScheduleRun, base)).is_active  # type: ignore[union-attr]


async def test_resolve_refusals_and_the_guard_on_unfinished_children(real: dict[str, Any]) -> None:
    c, h, tid, base = real["client"], real["admin"], real["term_id"], real["run_id"]
    r = await c.post(f"/api/v1/terms/{tid}/moderation/resolve", json={"base_run_id": base, "mode": "repair"}, headers=h)
    assert r.status_code == 422  # a repair names its changed requests
    r = await c.post(
        f"/api/v1/terms/{real['guz_id']}/moderation/resolve",
        json={"base_run_id": base, "changed_request_ids": [real["loser"]]},
        headers=h,
    )
    assert r.status_code == 422
    r = await c.post(
        f"/api/v1/terms/{tid}/moderation/resolve",
        json={"base_run_id": base, "changed_request_ids": [999999]},
        headers=h,
    )
    assert r.status_code == 422
    # a client cannot forge the moderation keys through POST /runs
    r = await c.post(
        "/api/v1/runs",
        json={"term_id": tid, "kind": "COURSE", "horizon": "WEEK", "params": {"unlock_request_ids": [1]}},
        headers=h,
    )
    assert r.status_code == 422
    # a queued (unsolved) child is not publishable
    async with dbmod.get_session_factory()() as s:
        q = ScheduleRun(term_id=tid, kind="COURSE", horizon="WEEK", parent_run_id=base, status="QUEUED")
        s.add(q)
        await s.commit()
        qid = q.id
    assert (await c.post(f"/api/v1/runs/{qid}/activate", headers=h)).status_code == 409
    r = await c.post(
        f"/api/v1/terms/{tid}/moderation/resolve",
        json={"base_run_id": qid, "changed_request_ids": [real["loser"]]},
        headers=h,
    )
    assert r.status_code == 409


async def test_matching_actions_write_only_on_a_draft_child_and_are_inherited(real: dict[str, Any]) -> None:
    from app.services.solver_bridge import build_solver_input

    c, admin, tid, base = real["client"], real["admin"], real["term_id"], real["run_id"]
    phar, eng = real["phar240"], real["eng106"]
    _pid, planner = await make_user(c, admin, "planlama@uni.edu.tr", role="PLANNER")
    # the published run is never edited
    r = await c.put(f"/api/v1/moderation/matchings/{phar}", json={"run_id": base, "action": "pin"}, headers=planner)
    assert r.status_code == 409
    async with dbmod.get_session_factory()() as s:
        child = ScheduleRun(
            term_id=tid,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"weeks": [3]},
            parent_run_id=base,
            status="FEASIBLE_PARTIAL",
            params={"moderation": {"base_run_id": base, "mode": "repair", "changed_request_ids": []}},
        )
        s.add(child)
        await s.commit()
        cid = child.id
        b201 = (await s.execute(select(Room.id).where(Room.code == "B201"))).scalar_one()
        a206 = (await s.execute(select(Room.id).where(Room.code == "A206"))).scalar_one()
    # pin "Bu taşımayı engelle": the class keeps its cell of the base run, as hard targeted rules of the child
    r = await c.put(f"/api/v1/moderation/matchings/{phar}", json={"run_id": cid, "action": "pin"}, headers=planner)
    assert r.status_code == 200, r.text
    assert r.json()["room_ids"] == [a206]
    async with dbmod.get_session_factory()() as s:
        rows = list((await s.execute(select(ConstraintRow).where(ConstraintRow.run_id == cid))).scalars())
        assert {(x.kind, x.hardness) for x in rows} == {("room_pin", "hard"), ("fixed_time", "hard")}
        assert all(x.term_id is None and x.params["event_ids"] == [phar] for x in rows)
        fixed = next(x for x in rows if x.kind == "fixed_time")
        assert (fixed.params["day"], fixed.params["start"]) == (1, 1)
    # Q8: a pin over the rooms' capacity is refused with the capacity named (ENG 106: 70 students, B 201: 30)
    r = await c.put(
        f"/api/v1/moderation/matchings/{eng}",
        json={"run_id": cid, "action": "pin", "room_ids": [b201], "day": 3, "start_period": 2},
        headers=planner,
    )
    assert r.status_code == 422 and "sığmaz" in r.json()["detail"]["message"]
    r = await c.put(
        f"/api/v1/moderation/matchings/{eng}",
        json={"run_id": cid, "action": "pin", "room_ids": [b201], "day": 3, "start_period": 2, "reason": "split"},
        headers=admin,
    )
    assert r.status_code == 200  # a planning administrator's override with a reason
    # prefer replaces the pin of that class with a soft wish (explicit weight 10, Q7)
    r = await c.put(
        f"/api/v1/moderation/matchings/{phar}",
        json={"run_id": cid, "action": "prefer", "room_ids": [a206]},
        headers=planner,
    )
    assert r.status_code == 200 and len(r.json()["disabled_constraint_ids"]) == 2
    async with dbmod.get_session_factory()() as s:
        live = list(
            (
                await s.execute(
                    select(ConstraintRow).where(ConstraintRow.run_id == cid, ConstraintRow.enabled.is_(True))
                )
            ).scalars()
        )
        pref = next(x for x in live if x.params.get("event_ids") == [phar])
        assert (pref.kind, pref.hardness, pref.weight) == ("room_preference", "soft", 10)
        # a re-solve from the draft inherits its run rules (decision "AI backlog finished")
        grand = ScheduleRun(
            term_id=tid, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]}, parent_run_id=cid, params={}
        )
        inp, _m = await build_solver_input(s, grand)
        assert pref.id in {x.id for x in inp.constraints}
        assert str(pref.id) in grand.stats["inherited_run_rules"]
    # unlock: the class's wishes on the draft are switched off and its planner lock is released next time
    r = await c.put(f"/api/v1/moderation/matchings/{phar}", json={"run_id": cid, "action": "unlock"}, headers=planner)
    assert r.status_code == 200 and r.json()["disabled_constraint_ids"] == [pref.id]
    async with dbmod.get_session_factory()() as s:
        child_row = await s.get(ScheduleRun, cid)
        assert child_row is not None and child_row.params["unlock_request_ids"] == [phar]
        grand = ScheduleRun(
            term_id=tid,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"weeks": [3]},
            parent_run_id=cid,
            params=dict(child_row.params),
        )
        inp, _m = await build_solver_input(s, grand)
        ev = next(e for e in inp.events if e.id == phar)
        assert ev.locked is None and ev.preferred_room_ids[0] == a206 and ev.fixed_day == 1
        assert any(d["code"] == "unlocked" for d in grand.stats["bridge_diagnoses"])
        audit = (
            (await s.execute(select(AuditEvent.action).where(AuditEvent.action.like("moderation.%")))).scalars().all()
        )
        assert {"moderation.pin", "moderation.prefer", "moderation.unlock"} <= set(audit)
    # the guard: never an untargeted rule (the solver's structural rules stay hard for every other class)
    from app.services.constraint_guard import is_waiver

    async with dbmod.get_session_factory()() as s:
        for x in (await s.execute(select(ConstraintRow).where(ConstraintRow.run_id == cid))).scalars():
            assert not is_waiver(x.kind, x.params, x.hardness)


@pytest.mark.slow
async def test_term_scope_resolve_keeps_hard_rules_or_explains(real: dict[str, Any]) -> None:
    """The whole Bahar term (week-segmented rows): a published term run, then the same priority edit."""
    from app.services.solver_bridge import run_schedule

    c, h, tid = real["client"], real["admin"], real["term_id"]
    async with dbmod.get_session_factory()() as s:
        run = ScheduleRun(
            term_id=tid,
            kind="COURSE",
            horizon="TERM",
            params={"time_limit_s": 120.0, "seed": 0, "solver": "cpsat", "publish_candidate": True},
        )
        s.add(run)
        await s.commit()
        term_run = run.id
    await run_schedule(dbmod.get_session_factory(), term_run)
    r = await c.put(f"/api/v1/moderation/requests/{real['loser']}/priority", json={"priority": 1}, headers=h)
    assert r.status_code == 200
    d = await _resolve(
        c, h, tid, {"base_run_id": term_run, "changed_request_ids": [real["loser"]], "time_limit_s": 120}
    )
    assert d["ready"]
    assert d["scores"]["hard"]["after"] == 100 or (d["status"] == "INFEASIBLE" and d["diagnosis"])
    assert d["counts"]["moved_unexplained"] == 0
