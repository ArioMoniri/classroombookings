"""P19-L2..L4 acceptance on the real Bahar 2026 + Güz 2026 planning lists (tests/fixtures).

* extraction from existing tables is idempotent and never learns from the planner's locked double bookings
  (MAT 112 §1 / HEM 236 in A 204 on Thursday) or over-capacity locks (MBG 034 §1, 80 students in B 407)
* MAT 112's prior names its definitive room (C 201: its Thursday A 204 rows are a double booking, its 180-student
  Monday row is over capacity, so only the joint listing without a count is evidence)
* a new same-season term (2027-BAHAR, classes copied without rooms) gets suggestions; accepting one writes exactly
  one soft, targeted ``LEARNED`` rule (weight 5, Q7); structural kinds, a higher weight and untargeted params are
  refused; a dismissal hides it for the scope and term; snooze hides it until the next solve
* memory reset per person hides the person's suggestions, undo restores them, a Planner gets 403, an audit row is
  written; the undo window closes after 30 days; the daily purge deletes expired observations and the watermark
  keeps them from being learned again; a KVKK erasure purges at once and cannot be undone
* a CP-SAT run (workers=1, seed 0) with an accepted learned preference keeps hard 100
"""

from __future__ import annotations

import asyncio
import shutil
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.core.security import hash_password
from app.importers.planning_list import import_planning_list
from app.models import (
    AuditEvent,
    Building,
    ConstraintRow,
    Course,
    Instructor,
    LearnedObservation,
    LearningReset,
    MeetingRequest,
    Room,
    Section,
    SectionInstructor,
    Term,
    User,
)
from app.models.base import utcnow
from app.services import learning, learning_extract
from app.services.seed import seed_admin
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.conftest import BAHAR_LIST, GUZ_LIST

API = "/api/v1"
PLANNER = ("planner@example.com", "planner1234")
_TEMPLATE: list[Path] = []


async def _build(path: Path) -> None:
    eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with eng.begin() as conn:
        from app.models import Base

        await conn.run_sync(Base.metadata.create_all)
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
        s.add(User(email=PLANNER[0], password_hash=hash_password(PLANNER[1]), role="PLANNER", full_name="Fatih Bey"))
        await s.commit()
        await import_planning_list(s, BAHAR_LIST, "2026-BAHAR")
        await s.commit()
        await import_planning_list(s, GUZ_LIST, "2026-GUZ")
        await s.commit()
        await learning_extract.extract(s)
        await s.commit()
    await dbmod.dispose_engine()


def _template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if _TEMPLATE:
        return _TEMPLATE[0]
    path = tmp_path_factory.mktemp("learning") / "bahar_guz.db"
    errors: list[BaseException] = []

    def target() -> None:  # own thread + loop: never collides with pytest-asyncio's loop
        try:
            asyncio.run(_build(path))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if errors:
        raise errors[0]
    _TEMPLATE.append(path)
    return path


@dataclass
class Env:
    client: AsyncClient
    admin: dict[str, str]
    planner: dict[str, str]
    bahar: int
    guz: int


@pytest.fixture
async def env(tmp_path_factory, tmp_path, monkeypatch) -> AsyncIterator[Env]:
    template = _template(tmp_path_factory)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    db = tmp_path / "api.db"
    shutil.copy(template, db)
    dbmod.configure_engine(f"sqlite+aiosqlite:///{db}")
    qmod.reset_queue()
    from app.main import app

    async with dbmod.get_session_factory()() as s:
        ids = dict((await s.execute(select(Term.code, Term.id))).all())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield Env(c, await login(c), await login(c, *PLANNER), ids["2026-BAHAR"], ids["2026-GUZ"])
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()
    db.unlink(missing_ok=True)


def _session():  # type: ignore[no-untyped-def]
    return dbmod.get_session_factory()()


async def _course_id(display: str) -> int:
    async with _session() as s:
        return (await s.execute(select(Course.id).where(Course.display_code == display))).scalar_one()


