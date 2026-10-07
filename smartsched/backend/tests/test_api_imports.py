from __future__ import annotations

from app.workers.queue import get_queue

from tests.api_fixtures import login
from tests.conftest import EXAM_LIST, GUZ_GRID
from tests.test_import_crbs import DATA, STRUCTURE


async def test_upload_exam_list_and_grid_jobs(client):
    h = await login(client)
    with EXAM_LIST.open("rb") as f:
        r = await client.post(
            "/api/v1/imports/exam-list",
            files={"file": (EXAM_LIST.name, f, "application/octet-stream")},
            data={"term_code": "2026-FINAL"},
            headers=h,
        )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    await get_queue().wait_idle()
    r = await client.get(f"/api/v1/imports/{job_id}", headers=h)
    assert r.status_code == 200
    job = r.json()
    assert job["status"] == "DONE", job
    assert job["summary"]["rows_imported"] > 900 and job["summary"]["created"]["exam_requests"] > 900
    assert job["summary"]["extra"]["merge_groups"] > 500

    with GUZ_GRID.open("rb") as f:
        r = await client.post(
            "/api/v1/imports/weekly-grid",
            files={"file": (GUZ_GRID.name, f, "application/octet-stream")},
            data={"term_code": "2026-GUZ", "year": "2026"},
            headers=h,
        )
    assert r.status_code == 202
    await get_queue().wait_idle()
    job = (await client.get(f"/api/v1/imports/{r.json()['id']}", headers=h)).json()
    assert job["status"] == "DONE" and job["summary"]["created"]["blocks"] > 600
    rooms = (await client.get("/api/v1/rooms", headers=h)).json()
    assert len(rooms) >= 56 and any(r_["code"] == "A204" and r_["capacity"] == 156 for r_ in rooms)
    exams = (await client.get("/api/v1/requests/exams", params={"group_by": "merge_key", "limit": 5}, headers=h)).json()
    assert exams["group_by"] == "merge_key" and exams["total"] > 500 and exams["items"][0]["enrolment"] >= 0
    cohort = next(
        c
        for c in (
            await client.get("/api/v1/requests/exams", params={"group_by": "merge_key", "search": "BME 419"}, headers=h)
        ).json()["items"]
        if c["course_code"] == "BME419"
    )
    assert len(cohort["request_ids"]) >= 3 and cohort["enrolment"] >= 70
    jobs = (await client.get("/api/v1/imports", headers=h)).json()
    assert len(jobs) == 2


async def test_upload_crbs_dump(client):
    h = await login(client)
    files = [
        ("files", (STRUCTURE.name, STRUCTURE.read_bytes(), "application/sql")),
        ("files", (DATA.name, DATA.read_bytes(), "application/sql")),
    ]
    r = await client.post("/api/v1/imports/crbs", files=files, headers=h)
    assert r.status_code == 202, r.text
    await get_queue().wait_idle()
    job = (await client.get(f"/api/v1/imports/{r.json()['id']}", headers=h)).json()
    assert job["status"] == "DONE" and job["summary"]["kind"] == "crbs"
    r = await client.post("/api/v1/imports/crbs", data={}, headers=h)
    assert r.status_code == 400
