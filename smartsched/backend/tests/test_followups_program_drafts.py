"""Backend follow-ups 2026-10-16, program wizard drafts (asks of the Phase 19 UI follow-up hand-off):

2. the "Aynı adlı program var" check (``program_clash``) ignores archived programmes: after a commit was undone, the
   same name can be created again (the archived row is reopened: ``programs.canonical_name`` is unique);
3. a new person whose name matches an archived instructor is caught by validation: the record is reused when it is
   clearly the same person (same normalised name and the same programme), otherwise a TR/EN error names it;
   ``POST /program-drafts/{id}/precheck`` never answers the raw English 409 "instructor ... already exists";
4. ``POST /audit/{id}/undo`` on the ``program.create`` row of a wizard commit hands over to the drafts undo (same
   blockers, the same 30-day window, the same permission).

Real rows: the Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans programme (Bahar R182-R198), typed into a draft for
an empty term with the real room master, as in ``tests/test_p19_gaps_drafts.py``.
"""

from __future__ import annotations

from typing import Any

from app.core.db import get_session_factory
from app.importers import normalize as n
from app.importers.room_master import import_room_master
from app.models import AuditEvent, Course, Faculty, Instructor, Program, ScheduleRun, Section
from httpx import AsyncClient
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.conftest import FIXTURES
from tests.crbs_support import make_user
from tests.test_p19_gaps_drafts import mbg_payload

API = "/api/v1"
MBG = "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (İngilizce)"


def _issues(v: dict[str, Any], code: str) -> list[dict[str, Any]]:
    return [i for i in v["issues"] if i["code"] == code]


async def _count(model: Any, *where: Any) -> int:
    async with get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(model).where(*where))).scalar_one())


async def _setup(client: AsyncClient) -> tuple[dict[str, str], int, int, dict[str, str]]:
    h = await login(client)
    async with get_session_factory()() as s:
        await import_room_master(s, FIXTURES / "room_master.csv")
        await s.commit()
    r = await client.post(
        f"{API}/terms", json={"code": "2027-BAHAR", "name": "2027 Bahar", "week_count": 14}, headers=h
    )
    assert r.status_code == 201, r.text
    uid, planner = await make_user(client, h, "koordinator@uni.edu.tr", role="PLANNER")
    return h, r.json()["id"], uid, planner


