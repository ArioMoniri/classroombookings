"""Invigilator assignment on the real 2026 Final exam run (``tests/planning_analytics_support.py``: the Bahar list for
the instructors and their teaching, Bahar week 13 published, the Final board + exam list solved like ``POST /runs``,
one invigilation plan with the default rules)."""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.models import AuditEvent, InvigilationPlan, ScheduleRun
from app.services import invigilation as svc
from app.services.calendar import week_index_for_date
from app.services.seed import seed_admin
from app.services.utilisation import teaching_spans
from app.solver import invigilation as inv
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.api_fixtures import login
from tests.planning_analytics_support import PLAN_PARAMS, build_final_plan, copy_db

P = "/api/v1/invigilation"


@pytest.fixture(scope="session")
def invig_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("invigilation")


@pytest.fixture
async def real(invig_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    base, ids = await build_final_plan(invig_dir)
    path = copy_db(base, tmp_path)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
    qmod.reset_queue()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.headers.update(await login(c))
        yield {"client": c, **ids}
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


async def _wait(c: AsyncClient, plan_id: int) -> dict[str, Any]:
    await qmod.get_queue().wait_idle(600)
    r = await c.get(f"{P}/plans/{plan_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a["date"] == b["date"] and a["start_period"] <= b["end_period"] and b["start_period"] <= a["end_period"]


# ------------------------------------------------------------------------------------------- the real plan


async def test_final_plan_staffs_every_exam_room_without_breaking_a_rule(real):
    c = real["client"]
    d = (await c.get(f"{P}/plans/{real['plan']}")).json()
    assert d["exam_run_id"] == real["exam_run"] and d["status"] in ("OPTIMAL", "FEASIBLE"), d["diagnosis"][:3]
    assert d["hard_score"] == 100 and d["counts"]["missing"] == 0
    assert d["counts"]["posts"] > 500 and d["counts"]["required"] >= d["counts"]["posts"]
    assert d["headline"]["tr"] and d["headline"]["en"]
    duties = [x for p in d["posts"] for x in p["assigned"]]
    for p in d["posts"]:
        assert len(p["assigned"]) == p["required"] and p["missing"] == 0
        assert p["exams"] and all(e["label"] for e in p["exams"])
    # nobody in two places at once
    by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for x in duties:
        by_person[x["person_key"]].append(x)
    for xs in by_person.values():
        for i, a in enumerate(xs):
            assert not any(_overlap(a, b) for b in xs[i + 1 :]), (a, xs)
        per_day = defaultdict(int)
        for a in xs:
            per_day[a["date"]] += 1
        assert max(per_day.values()) <= 3  # the default daily cap
    # nobody invigilates while teaching (Bahar week 13 is published: 11-15 May 2026)
    async with dbmod.get_session_factory()() as s:
        from app.models import Term

        run = await s.get(ScheduleRun, real["teach_run"])
        assert run is not None
        bahar = await s.get(Term, run.term_id)
        assert bahar is not None
        spans = await teaching_spans(s, run, [13])
    teach = defaultdict(list)
    for sp in spans:
        teach[sp.instructor_id].append(sp)
    checked = 0
    for x in duties:
        if not x["instructor_id"]:
            continue
        day = dt.date.fromisoformat(x["date"])
        if week_index_for_date(bahar, day) != 13:
            continue
        for sp in teach.get(x["instructor_id"], []):
            if sp.day == day.isoweekday():
                checked += 1
                assert not (sp.start <= x["end_period"] and x["start_period"] <= sp.end), (x, sp)
    assert checked > 0  # the rule had something to do on the real data
    # the published week 13 covers 11-15 May only: the May exams of weeks 14-15 are named as unchecked, June is not
    warn = next(w for w in d["diagnosis"] if w["code"] == "teaching_unchecked")
    assert warn["severity"] == "warning" and warn["text"]["tr"]
    assert all(x < "2026-06-01" for x in warn["dates"]) and all(
        week_index_for_date(bahar, dt.date.fromisoformat(x)) in (14, 15) for x in warn["dates"]
    )


async def test_final_plan_respects_own_exams_under_prefer(real):
    """``own_exam=prefer``: an instructor whose course's exam runs is never sent to another room meanwhile."""
    c = real["client"]
    d = (await c.get(f"{P}/plans/{real['plan']}")).json()
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, real["exam_run"])
        assert run is not None
        built = await svc.build_input(s, run, d["params"])
    own_spans: dict[str, list[inv.Post]] = defaultdict(list)
    keys = {p.id: p.key for p in built.inp.people}
    for post in built.inp.posts:
        for pid, key in keys.items():
            if key in post.owner_keys:
                own_spans[pid].append(post)
    own_duties = 0
    for p in d["posts"]:
        for x in p["assigned"]:
            mine = own_spans.get(x["person_key"], [])
            if any(o.key == p["key"] for o in mine):
                own_duties += 1
                continue
            for o in mine:
                assert not (
                    o.date.isoformat() == p["date"] and o.start <= p["end_period"] and p["start_period"] <= o.end
                ), (x, o.key)
    assert own_duties > 0
    assert d["objective_breakdown"]["own_exam"] < 0


async def test_plan_is_deterministic(real):
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, real["exam_run"])
        assert run is not None
        built = await svc.build_input(s, run, {"time_limit_s": 2.0})
    a, b = inv.solve_invigilation(built.inp), inv.solve_invigilation(built.inp)
    assert a.duties == b.duties and a.status == b.status and a.objective_breakdown == b.objective_breakdown