async def _requests(term_id: int, display: str) -> list[MeetingRequest]:
    async with _session() as s:
        q = (
            select(MeetingRequest)
            .join(Section, Section.id == MeetingRequest.section_id)
            .join(Course, Course.id == Section.course_id)
            .where(Section.term_id == term_id, Course.display_code == display)
            .order_by(MeetingRequest.id)
        )
        return list((await s.execute(q)).scalars())


async def _next_bahar(codes: list[str]) -> tuple[int, dict[str, list[int]]]:
    """A new same-season term 2027-BAHAR holding copies of the 2026-BAHAR classes of ``codes``: same courses,
    programmes, instructors, enrolment and times, but no requested or definitive rooms (nothing planned yet)."""
    out: dict[str, list[int]] = {}
    async with _session() as s:
        old = (await s.execute(select(Term).where(Term.code == "2026-BAHAR"))).scalar_one()
        term = Term(code="2027-BAHAR", name="2027 Bahar", kind="REGULAR", week_count=14)
        s.add(term)
        await s.flush()
        for code in codes:
            q = (
                select(Section)
                .join(Course, Course.id == Section.course_id)
                .where(Section.term_id == old.id, Course.display_code == code, Section.archived.is_(False))
                .order_by(Section.id)
            )
            for sec in (await s.execute(q)).scalars():
                new = Section(
                    term_id=term.id,
                    course_id=sec.course_id,
                    program_id=sec.program_id,
                    label=sec.label,
                    class_year=sec.class_year,
                    class_years=list(sec.class_years or []),
                    enrolment=sec.enrolment,
                    mode=sec.mode,
                    source_key=f"TEST27:{sec.id}",
                )
                s.add(new)
                await s.flush()
                sis = (
                    await s.execute(select(SectionInstructor).where(SectionInstructor.section_id == sec.id))
                ).scalars()
                for si in list(sis):
                    s.add(SectionInstructor(section_id=new.id, instructor_id=si.instructor_id, role=si.role))
                mrs = (await s.execute(select(MeetingRequest).where(MeetingRequest.section_id == sec.id))).scalars()
                for mr in list(mrs):
                    if mr.archived:
                        continue
                    copy = MeetingRequest(
                        section_id=new.id,
                        day=mr.day,
                        days=list(mr.days or []),
                        start_period=mr.start_period,
                        end_period=mr.end_period,
                        start_time=mr.start_time,
                        end_time=mr.end_time,
                        weeks=list(mr.weeks or []),
                        flexible_day=mr.flexible_day,
                        needs_room=mr.needs_room,
                        status="PARSED",
                    )
                    s.add(copy)
                    await s.flush()
                    if copy.needs_room:  # online / UZEM rows are copied but never targeted
                        out.setdefault(code, []).append(copy.id)
        await s.commit()
        return term.id, out


async def _suggestions(env: Env, term_id: int, headers: dict[str, str] | None = None, **params: Any) -> list[dict]:
    r = await env.client.get(
        f"{API}/learning/suggestions", params={"term_id": term_id, **params}, headers=headers or env.planner
    )
    assert r.status_code == 200, r.text
    return r.json()


def _pick(items: list[dict], subject_type: str, attribute: str, label: str | None = None) -> dict:
    found = [
        i
        for i in items
        if i["subject"]["type"] == subject_type
        and i["attribute"] == attribute
        and (label is None or i["subject"]["label"] == label)
    ]
    assert found, [(i["subject"], i["attribute"], i["value"]) for i in items][:20]
    return found[0]


# ------------------------------------------------------------------------------------------------ unit


def test_turkish_locative_follows_the_spoken_number():
    assert learning.locative("A 204") == "A 204'te"  # dört
    assert learning.locative("C 201") == "C 201'de"  # bir
    assert learning.locative("A 106") == "A 106'da"  # altı
    assert learning.locative("A Blok") == "A Blok'ta"
    assert learning.locative("B 407") == "B 407'de"  # yedi


def test_wilson_lower_bound_meets_the_decided_evidence_rule():
    # 2 rows over 2 terms and 3 repeats in one term reach 0.6; one of two does not
    assert learning.wilson_lower(2, 2) > 0.6 and learning.wilson_lower(3, 3) > 0.6
    assert learning.wilson_lower(1, 2) < 0.6 and learning.wilson_lower(4, 8) < 0.6
    assert learning.wilson_lower(8, 8) > learning.wilson_lower(4, 4) > learning.wilson_lower(2, 2)


