"""P19-00a / review 2026-10-15 D1: an untargeted *soft* structural rule (capacity, room_tags, fixed_time, room_pin,
room_forbid) switches the solver's implicit hard rule off for every class: 180 students in a 50-seat room would be
reported OPTIMAL with hard 100. ``POST /constraints`` refuses it (422) unless a ``planning.admin`` gives a reason,
which is audited. Targeted soft rules (one class, one cohort) stay a normal planner decision.

Runs on the real Bahar 2026 import (``tests/crbs_env``); MAT 112 is a real Bahar planning-list course.
"""

from __future__ import annotations

import pytest
from app.core import db as dbmod
from app.models import AuditEvent, Course, MeetingRequest, Section
from app.services.constraint_guard import STRUCTURAL_KINDS, guard_rule, is_waiver
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401

C = "/api/v1/constraints"


async def _mat112_request(term_id: int) -> int:
    async with dbmod.get_session_factory()() as s:
        q = (
            select(MeetingRequest.id)
            .join(Section, Section.id == MeetingRequest.section_id)
            .join(Course, Course.id == Section.course_id)
            .where(Section.term_id == term_id, Course.code == "MAT112")
            .order_by(MeetingRequest.id)
        )
        mid = (await s.execute(q)).scalars().first()
    assert mid is not None, "MAT 112 is in the Bahar planning list"
    return mid


@pytest.mark.parametrize("kind", sorted(STRUCTURAL_KINDS))
async def test_planner_cannot_soften_a_structural_rule_for_everyone(env, kind):  # noqa: F811
    body = {"term_id": env.term_id, "kind": kind, "params": {}, "hardness": "soft", "weight": 5}
    r = await env.client.post(C, json=body, headers=env.planner)
    assert r.status_code == 422, r.text
    assert "structural" in str(r.json()["detail"])
    # a reason does not help a planner
    r = await env.client.post(C, json={**body, "reason": "Bahar sınav haftası"}, headers=env.planner)
    assert r.status_code == 422, r.text


async def test_admin_waiver_needs_a_reason_and_is_audited(env):  # noqa: F811
    body = {"term_id": env.term_id, "kind": "capacity", "params": {}, "hardness": "soft", "weight": 3}
    r = await env.client.post(C, json=body, headers=env.admin)
    assert r.status_code == 422, r.text
    r = await env.client.post(C, json={**body, "reason": "   "}, headers=env.admin)
    assert r.status_code == 422, r.text
    reason = "Dekanlık onayı: İÖ sınıfları için kapasite esnetildi"
    r = await env.client.post(C, json={**body, "reason": reason}, headers=env.admin)
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["source_ref"]["waiver"]["reason"] == reason
    async with dbmod.get_session_factory()() as s:
        ev = (
            await s.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "constraint.waive", AuditEvent.entity_id == str(row["id"])
                )
            )
        ).scalar_one()
    assert ev.reason == reason and ev.term_id == env.term_id
    assert ev.after["kind"] == "capacity" and ev.after["hardness"] == "soft"


async def test_targeted_soft_structural_rule_stays_a_planner_decision(env):  # noqa: F811
    mid = await _mat112_request(env.term_id)
    r = await env.client.post(
        C,
        json={"term_id": env.term_id, "kind": "capacity", "params": {"event_ids": [mid]}, "hardness": "soft"},
        headers=env.planner,
    )
    assert r.status_code == 201, r.text
    assert (r.json()["source_ref"] or {}).get("waiver") is None


async def test_update_cannot_turn_the_default_rule_soft(env):  # noqa: F811
    r = await env.client.post(
        C, json={"term_id": env.term_id, "kind": "capacity", "params": {}, "hardness": "hard"}, headers=env.planner
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = await env.client.put(f"{C}/{cid}", json={"hardness": "soft"}, headers=env.planner)
    assert r.status_code == 422, r.text
    # untargeting a targeted soft rule is the same waiver
    mid = await _mat112_request(env.term_id)
    r = await env.client.post(
        C,
        json={"term_id": env.term_id, "kind": "room_tags", "params": {"event_ids": [mid]}, "hardness": "soft"},
        headers=env.planner,
    )
    assert r.status_code == 201, r.text
    r = await env.client.put(f"{C}/{r.json()['id']}", json={"params": {}}, headers=env.planner)
    assert r.status_code == 422, r.text
    # an admin with a reason may
    r = await env.client.put(
        f"{C}/{cid}", json={"hardness": "soft", "reason": "Kurul kararı 2026/14"}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["source_ref"]["waiver"]["reason"] == "Kurul kararı 2026/14"


def test_guard_never_lets_ai_upload_or_learned_rules_waive():
    for source in ("AI", "UPLOAD", "LEARNED"):
        issues = guard_rule("fixed_time", {}, "soft", source=source, may_waive=True, reason="any")
        assert issues and source in issues[0]
    assert guard_rule("fixed_time", {}, "soft", source="ADMIN", may_waive=True, reason="Rektörlük") == []
    assert guard_rule("fixed_time", {}, "hard", source="AI", may_waive=False, reason=None) == []
    assert guard_rule("room_preference", {}, "soft", source="AI", may_waive=False, reason=None) == []
    assert is_waiver("room_pin", {"cohort": "PROG:Psikoloji:Y1"}, "soft") is False
    assert is_waiver("room_pin", {"_source_ref": {"row": 12}}, "soft") is True
