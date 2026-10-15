"""Admin persona 2026-10-15 (docs/testing/2026-10-15-persona-admin.md), the imports scope:

* M-20: a wrong file says what was expected and what was detected ("Bu dosya bir sınav listesi gibi görünüyor;
  planlama listesi bekleniyordu"), and the failed job carries ``summary.detected_kind`` for an "import as" offer;
* KVKK: parsed rows and warnings (instructor names, notes) are for ``planning.edit``; a viewer
  (``planning.view``) gets the counts only - the council's D13 rule;
* M-13 (backend half): a job kind the API does not know is listed as ``other`` and logged, never a 500.
"""

from __future__ import annotations

import pytest
from app.importers import detect
from app.importers.exam_list import parse_exam_list
from app.importers.planning_list import parse_planning_list
from app.workers.queue import get_queue

from tests.api_fixtures import login
from tests.conftest import BAHAR_LIST, EXAM_LIST, GUZ_GRID, GUZ_LIST
from tests.crbs_env import env  # noqa: F401
from tests.test_importer_followups import subset


def test_planning_list_slot_given_an_exam_list() -> None:
    with pytest.raises(detect.WrongFileError) as info:
        parse_planning_list(EXAM_LIST)
    e = info.value
    assert e.expected == "planning-list" and e.detected == "exam-list"
    assert "Bu dosya bir sınav listesi gibi görünüyor; planlama listesi bekleniyordu" in e.message_tr
    assert "looks like an exam list; a planning list was expected" in e.message_en
    assert isinstance(e, ValueError)  # callers that catch ValueError keep working


def test_planning_list_slot_given_the_weekly_grid() -> None:
    with pytest.raises(detect.WrongFileError) as info:
        parse_planning_list(GUZ_GRID)
    assert info.value.detected == "weekly-grid"
    assert "haftalık derslik takvimi gibi görünüyor" in info.value.message_tr


def test_exam_list_slot_given_a_planning_list() -> None:
    with pytest.raises(detect.WrongFileError) as info:
        parse_exam_list(GUZ_LIST)
    assert info.value.detected == "planning-list"
    assert "sınav listesi bekleniyordu" in info.value.message_tr


def test_unknown_layout_names_the_missing_columns() -> None:
    e = detect.WrongFileError.build("planning-list", ["Ad", "Soyad"], ["code", "day"])
    assert e.detected is None
    assert "Ders Kodu" in e.message_tr and "Gün" in e.message_tr and "course code" in e.message_en


async def test_wrong_file_job_says_why(client) -> None:
    h = await login(client)
    with GUZ_GRID.open("rb") as f:
        r = await client.post(
            "/api/v1/imports/planning-list",
            files={"file": (GUZ_GRID.name, f, "application/octet-stream")},
            data={"term_code": "2026-GUZ"},
            headers=h,
        )
    assert r.status_code == 202
    await get_queue().wait_idle()
    job = (await client.get(f"/api/v1/imports/{r.json()['id']}", headers=h)).json()
    assert job["status"] == "FAILED"
    assert "haftalık derslik takvimi gibi görünüyor; planlama listesi bekleniyordu" in job["error"]
    assert "looks like a weekly room timetable" in job["error"]
    assert job["summary"]["detected_kind"] == "weekly-grid"


async def test_viewers_get_counts_only(env, tmp_path) -> None:  # noqa: F811
    from tests.test_admin_gaps import _role

    planner = await login(env.client)
    rid = await _role(env, "Görüntüleyici", ["planning.view"])
    _, viewer = await env.user("goruntuleyici@uni.edu.tr", role=None, role_id=rid)
    path = subset(BAHAR_LIST, [366, 1119], tmp_path / "kvkk.xlsx")  # ING 302 + PSY 278: names and notes
    with path.open("rb") as f:
        r = await env.client.post(
            "/api/v1/imports/planning-list",
            files={"file": (path.name, f, "application/octet-stream")},
            data={"term_code": "2026-BAHAR"},
            headers=planner,
        )
    await get_queue().wait_idle()
    jid = r.json()["id"]
    full = (await env.client.get(f"/api/v1/imports/{jid}", headers=planner)).json()
    assert full["summary"]["warnings"] or full["summary"]["extra"]["preferences"]["unparsed_items"]
    seen = (await env.client.get(f"/api/v1/imports/{jid}", headers=viewer)).json()
    listed = (await env.client.get("/api/v1/imports", headers=viewer)).json()
    for s in (seen["summary"], next(j for j in listed if j["id"] == jid)["summary"]):
        assert s["rows_total"] == full["summary"]["rows_total"] and s["warnings_count"] == full["summary"]["warnings_count"]
        assert s["created"] == full["summary"]["created"]
        for key in ("warnings", "rows_skipped", "warning_summary", "extra", "skip_reasons"):
            assert key not in s, key
        assert s["redacted"] is True
    text = str(seen) + str(listed)
    assert "JASP" not in text and "olmasın" not in text


async def test_an_unknown_job_kind_is_listed_as_other(client) -> None:
    from app.core.db import get_session_factory
    from app.models import ImportJob

    h = await login(client)
    async with get_session_factory()() as s:
        s.add(ImportJob(kind="timetable-pdf", filename="x.pdf", status="DONE", summary={}))
        await s.commit()
    r = await client.get("/api/v1/imports", headers=h)
    assert r.status_code == 200 and [j["kind"] for j in r.json()] == ["other"]
