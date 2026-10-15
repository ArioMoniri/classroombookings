"""P19-C1 / P19-C2: create a programme from scratch through the API, with no import.

The rows are the real Bahar planning-list rows 188-190 (``parsed_bahar_list``): Fen Bilimleri Enstitüsü,
"Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (İngilizce)", MBG 532 Epigenetik, MBG 534 Proteomiks and
MBG 546 Genetik ve Genomiks with their instructors, re-entered through the new endpoints into an empty term
(the coordinator's flow, docs/testing/2026-10-15-academician-needs.md §4 / S1). The acceptance checks:

(a) faculty -> programme -> 3 courses -> sections with instructors -> pattern "3 periods a week, Tue or Thu,
    weeks 1-14" -> ``POST /runs`` (CP-SAT, workers=1) places every meeting with hard 100 and
    ``planner_check`` reports 0 violations;
(b) a duplicate course code (spacing, case, NBSP, leading zero, and ÇEV = CEV once ``course_key`` folds) -> 409
    naming the existing course;
(c) a Viewer and a Teacher (no ``planning.edit``) -> 403;
(d) every create writes an audit row.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.core.db import get_session_factory
from app.importers import normalize as n
from app.models import Assignment, AuditEvent, MeetingRequest, Room, ScheduleRun
from app.workers.queue import get_queue
from httpx import AsyncClient
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.crbs_support import make_user

API = "/api/v1"
#: Bahar rows of the MBG Tezli YL programme (real fixture rows)
ROWS = (188, 189, 190)


def _row(parsed: Any, number: int) -> Any:
    return next(r for r in parsed.rows if r.row == number)


async def _rooms() -> dict[str, int]:
    """Room master rows as on the Bahar boards (A 101/A 106 58 seats, C 401 72, C 504 40, B 207 PC 60)."""
    async with get_session_factory()() as s:
        rooms = [
            Room(code="A101", display_name="A 101", capacity=58, exam_capacity=30),
            Room(code="A106", display_name="A 106", capacity=58, exam_capacity=30),
            Room(code="C401", display_name="C 401", capacity=72, exam_capacity=36),
            Room(code="C504", display_name="C 504", capacity=40, exam_capacity=20),
            Room(code="B207", display_name="B 207", capacity=60, exam_capacity=60, tags=["PC"]),
        ]
        s.add_all(rooms)
        await s.commit()
        return {r.code: r.id for r in rooms}


async def _term(client: AsyncClient, h: dict[str, str], code: str = "2027-BAHAR") -> int:
    r = await client.post(f"{API}/terms", json={"code": code, "name": "2027 Bahar", "week_count": 14}, headers=h)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _audit_count(action: str) -> int:
    async with get_session_factory()() as s:
        return int((await s.execute(select(func.count(AuditEvent.id)).where(AuditEvent.action == action))).scalar_one())


async def _build_programme(client: AsyncClient, h: dict[str, str], parsed: Any, term_id: int) -> dict[str, Any]:
    """The coordinator's steps 2-5 for the three real rows; returns the created ids."""
    rows = [_row(parsed, i) for i in ROWS]
    # step 2: unit and programme, typed the way the lists write them (capitals, trailing NBSP)
    r = await client.post(f"{API}/faculties", json={"name": "FEN BİLİMLERİ ENSTİTÜSÜ\xa0"}, headers=h)
    assert r.status_code == 201, r.text
    faculty = r.json()
    assert faculty["name"] == "Fen Bilimleri Enstitüsü"
    assert faculty["canonical_name"] == n.canon_faculty(rows[0].faculty).canonical  # the importer's key
    r = await client.post(f"{API}/programs", json={"name": rows[0].program, "faculty_id": faculty["id"]}, headers=h)
    assert r.status_code == 201, r.text
    program = r.json()
    assert program["faculty_id"] == faculty["id"] and program["is_evening"] is False
    # step 3: courses from the rows, code typed loosely, credits with a comma decimal
    courses = []
    for row, typed in zip(rows, ("MBG 532", "mbg534", "MBG\xa0546"), strict=True):
        body = {"code": typed, "name": row.course_name, "t_hours": row.t, "u_hours": row.u, "l_hours": row.l}
        body |= {"credits": "4,5" if row.row == 188 else row.credits, "ects": row.ects}
        r = await client.post(f"{API}/courses", json=body, headers=h)
        assert r.status_code == 201, r.text
        courses.append(r.json())
    assert [c["display_code"] for c in courses] == ["MBG 532", "MBG 534", "MBG 546"]
    assert [c["code"] for c in courses] == [r.course_code for r in rows]  # the importer's stored code
    assert courses[0]["credits"] == 4.5
    # step 4: instructors as written in the rows (titles glued, capitals)
    people: dict[str, int] = {}
    for row in rows[:2]:  # row 190's section stays "Belirlenmedi" (no instructor yet), scenario S1
        name = row.instructors[0]
        if n.canon_person_name(name).canonical in people:  # type: ignore[union-attr]
            continue
        r = await client.post(f"{API}/instructors", json={"full_name": name}, headers=h)
        assert r.status_code == 201, r.text
        people[r.json()["canonical_name"]] = r.json()["id"]
    sections = []
    for row, course in zip(rows, courses, strict=True):
        ins = n.canon_person_name(row.instructors[0])
        assert ins is not None
        links = [{"instructor_id": people[ins.canonical], "role": "PRIMARY"}] if ins.canonical in people else []
        body = {
            "term_id": term_id,
            "course_id": course["id"],
            "program_id": program["id"],
            "label": str(row.label),
            "class_years": "1. Sınıf",
            "enrolment": 20,  # estimated: a new programme has no history (Bahar rows count the joint lecture)
            "mode": "Yüz yüze",
            "instructors": links,
        }
        r = await client.post(f"{API}/sections", json=body, headers=h)
        assert r.status_code == 201, r.text
        sections.append(r.json())
    assert sections[0]["mode"] == "F2F" and sections[0]["class_years"] == [1]
    assert sections[0]["source_key"].startswith("MAN:")
    assert [len(s["instructors"]) for s in sections] == [1, 1, 0]
    # step 5: "3 periods a week, Tue or Thu, weeks 1-14", as 2 + 1 blocks at each course's own hour
    created = []
    for sec, start in zip(sections, ("08.30", "11:00", "13.30"), strict=True):
        body = {"block_size": [2, 1], "days": "Salı veya Perşembe", "start": start, "weeks": "1-14"}
        r = await client.post(f"{API}/sections/{sec['id']}/pattern", json=body, headers=h)
        assert r.status_code == 201, r.text
        out = r.json()
        assert len(out["created"]) == 2 and out["archived_ids"] == []
        created += out["created"]
    return {"faculty": faculty, "program": program, "courses": courses, "sections": sections, "meetings": created}


