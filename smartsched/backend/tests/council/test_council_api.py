"""Council API end to end without an API key: upload real files, watch, review, commit into a term."""

from __future__ import annotations

from pathlib import Path

from app.core.db import get_session_factory
from app.importers.exam_list import parse_exam_list
from app.models import Block, ExamRequest, Instructor, MeetingRequest, Room, Term
from app.workers import queue as qmod
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.council.conftest import EN_CSV, EXAM_LIST, FINAL_GRID, MEMO_DOCX, ROOM_MASTER, SCAN_PNG


def _files(*paths: Path) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in paths]


async def _run(client, headers, *paths: Path, **form) -> dict:
    data = {"lang": "en", "year_hint": "2026", **{k: str(v) for k, v in form.items()}}
    r = await client.post("/api/v1/council/jobs", headers=headers, files=_files(*paths), data=data)
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] in ("QUEUED", "RUNNING") and len(job["files"]) == len(paths)
    await qmod.get_queue().wait_idle(600)
    r = await client.get(f"/api/v1/council/jobs/{job['id']}", headers=headers)
    assert r.status_code == 200
    return r.json()


async def _count(model, *where) -> int:
    async with get_session_factory()() as s:
        q = select(func.count()).select_from(model)
        for w in where:
            q = q.where(w)
        return int((await s.execute(q)).scalar_one())


async def test_heuristic_job_reviews_and_commits_general_files(client):
    h = await login(client)
    job = await _run(client, h, ROOM_MASTER, EN_CSV, MEMO_DOCX)
    assert job["status"] in ("READY", "REVIEW"), job
    assert job["ai_mode"] == "heuristic" and "no Anthropic API key" in job["summary"]["ai"]
    routes = [f["route"] for f in job["files"]]
    assert routes == ["fast:room-master", "general", "general"]
    assert all(f["status"] == "DONE" for f in job["files"])
    en = job["files"][1]
    assert en["counts"]["meeting"] >= 1300 and en["kinds"] == ["request_list"]
    assert [s["agent"] for s in en["steps"]] == ["intake", "structure", "extract", "rules"]
    assert all(s["status"] == "DONE" and s["input_tokens"] == 0 for s in en["steps"])
    assert [s["agent"] for s in job["cross_steps"]] == ["reconcile", "planner", "critic"]
    rules_step = en["steps"][-1]
    assert "needs the AI model" in rules_step["message"]

    r = await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)
    review = r.json()
    kinds = {it["kind"] for it in review["items"]}
    assert {"rule_text", "plan"} <= kinds
    plan_item = next(it for it in review["items"] if it["kind"] == "plan")
    assert plan_item["current"]["code"] == "BAHAR" and plan_item["files"] == [1]
    pending = [it for it in review["items"] if it["blocking"] and it["decision"] is None]
    if pending:
        r = await client.post(
            f"/api/v1/council/jobs/{job['id']}/review",
            headers=h,
            json={"decisions": [{"id": it["id"], "action": "accept"} for it in pending]},
        )
        assert r.status_code == 200 and r.json()["blocking"] == 0

    # records keep their provenance
    r = await client.get(f"/api/v1/council/jobs/{job['id']}/records", headers=h, params={"file": 1, "type": "meeting"})
    rec = r.json()["items"][0]
    assert rec["course_code"] == "MAT112" and rec["source"] == {"file": EN_CSV.name, "row": 2}

    body = {"group": 0, "term": {"code": "2026-BAHAR-EN", "name": "Bahar 2026 (EN export)", "week_count": 14}}
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["term_code"] == "2026-BAHAR-EN" and out["term_created"]
    assert out["files"] == [0, 1, 2]
    assert out["fast_path"][0]["route"] == "fast:room-master"
    assert out["general"]["meeting_requests"] >= 1300
    merges = [it for it in pending if it["kind"] == "merge" and it["current"]["kind"] == "instructor"]
    assert out["general"].get("merges_applied", 0) == len([it for it in pending if it["kind"] == "merge"])
    async with get_session_factory()() as s:
        for it in merges:  # an accepted merge writes the second spelling as the first
            names = (await s.execute(select(Instructor.full_name))).scalars().all()
            assert it["current"]["b"] not in names
    async with get_session_factory()() as s:
        a101 = (await s.execute(select(Room).where(Room.code == "A101"))).scalar_one()
        term = (await s.execute(select(Term).where(Term.code == "2026-BAHAR-EN"))).scalar_one()
    assert a101.capacity == 58 and a101.exam_capacity == 30  # room master, not overwritten
    assert term.periods_json and term.periods_json[0]["start"] == "08:30"
    n = await _count(MeetingRequest, MeetingRequest.source_key.like(f"CC:{job['id']}:1:%"))
    assert n == out["general"]["meeting_requests"]
    locked = await _count(MeetingRequest, MeetingRequest.status == "LOCKED", MeetingRequest.source_key.like("CC:%"))
    assert locked > 0.5 * n  # assigned rooms of the export are the planner's definitive rooms

    # committing again updates, never duplicates
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert r.status_code == 200
    assert r.json()["general"].get("meeting_requests", 0) == 0
    assert await _count(MeetingRequest, MeetingRequest.source_key.like(f"CC:{job['id']}:1:%")) == n


