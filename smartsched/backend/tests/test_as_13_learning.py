"""AS-13 / audit RF-07: learning versions, revert, nightly refresh, calibration drafts, per-habit controls, the
planning-audit extractor and backtest **B4**, on the real Bahar 2026 + Güz 2026 planning lists (the shared learning
template of ``tests/test_p19_learning.py``).

* two refreshes give two versions with a correct diff; a revert restores the prior set byte for byte (checksum)
  and holds until the next manual refresh; accepted rules are untouched;
* B4: priors learned from Bahar only -> Güz building suggestions precision >= 0.8, no cross-season room / tag;
* a planning-audit move is learned once (not also from the parent-run comparison);
* a habit can be disabled, corrected or tuned (RF-07); calibration proposes drafts only an admin applies;
* the nightly job refreshes the active term at 03:15 Istanbul and skips a pinned term.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import AuditEvent, ConstraintRow, LearnedObservation, LearnedPrior, LearningVersion, Term
from app.services import backtest as bt
from app.services import learning_versions as lv
from sqlalchemy import func, select, update

from tests.test_p19_learning import _course_id, _pick, _session, _suggestions, env  # noqa: F401

API = "/api/v1"


async def _refresh(env: Any, term_id: int) -> dict:  # noqa: F811
    r = await env.client.post(f"{API}/learning/refresh", json={"term_id": term_id}, headers=env.planner)
    assert r.status_code == 200, r.text
    return r.json()


async def test_as_13_versions_diff_and_byte_for_byte_revert(env):  # noqa: F811
    first = await _refresh(env, env.guz)
    v1 = first["version"]
    assert v1["number"] == 1 and v1["trigger"] == "manual" and v1["priors"] > 0 and v1["suggestible"] > 0
    # new evidence: a planner correction that makes one more suggestion (lower one prior's confidence instead,
    # deterministically: hide the observations of one suggestible subject)
    async with _session() as s:
        p = (
            await s.execute(
                select(LearnedPrior)
                .where(LearnedPrior.term_id == env.guz, LearnedPrior.suggestible.is_(True))
                .order_by(LearnedPrior.id)
                .limit(1)
            )
        ).scalar_one()
        scope = lv.scope_key(p.subject_type, p.subject_key, p.attribute, p.value)
        await s.execute(
            update(LearnedObservation)
            .where(
                LearnedObservation.subject_type == p.subject_type,
                LearnedObservation.subject_key == p.subject_key,
                LearnedObservation.attribute == p.attribute,
                LearnedObservation.value == p.value,
            )
            .values(sign=-1)
        )
        await s.commit()
    second = await _refresh(env, env.guz)
    v2 = second["version"]
    assert v2["number"] == 2 and scope in {d["scope"] for d in v2["diff"]["dropped"]}
    assert v2["diff"]["counts"]["dropped"] >= 1 and v2["checksum"] != v1["checksum"]
    listed = (await env.client.get(f"{API}/learning/versions", params={"term_id": env.guz}, headers=env.planner)).json()
    assert [v["number"] for v in listed["versions"]] == [2, 1] and listed["pinned_version_id"] is None
    # a planner may not revert; an admin may
    r = await env.client.post(f"{API}/learning/versions/{v1['id']}/revert", headers=env.planner)
    assert r.status_code == 403
    async with _session() as s:
        rules_before = (await s.execute(select(func.count(ConstraintRow.id)))).scalar_one()
    r = await env.client.post(f"{API}/learning/versions/{v1['id']}/revert", headers=env.admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["identical"] is True and out["version"]["checksum"] == v1["checksum"]
    assert out["version"]["trigger"] == "revert" and out["version"]["restored_from"] == 1
    async with _session() as s:
        assert lv.checksum(await lv.prior_rows(s, env.guz)) == v1["checksum"]
        assert (await s.execute(select(func.count(ConstraintRow.id)))).scalar_one() == rules_before
        assert (await s.execute(select(AuditEvent).where(AuditEvent.action == "learning.version_revert"))).scalar_one()
    # reading suggestions does not recompute over the reverted set (pinned) ...
    await _suggestions(env, env.guz, state="all")
    async with _session() as s:
        assert lv.checksum(await lv.prior_rows(s, env.guz)) == v1["checksum"]
        assert await lv.pinned(s, env.guz) == v1["id"]
    # ... until the next manual refresh
    third = await _refresh(env, env.guz)
    assert third["version"]["checksum"] == v2["checksum"]
    async with _session() as s:
        assert await lv.pinned(s, env.guz) is None


async def test_as_13_b4_bahar_only_holdout(env):  # noqa: F811
    async with _session() as s:
        r = await bt.b4_learning_holdout(s)
        await s.rollback()
    assert r.passed, r.metrics
    assert r.metrics["precision"] >= 0.8 and r.metrics["cross_season_room_or_tag"] == 0
    assert r.metrics["building_suggestions"] >= 5


async def test_as_13_planning_audit_move_is_learned_once(env):  # noqa: F811
    """A manual move recorded in the planning audit becomes move_to / move_away observations from
    ``audit_events``; the same assignment is not learned again from the parent-run comparison."""
    from app.models import Assignment, MeetingRequest, Room, ScheduleRun, Section
    from app.services import learning_extract

    async with _session() as s:
        mr = (
            await s.execute(
                select(MeetingRequest)
                .join(Section, Section.id == MeetingRequest.section_id)
                .where(
                    Section.term_id == env.bahar,
                    MeetingRequest.status == "LOCKED",
                    MeetingRequest.start_period.is_not(None),
                )
                .order_by(MeetingRequest.id)
                .limit(1)
            )
        ).scalar_one()
        rooms = list((await s.execute(select(Room).where(Room.capacity >= 200).order_by(Room.code))).scalars())
        target = rooms[0] if rooms else (await s.execute(select(Room).order_by(Room.capacity.desc()))).scalars().first()
        parent = ScheduleRun(term_id=env.bahar, kind="COURSE", horizon="TERM", status="FEASIBLE")
        s.add(parent)
        await s.flush()
        child = ScheduleRun(
            term_id=env.bahar, kind="COURSE", horizon="TERM", status="FEASIBLE", parent_run_id=parent.id
        )
        s.add(child)
        await s.flush()
        old_rooms = list(mr.definitive_room_ids or [])
        s.add(
            Assignment(
                run_id=parent.id,
                meeting_request_id=mr.id,
                day=mr.day or 1,
                start_period=mr.start_period,
                end_period=mr.end_period,
                room_ids=old_rooms,
                weeks=[1],
            )
        )
        a = Assignment(
            run_id=child.id,
            meeting_request_id=mr.id,
            day=mr.day or 1,
            start_period=mr.start_period,
            end_period=mr.end_period,
            room_ids=[target.id],
            weeks=[1],
            origin="MANUAL",
        )
        s.add(a)
        await s.flush()
        s.add(
            AuditEvent(
                ts=datetime(2026, 2, 20, 10, 0),
                action="assignment.move",
                entity_type="assignment",
                entity_id=str(a.id),
                term_id=env.bahar,
                before={"meeting_request_id": mr.id, "room_ids": old_rooms, "run_id": child.id},
                after={"meeting_request_id": mr.id, "room_ids": [target.id], "run_id": child.id},
            )
        )
        await s.commit()
        await learning_extract.extract(s)
        await s.commit()
        audit_rows = (
            await s.execute(select(func.count()).where(LearnedObservation.source_table == "audit_events"))
        ).scalar_one()
        assignment_rows = (
            await s.execute(
                select(func.count()).where(
                    LearnedObservation.source_table == "assignments", LearnedObservation.source_id == a.id
                )
            )
        ).scalar_one()
    assert audit_rows > 0 and assignment_rows == 0


async def test_as_13_habit_controls_rf07(env):  # noqa: F811
    await _refresh(env, env.guz)
    async with _session() as s:
        p = (
            await s.execute(
                select(LearnedPrior)
                .where(
                    LearnedPrior.term_id == env.guz,
                    LearnedPrior.suggestible.is_(True),
                    LearnedPrior.attribute == "building",
                )
                .order_by(LearnedPrior.id)
                .limit(1)
            )
        ).scalar_one()
    pid = p.id
    r = await env.client.put(
        f"{API}/learning/priors/{pid}/habit", json={"state": "disabled", "reason": "yanlış"}, headers=env.planner
    )
    assert r.status_code == 403
    r = await env.client.put(
        f"{API}/learning/priors/{pid}/habit", json={"state": "disabled", "reason": "yanlış"}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    async with _session() as s:
        row = await s.get(LearnedPrior, pid)
        assert row is not None and row.suggestible is False and row.evidence["habit"]["state"] == "disabled"
    # tune: the weight an accept uses
    r = await env.client.put(
        f"{API}/learning/priors/{pid}/habit", json={"state": "tuned", "weight": 3}, headers=env.admin
    )
    assert r.status_code == 200 and r.json()["override"]["weight"] == 3
    async with _session() as s:
        assert (await s.get(LearnedPrior, pid)).suggestible is True  # type: ignore[union-attr]
    # correct: the wrong building is not suggested, the right one gets evidence
    other = "C" if p.value != "C" else "A"
    r = await env.client.put(
        f"{API}/learning/priors/{pid}/habit",
        json={"state": "corrected", "value": other, "reason": "taşındı"},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    async with _session() as s:
        assert (await s.get(LearnedPrior, pid)).suggestible is False  # type: ignore[union-attr]
        obs = (
            await s.execute(select(LearnedObservation).where(LearnedObservation.source_table == "habit_corrections"))
        ).scalar_one()
        assert (obs.value, obs.kind, obs.subject_key) == (other, "correction_to", p.subject_key)
    habits = (await env.client.get(f"{API}/learning/habits", headers=env.planner)).json()
    assert habits[0]["state"] == "corrected" and "|building|" in habits[0]["scope"]
    r = await env.client.put(f"{API}/learning/priors/{pid}/habit", json={"state": None}, headers=env.admin)
    assert r.status_code == 200 and r.json()["override"] is None
    r = await env.client.put(
        f"{API}/learning/priors/{pid}/habit", json={"state": "corrected", "value": p.value}, headers=env.admin
    )
    assert r.status_code == 422 and r.json()["detail"]["message_tr"]


async def test_as_13_calibration_drafts_need_an_admin(env):  # noqa: F811
    out = (await env.client.get(f"{API}/learning/calibration", headers=env.admin)).json()
    assert out["proposals"] == [] and out["confidence"] in ("none", "low", "medium")
    r = await env.client.post(
        f"{API}/learning/calibration/apply", json={"attribute": "building", "min_confidence": 0.8}, headers=env.admin
    )
    assert r.status_code == 200 and r.json()["applied"] == {"building": 0.8}
    await _refresh(env, env.guz)
    async with _session() as s:
        low = (
            await s.execute(
                select(func.count()).where(
                    LearnedPrior.term_id == env.guz,
                    LearnedPrior.attribute == "building",
                    LearnedPrior.suggestible.is_(True),
                    LearnedPrior.confidence < 0.8,
                )
            )
        ).scalar_one()
    assert low == 0
    r = await env.client.post(
        f"{API}/learning/calibration/apply", json={"attribute": "nonsense", "min_confidence": 0.8}, headers=env.admin
    )
    assert r.status_code == 422


def test_as_13_beta_and_schedule():
    assert lv.beta_summary(0, 0)["mean"] == 0.5
    assert lv.beta_summary(1, 9)["mean"] < 0.2
    assert lv.seconds_until(datetime(2026, 10, 18, 3, 0)) == 15 * 60
    assert lv.seconds_until(datetime(2026, 10, 18, 3, 16)) == 24 * 3600 - 60


async def test_as_13_nightly_refresh_active_term_and_pin(env):  # noqa: F811
    async with _session() as s:
        await s.execute(update(Term).where(Term.id == env.guz).values(is_active=True))
        await s.commit()
    out = await lv.nightly_once()
    assert out["term_id"] == env.guz and out["version"] == 1
    async with _session() as s:
        v = (await s.execute(select(LearningVersion).where(LearningVersion.term_id == env.guz))).scalar_one()
        assert v.trigger == "nightly"
    r = await env.client.post(f"{API}/learning/versions/{v.id}/revert", headers=env.admin)
    assert r.status_code == 200
    assert (await lv.nightly_once())["skipped"] == "pinned"
    r = await env.client.put(f"{API}/learning/settings", json={"nightly_refresh": False}, headers=env.admin)
    assert r.status_code == 200
    assert (await lv.nightly_once())["skipped"] == "off"
