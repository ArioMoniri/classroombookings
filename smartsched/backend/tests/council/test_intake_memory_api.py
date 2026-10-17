"""Intake memory management API (owner request 2026-10-16, batch 4): list what the intake remembers, grouped by
signature with a TR / EN description, and forget one decision or a whole signature (a learning reset of scope
``intake``: audited, undoable for 30 days). Real Bahar list on the general path."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import AuditEvent, LearnedObservation, User
from app.workers import queue as qmod
from sqlalchemy import select

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST
from tests.council.test_formats_api import upload

GENERAL = {"mode": "general", "review_threshold": 0.99}


async def _review(client, h, job_id: int) -> dict:
    r = await client.get(f"/api/v1/council/jobs/{job_id}/review", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _mappings(review: dict) -> dict[str, dict]:
    return {it["id"]: it for it in review["items"] if it["kind"] == "mapping"}


async def _remembered_job(client, h) -> tuple[dict, dict, str, list[dict]]:
    """A Bahar job whose reviewer renamed one column's field and accepted three others."""
    job = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), **GENERAL)
    maps = _mappings(await _review(client, h, job["id"]))
    item = next(iter(maps.values()))
    new_field = next(f for f in item["options"] if f and f != (item["current"] or {}).get("field"))
    other = [it for it in maps.values() if it["id"] != item["id"]][:3]
    decisions = [{"id": item["id"], "action": "edit", "value": {"field": new_field}}]
    decisions += [{"id": it["id"], "action": "accept"} for it in other]
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/review", headers=h, json={"decisions": decisions})
    assert r.status_code == 200, r.text
    await qmod.get_queue().wait_idle(600)
    return job, item, new_field, other


async def _viewer(client) -> dict:
    from app.core.security import hash_password

    async with get_session_factory()() as s:
        s.add(User(email="viewer@example.com", password_hash=hash_password("viewer123"), role="VIEWER"))
        await s.commit()
    return await login(client, "viewer@example.com", "viewer123")


async def test_memory_list_describes_each_decision_grouped_by_signature(client):
    h = await login(client)
    job, item, new_field, other = await _remembered_job(client, h)
    r = await client.get("/api/v1/council/memory", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] is True and body["total"] == len(body["items"]) >= len(other) + 2
    kinds = {it["kind"] for it in body["items"]}
    assert {"intake_mapping", "intake_lexicon"} <= kinds
    col = int(item["column"])
    edited = next(it for it in body["items"] if it["kind"] == "intake_mapping" and it["attribute"] == f"col:{col}")
    assert edited["value"] == new_field and edited["action"] == "edit" and edited["effective"] is True
    assert edited["job_id"] == job["id"] and edited["job_exists"] is True
    assert edited["created_by"]["id"] is not None and edited["created_by"]["name"]
    assert edited["context"]["file"] == BAHAR_LIST.name and edited["context"]["sheet"]
    assert edited["context"]["header"]  # file content: planners see the header text
    assert edited["description"]["en"].startswith(f"{BAHAR_LIST.name} › ")
    assert f"column {col + 1} '" in edited["description"]["en"] and edited["description"]["en"].endswith(new_field)
    assert f"{col + 1}. sütun '" in edited["description"]["tr"]
    lex = next(it for it in body["items"] if it["kind"] == "intake_lexicon")
    assert lex["description"]["tr"].startswith("'") and lex["description"]["en"].startswith("Header '")
    # one group per signature: the mappings of one sheet share a grid signature
    groups = {g["signature"]: g for g in body["groups"]}
    grid = groups[edited["signature"]]
    assert grid["group"] == "layout" and grid["count"] >= len(other) + 1 and edited["id"] in grid["ids"]
    assert grid["label"]["tr"].startswith(f"{BAHAR_LIST.name} › ") and grid["jobs"] == [job["id"]]
    assert len(edited["signature"]) == 64

    # filters: signature, kind, job
    r = await client.get("/api/v1/council/memory", headers=h, params={"signature": edited["signature"]})
    assert {it["signature"] for it in r.json()["items"]} == {edited["signature"]}
    r = await client.get("/api/v1/council/memory", headers=h, params={"kind": "intake_lexicon"})
    assert {it["kind"] for it in r.json()["items"]} == {"intake_lexicon"}
    r = await client.get("/api/v1/council/memory", headers=h, params={"job_id": job["id"] + 999})
    assert r.json()["total"] == 0
    r = await client.get("/api/v1/council/memory", headers=h, params={"kind": "nope"})
    assert r.status_code == 422

    # viewers see the list without file content and cannot forget
    hv = await _viewer(client)
    red = (await client.get("/api/v1/council/memory", headers=hv)).json()
    assert red["content"] is False and red["total"] == body["total"]
    for it in red["items"]:
        assert "header" not in it["context"] and "a" not in it["context"]
    r = await client.delete(f"/api/v1/council/memory/{edited['id']}", headers=hv)
    assert r.status_code == 403


