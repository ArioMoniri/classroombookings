"""FIX-A council note 1 (e2e results 2026-10-18): a renamed person named in two planner groups of one job is asked
about before the first commit, not only after it.

Real data: the Bahar 2026 list names "Dr. Nermin Kılıç Akdoğan" (row 1100, ACU 313) and the Güz 2026/2027 list
"Öğr. Gör. Dr. NERMİN KILIÇ AKOĞLAN" (row 274, ACU 313). In one job they are two groups (BAHAR,
2026-2027-GUZ). Before FIX-A nobody was known yet, so the review had no "Aynı kişi mi?" item; the first group's
commit created one spelling and the second group's commit got a 409 ``review_pending`` for a question nobody had
seen. Now the question is in the review from the start, blocks the first commit of either group, and its answer
holds for the second commit too (no second question)."""

from __future__ import annotations

from typing import Any

from app.core.db import get_session_factory
from app.importers.normalize import canon_person_name
from app.models import Course, Instructor, Section, SectionInstructor
from sqlalchemy import select

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST, GUZ_LIST
from tests.council.test_formats_api import upload


def _is_pair(it: dict[str, Any]) -> bool:
    names = {str(it.get("incoming_name") or "").casefold(), str(it.get("existing_name") or "").casefold()}
    return any("akdoğan" in x for x in names) and any("akoğlan" in x for x in names)


async def _items(client, h, job_id: int) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    r = await client.get(f"/api/v1/council/jobs/{job_id}/review", headers=h)
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


async def _decide_all_but_people(client, h, job_id: int) -> None:  # type: ignore[no-untyped-def]
    todo = [
        {"id": it["id"], "action": "reject" if it["kind"] == "merge" else "accept"}
        for it in await _items(client, h, job_id)
        if it["blocking"] and it["decision"] is None and it["kind"] != "person_merge"
    ]
    if todo:
        r = await client.post(f"/api/v1/council/jobs/{job_id}/review", headers=h, json={"decisions": todo})
        assert r.status_code == 200, r.text


async def _acu313_teachers() -> dict[str, set[str]]:
    async with get_session_factory()() as s:
        rows = (
            await s.execute(
                select(Section.term_id, Instructor.full_name)
                .join(SectionInstructor, SectionInstructor.section_id == Section.id)
                .join(Instructor, Instructor.id == SectionInstructor.instructor_id)
                .join(Course, Course.id == Section.course_id)
                .where(Course.code.in_(["ACU313", "ACU 313"]))
            )
        ).all()
    out: dict[str, set[str]] = {}
    for tid, name in rows:
        out.setdefault(str(tid), set()).add(name)
    return out


async def test_the_question_is_asked_before_the_first_commit_and_holds_for_both_groups(client) -> None:  # type: ignore[no-untyped-def]
    h = await login(client)
    job = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), (GUZ_LIST.name, GUZ_LIST.read_bytes()))
    groups = job["plan"]["groups"]
    assert sorted(g["code"] for g in groups) == ["2026-2027-GUZ", "BAHAR"], groups  # the list alone has no year
    guz = next(i for i, g in enumerate(groups) if g["code"].endswith("GUZ"))
    bahar = 1 - guz

    pairs = [it for it in await _items(client, h, job["id"]) if it["kind"] == "person_merge" and _is_pair(it)]
    assert len(pairs) == 1, pairs
    pair = pairs[0]
    assert pair["blocking"] is True and pair["decision"] is None and pair["default"] == "merge"
    assert "ACU313" in {c.replace(" ", "") for c in pair["shared_courses"]}
    assert "Akdoğan" not in pair["id"] and "AKOĞLAN" not in pair["id"]  # opaque (T-R1-22)

    await _decide_all_but_people(client, h, job["id"])
    # either group's first commit is held by the same question
    for gi in (guz, bahar):
        r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": gi})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "review_pending", r.text
        assert "AKOĞLAN" not in r.text and "Akdoğan" not in r.text
    others = [
        {"id": it["id"], "action": "accept"}
        for it in await _items(client, h, job["id"])
        if it["kind"] == "person_merge" and it["decision"] is None
    ]
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/review", headers=h, json={"decisions": others})
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": guz})
    assert r.status_code == 200, r.text
    # the second group has nothing new to decide: the answer above is its answer
    pending = [it for it in await _items(client, h, job["id"]) if it["blocking"] and it["decision"] is None]
    assert pending == [], pending
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": bahar})
    assert r.status_code == 200, r.text

    # one person teaches ACU 313 in both terms
    teachers = await _acu313_teachers()
    assert len(teachers) == 2, teachers
    names = set().union(*teachers.values())
    assert len(names) == 1, teachers
    async with get_session_factory()() as s:
        canon = {canon_person_name(x).canonical for x in ("Nermin Kılıç Akdoğan", "NERMİN KILIÇ AKOĞLAN")}  # type: ignore[union-attr]
        found = (await s.execute(select(Instructor.id).where(Instructor.canonical_name.in_(canon)))).all()
    assert len(found) == 1
