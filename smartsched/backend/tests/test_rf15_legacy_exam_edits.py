"""RF-15: exams imported before RF-06 have no stored import values (no ``imported_snapshots`` row ``entity = exam``),
so the first re-import after the deploy could not tell an admin's edit from the file's value and overwrote it.
The importer now rebuilds the import values of such a row on its first re-import:

* from the audit log's exam edit events (``exam_request.update``, ``exam.archive``): the ``before`` value of the
  first edit after the previous import is the imported value;
* an edit event that does not carry the old value marks the field as edited (current value kept);
* a row with no edit event follows the file, as before.

The edits are kept and reported as conflicts (``extra.conflicts``, the preview's ``summary.diff``).

Real fixture rows: the Final exam list, BME 419 rows 2-4 (one exam, three programmes; row 2 has 26 students).
"""

from __future__ import annotations

from pathlib import Path

from app.core import db as dbmod
from app.models import AuditEvent, ImportedSnapshot, ImportJob
from app.models.base import utcnow
from sqlalchemy import delete, select

from tests.api_fixtures import client, login  # noqa: F401
from tests.conftest import EXAM_LIST
from tests.test_rf06_reimport import FINAL, _edited_exam_list, _exam, _exam_by_row, _upload

API = "/api/v1"


async def _forget_import_values() -> None:
    """The database as an import before RF-06 left it: exam rows without stored import values."""
    async with dbmod.get_session_factory()() as s:
        await s.execute(delete(ImportedSnapshot).where(ImportedSnapshot.entity == "exam"))
        await s.commit()


async def _snapshot(ex_id: int) -> dict | None:  # type: ignore[type-arg]
    async with dbmod.get_session_factory()() as s:
        row = (
            await s.execute(
                select(ImportedSnapshot).where(ImportedSnapshot.entity == "exam", ImportedSnapshot.entity_id == ex_id)
            )
        ).scalar_one_or_none()
        return None if row is None else dict(row.values or {})


async def test_edit_made_before_rf06_survives_the_first_reimport(client, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    await _upload(client, h, "exam-list", EXAM_LIST, term_code=FINAL)
    ex2, ex3, ex4 = await _exam_by_row(2), await _exam_by_row(3), await _exam_by_row(4)
    assert ex2.enrolment == 26
    # before RF-06: the planning office corrects row 2's head count and archives row 3 (both audited)
    r = await client.put(f"{API}/requests/exams/{ex2.id}", json={"enrolment": "30"}, headers=h)
    assert r.status_code == 200, r.text
    r = await client.put(f"{API}/requests/exams/{ex3.id}", json={"archived": True}, headers=h)
    assert r.status_code == 200, r.text
    await _forget_import_values()
    async with dbmod.get_session_factory()() as s:
        actions = (
            await s.execute(
                select(AuditEvent.action).where(
                    AuditEvent.entity_type == "exam_request", AuditEvent.entity_id.in_([str(ex2.id), str(ex3.id)])
                )
            )
        ).scalars()
        assert sorted(actions) == ["exam_request.update", "exam_request.update"]

    # the next list changes row 2 to 28 students: the preview shows the conflict, nothing is written
    v3 = _edited_exam_list(tmp_path, enrolment_row2=28)
    preview = await _upload(client, h, "exam-list", v3, term_code=FINAL, dry_run="true")
    diff = preview["summary"]["diff"]
    conflict = next(row for row in diff["rows"] if row["change"] == "conflict")
    assert conflict["id"] == ex2.id
    assert [(c["field"], c["planner"], c["file"], c["previous_import"], c["resolution"]) for c in conflict["conflicts"]] == [
        ("enrolment", 30, 28, 26, "kept")
    ]
    assert diff["counts"]["exam_requests"]["conflict"] == 1
    assert (await _snapshot(ex2.id)) is None  # a preview writes nothing

    # the real re-import keeps both edits and reports the conflict
    job = await _upload(client, h, "exam-list", v3, term_code=FINAL)
    extra = job["summary"]["extra"]
    assert (await _exam(ex2.id)).enrolment == 30
    assert (await _exam(ex3.id)).archived is True
    assert [(c["id"], c["field"], c["planner"], c["file"], c["previous_import"]) for c in extra["conflicts"]] == [
        (ex2.id, "enrolment", 30, 28, 26)
    ]
    assert extra["rebuilt_import_values"] == {"from_audit": 2, "edited_unknown": 0}
    # the rebuilt import values are stored: the next import is an ordinary RF-06 merge
    snap2, snap4 = await _snapshot(ex2.id), await _snapshot(ex4.id)
    assert snap2 is not None and snap2["enrolment"] == 28 and snap4 is not None
    job = await _upload(client, h, "exam-list", v3, term_code=FINAL)
    assert (await _exam(ex2.id)).enrolment == 30 and (await _exam(ex3.id)).archived is True
    assert job["summary"]["extra"]["conflicts"] == [] and job["summary"]["extra"]["rebuilt_import_values"] == {
        "from_audit": 0,
        "edited_unknown": 0,
    }


async def test_edit_without_an_old_value_is_kept_and_a_row_without_edits_follows_the_file(client, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    await _upload(client, h, "exam-list", EXAM_LIST, term_code=FINAL)
    ex2 = await _exam_by_row(2)
    async with dbmod.get_session_factory()() as s:
        row = await s.get(type(ex2), ex2.id)
        assert row is not None
        row.enrolment = 31
        # an older edit event that recorded only the new value (no ``before``)
        s.add(
            AuditEvent(
                action="exam_request.update",
                entity_type="exam_request",
                entity_id=str(ex2.id),
                term_id=ex2.term_id,
                after={"enrolment": 31},
            )
        )
        await s.commit()
    await _forget_import_values()

    v3 = _edited_exam_list(tmp_path, enrolment_row2=28)
    job = await _upload(client, h, "exam-list", v3, term_code=FINAL)
    extra = job["summary"]["extra"]
    assert (await _exam(ex2.id)).enrolment == 31
    assert [(c["id"], c["field"], c["planner"], c["file"], c["previous_import"]) for c in extra["conflicts"]] == [
        (ex2.id, "enrolment", 31, 28, None)
    ]
    assert extra["rebuilt_import_values"] == {"from_audit": 0, "edited_unknown": 1}


async def test_edit_overwritten_by_an_older_reimport_is_not_resurrected(client, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """An edit made before an earlier (pre-RF-06) re-import was already replaced by that import's file value; only
    the edits after the previous import count."""
    h = await login(client)
    await _upload(client, h, "exam-list", EXAM_LIST, term_code=FINAL)
    ex2 = await _exam_by_row(2)
    r = await client.put(f"{API}/requests/exams/{ex2.id}", json={"enrolment": 30}, headers=h)
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        row = await s.get(type(ex2), ex2.id)
        assert row is not None
        row.enrolment = 27  # the pre-RF-06 re-import of a list saying 27 overwrote the edit
        s.add(ImportJob(kind="exam-list", term_code=FINAL, status="DONE", summary={}, finished_at=utcnow()))
        await s.commit()
    await _forget_import_values()

    job = await _upload(client, h, "exam-list", _edited_exam_list(tmp_path, enrolment_row2=28), term_code=FINAL)
    assert (await _exam(ex2.id)).enrolment == 28  # no edit since the previous import: the file applies
    assert job["summary"]["extra"]["conflicts"] == []