# ------------------------------------------------------------------------------------------- infeasible


async def test_an_understaffed_pool_is_explained_per_exam_room(real):
    """Only two staff members and one invigilator per 10 students: most rooms cannot be staffed. The plan is
    INFEASIBLE with the duties that do fit, every missing invigilator is in a named diagnosis, nothing is relaxed."""
    c = real["client"]
    for name in ("Arş. Gör. Deniz Ak", "Arş. Gör. Elif Kara"):
        r = await c.post(f"{P}/pool", json={"full_name": name, "kind": "ASSISTANT", "term_id": real["final_id"]})
        assert r.status_code == 201, r.text
    r = await c.post(
        f"{P}/plans",
        json={
            "exam_run_id": real["exam_run"],
            "params": {"instructor_pool": "none", "students_per_invigilator": 10, "time_limit_s": 3},
        },
    )
    assert r.status_code == 202, r.text
    d = await _wait(c, r.json()["plan_id"])
    assert d["status"] == "INFEASIBLE" and d["hard_score"] < 100
    assert d["counts"]["missing"] > 0 and d["counts"]["filled"] > 0
    errs = [x for x in d["diagnosis"] if x["severity"] == "error"]
    assert errs and {x["code"] for x in errs} <= {"no_candidates", "slot_shortage", "cap_shortage", "overlap_shortage"}
    for x in errs:
        assert x["text"]["tr"] and x["text"]["en"] and x["post_keys"] and x["exam_ids"]
        assert x["suggestions"] and all(s["text"]["tr"] for s in x["suggestions"])
    short_posts = {p["key"] for p in d["posts"] if p["missing"]}
    named = {k for x in errs for k in x["post_keys"]}
    assert short_posts <= named | {p for x in errs if x["code"] == "slot_shortage" for p in x["post_keys"]}
    # the duties that were made still break no rule: two people, never twice at once
    duties = [x for p in d["posts"] for x in p["assigned"]]
    assert {x["person_key"] for x in duties} <= {f"STAFF:{m['id']}" for m in (await c.get(f"{P}/pool")).json()}
    by = defaultdict(list)
    for x in duties:
        by[x["person_key"]].append(x)
    for xs in by.values():
        for i, a in enumerate(xs):
            assert not any(_overlap(a, b) for b in xs[i + 1 :])


async def test_empty_pool_is_an_error_not_a_silent_plan(real):
    c = real["client"]
    r = await c.post(f"{P}/plans", json={"exam_run_id": real["exam_run"], "params": {"instructor_pool": "none"}})
    d = await _wait(c, r.json()["plan_id"])
    assert d["status"] == "INFEASIBLE" and d["hard_score"] < 100
    assert any(x["code"] == "pool_empty" and x["severity"] == "error" for x in d["diagnosis"])
    assert any(x["code"] == "no_candidates" for x in d["diagnosis"])


