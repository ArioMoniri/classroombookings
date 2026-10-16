"""Phase 19 backend gaps, moderation side, on the real 2026 Bahar list (the published week-3 run of
``tests/test_p19_moderation.py``, built once and shared; every test works on a private copy):

1. a re-solve from a draft child diffs against the PUBLISHED run that started the chain (``compare_to`` overrides);
2. person- and programme-level priority (P19-P-04): request > section > person > programme, audited, read by the
   bridge;
3. ``GET /terms/{id}/changes-since-publish`` (P19-M-07);
5. ``GET /moderation/me`` and ``GET /moderation/current-term`` for a teacher (no 403 probe).

Real rows: R2 + R1001 MAT 112 §1 and R1022 HEM 236 (the A 204 lock clash: one of them loses), R49 PHY 102 §1,
R545 PHAR 240 §1.
"""

from __future__ import annotations

from typing import Any

from app.core import db as dbmod
from app.models import AuditEvent, Instructor, MeetingRequest, ScheduleRun, Section
from httpx import AsyncClient
from sqlalchemy import func, select

from tests.crbs_support import make_user
from tests.test_p19_moderation import real, workdir  # noqa: F401  (shared real-data fixture)

API = "/api/v1"


async def _resolve(c: AsyncClient, h: dict[str, str], tid: int, body: dict[str, Any]) -> dict[str, Any]:
    r = await c.post(
        f"{API}/terms/{tid}/moderation/resolve", json={"wait": True, "time_limit_s": 30, **body}, headers=h
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


# ------------------------------------------------------------------------------------------- 1. diff baseline


async def test_resolve_from_a_draft_child_diffs_against_the_published_run(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid, base = real["client"], real["admin"], real["term_id"], real["run_id"]
    loser, phy = real["loser"], real["phy102"]
    assert (await c.put(f"{API}/moderation/requests/{loser}/priority", json={"priority": "high"}, headers=h)).is_success
    d1 = await _resolve(c, h, tid, {"base_run_id": base, "changed_request_ids": [loser], "mode": "repair"})
    assert d1["compare_to_run_id"] == base and d1["compared_to"] == "published" and d1["chain"] == [d1["run_id"], base]
    assert loser in {x["request_id"] for x in d1["newly_placed"]}
    # a second step from the DRAFT child: still compared with the published run, both steps' edits in scope
    d2 = await _resolve(c, h, tid, {"base_run_id": d1["run_id"], "changed_request_ids": [phy], "mode": "repair"})
    assert d2["base_run_id"] == d1["run_id"]
    assert d2["compare_to_run_id"] == base and d2["compared_to"] == "published"
    assert d2["chain"] == [d2["run_id"], d1["run_id"], base]
    assert {loser, phy} <= set(d2["changed_request_ids"])
    newly = {x["request_id"]: x for x in d2["newly_placed"]}
    assert loser in newly and newly[loser]["in_scope"]  # placed by step 1, still "new" against the published plan
    assert d2["scores"]["hard"]["before"] == real["base_hard"]
    # compare_to: the last step only (the draft parent), where step 1's placement is no news
    r = await c.get(f"{API}/moderation/runs/{d2['run_id']}/diff", params={"compare_to": d1["run_id"]}, headers=h)
    assert r.status_code == 200, r.text
    only = r.json()
    assert only["compared_to"] == "explicit" and only["compare_to_run_id"] == d1["run_id"]
    assert loser not in {x["request_id"] for x in only["newly_placed"]}
    # the default diff of the stored child is the stored baseline (the same answer as the re-solve)
    r = await c.get(f"{API}/moderation/runs/{d2['run_id']}/diff", headers=h)
    assert r.json()["compare_to_run_id"] == base
    # compare_to must be a finished run of the same term and kind
    assert (await c.get(f"{API}/moderation/runs/{d2['run_id']}/diff?compare_to=999999", headers=h)).status_code == 404
    async with dbmod.get_session_factory()() as s:
        other = ScheduleRun(term_id=real["guz_id"], kind="COURSE", horizon="WEEK", status="OPTIMAL")
        s.add(other)
        await s.commit()
        oid = other.id
    r = await c.get(f"{API}/moderation/runs/{d2['run_id']}/diff?compare_to={oid}", headers=h)
    assert r.status_code == 422
    r = await c.post(
        f"{API}/terms/{tid}/moderation/resolve",
        json={"base_run_id": d1["run_id"], "changed_request_ids": [phy], "compare_to": oid},
        headers=h,
    )
    assert r.status_code == 422


# ------------------------------------------------------------------------------------------- 2. person priority


async def test_person_and_programme_priority_inherit_and_reach_the_bridge(real: dict[str, Any]) -> None:  # noqa: F811
    from app.services.solver_bridge import build_solver_input

    c, h, tid = real["client"], real["admin"], real["term_id"]
    loser, phy, ins = real["loser"], real["phy102"], real["ins_loser"]
    _vid, viewer = await make_user(c, h, "izleyici2@uni.edu.tr", role="VIEWER")
    body = {"term_id": tid, "priority": "Yüksek", "note": "bölüm başkanı"}
    assert (await c.put(f"{API}/moderation/people/{ins}/priority", json=body, headers=viewer)).status_code == 403
    assert (
        await c.put(f"{API}/moderation/people/{ins}/priority", json={"priority": "high"}, headers=h)
    ).status_code == 422  # the term is required
    r = await c.put(f"{API}/moderation/people/{ins}/priority", json=body, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["priority"] == 1 and out["previous"] is None and out["source"] == "person"
    assert loser in out["request_ids"]
    # the matching shows the inherited value and where it came from ("Yüksek · kişiden")
    r = await c.get(f"{API}/terms/{tid}/moderation/matchings/{loser}", headers=h)
    assert r.json()["priority"] == {"value": 1, "source": "person"}
    # programme level for a request whose people have none: PHY 102 §1's programme low
    async with dbmod.get_session_factory()() as s:
        mr = await s.get(MeetingRequest, phy)
        assert mr is not None
        sec = await s.get(Section, mr.section_id)
        assert sec is not None and sec.program_id is not None
        prog = sec.program_id
    r = await c.put(f"{API}/moderation/programs/{prog}/priority", json={"term_id": tid, "priority": -1}, headers=h)
    assert r.status_code == 200 and phy in r.json()["request_ids"]
    r = await c.get(f"{API}/terms/{tid}/moderation/matchings/{phy}", headers=h)
    assert r.json()["priority"] == {"value": -1, "source": "program"}
    listed = (await c.get(f"{API}/terms/{tid}/moderation/priorities", headers=viewer)).json()["items"]
    assert {(i["subject_type"], i["subject_id"], i["priority"]) for i in listed} == {
        ("person", ins, 1),
        ("program", prog, -1),
    }
    assert next(i for i in listed if i["subject_type"] == "person")["name"]
    # the bridge: the loser's event (the joint MAT 112 event takes its members' highest) now carries the person's 1
    async with dbmod.get_session_factory()() as s:
        probe = ScheduleRun(term_id=tid, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]})
        inp, members = await build_solver_input(s, probe)
        head = {m: hd for hd, ms in members.items() for m in ms}
        prio = {e.id: e.priority for e in inp.events}
        assert prio[head.get(loser, loser)] == 1
        assert prio[head.get(phy, phy)] == -1
        acts = {
            (a, e)
            for a, e in (
                await s.execute(
                    select(AuditEvent.action, AuditEvent.term_id).where(
                        AuditEvent.action.in_(["person.priority", "program.priority"])
                    )
                )
            ).all()
        }
        assert acts == {("person.priority", tid), ("program.priority", tid)}
    # more specific wins: a request override of 0 is an explicit Normal; a section's non-zero beats the person
    assert (await c.put(f"{API}/moderation/requests/{loser}/priority", json={"priority": 0}, headers=h)).is_success
    r = await c.get(f"{API}/terms/{tid}/moderation/matchings/{loser}", headers=h)
    assert r.json()["priority"] == {"value": 0, "source": "request"}
    assert (await c.put(f"{API}/moderation/requests/{loser}/priority", json={"priority": None}, headers=h)).is_success
    async with dbmod.get_session_factory()() as s:
        lmr = await s.get(MeetingRequest, loser)
        assert lmr is not None
        lsec = lmr.section_id
    assert (await c.put(f"{API}/moderation/sections/{lsec}/priority", json={"priority": -1}, headers=h)).is_success
    r = await c.get(f"{API}/terms/{tid}/moderation/matchings/{loser}", headers=h)
    assert r.json()["priority"] == {"value": -1, "source": "section"}
    # null clears the person's override
    r = await c.put(f"{API}/moderation/people/{ins}/priority", json={"term_id": tid, "priority": None}, headers=h)
    assert r.json()["priority"] is None and r.json()["previous"] == 1
    listed = (await c.get(f"{API}/terms/{tid}/moderation/priorities?subject=person", headers=h)).json()["items"]
    assert listed == []


# ------------------------------------------------------------------------------------------- 3. staged changes


async def test_changes_since_publish_lists_draft_edits_until_the_next_publish(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid, base = real["client"], real["admin"], real["term_id"], real["run_id"]
    loser, phar, ins = real["loser"], real["phar240"], real["ins_phy102"]
    r = await c.get(f"{API}/terms/{tid}/changes-since-publish", headers=h)
    assert r.status_code == 200 and r.json()["total"] == 0 and r.json()["published_run_id"] == base
    assert (await c.put(f"{API}/moderation/requests/{loser}/priority", json={"priority": 1}, headers=h)).is_success
    assert (
        await c.put(f"{API}/moderation/people/{ins}/priority", json={"term_id": tid, "priority": -1}, headers=h)
    ).is_success
    d1 = await _resolve(c, h, tid, {"base_run_id": base, "changed_request_ids": [loser], "mode": "repair"})
    r = await c.put(f"{API}/moderation/matchings/{phar}", json={"run_id": d1["run_id"], "action": "pin"}, headers=h)
    assert r.status_code == 200, r.text
    ch = (await c.get(f"{API}/terms/{tid}/changes-since-publish", headers=h)).json()
    assert ch["counts"]["priority"] == 2 and ch["counts"]["pin"] == 1 and ch["total"] == 3
    assert ch["items"][0]["kind"] == "pin" and ch["items"][0]["run_id"] == d1["run_id"]  # newest first
    assert ch["items"][0]["labels"] == ["PHAR 240 §1"]
    person = next(it for it in ch["items"] if it["action"] == "person.priority")
    assert real["phy102"] in person["request_ids"] and person["after"]["priority"] == -1
    assert {loser, phar, real["phy102"]} <= set(ch["changed_request_ids"])
    only = (await c.get(f"{API}/terms/{tid}/changes-since-publish?kinds=pin", headers=h)).json()
    assert only["total"] == 1
    # publishing the draft child takes them into the plan: the list starts again empty
    r = await c.post(f"{API}/runs/{d1['run_id']}/activate", headers=h)
    assert r.status_code == 200, r.text
    ch = (await c.get(f"{API}/terms/{tid}/changes-since-publish", headers=h)).json()
    assert ch["published_run_id"] == d1["run_id"] and ch["total"] == 0
    assert (await c.put(f"{API}/moderation/requests/{loser}/priority", json={"priority": None}, headers=h)).is_success
    ch = (await c.get(f"{API}/terms/{tid}/changes-since-publish", headers=h)).json()
    assert ch["total"] == 1 and ch["changed_request_ids"] == [loser]


# ------------------------------------------------------------------------------------------- 5. me + current term


async def test_me_and_the_current_term_for_teachers(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, own = real["client"], real["admin"], real["ins_phar240"]
    r = await c.get(f"{API}/moderation/me", headers=h)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["instructor_id"] is None and me["visibility"] == "all" and me["can_edit"] is True
    uid, teacher = await make_user(c, h, "hoca@uni.edu.tr", role="TEACHER")
    async with dbmod.get_session_factory()() as s:
        ins = await s.get(Instructor, own)
        assert ins is not None
        ins.user_id = uid
        await s.commit()
    me = (await c.get(f"{API}/moderation/me", headers=teacher)).json()
    assert me["instructor_id"] == own and me["instructor_ids"] == [own] and me["visibility"] == "own"
    assert me["can_edit"] is False and me["instructor"]["full_name"]
    assert me["current_term"] is not None and me["current_term"]["id"] in (real["term_id"], real["guz_id"])
    # an unlinked teacher: 200 with null, not a 403 probe
    _uid2, stranger = await make_user(c, h, "misafir2@uni.edu.tr", role="TEACHER")
    me2 = (await c.get(f"{API}/moderation/me", headers=stranger)).json()
    assert me2["instructor_id"] is None and me2["visibility"] == "none"
    # the planning term list stays planning data; the current term is readable by everyone
    assert (await c.get(f"{API}/terms/current", headers=teacher)).status_code == 403
    r = await c.get(f"{API}/moderation/current-term", headers=teacher)
    assert r.status_code == 200 and r.json()["code"] in ("2026-BAHAR", "2026-GUZ")
    if r.json()["id"] == real["term_id"]:
        assert r.json()["published_run_id"] == real["run_id"]
    assert (await c.get(f"{API}/moderation/current-term")).status_code == 401


# ------------------------------------------------------------------------------------------- 8. publish digest


async def test_publish_notifies_each_affected_academician_once(real: dict[str, Any]) -> None:  # noqa: F811
    from app.models import InAppNotification, NotificationOutbox

    c, h, tid, base = real["client"], real["admin"], real["term_id"], real["run_id"]
    loser = real["loser"]
    uid_a, hoca_a = await make_user(c, h, "hoca.a@uni.edu.tr", role="TEACHER")
    uid_b, hoca_b = await make_user(c, h, "hoca.b@uni.edu.tr", role="TEACHER")
    async with dbmod.get_session_factory()() as s:
        a = await s.get(Instructor, real["ins_loser"])
        b = await s.get(Instructor, real["ins_phar240"])
        assert a is not None and b is not None and a.id != b.id
        a.user_id, b.user_id = uid_a, uid_b
        await s.commit()
    # B keeps the in-app bell but switches the e-mail digest off (per-user opt-out)
    r = await c.put(
        f"{API}/me/notification-preferences", json={"events": {"timetable.published": {"email": False}}}, headers=hoca_b
    )
    assert r.status_code == 200, r.text
    assert (await c.put(f"{API}/moderation/requests/{loser}/priority", json={"priority": "high"}, headers=h)).is_success
    d1 = await _resolve(c, h, tid, {"base_run_id": base, "changed_request_ids": [loser], "mode": "repair"})
    affected = set(d1["affected_instructor_ids"])
    assert real["ins_loser"] in affected
    r = await c.post(f"{API}/runs/{d1['run_id']}/activate", json={"notify_people": True}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    expected_users = {uid_a} | ({uid_b} if real["ins_phar240"] in affected else set())
    assert out["notified"] == len(expected_users) and out["notify"]["affected_people"] >= len(affected)
    assert out["notify"]["unlinked_people"] == out["notify"]["affected_people"] - len(expected_users)
    async with dbmod.get_session_factory()() as s:
        bell = list((await s.execute(select(InAppNotification).where(InAppNotification.user_id == uid_a))).scalars())
        assert len(bell) == 1 and bell[0].kind == "timetable.published"
        classes = {x["request_id"]: x for x in bell[0].data["classes"]}
        assert loser in classes and classes[loser]["change"] in ("new", "moved")
        assert bell[0].title.startswith("2026-BAHAR planı yayınlandı")
        mails = list((await s.execute(select(NotificationOutbox).where(NotificationOutbox.user_id == uid_a))).scalars())
        assert [m.kind for m in mails] == ["timetable_published"] and "→" in mails[0].body
        if uid_b in expected_users:
            mails_b = (await s.execute(select(NotificationOutbox).where(NotificationOutbox.user_id == uid_b))).all()
            assert mails_b == []  # e-mail off; the bell still gets it
    # the teacher reads it on the bell
    r = await c.get(f"{API}/me/notifications", headers=hoca_a)
    assert r.status_code == 200 and "timetable.published" in r.text
    # publishing the base again and the child once more never sends the child's digest twice (ledger key per run)
    assert (await c.post(f"{API}/runs/{base}/activate", headers=h)).status_code == 200
    r = await c.post(f"{API}/runs/{d1['run_id']}/activate", json={"notify_people": True}, headers=h)
    assert r.json()["notified"] == 0
    async with dbmod.get_session_factory()() as s:
        n_bell = (
            await s.execute(
                select(func.count()).select_from(InAppNotification).where(InAppNotification.user_id == uid_a)
            )
        ).scalar_one()
        assert n_bell == 1
    # without the flag nobody is notified (the default)
    assert (await c.post(f"{API}/runs/{base}/activate", headers=h)).json()["notified"] is None