async def test_from_scratch_programme_is_placed_with_hard_100(client: AsyncClient, parsed_bahar_list: Any) -> None:
    h = await login(client)
    await _rooms()
    term_id = await _term(client, h)
    built = await _build_programme(client, h, parsed_bahar_list, term_id)
    meetings = built["meetings"]
    assert len(meetings) == 6
    for m in meetings:  # the planning-list importer's shape (planning_list.py: fields of a parsed row)
        assert m["day"] is None and m["days"] == [2, 4] and m["flexible_day"] is True
        assert m["weeks"] == list(range(1, 15)) and m["needs_room"] is True and m["status"] == "PARSED"
        assert m["requested_capacity"] == 20 and m["course_code"] in {"MBG 532", "MBG 534", "MBG 546"}
    assert {(m["start_period"], m["end_period"]) for m in meetings} == {(1, 2), (1, 1), (4, 5), (4, 4), (7, 8), (7, 7)}
    listed = (await client.get(f"{API}/requests/meetings", params={"term_id": term_id}, headers=h)).json()
    assert listed["total"] == 6

    # step 7-8: generate through the existing run API, deterministic (one worker, fixed seed)
    body = {"term_id": term_id, "kind": "COURSE", "params": {"workers": 1, "seed": 0, "time_limit_s": 30}}
    r = await client.post(f"{API}/runs", json=body, headers=h)
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    run = (await client.get(f"{API}/runs/{run_id}", headers=h)).json()
    assert run["status"] in {"OPTIMAL", "FEASIBLE"}, run
    assert run["hard_score"] == 100, run
    rows = (await client.get(f"{API}/runs/{run_id}/assignments", headers=h)).json()
    by_meeting: dict[int, list[dict[str, Any]]] = {}
    for a in rows:
        by_meeting.setdefault(a["meeting_request_id"], []).append(a)
    assert set(by_meeting) == {m["id"] for m in meetings}  # every meeting placed
    for sec in built["sections"]:
        mine = [a for m in meetings if m["section_id"] == sec["id"] for a in by_meeting[m["id"]]]
        assert {a["day"] for a in mine} == {2, 4}  # the 2-period and the 1-period block on different days
        assert all(a["room_ids"] for a in mine)
    from app.services.planner_check import check_run

    async with get_session_factory()() as s:
        stored = await s.get(ScheduleRun, run_id)
        assert stored is not None
        res = await check_run(s, stored)
    assert res.violations == [], [f.as_dict() for f in res.violations[:5]]
    assert res.hard_score == 100 and res.requests_placed == res.requests_total == 6
    print(  # evidence line for the hand-off (pytest -s)
        f"P19-C run {run_id}: status={run['status']} hard={run['hard_score']} soft={run['soft_score']} "
        f"assignments={len(rows)} planner_check={res.summary()}"
    )

    # (d) every create is audited, with the after-snapshot and the actor
    for action, count in (
        ("faculty.create", 1),
        ("program.create", 1),
        ("course.create", 3),
        ("instructor.create", 2),
        ("section.create", 3),
        ("section.pattern", 3),
        ("meeting.create", 6),
    ):
        assert await _audit_count(action) == count, action
    async with get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "course.create"))).scalars().first()
        assert ev is not None and ev.actor_id is not None and ev.before is None
        assert ev.after is not None and ev.after["display_code"] == "MBG 532"
        pattern_ev = (
            (await s.execute(select(AuditEvent).where(AuditEvent.action == "section.pattern"))).scalars().first()
        )
        assert pattern_ev is not None and pattern_ev.term_id == term_id and pattern_ev.after["count"] == 2