async def test_forget_one_and_a_signature_with_audit_and_undo(client):
    h = await login(client)
    job, item, new_field, other = await _remembered_job(client, h)
    body = (await client.get("/api/v1/council/memory", headers=h)).json()
    col = int(item["column"])
    edited = next(it for it in body["items"] if it["kind"] == "intake_mapping" and it["attribute"] == f"col:{col}")
    lex = [it for it in body["items"] if it["kind"] == "intake_lexicon"]

    # forget the edited column: the next matching upload no longer pre-fills it (but still the accepted ones)
    r = await client.delete(f"/api/v1/council/memory/{edited['id']}", headers=h)
    assert r.status_code == 200, r.text
    one = r.json()
    assert one["forgotten"] == 1 and one["ids"] == [edited["id"]] and one["scope"] == "intake"
    assert one["undoable"] is True and one["value"] == f"#{edited['id']}"
    r = await client.delete(f"/api/v1/council/memory/{edited['id']}", headers=h)
    assert r.status_code == 404
    # the lexicon still names the field for that header: forget it too, then the column is not recalled at all
    for it in lex:
        assert (await client.delete(f"/api/v1/council/memory/{it['id']}", headers=h)).status_code == 200
    after = (await client.get("/api/v1/council/memory", headers=h)).json()
    assert edited["id"] not in {it["id"] for it in after["items"]}
    job2 = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), **GENERAL)
    maps2 = _mappings(await _review(client, h, job2["id"]))
    assert "remembered" not in maps2[item["id"]]
    assert all(maps2[it["id"]]["suggestion"] == {"action": "accept"} for it in other)

    # undo (the learning lane's reset undo) brings the column back
    r = await client.post(f"/api/v1/learning/resets/{one['id']}/undo", headers=h)
    assert r.status_code == 200, r.text
    assert _mappings(await _review(client, h, job2["id"]))[item["id"]]["suggestion"] == {
        "action": "edit",
        "value": {"field": new_field},
    }

    # forget the whole signature: nothing of that sheet is offered any more
    r = await client.delete("/api/v1/council/memory", headers=h, params={"signature": edited["signature"]})
    assert r.status_code == 200, r.text
    assert r.json()["forgotten"] >= len(other) + 1
    maps3 = _mappings(await _review(client, h, job2["id"]))
    assert not any(
        it.get("remembered") and it["id"] in {item["id"], *(o["id"] for o in other)} for it in maps3.values()
    )
    r = await client.delete("/api/v1/council/memory", headers=h, params={"signature": edited["signature"]})
    assert r.status_code == 404

    async with get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "council.memory.forget"))).scalars().all()
        hidden = (
            (
                await s.execute(
                    select(LearnedObservation).where(
                        LearnedObservation.subject_key == edited["signature"], LearnedObservation.reset_id.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(ev) == 2 + len(lex) and ev[-1].after["signature"] == edited["signature"]
    assert ev[0].after == {**ev[0].after, "scope": "intake", "row": edited["id"], "rows": 1}
    assert ev[0].actor_id is not None and not hidden
