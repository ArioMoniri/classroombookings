"""Round-1 admin flow loop (docs/testing/flows/rounds/round-1-admin.md), hard-rule integrity on the real Bahar 2026
import ("100/100 on hard rules, or explain the infeasibility").

R1-M-03: ING 302 (100 students, Monday P3-P5) hard-pinned to B 201 (30 seats). Every write path refuses it with
"100 öğrenci 30 kişilik B 201'e sığmaz" (an administrator may keep it with a written reason), the Studio pre-check
names a pre-existing one, and the run explains the left-out class by its own pin (never "rooms that fit are busy").
"""

from __future__ import annotations

from typing import Any

from app.core import db as dbmod
from app.models import AuditEvent, ConstraintRow, Course, MeetingRequest, Section
from app.workers.queue import get_queue
from sqlalchemy import select

from tests import studio_support
from tests.studio_support import room

bahar = studio_support.bahar

SENTENCE = "100 öğrenci 30 kişilik B 201'e sığmaz"


async def _ing302() -> int:
    """The ING 302 meeting of the round-1 report: 100 students, Monday P3-P5."""
    async with dbmod.get_session_factory()() as s:
        rows = (
            await s.execute(
                select(MeetingRequest.id, Section.enrolment, MeetingRequest.requested_capacity)
                .join(Section, Section.id == MeetingRequest.section_id)
                .join(Course, Course.id == Section.course_id)
                .where(Course.code == "ING302", MeetingRequest.day == 1, MeetingRequest.start_period == 3)
                .order_by(MeetingRequest.id)
            )
        ).all()
    hit = [r[0] for r in rows if int(r[1] or r[2] or 0) == 100]
    assert hit, rows
    return hit[0]


def _pin(term_id: int, event_id: int, room_id: int, **extra: Any) -> dict[str, Any]:
    return {
        "term_id": term_id,
        "kind": "room_pin",
        "params": {"event_ids": [event_id], "room_ids": [room_id]},
        "hardness": "hard",
        "weight": 5,
        **extra,
    }


async def test_constraint_api_refuses_an_impossible_hard_pin(bahar):
    c, term = bahar.client, bahar.term_id
    ing, b201, c201 = await _ing302(), (await room("B201")).id, (await room("C201")).id
    for who in (bahar.planner, bahar.admin):
        r = await c.post("/api/v1/constraints", json=_pin(term, ing, b201), headers=who)
        assert r.status_code == 422, r.text
        d = r.json()["detail"]
        assert d["code"] == "capacity" and d["message_tr"] == SENTENCE
        assert d["message_en"] == "100 students do not fit B 201 (30 seats)"
        assert d["classes"][0]["request_id"] == ing
    # a planner's reason is not enough; an administrator's written reason keeps it (audited, on source_ref)
    r = await c.post("/api/v1/constraints", json=_pin(term, ing, b201, reason="Bölüm kararı"), headers=bahar.planner)
    assert r.status_code == 422
    r = await c.post("/api/v1/constraints", json=_pin(term, ing, b201, reason="Bölüm kararı"), headers=bahar.admin)
    assert r.status_code == 201, r.text
    kept = r.json()
    assert "Bölüm kararı" in kept["source_ref"]["capacity_override"]
    async with dbmod.get_session_factory()() as s:
        ev = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "constraint.create", AuditEvent.entity_id == kept["id"])
            )
        ).scalar_one()
        assert "Bölüm kararı" in (ev.reason or "") and "do not fit B 201" in (ev.reason or "")
    # a soft pin is a wish (capacity stays hard in the solver): allowed
    r = await c.post("/api/v1/constraints", json=_pin(term, ing, b201, hardness="soft"), headers=bahar.planner)
    assert r.status_code == 201, r.text
    # editing a fitting pin onto B 201 is refused the same way
    r = await c.post("/api/v1/constraints", json=_pin(term, ing, c201), headers=bahar.planner)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = await c.put(
        f"/api/v1/constraints/{cid}", json={"params": {"event_ids": [ing], "room_ids": [b201]}}, headers=bahar.planner
    )
    assert r.status_code == 422 and r.json()["detail"]["message_tr"] == SENTENCE


