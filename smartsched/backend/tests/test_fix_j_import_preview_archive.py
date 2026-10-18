"""FIX-J, round-4 e2e findings on the import preview and re-imports (real fixtures):

* E2EA2-F01: rows the file no longer has are counted as ``archive`` (not ``update``), per entity, with
  ``change: "archive"`` rows listed first after conflicts, so the preview can say "N kayıt arşivlenecek";
* E2EA-F03: a composite primary key (``section_instructors``) is a plain string id in the diff, never an array;
* E2EA-F02: renaming a programme and re-importing the planning list keeps that programme's sections and meeting
  requests (no archive and recreate).
"""

from __future__ import annotations

from app.core import db as dbmod
from app.council.dryrun import ChangeRecorder, summarize
from app.models import MeetingRequest, Program, Section, SectionInstructor
from sqlalchemy import func, select

from tests.api_fixtures import client, login  # noqa: F401
from tests.conftest import EXAM_LIST, GUZ_LIST
from tests.test_rf06_reimport import API, FINAL, GUZ, _edited_exam_list, _exam_by_row, _upload


def test_composite_primary_key_is_a_string_id() -> None:
    rec = ChangeRecorder()
    assert rec._ident(SectionInstructor(section_id=12, instructor_id=34, role="PRIMARY")) == (
        "section_instructors",
        "12:34",
    )


def test_archived_rows_are_counted_as_archive() -> None:
    rec = ChangeRecorder()
    rec.updated[("exam_requests", 4)] = {
        "entity": "exam_requests",
        "id": 4,
        "key": "BME419",
        "fields": {"archived": [False, True]},
    }
    rec.updated[("exam_requests", 5)] = {
        "entity": "exam_requests",
        "id": 5,
        "key": "X",
        "fields": {"enrolment": [3, 4]},
    }
    out = summarize(rec, {}, "keep")
    assert out["counts"]["exam_requests"] == {"create": 0, "update": 1, "archive": 1, "unchanged": 0, "conflict": 0}
    assert [r["change"] for r in out["rows"]] == ["archive", "update"]


async def test_preview_names_archives(client, tmp_path) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    await _upload(client, h, "exam-list", EXAM_LIST, term_code=FINAL)
    ex4 = await _exam_by_row(4)
    preview = await _upload(
        client, h, "exam-list", _edited_exam_list(tmp_path, drop_row=4), term_code=FINAL, dry_run="true"
    )
    diff = preview["summary"]["diff"]
    assert diff["counts"]["exam_requests"]["archive"] == 1
    row = next(r for r in diff["rows"] if r["change"] == "archive")
    assert row["id"] == ex4.id and row["entity"] == "exam_requests"


async def test_programme_rename_keeps_sections_on_planning_list_reimport(client) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    await _upload(client, h, "planning-list", GUZ_LIST, term_code=GUZ)
    async with dbmod.get_session_factory()() as s:
        pid = (
            await s.execute(
                select(Section.program_id)
                .where(Section.program_id.is_not(None))
                .group_by(Section.program_id)
                .order_by(func.count(Section.id).desc())
                .limit(1)
            )
        ).scalar_one()
        prog = await s.get(Program, pid)
        assert prog is not None
        before = set(
            (
                await s.execute(select(Section.id).where(Section.program_id == pid, Section.archived.is_(False)))
            ).scalars()
        )
        meetings = set(
            (
                await s.execute(
                    select(MeetingRequest.id)
                    .join(Section)
                    .where(Section.program_id == pid, MeetingRequest.archived.is_(False))
                )
            ).scalars()
        )
    assert before and meetings
    r = await client.put(f"{API}/departments/{pid}", json={"name": f"{prog.name} RFB"}, headers=h)
    assert r.status_code == 200, r.text
    preview = await _upload(client, h, "planning-list", GUZ_LIST, term_code=GUZ, dry_run="true")
    counts = preview["summary"]["diff"]["counts"]
    assert counts.get("sections", {}).get("create", 0) == 0 and counts.get("sections", {}).get("archive", 0) == 0
    assert counts.get("meeting_requests", {}).get("create", 0) == 0
    await _upload(client, h, "planning-list", GUZ_LIST, term_code=GUZ)
    async with dbmod.get_session_factory()() as s:
        after = set(
            (
                await s.execute(select(Section.id).where(Section.program_id == pid, Section.archived.is_(False)))
            ).scalars()
        )
        meetings_after = set(
            (
                await s.execute(
                    select(MeetingRequest.id)
                    .join(Section)
                    .where(Section.program_id == pid, MeetingRequest.archived.is_(False))
                )
            ).scalars()
        )
        renamed = await s.get(Program, pid)
    assert after == before and meetings_after == meetings
    assert renamed is not None and renamed.name.endswith(" RFB")
