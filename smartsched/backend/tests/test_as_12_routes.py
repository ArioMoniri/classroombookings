"""AS-12 surfaces merged by AS-B: the course-side ``exam_overlap`` data-issues group and
``GET /analytics/forecast/exams/advice`` (the date advisor, changes nothing)."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import Assignment, ScheduleRun
from app.services.data_issues import build_data_issues

from tests.api_fixtures import login
from tests.test_as_12_class_plan import WEEK8_MON, _seed


async def test_course_run_data_issues_have_the_exam_overlap_group(engine):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        ids = await _seed(s)
        exam_run = ScheduleRun(term_id=ids["term"], kind="EXAM", horizon="TERM", status="OPTIMAL", is_active=True)
        s.add(exam_run)
        await s.flush()
        s.add(
            Assignment(
                run_id=exam_run.id,
                exam_request_id=ids["exam"],
                weeks=[8],
                day=1,
                date=WEEK8_MON,
                start_period=4,
                end_period=5,
                room_ids=[ids["a101"]],
                label="KIM101",
            )
        )
        await s.commit()
        course_run = await s.get(ScheduleRun, ids["course_run"])
        assert course_run is not None
        out = await build_data_issues(s, course_run)
    group = next(g for g in out["groups"] if g["code"] == "exam_overlap")
    assert group["title_tr"] == "Sınavla çakışan dersler" and group["title_en"] == "Classes that meet an exam's room"
    (it,) = group["items"]
    assert it["code"] == "exam_overlap" and it["message_tr"].startswith("FIZ 101 (A101, 3.–4. ders) 8. hafta")
    assert sorted(it["request_ids"]) == sorted([ids["mr"], ids["exam"]])


async def test_exam_advice_route(client):  # type: ignore[no-untyped-def]
    h = await login(client)
    async with get_session_factory()() as s:
        ids = await _seed(s)
        await s.commit()
    r = await client.get("/api/v1/analytics/forecast/exams/advice", params={"term_id": ids["term"]}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["term_id"] == ids["term"] and out["term_code"] == "T-MID" and out["changes_nothing"] is True
    assert {"cards", "suggestions", "confidence", "before", "after"} <= set(out)
    r = await client.get("/api/v1/analytics/forecast/exams/advice", params={"term_id": 999_999}, headers=h)
    assert r.status_code == 404 and r.json()["detail"]["message_tr"] == "dönem bulunamadı"
    assert (await client.get("/api/v1/analytics/forecast/exams/advice", params={"term_id": ids["term"]})).status_code == 401