async def test_low_confidence_mapping_blocks_until_reviewed(client):
    h = await login(client)
    job = await _run(client, h, EN_CSV, review_threshold=0.99)
    assert job["status"] == "REVIEW" and job["summary"]["blocking_items"] > 0
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": 0})
    assert r.status_code == 409 and "must be decided" in r.json()["detail"]
    review = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)).json()
    remarks = next(it for it in review["items"] if it["kind"] == "mapping" and "Remarks" in it["title"])
    assert remarks["current"]["field"] == "notes" and remarks["samples"]
    # unmap "Remarks": the file is re-extracted deterministically, notes disappear
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/review",
        headers=h,
        json={"decisions": [{"id": remarks["id"], "action": "reject"}, {"id": "nope", "action": "accept"}]},
    )
    body = r.json()
    assert body["saved"] == 1 and body["rerun_files"] == [0] and "unknown review item nope" in body["errors"]
    recs = (
        await client.get(f"/api/v1/council/jobs/{job['id']}/records", headers=h, params={"file": 0, "limit": 500})
    ).json()["items"]
    assert all(r["notes"] is None for r in recs)
    rest = [it for it in body["items"] if it["blocking"] and it["decision"] is None]
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/review",
        headers=h,
        json={"decisions": [{"id": it["id"], "action": "accept"} for it in rest]},
    )
    assert r.json()["blocking"] == 0 and r.json()["status"] == "READY"
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": 0, "term": {"code": "EN-REVIEWED"}}
    )
    assert r.status_code == 200, r.text
    # the audit trail keeps every version
    arts = (await client.get(f"/api/v1/council/jobs/{job['id']}/artifacts", headers=h)).json()
    kinds = [a["kind"] for a in arts]
    assert kinds.count("structure") == 2 and kinds.count("review") == 2 and "commit" in kinds


async def test_fast_path_commit_uses_the_university_importers(client):
    h = await login(client)
    job = await _run(client, h, EXAM_LIST, FINAL_GRID)
    assert [f["route"] for f in job["files"]] == ["fast:exam-list", "fast:weekly-grid"]
    plan = job["plan"]["groups"]
    assert len(plan) == 1 and plan[0]["code"] == "2026-FINAL" and plan[0]["kind"] == "FINAL"
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": 0})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [x["route"] for x in out["fast_path"]] == ["fast:weekly-grid", "fast:exam-list"]  # board first
    async with get_session_factory()() as s:
        tid = (await s.execute(select(Term.id).where(Term.code == "2026-FINAL"))).scalar_one()
    assert await _count(ExamRequest, ExamRequest.term_id == tid) == len(parse_exam_list(EXAM_LIST).rows)
    assert await _count(Block, Block.term_id == tid) > 0


async def test_forced_general_path_on_a_real_workbook(client):
    h = await login(client)
    fast = await _run(client, h, EXAM_LIST)
    general = await _run(client, h, EXAM_LIST, mode="general")
    assert fast["files"][0]["route"] == "fast:exam-list" and general["files"][0]["route"] == "general"
    a, b = fast["files"][0]["counts"]["exam"], general["files"][0]["counts"]["exam"]
    assert abs(a - b) <= 2


async def test_image_without_key_is_explained_and_sse_streams(client):
    h = await login(client)
    job = await _run(client, h, SCAN_PNG)
    f = job["files"][0]
    assert f["route"] == "vision" and "AI model" in f["message"]
    assert "needs the AI model" in f["steps"][0]["message"]
    review = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)).json()
    assert any(it["kind"] == "file" for it in review["items"])
    async with client.stream("GET", f"/api/v1/council/jobs/{job['id']}/events", headers=h) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in resp.aiter_text()])
    assert "event: snapshot" in body and "event: done" in body


async def test_upload_limits_and_auth(client):
    r = await client.post("/api/v1/council/jobs", files=_files(ROOM_MASTER))
    assert r.status_code == 401
    h = await login(client)
    r = await client.post("/api/v1/council/jobs", headers=h, files=_files(ROOM_MASTER), data={"mode": "magic"})
    assert r.status_code == 400
    r = await client.get("/api/v1/council/jobs/999", headers=h)
    assert r.status_code == 404
