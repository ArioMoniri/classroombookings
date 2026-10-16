"""P19-T2 "Tercih ekle" on the real 2026 Bahar list (the shared published week-3 database of
``tests/test_p19_moderation.py``; every test works on a private copy).

Real row: R601 PTL 102 §1 (52 students), the department asked for C 601 (72 seats; the planner's definitive room,
LOCKED). Its primary instructor logs in as an academician (TEACHER) linked to the instructor record and prefers
C 301 (72 seats as well). (R120 PTL 204 §1 was the first pick: the bridge solves it with §2 as one 51-student joint
lecture, which neither C 403 nor C 404 seats.)

Q12: the department form is the official request; the academician's wish is a lower-ranked soft preference that
waits for coordinator review. The tests pin: never hard / untargeted / structural, only the caller's own classes,
the rule ranks the department's room first (proved with the solver), coordinators see it in their read models,
acceptance takes effect at the next solve (the bridge reads it), a rejection reaches the academician with its
reason through notify_dispatch, every step is audited, every refusal has a Turkish and an English text.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.core import db as dbmod
from app.models import (
    AuditEvent,
    ConstraintRow,
    InAppNotification,
    Instructor,
    MeetingRequest,
    NotificationOutbox,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
)
from httpx import AsyncClient
from sqlalchemy import select

from tests.crbs_support import make_user
from tests.test_p19_moderation import real, workdir  # noqa: F401  (shared real-data fixture)

API = "/api/v1"
ROW = 601  # PTL 102 §1


async def _row(term_id: int, row: int) -> tuple[int, int, list[int]]:
    """(request id, primary instructor id, requested room ids) of a Bahar row."""
    async with dbmod.get_session_factory()() as s:
        mr = (
            await s.execute(
                select(MeetingRequest)
                .join(Section, Section.id == MeetingRequest.section_id)
                .where(Section.term_id == term_id, MeetingRequest.source_row_index == row)
            )
        ).scalar_one()
        iid = (
            await s.execute(
                select(SectionInstructor.instructor_id).where(
                    SectionInstructor.section_id == mr.section_id, SectionInstructor.role == "PRIMARY"
                )
            )
        ).scalar_one()
        return mr.id, int(iid), [int(x) for x in mr.requested_room_ids or []]


async def _room(code: str) -> int:
    async with dbmod.get_session_factory()() as s:
        return int((await s.execute(select(Room.id).where(Room.code == code))).scalar_one())


async def _teacher(c: AsyncClient, h: dict[str, str], instructor_id: int, email: str) -> tuple[int, dict[str, str]]:
    uid, headers = await make_user(c, h, email, role="TEACHER")
    async with dbmod.get_session_factory()() as s:
        ins = await s.get(Instructor, instructor_id)
        assert ins is not None
        ins.user_id = uid
        await s.commit()
    return uid, headers


def _tr_en(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    d = r.json()["detail"]
    assert d["code"] == code and d["message"] and d["message_tr"], d
    return dict(d)


async def test_tercih_ekle_is_soft_targeted_lower_ranked_and_reviewed(real: dict[str, Any]) -> None:  # noqa: F811
    from app.services.solver_bridge import build_solver_input
    from app.solver import Constraint, SolverInput, solve

    c, h, tid = real["client"], real["admin"], real["term_id"]
    rid, iid, dept = await _row(tid, ROW)
    c601, c301 = await _room("C601"), await _room("C301")  # the department's room, the wished room
    assert dept == [c601]  # the department form asked for C 601 (Bahar R601 "Derslik Talebi")
    uid, teacher = await _teacher(c, h, iid, "ptl.hoca@uni.edu.tr")
    _pid, planner = await make_user(c, h, "koordinator.t2@uni.edu.tr", role="PLANNER")

    me = (await c.get(f"{API}/moderation/me", headers=teacher)).json()
    assert me["can_add_preference"] is True and me["preferences"] == {"pending": 0, "accepted": 0, "rejected": 0}

    # --- refusals, each in Turkish and English
    base = {"kind": "room", "request_ids": [rid], "rooms": ["c\xa0301"]}  # typed with an NBSP, lower case
    _tr_en(
        await c.post(f"{API}/moderation/me/preferences", json={**base, "hardness": "hard"}, headers=teacher),
        422,
        "hard",
    )
    _tr_en(
        await c.post(f"{API}/moderation/me/preferences", json={**base, "weight": 10}, headers=teacher), 422, "weight"
    )
    _tr_en(
        await c.post(f"{API}/moderation/me/preferences", json={**base, "request_ids": []}, headers=teacher),
        422,
        "no_classes",
    )
    _tr_en(
        await c.post(f"{API}/moderation/me/preferences", json={**base, "kind": "room_pin"}, headers=teacher),
        422,
        "kind",
    )
    _tr_en(
        await c.post(f"{API}/moderation/me/preferences", json={**base, "kind": "capacity"}, headers=teacher),
        422,
        "kind",
    )
    _tr_en(
        await c.post(
            f"{API}/moderation/me/preferences", json={**base, "request_ids": [real["phar240"]]}, headers=teacher
        ),
        403,
        "not_yours",
    )
    _tr_en(
        await c.post(
            f"{API}/moderation/me/preferences",
            json={"kind": "time", "request_ids": [rid], "not_before": "10.10"},
            headers=teacher,
        ),
        422,
        "fixed_by_department",  # the day and time are fixed by the department form
    )
    _tr_en(
        await c.post(f"{API}/moderation/me/preferences", json={**base, "rooms": ["C 601"]}, headers=teacher),
        422,
        "already_requested",
    )
    _tr_en(
        await c.post(f"{API}/moderation/me/preferences", json={**base, "rooms": ["Z 999"]}, headers=teacher),
        422,
        "unknown_room",
    )
    _sid, stranger = await make_user(c, h, "bagsiz.hoca@uni.edu.tr", role="TEACHER")
    _tr_en(await c.post(f"{API}/moderation/me/preferences", json=base, headers=stranger), 403, "not_linked")
    assert (await c.get(f"{API}/moderation/me/preferences", headers=stranger)).json()["linked"] is False

    # --- the wish: soft, targeted, the department's room first, switched off until reviewed
    r = await c.post(
        f"{API}/moderation/me/preferences", json={**base, "note": "Projeksiyonlu sınıf daha uygun"}, headers=teacher
    )
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["status"] == "pending" and len(sub["items"]) == 1 and sub["effective"]["tr"]
    item = sub["items"][0]
    cid = item["id"]
    assert item["kind"] == "room_preference" and item["hardness"] == "soft" and item["weight"] == 1
    assert item["params"] == {"event_ids": [rid], "room_ids": [c601, c301]}
    assert item["wish"]["rooms"] == ["C 301"] and item["department"]["rooms"] == ["C 601"]
    assert item["labels"] == ["PTL 102 §1"] and item["rank"] == "below_department"
    assert item["text"]["tr"] == "PTL 102 §1: oda tercihi C 301"
    assert item["text"]["en"] == "PTL 102 §1: room preference C 301"
    async with dbmod.get_session_factory()() as s:
        row = await s.get(ConstraintRow, cid)
        assert row is not None and row.source == "TEACHER" and row.enabled is False
        assert row.created_by == uid and row.source_ref["review"] == "pending"
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "preference.submit"))).scalar_one()
        assert ev.actor_id == uid and ev.after["constraint_ids"] == [cid]
    mine = (await c.get(f"{API}/moderation/me/preferences", params={"term_id": tid}, headers=teacher)).json()
    assert mine["counts"]["pending"] == 1 and mine["items"][0]["id"] == cid

    # --- coordinators see it: Tercihler (/constraints), the review list, Kişiler and Eşleşmeler
    rules = (await c.get(f"{API}/constraints", params={"term_id": tid}, headers=planner)).json()
    assert any(x["id"] == cid and x["source"] == "TEACHER" and not x["enabled"] for x in rules)
    review = (
        await c.get(f"{API}/terms/{tid}/moderation/teacher-preferences", params={"status": "pending"}, headers=planner)
    ).json()
    assert review["counts"]["pending"] == 1 and review["items"][0]["instructor"]["id"] == iid
    assert review["items"][0]["note"] == "Projeksiyonlu sınıf daha uygun"
    people = (await c.get(f"{API}/terms/{tid}/moderation/people", params={"q": "PTL 102"}, headers=planner)).json()
    assert next(p for p in people["items"] if p["id"] == iid)["pending_preferences"] == 1
    m = (await c.get(f"{API}/terms/{tid}/moderation/matchings/{rid}", headers=planner)).json()
    assert [w["id"] for w in m["teacher_preferences"]] == [cid] and m["teacher_preferences"][0]["status"] == "pending"
    # the academician sees it on their own matching too; never someone else's review list
    own = (await c.get(f"{API}/terms/{tid}/moderation/teacher-preferences", headers=teacher)).json()
    assert [x["id"] for x in own["items"]] == [cid]

    # a pending wish is switched on by its decision only (the academician is told), not through /constraints
    _tr_en(await c.put(f"{API}/constraints/{cid}", json={"enabled": True}, headers=planner), 409, "review_first")

    # --- pending: the bridge does not read it
    async with dbmod.get_session_factory()() as s:
        probe = ScheduleRun(term_id=tid, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]})
        inp, _members = await build_solver_input(s, probe)
        assert cid not in {k.id for k in inp.constraints}

    # --- the coordinator accepts; the academician cannot decide
    assert (
        await c.post(f"{API}/moderation/preferences/{cid}/decide", json={"decision": "accept"}, headers=teacher)
    ).status_code == 403
    r = await c.post(f"{API}/moderation/preferences/{cid}/decide", json={"decision": "accept"}, headers=planner)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "accepted" and out["decided_ids"] == [cid] and out["notified"] is True
    _tr_en(
        await c.post(
            f"{API}/moderation/preferences/{cid}/decide", json={"decision": "reject", "reason": "x"}, headers=planner
        ),
        409,
        "decided",
    )
    # it acts at the next solve: the bridge reads it as a soft targeted rule (weight 1)
    async with dbmod.get_session_factory()() as s:
        probe = ScheduleRun(term_id=tid, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]})
        inp, members = await build_solver_input(s, probe)
        mine_rule = next(k for k in inp.constraints if k.id == cid)
        assert mine_rule.kind == "room_preference" and mine_rule.hard is False and mine_rule.weight == 1
        head = {mm: hd for hd, ms in members.items() for mm in ms}.get(rid, rid)
        ev_ = next(e for e in inp.events if e.id == head)
        assert mine_rule.params["room_ids"] == [c601, c301] and head in mine_rule.params["event_ids"]
        rooms = {r.id: r for r in inp.rooms}
        # the changes-since-publish list names it (it changes the next solve)
        ch = (
            await c.get(f"{API}/terms/{tid}/changes-since-publish", params={"kinds": "preference"}, headers=planner)
        ).json()
        assert any(it["action"] == "preference.accept" and it["request_ids"] == [rid] for it in ch["items"])
        bell = list((await s.execute(select(InAppNotification).where(InAppNotification.user_id == uid))).scalars())
        assert [b.kind for b in bell] == ["preference.accepted"]

    # --- lower rank, proved with the solver on the class's own event and the two real rooms (unlocked, so the
    # solver may choose): the department's C 601 wins over the wished C 301; with no department ask the wish wins
    free = replace(
        ev_,
        locked=None,
        required_room_ids=frozenset(),
        forbidden_room_ids=frozenset(),
        cohort_keys=frozenset(),
        instructor_keys=frozenset(),
    )
    pair = (rooms[c301], rooms[c601])  # the wished room first, so the order of the rooms cannot decide it
    base_inp = SolverInput(
        rooms=pair,
        events=(replace(free, preferred_room_ids=(c601,)),),
        constraints=(mine_rule,),
        weeks=tuple(sorted(free.weeks)) or (3,),
        time_limit_s=10,
        workers=1,
    )
    res = solve(base_inp)
    assert res.status in ("OPTIMAL", "FEASIBLE") and res.assignments[0].room_ids == (c601,), res
    only_wish = Constraint("room_preference", {"event_ids": [free.id], "room_ids": [c301]}, False, 1, cid)
    res2 = solve(replace(base_inp, events=(replace(free, preferred_room_ids=()),), constraints=(only_wish,)))
    assert res2.assignments[0].room_ids == (c301,), res2

    # --- the wish was reviewed for this term: copying the term's rules to another term leaves it out
    r = await c.post(
        f"{API}/studio/constraints/copy",
        json={"to_term_id": real["guz_id"], "from_term_id": tid, "dry_run": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    copied = {it["source_id"] for bucket in ("will_match", "needs_review", "cannot_match") for it in r.json()[bucket]}
    assert cid not in copied

    # --- a second wish is rejected with a reason: the academician is told why (in-app + e-mail outbox)
    r = await c.post(
        f"{API}/moderation/me/preferences",
        json={"kind": "building", "request_ids": [rid], "buildings": ["a blok"]},
        headers=teacher,
    )
    assert r.status_code == 201, r.text
    b = r.json()["items"][0]
    assert b["params"] == {"event_ids": [rid], "buildings": ["C", "A"]}  # the department's C first
    bid = b["id"]
    _tr_en(
        await c.post(f"{API}/moderation/preferences/{bid}/decide", json={"decision": "reject"}, headers=planner),
        422,
        "reason_required",
    )
    r = await c.post(
        f"{API}/moderation/preferences/{bid}/decide",
        json={"decision": "reject", "reason": "A blokta laboratuvar yok", "reason_code": "capacity"},
        headers=planner,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    mine = (await c.get(f"{API}/moderation/me/preferences", headers=teacher)).json()
    rej = next(x for x in mine["items"] if x["id"] == bid)
    assert (
        rej["status"] == "rejected" and rej["reason"] == "A blokta laboratuvar yok" and rej["reason_code"] == "capacity"
    )
    assert mine["counts"] == {"pending": 0, "accepted": 1, "rejected": 1}
    async with dbmod.get_session_factory()() as s:
        row = await s.get(ConstraintRow, bid)
        assert row is not None and row.enabled is False
        bell = list(
            (
                await s.execute(
                    select(InAppNotification).where(
                        InAppNotification.user_id == uid, InAppNotification.kind == "preference.rejected"
                    )
                )
            ).scalars()
        )
        assert len(bell) == 1 and "A blokta laboratuvar yok" in (bell[0].body or "")
        assert bell[0].data and bell[0].data["reason"] == "A blokta laboratuvar yok"
        mail = list(
            (
                await s.execute(select(NotificationOutbox).where(NotificationOutbox.kind == "preference_rejected"))
            ).scalars()
        )
        assert len(mail) == 1
        acts = [
            a
            for a in (
                await s.execute(
                    select(AuditEvent.action).where(AuditEvent.action.startswith("preference.")).order_by(AuditEvent.id)
                )
            ).scalars()
        ]
        assert acts == ["preference.submit", "preference.accept", "preference.submit", "preference.reject"]
        rej_ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "preference.reject"))).scalar_one()
        assert rej_ev.reason == "A blokta laboratuvar yok"

    # --- withdraw: only a pending wish, only by its author
    r = await c.post(
        f"{API}/moderation/me/preferences",
        json={
            "kind": "room_preference",
            "section_id": None,
            "request_ids": [rid],
            "room_ids": [c301],
            "rooms": ["C 302"],
        },
        headers=teacher,
    )
    assert r.status_code == 201, r.text
    wid = r.json()["items"][0]["id"]
    assert (await c.delete(f"{API}/moderation/me/preferences/{wid}", headers=stranger)).status_code == 404
    _tr_en(await c.delete(f"{API}/moderation/me/preferences/{cid}", headers=teacher), 409, "decided")
    assert (await c.delete(f"{API}/moderation/me/preferences/{wid}", headers=teacher)).status_code == 204
    async with dbmod.get_session_factory()() as s:
        assert await s.get(ConstraintRow, wid) is None
        assert (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "preference.withdraw"))
        ).scalar_one().actor_id == uid