def test_learned_rule_guard_refuses_structural_untargeted_and_heavy_rules():
    ok = {"event_ids": [384], "building": "C"}
    assert learning.learned_rule_issues("building_preference", ok, "soft", 5) == []
    for kind in ("capacity", "room_tags", "fixed_time", "room_pin", "room_forbid"):
        assert learning.learned_rule_issues(kind, {"event_ids": [384]}, "soft", 5), kind
    assert learning.learned_rule_issues("building_preference", {"building": "C"}, "soft", 5)  # untargeted
    assert learning.learned_rule_issues("building_preference", {"event_ids": [], "building": "C"}, "soft", 5)
    assert learning.learned_rule_issues("building_preference", {"event_ids": ["\xa0"], "building": "C"}, "soft", 5)
    assert learning.learned_rule_issues("building_preference", ok, "hard", 5)
    assert learning.learned_rule_issues("building_preference", ok, "soft", 10)  # Q7: explicit rules weigh 10


# ------------------------------------------------------------------------------------------------ L2


async def test_extraction_is_idempotent_and_skips_planner_errors(env: Env):
    async with _session() as s:
        stored = (await s.execute(select(func.count(LearnedObservation.id)))).scalar_one()
    assert stored > 20_000  # Bahar + Güz: definitive rooms, request text and request times

    r = await env.client.post(f"{API}/learning/refresh", json={}, headers=env.planner)
    assert r.status_code == 200, r.text
    rep = r.json()["extract"]
    assert rep["added_total"] == 0, rep  # the template already holds every observation
    assert rep["excluded"]["locked_double_booking"] >= 19 and rep["excluded"]["over_capacity_lock"] >= 70

    # from scratch: the same rows again, then 0 on a re-run
    async with _session() as s:
        await s.execute(LearnedObservation.__table__.delete())
        await s.commit()
    first = (await env.client.post(f"{API}/learning/refresh", json={}, headers=env.planner)).json()["extract"]
    again = (await env.client.post(f"{API}/learning/refresh", json={}, headers=env.planner)).json()["extract"]
    assert first["added_total"] == stored and again["added_total"] == 0

    async with _session() as s:
        rooms = {r.display_name: r.id for r in (await s.execute(select(Room))).scalars()}
        hem = await _requests(env.bahar, "HEM 236")
        mat_thu = [m for m in await _requests(env.bahar, "MAT 112") if m.day == 4]
        assert hem and mat_thu and all(m.definitive_room_ids == [rooms["A 204"]] for m in hem + mat_thu)
        ids = [m.id for m in hem + mat_thu]
        q = select(LearnedObservation.kind, LearnedObservation.weight).where(LearnedObservation.source_id.in_(ids))
        kinds = {(k, w) for k, w in (await s.execute(q.where(LearnedObservation.source_table == "meeting_requests")))}
        assert ("definitive_room", 3) not in kinds and ("excluded_lock", 0) in kinds  # L5: A 204 teaches nothing
        mbg = [m for m in await _requests(env.bahar, "MBG 034") if m.definitive_room_ids == [rooms["B 407"]]]
        assert len(mbg) >= 2, "MBG 034 §1 is locked to B 407 (30 seats): 80 students, plus a 15-student listing"
        q = select(LearnedObservation.weight, LearnedObservation.detail).where(
            LearnedObservation.attribute == "room",
            LearnedObservation.value == str(rooms["B 407"]),
            LearnedObservation.source_table == "meeting_requests",
            LearnedObservation.source_id.in_([m.id for m in mbg]),
        )
        found = (await s.execute(q)).all()
        # L6: no row of the over-capacity lecture is evidence, not even its 15-student listing
        assert found and {w for w, _ in found} == {0}
        assert {d["excluded"] for _, d in found} == {"over_capacity_lock"} and {d["seats"] for _, d in found} == {30}
        # subjects are ids, never names (KVKK)
        q = select(LearnedObservation.subject_key).where(LearnedObservation.subject_type == "instructor").limit(50)
        assert all(k.isdigit() for k in (await s.execute(q)).scalars())


