"""Row review for AI-route files (P19-A2): every row of a PDF / DOCX / TXT / EML / image starts pending, commit
refuses (409) until each is decided whatever ``allow_pending`` says, bulk decisions are capped and confirmed, and
low-confidence rows are decided one at a time. The real rules memo (DOCX, 36 room rows) is read without a model."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.council import airows
from app.models import AuditEvent, Room
from sqlalchemy import select

from tests.api_fixtures import login
from tests.council.conftest import MEMO_DOCX
from tests.council.test_formats_api import upload

TERM = {"code": "2026-MEMO", "week_count": 14}


async def accept_ai_rows(client, h, job_id: int) -> int:
    """Accept every pending AI row in confirmed batches of at most 50 (low-confidence rows one by one)."""
    rows = [r for r in (await _rows(client, h, job_id, state="pending"))["items"]]
    batch = [r["id"] for r in rows if not r["low_confidence"]]
    for k in range(0, len(batch), airows.BULK_MAX):
        r = await _decide(client, h, job_id, [{"row_id": i, "action": "accept"} for i in batch[k : k + 50]], True)
        assert r.status_code == 200, r.text
    for row in rows:
        if row["low_confidence"]:
            assert (await _decide(client, h, job_id, [{"row_id": row["id"], "action": "accept"}])).status_code == 200
    return len(rows)


async def _rows(client, h, job_id: int, **params) -> dict:
    r = await client.get(f"/api/v1/council/jobs/{job_id}/rows", headers=h, params={"limit": 500, **params})
    assert r.status_code == 200, r.text
    return r.json()


async def _decide(client, h, job_id: int, decisions: list[dict], confirm: bool = False):
    return await client.post(
        f"/api/v1/council/jobs/{job_id}/rows/decisions",
        headers=h,
        json={"decisions": decisions, "confirm": confirm},
    )


async def test_ai_route_rows_need_a_person_before_commit(client, monkeypatch):
    h = await login(client)
    job = await upload(client, h, (MEMO_DOCX.name, MEMO_DOCX.read_bytes()), ai="false")
    f = job["files"][0]
    assert f["format"] == "docx" and f["route_kind"] == "ai" and f["counts"] == {"room": 36}
    assert job["status"] == "REVIEW"
    review = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)).json()
    item = next(it for it in review["items"] if it["kind"] == "ai_rows")
    assert item["blocking"] and item["pending"] == item["total"] == 36 and item["decision"] is None

    body = {"files": [0], "term": TERM, "allow_pending": True}
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert (
        r.status_code == 409 and "read by the AI model" in r.json()["detail"] and "allow_pending" in r.json()["detail"]
    )
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={**body, "dry_run": True})
    assert r.status_code == 409  # a dry-run is refused for the same reason

    rows = (await _rows(client, h, job["id"], method="ai"))["items"]
    assert len(rows) == 36 and {r["state"] for r in rows} == {"pending"}
    assert rows[0]["provenance"] == {"file": MEMO_DOCX.name, "table": 1, "row": 2, "col": 1}
    ids = [r["id"] for r in rows]

    # bulk rules: a cap, one confirmation, and never a low-confidence row in a batch
    monkeypatch.setattr(airows, "BULK_MAX", 10)
    r = await _decide(client, h, job["id"], [{"row_id": i, "action": "accept"} for i in ids[:11]], confirm=True)
    assert r.status_code == 422 and "at most 10" in r.text
    r = await _decide(client, h, job["id"], [{"row_id": i, "action": "accept"} for i in ids[:5]])
    assert r.status_code == 422 and "confirm=true" in r.text
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/review",
        headers=h,
        json={"decisions": [{"id": item["id"], "action": "accept"}]},
    )
    assert "decide the rows themselves" in r.json()["errors"][0]

    # one row rejected, one edited, the rest accepted in confirmed batches of 10
    r = await _decide(client, h, job["id"], [{"row_id": ids[0], "action": "reject"}])
    assert r.status_code == 200 and r.json()["saved"] == 1
    r = await _decide(client, h, job["id"], [{"row_id": ids[1], "action": "edit", "value": {"capacity": 99}}])
    assert r.status_code == 200
    r = await _decide(client, h, job["id"], [{"row_id": ids[2], "action": "edit", "value": {"source": {}}}])
    assert r.json()["saved"] == 0 and "edit needs value with record fields (source)" in r.json()["errors"][0]
    rest = ids[2:]
    for k in range(0, len(rest), 10):
        r = await _decide(client, h, job["id"], [{"row_id": i, "action": "accept"} for i in rest[k : k + 10]], True)
        assert r.status_code == 200, r.text
    assert r.json()["counts"]["state"] == {"rejected": 1, "edited": 1, "accepted": 34}
    review = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)).json()
    assert next(it for it in review["items"] if it["kind"] == "ai_rows")["decision"]["auto"] is True

    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["general"]["rows_rejected"] == 1 and r.json()["general"]["rows_edited"] == 1
    async with get_session_factory()() as s:
        codes = {room.code: room for room in (await s.execute(select(Room))).scalars()}
        first, second = rows[0]["values"]["code"], rows[1]["values"]["code"]
        assert first not in codes and codes[second].capacity == 99
        events = (await s.execute(select(AuditEvent).where(AuditEvent.action == "council.review"))).scalars().all()
    assert any((e.after or {}).get("confirmed_bulk") for e in events)


async def test_low_confidence_ai_rows_are_decided_one_by_one(client):
    h = await login(client)
    job = await upload(client, h, (MEMO_DOCX.name, MEMO_DOCX.read_bytes()), ai="false", review_threshold=0.95)
    rows = (await _rows(client, h, job["id"], method="ai"))["items"]
    assert all(r["low_confidence"] for r in rows)  # the heuristic reads the memo's table at 0.9
    r = await _decide(client, h, job["id"], [{"row_id": x["id"], "action": "accept"} for x in rows[:2]], True)
    assert r.status_code == 422 and "one at a time" in r.text
    r = await _decide(client, h, job["id"], [{"row_id": rows[0]["id"], "action": "accept"}])
    assert r.status_code == 200 and r.json()["saved"] == 1