async def _draft(client: AsyncClient, planner: dict[str, str], tid: int, payload: dict[str, Any]) -> int:
    r = await client.post(f"{API}/program-drafts", json={"term_id": tid, "payload": payload}, headers=planner)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _validate(client: AsyncClient, planner: dict[str, str], did: int) -> dict[str, Any]:
    r = await client.post(f"{API}/program-drafts/{did}/validate", headers=planner)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_recreate_after_undo_reopens_the_archived_programme_and_people(
    client: AsyncClient, parsed_bahar_list: Any
) -> None:
    h, tid, _uid, planner = await _setup(client)
    payload = mbg_payload(parsed_bahar_list)
    first = await _draft(client, planner, tid, payload)
    r = await client.post(f"{API}/program-drafts/{first}/commit", json={}, headers=planner)
    assert r.status_code == 201, r.text
    made = r.json()
    people = sorted(made["created"]["people"])
    assert people and made["audit_id"]

    # item 4: the audit log offers the undo of the wizard's programme and hands it to the drafts undo
    ev = (await client.get(f"{API}/audit/{made['audit_id']}", headers=h)).json()
    assert ev["action"] == "program.create" and ev["reversible"] is True and ev["undo_via"] == "program_draft"
    page = (await client.get(f"{API}/audit", params={"action": "program.create"}, headers=h)).json()
    row = next(i for i in page["items"] if i["id"] == made["audit_id"])
    assert row["reversible"] is True and row["undo_via"] == "program_draft"
    _oid, other = await make_user(client, h, "baska@uni.edu.tr", role="PLANNER")
    r = await client.post(f"{API}/audit/{made['audit_id']}/undo", headers=other)
    assert r.status_code in (403, 404), r.text  # not the owner and no planning.admin (and not their audit row)
    # a published plan holding the classes blocks it, with the drafts' own TR/EN blocker
    body = {"term_id": tid, "kind": "COURSE", "params": {"workers": 1, "seed": 0, "time_limit_s": 30}}
    async with get_session_factory()() as s:
        run = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", status="OPTIMAL", is_active=True, params=body)
        s.add(run)
        await s.flush()
        from app.models import Assignment

        s.add(
            Assignment(
                run_id=run.id,
                meeting_request_id=made["created"]["requests"][0],
                day=2,
                start_period=4,
                end_period=6,
                room_ids=[],
                weeks=[1],
            )
        )
        await s.commit()
        run_id = run.id
    r = await client.post(f"{API}/audit/{made['audit_id']}/undo", headers=h)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "blocked" and d["message_tr"] and d["blockers"][0]["code"] == "published"
    assert d["blockers"][0]["text"]["tr"] and d["blockers"][0]["text"]["en"]
    async with get_session_factory()() as s:
        stored = await s.get(ScheduleRun, run_id)
        assert stored is not None
        stored.is_active = False
        await s.commit()
    r = await client.post(f"{API}/audit/{made['audit_id']}/undo", headers=planner)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action"] == "program.create" and out["booking_ids"] == []
    assert out["draft_id"] == first and out["program_id"] == made["program_id"]
    assert len(out["archived"]["sections"]) == 7 and out["undone"]
    async with get_session_factory()() as s:
        undo_ev = await s.get(AuditEvent, out["undone"])
        assert undo_ev is not None and undo_ev.action == "program.undo" and undo_ev.undo_of == made["audit_id"]
    assert await _count(Program, Program.archived.is_(False)) == 0
    assert await _count(Instructor, Instructor.archived.is_(False)) == 0
    again = await client.post(f"{API}/audit/{made['audit_id']}/undo", headers=planner)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_undone"
    assert again.json()["detail"]["message_tr"]
    ev = (await client.get(f"{API}/audit/{made['audit_id']}", headers=h)).json()
    assert ev["undone"] is True

    # item 2: the same programme again - the archived namesake is no "Aynı adlı program var" error
    second = await _draft(client, planner, tid, payload)
    v = await _validate(client, planner, second)
    assert not _issues(v, "program_exists"), _issues(v, "program_exists")
    reopen = _issues(v, "program_restored")
    assert reopen and reopen[0]["level"] == "info" and reopen[0]["vars"]["program_id"] == made["program_id"]
    assert reopen[0]["text"]["tr"] and reopen[0]["text"]["en"]
    # item 3: every person of the undone commit is the same person (same name, same programme): reused
    restored = _issues(v, "instructor_restored")
    assert {i["vars"]["id"] for i in restored} == set(people), restored
    assert all(i["level"] == "info" for i in restored)
    assert not _issues(v, "instructor_new")
    assert v["can_commit"] is True, [i for i in v["issues"] if i["level"] == "error"]
    pre = await client.post(f"{API}/program-drafts/{second}/precheck", headers=planner)
    assert pre.status_code == 200, pre.text
    assert pre.json()["counts"]["requests"] == 7

    r = await client.post(f"{API}/program-drafts/{second}/commit", json={}, headers=planner)
    assert r.status_code == 201, r.text
    made2 = r.json()
    assert made2["program_id"] == made["program_id"]  # the archived row is reopened (canonical names are unique)
    assert sorted(made2["created"]["people"]) == people and made2["created"]["restored"]["people"] == people
    assert made2["created"]["restored"]["program_id"] == made["program_id"]
    async with get_session_factory()() as s:
        prog = await s.get(Program, made["program_id"])
        assert prog is not None and prog.archived is False and prog.name == MBG
        assert prog.faculty_id is not None
        fac = await s.get(Faculty, prog.faculty_id)
        assert fac is not None and fac.archived is False
        live = list((await s.execute(select(Instructor).where(Instructor.id.in_(people)))).scalars())
        assert all(not i.archived for i in live)
        courses = list(
            (
                await s.execute(
                    select(Course)
                    .join(Section, Section.course_id == Course.id)
                    .where(Section.id.in_(made2["created"]["sections"]))
                )
            ).scalars()
        )
        assert len(courses) == 7 and all(not c.archived for c in courses)
        ev2 = await s.get(AuditEvent, made2["audit_id"])
        assert ev2 is not None and ev2.action == "program.restore"
    # and the reopened programme undoes like a new one (through the audit log as well)
    ev = (await client.get(f"{API}/audit/{made2['audit_id']}", headers=h)).json()
    assert ev["reversible"] is True and ev["undo_via"] == "program_draft"
    r = await client.post(f"{API}/audit/{made2['audit_id']}/undo", headers=planner)
    assert r.status_code == 200, r.text
    assert await _count(Program, Program.archived.is_(False)) == 0
    assert await _count(Instructor, Instructor.archived.is_(False)) == 0
    assert await _count(Course, Course.archived.is_(False)) == 0


