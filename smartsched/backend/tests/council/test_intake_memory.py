"""Intake memory (owner request 2026-10-15): review decisions are remembered per file signature in the learning
lane's tables and offered again, visibly marked, on the next matching upload; a memory reset removes them.

The Bahar list is read on the general path (``mode=general``, high review threshold), so its column mappings are
review items; the fast path has no mapping to remember."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import AuditEvent, LearnedObservation, User
from app.services import learning
from app.services.learning import recompute_priors
from app.workers import queue as qmod
from sqlalchemy import select

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST, EN_CSV
from tests.council.test_formats_api import upload

GENERAL = {"mode": "general", "review_threshold": 0.99}


async def _review(client, h, job_id: int) -> dict:
    r = await client.get(f"/api/v1/council/jobs/{job_id}/review", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _mappings(review: dict) -> dict[str, dict]:
    return {it["id"]: it for it in review["items"] if it["kind"] == "mapping"}


async def test_a_reviewed_mapping_is_remembered_for_the_same_file_and_reset_forgets_it(client):
    h = await login(client)
    job1 = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), **GENERAL)
    assert job1["files"][0]["route"] == "general"
    maps = _mappings(await _review(client, h, job1["id"]))
    assert maps, "the general path asks about at least one column of the Bahar list"
    item = next(iter(maps.values()))
    new_field = next(f for f in item["options"] if f and f != (item["current"] or {}).get("field"))
    other = [it for it in maps.values() if it["id"] != item["id"]][:3]
    decisions = [{"id": item["id"], "action": "edit", "value": {"field": new_field}}]
    decisions += [{"id": it["id"], "action": "accept"} for it in other]
    r = await client.post(f"/api/v1/council/jobs/{job1['id']}/review", headers=h, json={"decisions": decisions})
    body = r.json()
    assert r.status_code == 200 and body["saved"] == len(decisions) and body["rerun_queued"] is True
    assert body["status"] == "RUNNING"  # the re-read runs on the job queue
    await qmod.get_queue().wait_idle(600)
    assert (await _review(client, h, job1["id"]))["status"] in ("REVIEW", "READY")
    async with get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "council.review"))).scalars().all()
        rows = (
            (await s.execute(select(LearnedObservation).where(LearnedObservation.subject_type == "intake")))
            .scalars()
            .all()
        )
    assert len(ev) == 1 and ev[0].after["decisions"][item["id"]] == {
        "kind": "mapping",
        "action": "edit",
        "value": {"field": new_field},
    }
    assert {r.kind for r in rows} >= {"intake_mapping", "intake_lexicon"} and all(
        r.source_id == job1["id"] for r in rows
    )
    assert all(len(r.subject_key) == 64 and r.weight == 0 for r in rows)  # hashes only, never a scheduling prior

    # the same file in a new job: the coordinator's mapping is pre-filled as a marked suggestion
    job2 = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), **GENERAL)
    maps2 = _mappings(await _review(client, h, job2["id"]))
    again = maps2[item["id"]]
    assert again["decision"] is None and again["blocking"]  # still review-gated
    assert again["suggestion"] == {"action": "edit", "value": {"field": new_field}}
    assert again["remembered"]["job"] == job1["id"] and again["remembered"]["label"].startswith("remembered from 20")
    for it in other:
        assert maps2[it["id"]]["suggestion"] == {"action": "accept"}

    # the learning lane's priors ignore the intake memory (weight 0, no proposal)
    async with get_session_factory()() as s:
        from app.models import Term

        s.add(Term(code="2026-BAHAR", name="Bahar", kind="REGULAR", week_count=14))
        await s.commit()
        term = (await s.execute(select(Term))).scalar_one()
        await recompute_priors(s, term.id)
        await s.commit()

    # a memory reset (learning lane, audited, undoable) forgets it
    async with get_session_factory()() as s:
        admin = (await s.execute(select(User).order_by(User.id))).scalars().first()
        assert admin is not None
        out = await learning.reset(s, admin, scope="all", value=None, reason="intake memory test")
        await s.commit()
    assert out["counts"]["observations"] >= len(rows)
    maps3 = _mappings(await _review(client, h, job2["id"]))
    assert not any("remembered" in it for it in maps3.values())
    async with get_session_factory()() as s:
        admin = (await s.execute(select(User).order_by(User.id))).scalars().first()
        await learning.undo_reset(s, out["id"], admin)
        await s.commit()
    assert _mappings(await _review(client, h, job2["id"]))[item["id"]]["remembered"]["job"] == job1["id"]


async def test_another_file_signature_gets_nothing_from_memory(client):
    h = await login(client)
    job1 = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), **GENERAL)
    maps = _mappings(await _review(client, h, job1["id"]))
    decisions = [{"id": i, "action": "accept"} for i in maps]
    r = await client.post(f"/api/v1/council/jobs/{job1['id']}/review", headers=h, json={"decisions": decisions})
    assert r.status_code == 200
    job2 = await upload(client, h, (EN_CSV.name, EN_CSV.read_bytes()), **GENERAL)  # English headers, one sheet
    review = await _review(client, h, job2["id"])
    assert not any("remembered" in it or "suggestion" in it for it in review["items"])


async def test_viewers_see_review_items_without_file_content(client):
    from app.core.security import hash_password

    h = await login(client)
    job = await upload(client, h, (EN_CSV.name, EN_CSV.read_bytes()), **GENERAL)
    full = await _review(client, h, job["id"])
    assert full["content"] is True and any(it.get("samples") for it in full["items"])
    async with get_session_factory()() as s:
        s.add(User(email="viewer@example.com", password_hash=hash_password("viewer123"), role="VIEWER"))
        await s.commit()
    hv = await login(client, "viewer@example.com", "viewer123")
    red = await _review(client, hv, job["id"])
    assert red["content"] is False and len(red["items"]) == len(full["items"])
    for it in red["items"]:
        assert not {"samples", "text", "texts", "sources", "evidence", "alternatives"} & set(it)
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/review", headers=hv, json={"decisions": [{"id": "x", "action": "accept"}]}
    )
    assert r.status_code == 403