# ------------------------------------------------------------------------------------------- pool, locks, re-run


async def test_unavailability_lock_and_rerun(real):
    c = real["client"]
    plan_id = real["plan"]
    d = (await c.get(f"{P}/plans/{plan_id}")).json()
    duties = [x for p in d["posts"] for x in p["assigned"] if x["instructor_id"]]
    keep = duties[0]
    # the busiest instructor declares one exam day unavailable
    busiest = next(
        p for p in d["people"] if p["person_key"].startswith("INS:") and p["person_key"] != keep["person_key"]
    )
    ins_id = int(busiest["person_key"].split(":")[1])
    day = next(x["date"] for x in duties if x["person_key"] == busiest["person_key"])
    r = await c.post(
        f"{P}/pool",
        json={"instructor_id": ins_id, "term_id": real["final_id"], "unavailable": [{"date": day, "note": "kurul"}]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["person_key"] == busiest["person_key"] and r.json()["kind"] == "INSTRUCTOR"
    # lock one duty, then re-run
    r = await c.post(f"{P}/plans/{plan_id}/duties/{keep['id']}/lock", params={"locked": True})
    assert r.status_code == 200 and r.json()["is_locked"] is True
    r = await c.post(f"{P}/plans/{plan_id}/rerun", json={"params": PLAN_PARAMS})
    assert r.status_code == 202, r.text
    child = await _wait(c, r.json()["plan_id"])
    assert child["parent_plan_id"] == plan_id and child["status"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE")
    cd = [x for p in child["posts"] for x in p["assigned"]]
    kept = [x for x in cd if x["post_key"] == keep["post_key"] and x["person_key"] == keep["person_key"]]
    assert kept and kept[0]["is_locked"] and kept[0]["origin"] == "LOCK"
    assert not [x for x in cd if x["person_key"] == busiest["person_key"] and x["date"] == day]
    # stability: most duties stay with the same people
    before = {(x["post_key"], x["person_key"]) for p in d["posts"] for x in p["assigned"]}
    after = {(x["post_key"], x["person_key"]) for x in cd}
    assert len(before & after) > len(before) // 2
    async with dbmod.get_session_factory()() as s:
        acts = {a for (a,) in (await s.execute(select(AuditEvent.action))).all()}
    assert {"invigilator.create", "invigilation.lock", "invigilation.rerun"} <= acts


async def test_candidates_and_reassign(real):
    c = real["client"]
    plan_id = real["plan"]
    d = (await c.get(f"{P}/plans/{plan_id}")).json()
    post = next(p for p in d["posts"] if p["assigned"])
    r = await c.get(f"{P}/plans/{plan_id}/candidates", params={"post_key": post["key"]})
    assert r.status_code == 200, r.text
    cand = r.json()
    assert cand["free"] and cand["unavailable"]
    assert all(x["reason_text"]["tr"] for x in cand["unavailable"])
    duty = post["assigned"][0]
    bad = cand["unavailable"][0]
    r = await c.put(f"{P}/plans/{plan_id}/duties/{duty['id']}", json={"person_key": bad["person_key"]})
    assert r.status_code == 409 and r.json()["detail"]["problems"]
    good = cand["free"][0]
    r = await c.put(
        f"{P}/plans/{plan_id}/duties/{duty['id']}", json={"person_key": good["person_key"], "reason": "takas"}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["person_key"] == good["person_key"] and out["origin"] == "MANUAL" and out["is_locked"]
    r = await c.put(f"{P}/plans/{plan_id}/duties/{duty['id']}", json={"person_key": "STAFF:999999"})
    assert r.status_code == 422
    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "invigilation.reassign"))).scalar_one()
    assert ev.reason == "takas" and ev.before["person_key"] == duty["person_key"]


async def test_activate_delete_and_exports(real):
    c = real["client"]
    plan_id = real["plan"]
    r = await c.post(f"{P}/plans/{plan_id}/activate")
    assert r.status_code == 200 and r.json()["is_active"] is True
    assert (await c.delete(f"{P}/plans/{plan_id}")).status_code == 409
    listed = (await c.get(f"{P}/plans", params={"exam_run_id": real["exam_run"]})).json()
    assert [p["id"] for p in listed if p["is_active"]] == [plan_id]
    roster = await c.get(f"{P}/plans/{plan_id}/export")
    assert roster.status_code == 200 and roster.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(roster.text.lstrip("﻿"))))
    d = (await c.get(f"{P}/plans/{plan_id}")).json()
    assert len(rows) == sum(max(1, len(p["assigned"])) for p in d["posts"])
    assert {"date", "room", "exams", "person"} <= set(rows[0])
    load = (await c.get(f"{P}/plans/{plan_id}/load")).json()
    assert sum(r_["duties"] for r_ in load["rows"]) == sum(len(p["assigned"]) for p in d["posts"])
    assert sum(x["duties"] for x in load["per_date"]) == sum(r_["duties"] for r_ in load["rows"])
    lcsv = await c.get(f"{P}/plans/{plan_id}/load", params={"format": "csv"})
    assert lcsv.status_code == 200 and "total_periods" in lcsv.text.splitlines()[0]
    one = d["people"][0]["person_key"]
    mine = (await c.get(f"{P}/plans/{plan_id}", params={"person": one})).json()
    assert mine["posts"] and all(all(x["person_key"] == one for x in p["assigned"]) for p in mine["posts"])