async def test_archived_namesake_in_another_programme_is_a_tr_en_issue_not_a_raw_409(
    client: AsyncClient, parsed_bahar_list: Any
) -> None:
    _h, tid, _uid, planner = await _setup(client)
    payload = mbg_payload(parsed_bahar_list)
    first = await _draft(client, planner, tid, payload)
    made = (await client.post(f"{API}/program-drafts/{first}/commit", json={}, headers=planner)).json()
    assert (await client.post(f"{API}/program-drafts/{first}/undo", headers=planner)).status_code == 200
    archived_id = sorted(made["created"]["people"])[0]
    async with get_session_factory()() as s:
        person = await s.get(Instructor, archived_id)
        assert person is not None and person.archived
        name = person.full_name
    # another programme, one new course taught by a person written like the archived instructor (Turkish case
    # folding and a non-breaking space must not hide the match)
    typed = name.replace("i", "İ").replace("ı", "I").upper().replace(" ", "\xa0", 1)  # "AHMET\xa0CAN TİMUÇİN"
    assert n.canon_person_name(typed) and n.canon_person_name(typed).canonical == person.canonical_name  # type: ignore[union-attr]
    other = {
        "program": {
            "facultyName": "Fen Bilimleri Enstitüsü",
            "name": "Biyoteknoloji Tezli Yüksek Lisans",
            "prefix": "BTK",
        },
        "courses": [
            {
                "key": "c1",
                "code": "BTK 501",
                "name": "Biyoteknolojide Yöntemler",
                "t": 3,
                "u": 0,
                "l": 0,
                "credits": "3",
                "ects": 7,
                "year": 1,
                "mode": "Yüz yüze",
                "sections": [{"key": "s1", "label": "1", "enrolment": 20, "instructors": [{"name": typed}]}],
                "pattern": {"theoryBlocks": [3], "days": [3], "start": "13.30", "weeks": "1-14"},
                "room": {"capacity": None, "tags": [], "building": "", "preferred": ""},
            }
        ],
        "cohorts": [],
        "rules": {},
    }
    did = await _draft(client, planner, tid, other)
    v = await _validate(client, planner, did)
    clash = _issues(v, "instructor_archived_namesake")
    assert len(clash) == 1 and clash[0]["level"] == "error" and v["can_commit"] is False
    assert clash[0]["vars"]["id"] == archived_id and clash[0]["path"] == "courses.c1.sections.s1.instructors.0"
    assert MBG in clash[0]["text"]["tr"] and MBG in clash[0]["text"]["en"]
    assert "arşiv" in clash[0]["text"]["tr"].lower() and "archived" in clash[0]["text"]["en"].lower()
    # the pre-check answers the same TR/EN issue (422), never "instructor ... already exists" (409)
    pre = await client.post(f"{API}/program-drafts/{did}/precheck", headers=planner)
    assert pre.status_code == 422, pre.text
    detail = pre.json()["detail"]
    assert detail["message_tr"] and [i["code"] for i in detail["issues"]] == ["instructor_archived_namesake"]
    r = await client.post(f"{API}/program-drafts/{did}/commit", json={}, headers=planner)
    assert r.status_code == 422 and "already exists" not in r.text
    # picking the archived record on purpose (same person after all) reopens it
    r = await client.patch(
        f"{API}/program-drafts/{did}",
        json={"path": "courses.c1.sections.s1.instructors", "value": [{"id": archived_id}]},
        headers=planner,
    )
    assert r.status_code == 200, r.text
    v = r.json()["validation"]
    assert v["can_commit"] is True, [i for i in v["issues"] if i["level"] == "error"]
    assert [i["vars"]["id"] for i in _issues(v, "instructor_restored")] == [archived_id]
    pre = await client.post(f"{API}/program-drafts/{did}/precheck", headers=planner)
    assert pre.status_code == 200, pre.text
    r = await client.post(f"{API}/program-drafts/{did}/commit", json={}, headers=planner)
    assert r.status_code == 201, r.text
    assert r.json()["created"]["restored"]["people"] == [archived_id]
    async with get_session_factory()() as s:
        person = await s.get(Instructor, archived_id)
        assert person is not None and not person.archived


async def test_audit_undo_of_a_catalogue_programme_is_refused_in_both_languages(client: AsyncClient) -> None:
    h = await login(client)
    r = await client.post(f"{API}/programs", json={"name": "Deneme Programı"}, headers=h)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    async with get_session_factory()() as s:
        ev = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "program.create", AuditEvent.entity_id == str(pid))
            )
        ).scalar_one()
        eid = ev.id
    out = (await client.get(f"{API}/audit/{eid}", headers=h)).json()
    assert out["reversible"] is False and out.get("undo_via") is None
    r = await client.post(f"{API}/audit/{eid}/undo", headers=h)
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["code"] == "not_reversible" and d["message_tr"]


