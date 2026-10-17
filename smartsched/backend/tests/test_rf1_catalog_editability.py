"""RF-01 / RF-03 / RF-05 (audit docs/testing/audits/2026-10-17-no-mock-and-editability.md, A1, A3, Part B).

* RF-01: the /classes "Öğrenci" edit sends ``{"enrolment": n}`` to ``PUT /requests/meetings|exams/{id}``; the
  schemas had no such field, so pydantic dropped it (HTTP 200, value unchanged). It is now written to the
  section (meetings) or the exam request, audited, and a negative or time-shaped value is refused (422).
* RF-03: ``GET /auth/sso/admin/invite-mail`` tells the users screen whether SMTP is set up, so the invite sheet's
  "Davet e-postası gönder" switch defaults on with SMTP and explains itself without.
* RF-05: ``GET /catalog/usage/{entity}/{id}`` answers what a delete would touch (and whether the backend would
  refuse it) and "Son değişiklik" (who, when) from the audit log, for the /admin/catalog screens.
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import AuditEvent, ExamRequest, MeetingRequest, Section
from httpx import AsyncClient
from sqlalchemy import select

from tests.api_fixtures import add_one_request, login
from tests.crbs_support import make_user

API = "/api/v1"


async def _term(client: AsyncClient, h: dict[str, str]) -> int:
    r = await client.post(f"{API}/terms", json={"code": "2026-BAHAR", "name": "2026 Bahar", "week_count": 14}, headers=h)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _events(action: str) -> list[AuditEvent]:
    async with dbmod.get_session_factory()() as s:
        q = select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        return list((await s.execute(q)).scalars())


# --------------------------------------------------------------------------------------------- RF-01


async def test_meeting_enrolment_edit_is_persisted_and_audited(client: AsyncClient) -> None:
    h = await login(client)
    term_id = await _term(client, h)
    mid = await add_one_request(term_id)  # its section seats 10
    r = await client.put(f"{API}/requests/meetings/{mid}", json={"enrolment": 77}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["enrolment"] == 77
    # survives a reload
    assert (await client.get(f"{API}/requests/meetings/{mid}", headers=h)).json()["enrolment"] == 77
    async with dbmod.get_session_factory()() as s:
        mr = await s.get(MeetingRequest, mid)
        assert mr is not None
        sec = await s.get(Section, mr.section_id)
        assert sec is not None and sec.enrolment == 77
    (ev,) = await _events("section.update")
    assert ev.before is not None and ev.after is not None
    assert ev.before["enrolment"] == 10 and ev.after["enrolment"] == 77
    assert ev.term_id == term_id and ev.actor_id is not None
    # clearing it is allowed (unknown size), the same value is a no-op (no second audit row)
    r = await client.put(f"{API}/requests/meetings/{mid}", json={"enrolment": 77}, headers=h)
    assert r.status_code == 200 and len(await _events("section.update")) == 1
    r = await client.put(f"{API}/requests/meetings/{mid}", json={"enrolment": None}, headers=h)
    assert r.status_code == 200 and r.json()["enrolment"] is None


async def test_meeting_enrolment_rejects_bad_values(client: AsyncClient) -> None:
    h = await login(client)
    mid = await add_one_request(await _term(client, h))
    for bad in (-1, 5000, "12:30"):
        r = await client.put(f"{API}/requests/meetings/{mid}", json={"enrolment": bad}, headers=h)
        assert r.status_code == 422, (bad, r.text)
    assert (await client.get(f"{API}/requests/meetings/{mid}", headers=h)).json()["enrolment"] == 10


async def test_meeting_enrolment_needs_planning_edit(client: AsyncClient) -> None:
    admin = await login(client)
    mid = await add_one_request(await _term(client, admin))
    _, viewer = await make_user(client, admin, "izleyici@example.com", role="VIEWER")
    r = await client.put(f"{API}/requests/meetings/{mid}", json={"enrolment": 77}, headers=viewer)
    assert r.status_code == 403


async def test_exam_enrolment_edit_is_persisted_and_audited(client: AsyncClient) -> None:
    h = await login(client)
    term_id = await _term(client, h)
    async with dbmod.get_session_factory()() as s:
        ex = ExamRequest(term_id=term_id, course_code="MAT112", course_name="Analiz II", enrolment=40)
        s.add(ex)
        await s.commit()
        ex_id = ex.id
    r = await client.put(f"{API}/requests/exams/{ex_id}", json={"enrolment": 64}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["enrolment"] == 64
    async with dbmod.get_session_factory()() as s:
        row = await s.get(ExamRequest, ex_id)
        assert row is not None and row.enrolment == 64
    (ev,) = await _events("exam_request.update")
    assert ev.before == {"enrolment": 40} and ev.after == {"enrolment": 64}
    r = await client.put(f"{API}/requests/exams/{ex_id}", json={"enrolment": -3}, headers=h)
    assert r.status_code == 422


# --------------------------------------------------------------------------------------------- RF-03


async def test_invite_mail_status_without_smtp(client: AsyncClient) -> None:
    h = await login(client)
    r = await client.get(f"{API}/auth/sso/admin/invite-mail", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"configured": False}
    _, viewer = await make_user(client, h, "izleyici2@example.com", role="VIEWER")
    assert (await client.get(f"{API}/auth/sso/admin/invite-mail", headers=viewer)).status_code == 403


# --------------------------------------------------------------------------------------------- RF-05


async def test_catalog_usage_reports_uses_and_last_change(client: AsyncClient) -> None:
    h = await login(client)
    term_id = await _term(client, h)
    fac = (await client.post(f"{API}/faculties", json={"name": "Fen Fakültesi"}, headers=h)).json()
    prog = (await client.post(f"{API}/programs", json={"name": "Matematik", "faculty_id": fac["id"]}, headers=h)).json()
    course = (await client.post(f"{API}/courses", json={"code": "MAT 112", "name": "Analiz II"}, headers=h)).json()
    ins = (await client.post(f"{API}/instructors", json={"full_name": "Dr. Ayşe Yılmaz"}, headers=h)).json()
    sec = (
        await client.post(
            f"{API}/sections",
            json={
                "term_id": term_id,
                "course_id": course["id"],
                "program_id": prog["id"],
                "label": "1",
                "enrolment": 30,
                "instructors": [{"instructor_id": ins["id"]}],
            },
            headers=h,
        )
    ).json()

    r = await client.get(f"{API}/catalog/usage/instructor/{ins['id']}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uses"] == {"sections": 1} and body["blocked"] is True
    assert body["last_change"]["action"] == "instructor.create"
    assert body["last_change"]["actor"] and body["last_change"]["at"]

    r = await client.put(f"{API}/instructors/{ins['id']}", json={"full_name": "Dr. Ayşe Yılmaz Kaya"}, headers=h)
    assert r.status_code == 200, r.text
    body = (await client.get(f"{API}/catalog/usage/instructor/{ins['id']}", headers=h)).json()
    assert body["last_change"]["action"] == "instructor.update"

    assert (await client.get(f"{API}/catalog/usage/course/{course['id']}", headers=h)).json()["uses"] == {
        "sections": 1
    }
    assert (await client.get(f"{API}/catalog/usage/faculty/{fac['id']}", headers=h)).json()["uses"] == {"programs": 1}
    prog_use = (await client.get(f"{API}/catalog/usage/program/{prog['id']}", headers=h)).json()
    assert prog_use["uses"] == {"sections": 1} and prog_use["blocked"] is True
    sec_use = (await client.get(f"{API}/catalog/usage/section/{sec['id']}", headers=h)).json()
    # a section is archived, never refused: the answer lists what goes with it
    assert sec_use["blocked"] is False and sec_use["action"] == "archive"
    assert sec_use["uses"] == {}

    # an unused instructor can be deleted
    other = (await client.post(f"{API}/instructors", json={"full_name": "Mehmet Demir"}, headers=h)).json()
    free = (await client.get(f"{API}/catalog/usage/instructor/{other['id']}", headers=h)).json()
    assert free == {**free, "uses": {}, "blocked": False, "action": "delete"}

    assert (await client.get(f"{API}/catalog/usage/instructor/999999", headers=h)).status_code == 404
    assert (await client.get(f"{API}/catalog/usage/room/1", headers=h)).status_code == 422


async def test_catalog_usage_needs_planning_view(client: AsyncClient) -> None:
    h = await login(client)
    ins = (await client.post(f"{API}/instructors", json={"full_name": "Mehmet Demir"}, headers=h)).json()
    _, teacher = await make_user(client, h, "ogretmen@example.com", role="TEACHER")
    assert (await client.get(f"{API}/catalog/usage/instructor/{ins['id']}", headers=teacher)).status_code == 403