async def test_ai_upload_approval_and_copy_refuse_an_impossible_pin(bahar):
    c, term = bahar.client, bahar.term_id
    ing, b201 = await _ing302(), (await room("B201")).id
    prop = {
        "kind": "room_pin",
        "params": {"event_ids": [ing], "room_ids": [b201]},
        "hardness": "hard",
        "weight": 5,
        "nl_text": "ING 302 her zaman B 201'de",
        "source": "UPLOAD",
        "source_ref": {"file": "istekler.xlsx", "row": 4},
    }
    r = await c.post(f"/api/v1/terms/{term}/studio/proposals/accept", json={"proposals": [prop]}, headers=bahar.planner)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == [] and SENTENCE in " ".join(out["rejected"][0]["issues"]), out
    # a pre-existing row (written before the guard) is not copied into another term either
    async with dbmod.get_session_factory()() as s:
        s.add(
            ConstraintRow(
                term_id=term, kind="room_pin", params=prop["params"], hardness="hard", weight=5, source="ADMIN"
            )
        )
        await s.commit()
    r = await c.post(
        "/api/v1/studio/constraints/copy",
        json={"from_term_id": term, "to_term_id": term, "dry_run": True},
        headers=bahar.planner,
    )
    assert r.status_code == 200, r.text
    reasons = [x for b in ("cannot_match",) for it in r.json()[b] for x in it["reasons"]]
    assert any(SENTENCE in x for x in reasons), r.json()


async def _seed_impossible_pin(term: int) -> tuple[int, int]:
    """A rule written before the guard existed (straight into the DB)."""
    ing, b201 = await _ing302(), (await room("B201")).id
    async with dbmod.get_session_factory()() as s:
        row = ConstraintRow(
            term_id=term,
            kind="room_pin",
            params={"event_ids": [ing], "room_ids": [b201]},
            hardness="hard",
            weight=5,
            source="ADMIN",
        )
        s.add(row)
        await s.commit()
        return row.id, ing


async def test_precheck_names_a_pre_existing_impossible_pin(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    cid, ing = await _seed_impossible_pin(bahar.term_id)
    await c.get(url, headers=h)
    r = await c.put(url, json={"version": 1, "horizon": "WEEK", "horizon_params": {"weeks": [3]}}, headers=h)
    assert r.status_code == 200, r.text
    pre = (await c.post(f"{url}/precheck", headers=h)).json()
    hits = [it for it in pre["items"] if it["group"] == "pin_capacity"]
    assert hits, [(it["group"], it["message"]["tr"]) for it in pre["items"] if it["severity"] == "error"][:10]
    it = hits[0]
    assert it["severity"] == "error" and ing in [x for cl in it["classes"] for x in cl["request_ids"]]
    assert f"#{cid}" in it["message"]["tr"] and SENTENCE in it["message"]["tr"], it["message"]
    assert any(f["option"] == f"rule_off:{cid}" for f in it["fixes"])


async def test_run_explains_the_class_by_its_own_pin(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    cid, ing = await _seed_impossible_pin(bahar.term_id)
    await c.get(url, headers=h)
    r = await c.put(url, json={"version": 1, "horizon": "WEEK", "horizon_params": {"weeks": [3]}}, headers=h)
    assert r.status_code == 200, r.text
    r = await c.post(
        f"{url}/generate", json={"params": {"solver": "cpsat", "time_limit_s": 20, "workers": 2, "seed": 1}}, headers=h
    )
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    await get_queue().wait_idle(timeout=600)
    run = (await c.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["status"] == "FEASIBLE_PARTIAL" and run["hard_score"] == 100, (run["status"], run.get("error"))
    mine = [d for d in run["diagnosis"] if ing in (d.get("event_ids") or []) and len(d["event_ids"]) == 1]
    assert mine, "the pinned class has its own explanation"
    assert {d["code"] for d in mine} == {"no_room"}, [(d["code"], d["message"]) for d in mine]
    tr = mine[0]["text"]["tr"]
    assert f"kesin kural #{cid} onu yalnız B 201'e sabitliyor" in tr and SENTENCE in tr, tr
    assert "o saatte dolu" not in tr