async def test_mat112_prior_names_its_definitive_room(env: Env):
    mat = await _course_id("MAT 112")
    r = await env.client.get(
        f"{API}/learning/priors",
        params={"term_id": env.bahar, "subject_type": "course", "subject_id": mat},
        headers=env.planner,
    )
    assert r.status_code == 200, r.text
    rooms = {p["value_label"]["tr"]: p for p in r.json() if p["attribute"] == "room"}
    definitive = {m.definitive_room_text for m in await _requests(env.bahar, "MAT 112")}
    assert set(rooms) == definitive == {"C 201", "A 204"}  # the prior names both definitive rooms ...
    assert all(p["support"] == 0 and p["score"] == 0 and not p["suggestible"] for p in rooms.values())
    # ... and says why neither is learned (180 students: over capacity in C 201, double-booked in A 204)
    assert rooms["C 201"]["explanation"]["tr"] == (
        "MAT 112: C 201 kesinleşen derslikti ama öğrenilmedi "
        "(kapasite üstü kilit: 180 öğrenci, 126 koltuk; 2026-BAHAR: 1 ders)."
    )
    assert rooms["C 201"]["explanation"]["en"] == (
        "MAT 112: C 201 was the definitive room but is not learned "
        "(over-capacity lock: 180 students, 126 seats; 2026-BAHAR: 1 lecture)."
    )
    assert rooms["A 204"]["explanation"]["tr"] == (
        "MAT 112: A 204 kesinleşen derslikti ama öğrenilmedi (kilitli çift rezervasyon; 2026-BAHAR: 1 ders)."
    )
    assert [e["reason"] for e in rooms["A 204"]["evidence"]["excluded"]] == ["locked_double_booking"]
    # the other side of the A 204 double booking learned nothing either (L5)
    hem = await _course_id("HEM 236")
    r = await env.client.get(
        f"{API}/learning/priors",
        params={"term_id": env.bahar, "subject_type": "course", "subject_id": hem},
        headers=env.planner,
    )
    a204 = [p for p in r.json() if p["attribute"] == "room" and p["value_label"]["tr"] == "A 204"]
    assert a204 and a204[0]["support"] == 0 and not a204[0]["suggestible"]


# ------------------------------------------------------------------------------------------------ L3


