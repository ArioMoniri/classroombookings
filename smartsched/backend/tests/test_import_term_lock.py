"""P19-03: imports of one term hold the term's write lock (``app/services/term_lock.py``).

* a request for a term whose lock is held is refused up front with 409, in Turkish and English, naming the
  holder and since when;
* two planning-list imports of one term started together never overlap: the second is refused (409) or its
  job waits for the lock; neither fails with an IntegrityError and the term holds the rows of one import.

The workbook is a real slice of the Bahar planning list (rows 2-61).
"""

from __future__ import annotations

import asyncio

from app.workers.queue import get_queue
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.conftest import BAHAR_LIST
from tests.test_importer_followups import subset

ROWS = list(range(2, 62))


async def _post(client, headers, path, term: str = "2026-BAHAR"):  # type: ignore[no-untyped-def]
    with path.open("rb") as f:
        return await client.post(
            "/api/v1/imports/planning-list",
            files={"file": (path.name, f, "application/octet-stream")},
            data={"term_code": term},
            headers=headers,
        )


async def test_a_locked_term_refuses_imports_with_409(client, tmp_path) -> None:
    from app.services import term_lock

    h = await login(client)
    path = subset(BAHAR_LIST, ROWS[:5], tmp_path / "bahar5.xlsx")
    async with term_lock.term_write_lock(term_lock.term_key("2026-bahar"), "commit:7 planner@uni.edu.tr"):
        r = await _post(client, h, path)
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "term_locked" and detail["holder"] == "commit:7 planner@uni.edu.tr"
        assert detail["since"] and "commit:7" in detail["message"] and "commit:7" in detail["message_tr"]
        assert "kilitli" in detail["message_tr"]
        # another term is not affected
        assert (await _post(client, h, path, term="2026-GUZ")).status_code == 202
    await get_queue().wait_idle()
    assert (await _post(client, h, path)).status_code == 202  # released
    await get_queue().wait_idle()


async def test_two_parallel_imports_of_one_term_do_not_overlap(client, tmp_path) -> None:
    from app.core.db import get_session_factory
    from app.models import ImportJob, MeetingRequest, Section, Term

    h = await login(client)
    path = subset(BAHAR_LIST, ROWS, tmp_path / "bahar60.xlsx")
    first, second = await asyncio.gather(_post(client, h, path), _post(client, h, path))
    codes = sorted([first.status_code, second.status_code])
    assert codes in ([202, 202], [202, 409]), (first.text, second.text)
    await get_queue().wait_idle()
    async with get_session_factory()() as s:
        jobs = list((await s.execute(select(ImportJob).where(ImportJob.kind == "planning-list"))).scalars())
        assert jobs and all(j.status == "DONE" for j in jobs if j.status != "QUEUED"), [
            (j.status, j.error) for j in jobs
        ]
        assert not any("IntegrityError" in (j.error or "") for j in jobs)
        term = (await s.execute(select(Term).where(Term.code == "2026-BAHAR"))).scalar_one()
        n_meetings = (
            await s.execute(
                select(func.count(MeetingRequest.id))
                .join(Section, Section.id == MeetingRequest.section_id)
                .where(Section.term_id == term.id, MeetingRequest.archived.is_(False))
            )
        ).scalar_one()
        done = [j for j in jobs if j.status == "DONE"]
        assert n_meetings == done[0].summary["rows_imported"]  # the rows of one import, never twice
        if len(done) == 2:  # the second waited for the lock and re-imported: nothing new
            later = max(done, key=lambda j: j.id)
            assert later.summary["created"].get("meeting_requests", 0) == 0
