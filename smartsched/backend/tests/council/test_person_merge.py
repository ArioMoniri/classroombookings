"""Renamed instructors in the intake review (owner decision 2026-10-17, decisions-2026-10-17; the T-R1-25 part that
waited for it): a file's instructor whose name is almost a known person's who teaches one of the same courses is not
silently created as a second person. The review asks "Aynı kişi mi?" (``person_merge``, blocking, default merge,
:mod:`app.services.person_match`); a merge writes the file's rows to the existing person, "keep new" adds the
person as before. An exact name (other capitals, titles, NBSP) reuses the person with no question.

Real data: the Bahar 2026 workbook is committed first (its people and courses); the second file is a native
intake.v1 request list naming the same courses."""

from __future__ import annotations

import json
from typing import Any

from app.core.db import get_session_factory
from app.council.formats_text import INTAKE_V1
from app.models import Course, Instructor, MeetingRequest, Section, SectionInstructor
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST
from tests.council.test_formats_api import upload
from tests.crbs_support import make_user

TERM = {"code": "2026-BAHAR", "name": "2026 Bahar", "week_count": 14}


def _doc(*requests: dict[str, Any]) -> bytes:
    return json.dumps({"schema": INTAKE_V1, "requests": list(requests)}, ensure_ascii=False).encode()


def _request(code: str, instructor: str, section: str = "1", program: str = "Bilgisayar Mühendisliği (İngilizce)"):
    return {
        "course_code": code,
        "section": section,
        "program": program,
        "day": "Perşembe",
        "start": "13:30",
        "end": "16:00",
        "instructors": instructor,
        "weeks": "1-14",
    }


async def _bahar(client, h) -> None:
    job = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), ai="false")
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": 0, "term": TERM, "allow_pending": True}
    )
    assert r.status_code == 200, r.text


async def _teacher_of(code: str) -> tuple[int, str]:
    """A real person of the workbook who teaches ``code`` (and whose surname is long enough for a near match)."""
    async with get_session_factory()() as s:
        rows = (
            await s.execute(
                select(Instructor.id, Instructor.full_name)
                .join(SectionInstructor, SectionInstructor.instructor_id == Instructor.id)
                .join(Section, Section.id == SectionInstructor.section_id)
                .join(Course, Course.id == Section.course_id)
                .where(Course.code.in_([code, code.replace(" ", "")]))
            )
        ).all()
    ok = [(i, nm) for i, nm in rows if len(nm.split()[-1]) >= 5]
    assert ok, (code, rows)
    return ok[0]


def _renamed(full_name: str) -> str:
    """The same person with one letter of the surname changed (a typo or a changed spelling)."""
    words = full_name.split()
    last = words[-1]
    words[-1] = last[:-1] + ("a" if last[-1] != "a" else "e")
    return " ".join(words)


async def _people() -> int:
    async with get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(Instructor))).scalar_one())


async def _items(client, h, job_id: int) -> list[dict[str, Any]]:
    r = await client.get(f"/api/v1/council/jobs/{job_id}/review", headers=h)
    assert r.status_code == 200, r.text
    return [it for it in r.json()["items"] if it["kind"] == "person_merge"]


async def test_a_renamed_instructor_is_asked_about_and_merged_into_the_known_person(client):
    h = await login(client)
    await _bahar(client, h)
    known_id, known_name = await _teacher_of("MAT 112")
    typed = _renamed(known_name)
    people = await _people()

    job = await upload(client, h, ("talepler.json", _doc(_request("MAT 112", typed))), ai="false")
    items = await _items(client, h, job["id"])
    assert len(items) == 1, items
    it = items[0]
    assert it["blocking"] is True and it["decision"] is None and it["default"] == "merge"
    assert it["existing_id"] == known_id and it["reason"] == "surname" and it["distance"] == 1
    assert "MAT 112" in it["shared_courses"]
    assert it["title"] in ("Aynı kişi mi?", "Same person?") or "Aynı kişi mi?" in it["title"]
    assert typed not in it["id"] and known_name not in it["id"]  # opaque ids (T-R1-22)

    # undecided: the commit is refused with the coded, name-free 409
    body = {"files": [0], "term": TERM}
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "review_pending" and typed not in r.text

    # a viewer sees the question, not the names
    _uid, viewer = await make_user(client, h, "izleyici@uni.edu.tr", role="VIEWER")
    seen = await _items(client, viewer, job["id"])
    assert seen and typed not in json.dumps(seen, ensure_ascii=False) and known_name not in json.dumps(seen)

    # merge: the request is written to the known person, nobody new
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/review",
        headers=h,
        json={"decisions": [{"id": it["id"], "action": "accept"}]},
    )
    assert r.status_code == 200, r.text
    dry = (
        await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={**body, "dry_run": True})
    ).json()
    assert dry["counts"].get("instructors", {}).get("create", 0) == 0, dry["counts"]
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["general"].get("person_merges_applied") == 1
    assert await _people() == people
    async with get_session_factory()() as s:
        names = set((await s.execute(select(Instructor.full_name))).scalars())
        assert typed not in names
        mr = (
            (
                await s.execute(
                    select(MeetingRequest).where(MeetingRequest.source_key.like("PL:%"), MeetingRequest.day == 4)
                )
            )
            .scalars()
            .all()
        )
        assert mr


async def test_keep_new_adds_the_person_and_an_exact_name_asks_nothing(client):
    h = await login(client)
    await _bahar(client, h)
    known_id, known_name = await _teacher_of("MAT 112")
    typed = _renamed(known_name)
    people = await _people()

    # the same name in other capitals with a title: the known person, no question
    job = await upload(client, h, ("ayni.json", _doc(_request("MAT 112", "Dr. " + known_name.upper()))), ai="false")
    assert await _items(client, h, job["id"]) == []

    # a near name on a course the known person does not teach: no question either (a course in common decides)
    job = await upload(client, h, ("baska.json", _doc(_request("ZZZ 999", typed))), ai="false")
    assert await _items(client, h, job["id"]) == []

    # keep_new (reject): the person is added as today
    job = await upload(client, h, ("yeni.json", _doc(_request("MAT 112", typed))), ai="false")
    (it,) = await _items(client, h, job["id"])
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/review",
        headers=h,
        json={"decisions": [{"id": it["id"], "action": "reject"}]},
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"files": [0], "term": TERM})
    assert r.status_code == 200, r.text
    assert await _people() == people + 1
    async with get_session_factory()() as s:
        assert typed in set((await s.execute(select(Instructor.full_name))).scalars())