async def test_accept_creates_one_soft_targeted_learned_rule(env: Env):
    term, copies = await _next_bahar(["SYS 19", "RAD 202"])
    items = await _suggestions(env, term, course_id=await _course_id("SYS 19"))
    sys19 = _pick(items, "course", "building", "SYS 19")
    assert sys19["value"] == "A" and sys19["state"] == "open"
    assert sys19["claim"]["tr"] == "SYS 19 için A Blok tercih edilsin mi?"
    assert sys19["explanation"]["tr"].startswith("SYS 19 2 dönemdir A Blok'ta: ")
    assert "Farklı dönem verisi" in sys19["explanation"]["tr"]  # the Güz half of the evidence
    assert sys19["support"]["seen_terms"] == 2 and sys19["confidence"] >= 0.6
    assert sys19["if_accepted"]["tr"].startswith("Kabul ederseniz yumuşak bir tercih (ağırlık 5)")
    assert sorted(sys19["proposal"]["params"]["event_ids"]) == sorted(copies["SYS 19"])

    url = f"{API}/learning/suggestions/{sys19['id']}/accept"
    r = await env.client.post(url, json={"kind": "capacity"}, headers=env.planner)
    assert r.status_code == 422 and "structural" in r.text  # the guard refuses structural kinds
    r = await env.client.post(url, json={"weight": 10}, headers=env.planner)
    assert r.status_code == 422 and "weight 1..5" in r.text
    viewer = await _viewer(env)
    assert (await env.client.post(url, json={}, headers=viewer)).status_code == 403
    r = await env.client.post(url, json={}, headers=env.planner)
    assert r.status_code == 201, r.text
    cid = r.json()["constraint_id"]
    async with _session() as s:
        row = await s.get(ConstraintRow, cid)
        assert row is not None
        assert (row.source, row.hardness, row.weight, row.kind, row.term_id, row.run_id) == (
            "LEARNED",
            "soft",
            5,
            "building_preference",
            term,
            None,
        )
        assert row.params == {"building": "A", "event_ids": sorted(copies["SYS 19"])}
        assert row.source_ref["prior_id"] == sys19["id"] and "A Blok" in row.source_ref["explanation"]["tr"]
        assert (
            await s.execute(select(func.count(ConstraintRow.id)).where(ConstraintRow.source == "LEARNED"))
        ).scalar_one() == 1
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "suggestion.accept"))).scalar_one()
        assert ev.entity_id == str(sys19["id"])
    assert (await env.client.post(url, json={}, headers=env.planner)).status_code == 409  # once
    accepted = await _suggestions(env, term, state="accepted")
    assert [i["id"] for i in accepted] == [sys19["id"]] and accepted[0]["constraint_id"] == cid
    assert sys19["id"] not in {i["id"] for i in await _suggestions(env, term)}

    # instructor-level stored text never carries the name (KVKK); the API renders it at read time
    people = [i for i in await _suggestions(env, term) if i["subject"]["type"] == "instructor"]
    assert people
    r = await env.client.post(f"{API}/learning/suggestions/{people[0]['id']}/accept", json={}, headers=env.planner)
    assert r.status_code == 201, r.text
    async with _session() as s:
        row = await s.get(ConstraintRow, r.json()["constraint_id"])
        ins = await s.get(Instructor, people[0]["subject"]["id"])
        assert row is not None and ins is not None
        assert ins.full_name in people[0]["claim"]["tr"]
        stored = f"{row.nl_text} {row.source_ref}"
        assert ins.full_name not in stored and f"öğretim elemanı #{ins.id}" in stored


async def _viewer(env: Env) -> dict[str, str]:
    async with _session() as s:
        s.add(User(email="viewer@example.com", password_hash=hash_password("viewer1234"), role="VIEWER"))
        await s.commit()
    return await login(env.client, "viewer@example.com", "viewer1234")


async def test_reject_suppresses_and_snooze_waits_for_the_next_solve(env: Env):
    term, _ = await _next_bahar(["SYS 19", "RAD 202"])
    items = await _suggestions(env, term)
    rad = _pick(items, "course", "building", "RAD 202")
    r = await env.client.post(
        f"{API}/learning/suggestions/{rad['id']}/reject", json={"reason": "Bu dönem farklı"}, headers=env.planner
    )
    assert r.status_code == 200, r.text
    after = await _suggestions(env, term)
    assert rad["id"] not in {i["id"] for i in after}
    assert [i["id"] for i in await _suggestions(env, term, state="dismissed")] == [rad["id"]]
    async with _session() as s:
        q = select(LearnedObservation).where(LearnedObservation.kind == "suggestion_rejected")
        obs = (await s.execute(q)).scalar_one()
        assert (obs.sign, obs.weight, obs.subject_type, obs.value) == (-1, 3, "course", "A")
        assert (
            await s.execute(select(func.count()).where(AuditEvent.action == "suggestion.dismiss"))
        ).scalar_one() == 1
    # still dismissed after the evidence is extracted again (L8)
    await env.client.post(f"{API}/learning/refresh", json={"term_id": term}, headers=env.planner)
    assert rad["id"] not in {i["id"] for i in await _suggestions(env, term)}

    other = next(i for i in after if i["id"] != rad["id"])
    r = await env.client.post(
        f"{API}/learning/suggestions/{other['id']}/snooze", json={"until": "next_solve"}, headers=env.planner
    )
    assert r.status_code == 200, r.text
    assert other["id"] in {i["id"] for i in await _suggestions(env, term, state="snoozed")}
    assert other["id"] not in {i["id"] for i in await _suggestions(env, term)}


# ------------------------------------------------------------------------------------------------ L4


