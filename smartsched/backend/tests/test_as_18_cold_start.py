"""AS-18: cold start.

* an empty install answers every adaptive endpoint (no 500) with ``confidence: none`` and a TR/EN ``needs`` text;
  only the built-in ``standard`` and ``exam_week`` profiles exist;
* after the universal fixture (``tests/fixtures/universal/bahar_requests_en.csv``, an English CSV of the Bahar
  list) is committed through the intake council, request-driven demand is not empty;
* ``seasons.after_import`` proposes draft segments only from week names that say so ("Vize haftası").
"""

from __future__ import annotations

from datetime import date

from app.core.db import get_session_factory
from app.models import Term, Week
from app.services import seasons
from app.workers import queue as qmod
from sqlalchemy import select

from tests.api_fixtures import login
from tests.council.conftest import EN_CSV, ROOM_MASTER

EMPTY_GETS = (
    "/api/v1/analytics/peaks",
    "/api/v1/analytics/demand",
    "/api/v1/analytics/forecast/demand",
)


async def test_as_18_empty_install_answers_with_needs(client):
    h = await login(client)
    for url in EMPTY_GETS:
        r = await client.get(url, headers=h)
        assert r.status_code == 200, (url, r.text)
        out = r.json()
        assert out["confidence"] == "none" and out["needs"]["tr"] and out["needs"]["en"], url
    profiles = (await client.get("/api/v1/seasons/profiles", headers=h)).json()["profiles"]
    assert {p["key"] for p in profiles} == {"standard", "exam_week"} and all(p["builtin"] for p in profiles)
    async with get_session_factory()() as s:
        t = Term(code="2027-BAHAR", name="2027 Bahar", week_count=14)
        s.add(t)
        await s.commit()
        tid = t.id
    for url, params in (
        ("/api/v1/analytics/peaks", {"term_id": tid}),
        ("/api/v1/analytics/forecast/demand", {"term_id": tid}),
        ("/api/v1/analytics/forecast/shortfall", {"term_id": tid}),
        ("/api/v1/analytics/forecast/exams", {"term_id": tid}),
        ("/api/v1/seasons/terms/" + str(tid) + "/periods", {}),
        ("/api/v1/learning/versions", {"term_id": tid}),
        ("/api/v1/learning/calibration", {}),
    ):
        r = await client.get(url, params=params, headers=h)
        assert r.status_code == 200, (url, r.text)
        out = r.json()
        assert out.get("needs") and out["needs"]["tr"] and out["needs"]["en"], (url, out)
    r = await client.post("/api/v1/analytics/forecast/what-if", json={"term_id": tid, "enrolment_pct": 10}, headers=h)
    assert r.status_code == 200 and r.json()["confidence"] == "none"


async def test_as_18_universal_csv_gives_request_demand(client):
    h = await login(client)
    files = [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in (ROOM_MASTER, EN_CSV)]
    r = await client.post("/api/v1/council/jobs", headers=h, files=files, data={"lang": "en", "year_hint": "2026"})
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    await qmod.get_queue().wait_idle(600)
    review = (await client.get(f"/api/v1/council/jobs/{job_id}/review", headers=h)).json()
    pending = [it for it in review["items"] if it["blocking"] and it["decision"] is None]
    if pending:
        decisions = [{"id": it["id"], "action": "reject" if it["kind"] == "merge" else "accept"} for it in pending]
        r = await client.post(f"/api/v1/council/jobs/{job_id}/review", headers=h, json={"decisions": decisions})
        assert r.status_code == 200, r.text
        await qmod.get_queue().wait_idle(600)
    r = await client.post(
        f"/api/v1/council/jobs/{job_id}/commit", headers=h, json={"group": 0, "term": {"code": "EN-2026-SPRING"}}
    )
    assert r.status_code == 200, r.text
    async with get_session_factory()() as s:
        tid = (await s.execute(select(Term.id).where(Term.code == "EN-2026-SPRING"))).scalar_one()
    out = (
        await client.get("/api/v1/analytics/forecast/demand", params={"term_id": tid, "group_by": "weekday"}, headers=h)
    ).json()
    assert out["method"] == "requests" and out["confidence"] == "high" and out["total"] > 0
    assert {c["key"][0] for c in out["cells"]} >= {1, 2, 3, 4, 5}


async def test_as_18_after_import_proposes_drafts_from_week_names(engine, session):
    term = Term(code="2026-BAHAR", name="2026 Bahar", week_count=4, start_date=date(2026, 2, 2))
    session.add(term)
    await session.flush()
    for i, label in enumerate(
        ("2 - 8 Şubat Bahar Dönem Açılış", "9 - 15 Şubat", "VİZE HAFTASI 16-22 Şubat", "23 Şubat"), 1
    ):
        session.add(Week(term_id=term.id, index=i, kind="LECTURE", label=label))
    await session.flush()
    out = await seasons.after_import(session, term)
    assert [(sg.kind, sg.week_from, sg.week_to, sg.status) for sg in out] == [("MIDTERM", 3, 3, "draft")]
    assert out[0].label_tr == "Ara sınav haftası: 3. hafta"
    assert await seasons.after_import(session, term) == []  # not repeated
    # a draft does not change the period kind until it is approved
    weeks_rows, hol, segs = await seasons.load_calendar(session, term)
    assert seasons.period_kind_on(term, date(2026, 2, 17), weeks_rows, hol, segs) == "LECTURE"
    segs[0].status = "active"
    assert seasons.period_kind_on(term, date(2026, 2, 17), weeks_rows, hol, segs) == "MIDTERM"