async def test_duplicates_answer_409_naming_the_existing_row(client: AsyncClient, parsed_bahar_list: Any) -> None:
    h = await login(client)
    row = _row(parsed_bahar_list, 188)
    r = await client.post(f"{API}/courses", json={"code": row.raw["Ders Kodu"], "name": row.course_name}, headers=h)
    assert r.status_code == 201, r.text
    first = r.json()
    for typed in ("MBG 532", "mbg532", "MBG\xa0532", " MBG  0532 ", "Mbg 532"):
        r = await client.post(f"{API}/courses", json={"code": typed, "name": "Epigenetik"}, headers=h)
        assert r.status_code == 409, (typed, r.text)
        detail = r.json()["detail"]
        assert detail["existing"]["id"] == first["id"] and "MBG 532" in detail["message"]
    check = (await client.get(f"{API}/courses/code-check", params={"code": "mbg 0532"}, headers=h)).json()
    assert check["display_code"] == "MBG 0532" and check["duplicate"]["id"] == first["id"]
    # renaming another course onto the code is the same collision
    other = (await client.post(f"{API}/courses", json={"code": "MBG 534", "name": "Proteomiks"}, headers=h)).json()
    r = await client.put(f"{API}/courses/{other['id']}", json={"code": "MBG532"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["existing"]["id"] == first["id"]
    # junk around the code is refused, not silently trimmed
    for bad in ("YENİ DERS MBG 536", "MBG", "532", "MBG 532 / MBG 012"):
        r = await client.post(f"{API}/courses", json={"code": bad}, headers=h)
        assert r.status_code == 422, (bad, r.text)
    # İ/ı folding of codes already holds: BİF 111 = BIF 111 (usability U6)
    assert (await client.post(f"{API}/courses", json={"code": "BİF 111"}, headers=h)).status_code == 201
    assert (await client.post(f"{API}/courses", json={"code": "bif111"}, headers=h)).status_code == 409
    # faculties, programmes and instructors collide on their canonical keys
    fac = await client.post(f"{API}/faculties", json={"name": row.faculty}, headers=h)
    assert fac.status_code == 201
    r = await client.post(f"{API}/faculties", json={"name": "FEN BİLİMLERİ ENSTİTÜSÜ"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["existing"]["id"] == fac.json()["id"]
    prog = await client.post(f"{API}/programs", json={"name": row.program}, headers=h)
    assert prog.status_code == 201
    r = await client.post(f"{API}/programs", json={"name": n.tr_upper(row.program)}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["existing"]["id"] == prog.json()["id"]
    person = await client.post(f"{API}/instructors", json={"full_name": row.instructors[0]}, headers=h)
    assert person.status_code == 201 and person.json()["full_name"] == "Eda TAHİR TURANLI"
    assert person.json()["title"] == "Prof. Dr."
    r = await client.post(f"{API}/instructors", json={"full_name": "Prof. Dr. Eda Tahir Turanlı"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["existing"]["id"] == person.json()["id"]
    # a placeholder is not a person: "not yet assigned" is a section without instructors
    r = await client.post(
        f"{API}/instructors", json={"full_name": "Dersi verecek öğretim üyesi henüz belli değildir"}, headers=h
    )
    assert r.status_code == 422


@pytest.mark.skipif(
    n.course_key("ÇEV 101") != n.course_key("CEV 101"),
    reason="course_key does not fold Ç yet (ÇEV = CEV product decision lands with the importer agent's P19-Q1)",
)
async def test_cev_and_cev_without_cedilla_are_one_code(client: AsyncClient) -> None:
    h = await login(client)
    r = await client.post(f"{API}/courses", json={"code": "ÇEV 101", "name": "Çevre Bilimi"}, headers=h)
    assert r.status_code == 201 and r.json()["display_code"] == "ÇEV 101"
    for typed in ("CEV101", "çev 101", "Cev 0101"):
        r = await client.post(f"{API}/courses", json={"code": typed}, headers=h)
        assert r.status_code == 409, typed
        assert r.json()["detail"]["existing"]["display_code"] == "ÇEV 101"


async def test_viewers_and_users_without_planning_edit_get_403(client: AsyncClient) -> None:
    admin = await login(client)
    term_id = await _term(client, admin)
    course = (await client.post(f"{API}/courses", json={"code": "MBG 532"}, headers=admin)).json()
    section = await client.post(
        f"{API}/sections", json={"term_id": term_id, "course_id": course["id"], "enrolment": 20}, headers=admin
    )
    assert section.status_code == 201
    sid = section.json()["id"]
    _, viewer = await make_user(client, admin, "izleyici@uni.edu.tr", role="VIEWER")
    _, teacher = await make_user(client, admin, "ogretmen@uni.edu.tr", role="TEACHER")
    writes = [
        ("POST", "/faculties", {"name": "Fen Bilimleri Enstitüsü"}),
        ("POST", "/programs", {"name": "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (İngilizce)"}),
        ("POST", "/courses", {"code": "MBG 534"}),
        ("PUT", f"/courses/{course['id']}", {"name": "Epigenetik"}),
        ("DELETE", f"/courses/{course['id']}", None),
        ("POST", "/instructors", {"full_name": "Prof.Dr. Eda TAHİR TURANLI"}),
        ("POST", "/sections", {"term_id": term_id, "course_id": course["id"]}),
        ("PUT", f"/sections/{sid}", {"enrolment": 30}),
        ("DELETE", f"/sections/{sid}", None),
        ("POST", f"/sections/{sid}/pattern", {"days": "TUE", "start": "11:00", "theory": 1}),
        ("POST", "/requests/meetings", {"section_id": sid, "days": "TUE", "start": "11:00", "periods": 1}),
        ("POST", "/requests/exams", {"term_id": term_id, "course_code": "MBG 532"}),
    ]
    for who in (viewer, teacher):
        for method, path, body in writes:
            r = await client.request(method, f"{API}{path}", json=body, headers=who)
            assert r.status_code == 403, (method, path, r.status_code)
    # the Viewer may read, the teacher (no planning.view) may not
    assert (await client.get(f"{API}/sections/{sid}", headers=viewer)).status_code == 200
    assert (await client.get(f"{API}/sections/{sid}", headers=teacher)).status_code == 403
    assert (await client.get(f"{API}/courses/code-check", params={"code": "MBG 1"}, headers=viewer)).status_code == 200


async def test_archive_never_orphans_assignments_of_a_run(client: AsyncClient, stub_solver: Any) -> None:
    """Deletes archive; a hard delete (``purge``) is refused while a run's assignments point at the row, because
    ``Assignment.meeting_request_id`` is ``SET NULL`` (the published plan would lose its class)."""
    h = await login(client)
    await _rooms()
    term_id = await _term(client, h)
    course = (await client.post(f"{API}/courses", json={"code": "MBG 546", "t_hours": 3}, headers=h)).json()
    sec = (
        await client.post(
            f"{API}/sections", json={"term_id": term_id, "course_id": course["id"], "enrolment": 20}, headers=h
        )
    ).json()
    out = (
        await client.post(f"{API}/sections/{sec['id']}/pattern", json={"days": "Perşembe", "start": "11:00"}, headers=h)
    ).json()
    (mr,) = out["created"]
    r = await client.post(f"{API}/runs", json={"term_id": term_id, "kind": "COURSE", "params": {}}, headers=h)
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    assert (await client.post(f"{API}/runs/{run_id}/activate", headers=h)).status_code == 200
    # hard deletes refused while the active run uses the meeting / the course / the section
    r = await client.delete(f"{API}/requests/meetings/{mr['id']}", params={"purge": "true"}, headers=h)
    assert r.status_code == 409 and str(run_id) in r.json()["detail"]["message"]
    r = await client.delete(f"{API}/sections/{sec['id']}", params={"purge": "true"}, headers=h)
    assert r.status_code == 409
    r = await client.delete(f"{API}/courses/{course['id']}", headers=h)
    assert r.status_code == 409 and "section" in r.json()["detail"]["message"]
    # archiving keeps every row and the assignment link
    r = await client.delete(f"{API}/requests/meetings/{mr['id']}", headers=h)
    assert r.status_code == 200 and r.json()["action"] == "archived"
    async with get_session_factory()() as s:
        row = await s.get(MeetingRequest, mr["id"])
        assert row is not None and row.archived
        linked = (await s.execute(select(Assignment).where(Assignment.meeting_request_id == mr["id"]))).scalars().all()
        assert linked
    assert await _audit_count("meeting.archive") == 1
    # re-applying a pattern replaces the hand-made meetings (archived, listed) instead of duplicating them
    again = await client.post(
        f"{API}/sections/{sec['id']}/pattern",
        json={"days": "Salı", "start": "13:30", "weeks": "İlk 7 hafta"},
        headers=h,
    )
    assert again.status_code == 201 and again.json()["archived_ids"] == []  # the only one was archived above
    second = await client.post(
        f"{API}/sections/{sec['id']}/pattern", json={"days": "Salı", "start": "13:30", "weeks": "1-7"}, headers=h
    )
    assert second.json()["archived_ids"] == [again.json()["created"][0]["id"]]
    # a meeting no run uses can be purged
    fresh = second.json()["created"][0]["id"]
    r = await client.delete(f"{API}/requests/meetings/{fresh}", params={"purge": "true"}, headers=h)
    assert r.status_code == 200 and r.json()["action"] == "deleted"
    assert await _audit_count("meeting.delete") == 1


async def test_meeting_and_exam_requests_by_hand(client: AsyncClient, parsed_bahar_list: Any) -> None:
    h = await login(client)
    rooms = await _rooms()
    term_id = await _term(client, h)
    row = _row(parsed_bahar_list, 188)  # MBG 532, Salı 11:00-13:20, requested/definitive C 504
    course = (await client.post(f"{API}/courses", json={"code": "MBG 532", "t_hours": row.t}, headers=h)).json()
    sec = (
        await client.post(
            f"{API}/sections",
            json={"term_id": term_id, "course_id": course["id"], "enrolment": row.enrolment, "label": row.label},
            headers=h,
        )
    ).json()
    # one meeting as the row has it, the end typed as a clock time
    body = {
        "section_id": sec["id"],
        "days": "SALI",
        "start": "11.00",
        "end": "13:20",
        "weeks": "Tüm Haftalar",
        "room_needs": {"preferred_room": "C\xa0504", "building": "c blok"},
    }
    r = await client.post(f"{API}/requests/meetings", json=body, headers=h)
    assert r.status_code == 201, r.text
    m = r.json()
    imported = n.time_range_to_periods(row.start_time, row.end_time)
    assert (m["day"], m["days"], m["flexible_day"]) == (2, [2], False)
    assert (m["start_period"], m["end_period"]) == (imported.start_period, imported.end_period)
    assert m["requested_room_ids"] == [rooms["C504"]] and m["requested_room_text"] == "C 504"
    assert m["requested_building"] == "C" and m["requested_capacity"] == 80
    # an unknown room, an off-grid time and a section of another term are refused
    for bad in (
        {**body, "room_needs": {"preferred_room": "B 501"}},
        {**body, "start": "09:00"},
        {**body, "end": None},
    ):
        r = await client.post(f"{API}/requests/meetings", json=bad, headers=h)
        assert r.status_code == 422, (bad, r.text)
    # an online section's meeting needs no room
    r = await client.put(f"{API}/sections/{sec['id']}", json={"mode": "Çevrimiçi"}, headers=h)
    assert r.status_code == 200 and r.json()["mode"] == "ONLINE"
    async with get_session_factory()() as s:
        row_m = await s.get(MeetingRequest, m["id"])
        assert row_m is not None and row_m.needs_room is False
    assert await _audit_count("section.update") == 1
    # an exam request by hand, dotted times, merge key like the exam-list importer's
    exam = {
        "term_id": term_id,
        "section_id": sec["id"],
        "date": "2027-06-02",
        "start": "09.20",
        "end": "11.00",
        "requested_tags": "PC",
    }
    r = await client.post(f"{API}/requests/exams", json=exam, headers=h)
    assert r.status_code == 201, r.text
    ex = r.json()
    assert ex["course_code"] == "MBG532" and ex["enrolment"] == 80
    assert (ex["start_period"], ex["end_period"]) == (2, 3)
    assert ex["merge_key"] == "2027-BAHAR:MBG532:2027-06-02:0920" and ex["requested_tags"] == ["PC"]
    r = await client.delete(f"{API}/requests/exams/{ex['id']}", headers=h)
    assert r.status_code == 200 and r.json()["action"] == "archived"
    assert await _audit_count("exam.create") == 1 and await _audit_count("exam.archive") == 1


def _one_row_list(parsed: Any, number: int, path: Any) -> Any:
    """A planning list holding one real Bahar row (its own headers and cells), for import interplay tests."""
    from openpyxl import Workbook

    raw = _row(parsed, number).raw
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sayfa1"
    ws.append(list(raw))
    ws.append(list(raw.values()))
    wb.save(path)
    return path


@pytest.mark.xfail(
    strict=True,
    reason="importers/planning_list.py archives every section of the term missing from the file, MAN: ones too "
    "(diff routed to the importer agent in the P19-C hand-off)",
)
async def test_a_later_import_keeps_hand_made_sections(
    client: AsyncClient, parsed_bahar_list: Any, tmp_path: Any
) -> None:
    from app.importers.planning_list import import_planning_list
    from app.models import Section

    h = await login(client)
    term_id = await _term(client, h, "2026-BAHAR")
    course = (await client.post(f"{API}/courses", json={"code": "MBG 532", "t_hours": 3}, headers=h)).json()
    sec = (
        await client.post(
            f"{API}/sections", json={"term_id": term_id, "course_id": course["id"], "enrolment": 20}, headers=h
        )
    ).json()
    path = _one_row_list(parsed_bahar_list, 189, tmp_path / "bahar_row189.xlsx")  # MBG 534, another course
    async with get_session_factory()() as s:
        await import_planning_list(s, path, "2026-BAHAR")
    async with get_session_factory()() as s:
        row = await s.get(Section, sec["id"])
        assert row is not None and row.archived is False