async def test_person_reset_hides_undo_restores_and_planner_gets_403(env: Env):
    term, _ = await _next_bahar(["SYS 19", "RAD 202"])
    before = await _suggestions(env, term)
    person = _pick(before, "instructor", "building")
    pid = person["subject"]["id"]
    mine = sorted(i["id"] for i in await _suggestions(env, term, person_id=pid))
    others = sorted(i["id"] for i in before if i["id"] not in mine)
    assert mine and others
    # one "Bir daha önerme" for the person: the reset removes it too, undo brings it back (L9 / L10)
    dismissed = mine[-1]
    await env.client.post(f"{API}/learning/suggestions/{dismissed}/reject", json={}, headers=env.planner)

    body = {"scope": "person", "value": f"\xa0{pid}", "reason": "görev değişikliği"}  # NBSP from a pasted id
    r = await env.client.post(f"{API}/learning/reset", json=body, headers=env.planner)
    assert r.status_code == 403
    r = await env.client.post(f"{API}/learning/reset", json=body, headers=env.admin)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["scope"] == "person" and out["value"] == str(pid) and out["undoable"] and out["days_left"] >= 29
    assert out["counts"]["observations"] > 0 and out["counts"]["feedback"] == 1
    assert await _suggestions(env, term, person_id=pid, state="all") == []
    assert sorted(i["id"] for i in await _suggestions(env, term) if i["id"] not in mine) == others
    async with _session() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "learning.reset"))).scalar_one()
        assert ev.entity_id == str(out["id"]) and ev.after["scope"] == "person" and ev.reason == "görev değişikliği"
        assert (await s.execute(select(func.count()).where(ConstraintRow.source == "LEARNED"))).scalar_one() == 0
    # extraction does not learn the reset evidence again (watermark)
    rep = (await env.client.post(f"{API}/learning/refresh", json={}, headers=env.planner)).json()["extract"]
    assert rep["added_total"] == 0

    assert (await env.client.get(f"{API}/learning/resets", headers=env.planner)).status_code == 403
    listed = (await env.client.get(f"{API}/learning/resets", headers=env.admin)).json()
    assert listed[0]["id"] == out["id"]
    assert (await env.client.post(f"{API}/learning/resets/{out['id']}/undo", headers=env.planner)).status_code == 403
    r = await env.client.post(f"{API}/learning/resets/{out['id']}/undo", headers=env.admin)
    assert r.status_code == 200, r.text
    assert sorted(i["id"] for i in await _suggestions(env, term, person_id=pid) if i["id"] != dismissed) == [
        x for x in mine if x != dismissed
    ]
    assert dismissed in {i["id"] for i in await _suggestions(env, term, state="dismissed")}
    assert (await env.client.post(f"{API}/learning/resets/{out['id']}/undo", headers=env.admin)).status_code == 409
    async with _session() as s:
        assert (
            await s.execute(select(func.count()).where(AuditEvent.action == "learning.reset.undo"))
        ).scalar_one() == 1

    # after 30 days the undo is refused with the date it expired
    r = await env.client.post(
        f"{API}/learning/reset",
        json={"scope": "term", "value": env.guz, "reason": "Güz binada tadilat"},
        headers=env.admin,
    )
    rid = r.json()["id"]
    async with _session() as s:
        rs = await s.get(LearningReset, rid)
        assert rs is not None
        rs.expires_at = utcnow() - timedelta(days=1)
        expired = rs.expires_at.date().isoformat()
        await s.commit()
    r = await env.client.post(f"{API}/learning/resets/{rid}/undo", headers=env.admin)
    assert r.status_code == 409 and expired in r.text