async def test_errors_and_recovery(real):
    c = real["client"]
    async with dbmod.get_session_factory()() as s:
        course = (
            (await s.execute(select(ScheduleRun).where(ScheduleRun.kind == "COURSE").order_by(ScheduleRun.id)))
            .scalars()
            .first()
        )
        assert course is not None
        course_id = course.id
    r = await c.post(f"{P}/plans", json={"exam_run_id": course_id})
    assert r.status_code == 422 and r.json()["detail"]["tr"]
    assert (await c.post(f"{P}/plans", json={"exam_run_id": 99999})).status_code == 404
    r = await c.post(f"{P}/plans", json={"exam_run_id": real["exam_run"], "params": {"own_exam": "never"}})
    assert r.status_code == 422
    r = await c.post(f"{P}/plans", json={"exam_run_id": real["exam_run"], "params": {"weights": {"luck": 3}}})
    assert r.status_code == 422
    assert (await c.get(f"{P}/plans/99999")).status_code == 404
    r = await c.post(f"{P}/pool", json={"full_name": "X", "unavailable": [{"start_period": 2, "end_period": 3}]})
    assert r.status_code == 422
    # a plan left RUNNING by this process with no live job (a restart) is reported as FAILED, never as running
    from app.workers.queue import worker_id

    async with dbmod.get_session_factory()() as s:
        p = InvigilationPlan(
            term_id=real["final_id"], exam_run_id=real["exam_run"], status="RUNNING", stats={"worker": worker_id()}
        )
        s.add(p)
        await s.commit()
        pid = p.id
    d = (await c.get(f"{P}/plans/{pid}")).json()
    assert d["status"] == "FAILED" and "interrupted" in d["error"]


async def test_pool_crud_is_audited(real):
    c = real["client"]
    r = await c.post(
        f"{P}/pool",
        json={
            "full_name": "Öğr. Gör. Selin Tan",
            "kind": "STAFF",
            "max_per_day": 2,
            "load_factor": 150,
            "unavailable": [{"day": 5}, {"date": "2026-06-03", "start_period": 1, "end_period": 4}],
        },
    )
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["full_name"] == "Selin Tan" and m["unavailable"][0] == {"day": 5}
    r = await c.put(f"{P}/pool/{m['id']}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["load_factor"] == 150
    assert any(x["id"] == m["id"] for x in (await c.get(f"{P}/pool")).json())
    assert (await c.delete(f"{P}/pool/{m['id']}")).status_code == 204
    assert (await c.delete(f"{P}/pool/{m['id']}")).status_code == 404
    async with dbmod.get_session_factory()() as s:
        acts = [
            a
            for (a,) in (
                await s.execute(select(AuditEvent.action).where(AuditEvent.entity_type == "invigilator_pool"))
            ).all()
        ]
    assert acts == ["invigilator.create", "invigilator.update", "invigilator.delete"]