async def test_undo_archives_the_courses_the_commit_created_and_keeps_catalogue_courses(
    client: AsyncClient, parsed_bahar_list: Any
) -> None:
    """Round-1 R1-S-29 (T-R1-50): "Arşivlendi: 3 şube, 0 ders, 2 kişi" after a commit that typed 3 courses. The 0 was
    right for the tester's rows (MBG 598 / 532 / 534 exist in the Bahar catalogue, so the commit reused them) and
    wrong-looking next to the "3 ders" the done view counted. The API separates the two: ``created.courses`` are the
    rows the commit wrote (archived by the undo), ``created.reused_courses`` the catalogue rows it only used (kept)."""
    h, tid, _uid, planner = await _setup(client)
    payload = mbg_payload(parsed_bahar_list)
    typed = [str(c["code"]) for c in payload["courses"]]
    assert len(typed) >= 3
    # one of the typed codes already exists in the catalogue (typed any way: the key is canonical)
    existing = typed[0]
    r = await client.post(f"{API}/courses", json={"code": existing, "name": "Katalogdaki ders"}, headers=h)
    assert r.status_code == 201, r.text
    catalogue_id = int(r.json()["id"])

    did = await _draft(client, planner, tid, payload)
    r = await client.post(f"{API}/program-drafts/{did}/commit", json={}, headers=planner)
    assert r.status_code == 201, r.text
    made = r.json()["created"]
    assert made["reused_courses"] == [catalogue_id]
    assert catalogue_id not in made["courses"] and len(made["courses"]) == len(typed) - 1

    r = await client.post(f"{API}/program-drafts/{did}/undo", headers=planner)
    assert r.status_code == 200, r.text
    arch = r.json()["archived"]
    assert sorted(arch["courses"]) == sorted(made["courses"]) and catalogue_id not in arch["courses"]
    async with get_session_factory()() as s:
        kept = await s.get(Course, catalogue_id)
        assert kept is not None and kept.archived is False
        gone = [await s.get(Course, cid) for cid in made["courses"]]
        assert gone and all(c is not None and c.archived for c in gone)


async def test_the_same_new_person_twice_on_a_section_is_a_step_issue_not_a_raw_422(client: AsyncClient) -> None:
    """R2-M-07 / T-R2-22: 'Yeni kişi' pressed twice for the same name. Validation refuses it on the instructors step
    (code ``instructor_twice``, TR/EN, the second slot's path), the pre-check answers the same issue and the commit
    never reaches catalog_admin's "instructor N is listed twice"."""
    _h, tid, _uid, planner = await _setup(client)
    payload = {
        "program": {
            "facultyName": "Fen Bilimleri Enstitüsü",
            "name": "Biyoteknoloji Tezli Yüksek Lisans",
            "prefix": "BTK",
        },
        "courses": [
            {
                "key": "c1",
                "code": "BTK 501",
                "name": "Biyoteknolojide Yöntemler",
                "t": 3,
                "u": 0,
                "l": 0,
                "credits": "3",
                "ects": 7,
                "year": 1,
                "mode": "Yüz yüze",
                "sections": [
                    {
                        "key": "s1",
                        "label": "1",
                        "enrolment": 20,
                        "instructors": [
                            {"name": "Tolga Emre"},
                            {"name": "TOLGA\xa0EMRE"},
                        ],  # the same person, typed twice
                    }
                ],
                "pattern": {"theoryBlocks": [3], "days": [3], "start": "13.30", "weeks": "1-14"},
                "room": {"capacity": None, "tags": [], "building": "", "preferred": ""},
            }
        ],
        "cohorts": [],
        "rules": {},
    }
    did = await _draft(client, planner, tid, payload)
    v = await _validate(client, planner, did)
    twice = _issues(v, "instructor_twice")
    assert len(twice) == 1 and twice[0]["level"] == "error" and v["can_commit"] is False
    assert twice[0]["step"] == "instructors" and twice[0]["path"] == "courses.c1.sections.s1.instructors.1"
    assert twice[0]["text"]["tr"] == "Bu kişi bu şubede zaten var: Tolga Emre"
    assert twice[0]["text"]["en"] == "This person is already on this section: Tolga Emre"
    assert len(_issues(v, "instructor_new")) == 1  # the first slot is the new person; the second is not another one
    pre = await client.post(f"{API}/program-drafts/{did}/precheck", headers=planner)
    assert pre.status_code == 422, pre.text
    detail = pre.json()["detail"]
    assert detail["message_tr"] and "instructor_twice" in [i["code"] for i in detail["issues"]]
    r = await client.post(f"{API}/program-drafts/{did}/commit", json={}, headers=planner)
    assert r.status_code == 422 and "listed twice" not in r.text and "Kayıt yazılamadı" not in r.text, r.text
    # one entry for the person: the commit goes through
    r = await client.patch(
        f"{API}/program-drafts/{did}",
        json={"path": "courses.c1.sections.s1.instructors", "value": [{"name": "Tolga Emre"}]},
        headers=planner,
    )
    assert r.status_code == 200, r.text
    assert r.json()["validation"]["can_commit"] is True
    r = await client.post(f"{API}/program-drafts/{did}/commit", json={}, headers=planner)
    assert r.status_code == 201, r.text
    assert len(r.json()["created"]["people"]) == 1