async def test_purge_removes_expired_observations_and_they_stay_unlearned(env: Env):
    r = await env.client.post(
        f"{API}/learning/reset",
        json={"scope": "term", "value": env.guz, "reason": "Güz binada tadilat"},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    async with _session() as s:
        hidden = (await s.execute(select(func.count()).where(LearnedObservation.reset_id == rid))).scalar_one()
        guz = (await s.execute(select(func.count()).where(LearnedObservation.term_id == env.guz))).scalar_one()
        assert hidden == guz > 5_000
        assert (await learning.purge_expired(s)) == {"resets": 0, "observations": 0, "feedback": 0}  # not yet due
        out = await learning.purge_expired(s, now=utcnow() + timedelta(days=31))
        await s.commit()
    assert out == {"resets": 1, "observations": hidden, "feedback": 0}
    async with _session() as s:
        assert (await s.execute(select(func.count()).where(LearnedObservation.term_id == env.guz))).scalar_one() == 0
        rs = await s.get(LearningReset, rid)
        assert rs is not None and rs.purged_at is not None
        assert (await s.execute(select(func.count()).where(AuditEvent.action == "learning.purge"))).scalar_one() == 1
    assert (await env.client.post(f"{API}/learning/resets/{rid}/undo", headers=env.admin)).status_code == 409
    rep = (await env.client.post(f"{API}/learning/refresh", json={}, headers=env.planner)).json()["extract"]
    assert rep["added_total"] == 0 and rep["skipped"]["reset_watermark"] == guz
    # the Güz term itself is untouched (a reset is memory only)
    async with _session() as s:
        q = (
            select(func.count())
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == env.guz)
        )
        assert (await s.execute(q)).scalar_one() > 1000
    summary = (await env.client.get(f"{API}/learning/memory/summary", headers=env.planner)).json()
    assert {t["code"] for t in summary["terms"]} == {"2026-BAHAR"}


async def test_kvkk_erasure_purges_a_person_at_once(env: Env):
    term, _ = await _next_bahar(["SYS 19"])
    person = _pick(await _suggestions(env, term), "instructor", "building")
    pid = person["subject"]["id"]
    body = {"instructor_id": pid, "reason": "KVKK md. 11 silme talebi"}
    assert (await env.client.post(f"{API}/learning/erase", json=body, headers=env.planner)).status_code == 403
    r = await env.client.post(f"{API}/learning/erase", json=body, headers=env.admin)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["kind"] == "ERASURE" and out["purged_at"] and not out["undoable"] and out["counts"]["observations"] > 0
    async with _session() as s:
        q = select(func.count()).where(
            LearnedObservation.subject_type == "instructor", LearnedObservation.subject_key == str(pid)
        )
        assert (await s.execute(q)).scalar_one() == 0
        assert (await s.execute(select(func.count()).where(AuditEvent.action == "learning.erase"))).scalar_one() == 1
    assert await _suggestions(env, term, person_id=pid, state="all") == []
    assert (await env.client.post(f"{API}/learning/resets/{out['id']}/undo", headers=env.admin)).status_code == 409
    rep = (await env.client.post(f"{API}/learning/refresh", json={}, headers=env.planner)).json()["extract"]
    assert rep["added_total"] == 0  # never learned again


# ------------------------------------------------------------------------------------------------ solve


async def test_run_with_an_accepted_learned_preference_keeps_hard_100(env: Env):
    term, copies = await _next_bahar(["SYS 19", "RAD 202"])
    sys19 = _pick(await _suggestions(env, term), "course", "building", "SYS 19")
    r = await env.client.post(f"{API}/learning/suggestions/{sys19['id']}/accept", json={}, headers=env.planner)
    assert r.status_code == 201, r.text
    body = {"term_id": term, "kind": "COURSE", "params": {"workers": 1, "seed": 0, "time_limit_s": 30}}
    r = await env.client.post(f"{API}/runs", json=body, headers=env.planner)
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    await qmod.get_queue().wait_idle()
    run = (await env.client.get(f"{API}/runs/{run_id}", headers=env.planner)).json()
    assert run["status"] in {"OPTIMAL", "FEASIBLE"}, run
    assert run["hard_score"] == 100, run
    rows = (await env.client.get(f"{API}/runs/{run_id}/assignments", headers=env.planner)).json()
    async with _session() as s:
        a_id = (await s.execute(select(Building.id).where(Building.code == "A"))).scalar_one()
        a_block = set((await s.execute(select(Room.id).where(Room.building_id == a_id))).scalars())
    placed = [a for a in rows if a["meeting_request_id"] in set(copies["SYS 19"])]
    assert placed and all(set(a["room_ids"]) <= a_block for a in placed)  # the learned preference was honoured
    print(
        f"P19-L run {run_id}: status={run['status']} hard={run['hard_score']} soft={run['soft_score']} rows={len(rows)}"
    )
