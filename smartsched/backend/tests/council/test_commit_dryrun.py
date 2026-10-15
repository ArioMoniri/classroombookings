"""Commit dry-run (P19-I4) and the per-term write lock on real council commits, on the real Bahar list.

The dry-run runs the same importers and writer and rolls back: the database is unchanged, its counts equal
the real commit's, a re-upload of the same file is all "unchanged", and a planner's studio edit that the file
also changes is a conflict (keep = the planner's value stays, take = the file's value)."""

from __future__ import annotations

from typing import Any

from app.core.db import get_session_factory
from app.models import (
    Assignment,
    AuditEvent,
    Block,
    Building,
    ConstraintRow,
    CouncilJob,
    Course,
    ExamRequest,
    Faculty,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    Term,
    Week,
)
from app.services import term_lock
from app.services.studio_classes import ensure_snapshots, load_snapshots
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from tests.api_fixtures import login
from tests.council import exports
from tests.council.conftest import BAHAR_LIST
from tests.council.test_formats_api import upload

TABLES = (
    Term,
    Week,
    Building,
    Room,
    Faculty,
    Program,
    Course,
    Instructor,
    Section,
    MeetingRequest,
    ExamRequest,
    Block,
    ScheduleRun,
    Assignment,
    ConstraintRow,
    AuditEvent,
)
TERM = {"code": "2026-BAHAR", "name": "Bahar 2026", "week_count": 14}


async def db_state() -> dict[str, Any]:
    async with get_session_factory()() as s:
        out: dict[str, Any] = {
            m.__tablename__: (await s.execute(select(func.count()).select_from(m))).scalar_one() for m in TABLES
        }
        out["jobs"] = [(j.id, j.status, len(j.commits or [])) for j in (await s.execute(select(CouncilJob))).scalars()]
    return out


def bahar_csv(patch: bool = False) -> bytes:
    data = exports.csv_bytes(BAHAR_LIST, delimiter=";", encoding="cp1254", decimal=",", dotted_times=True)
    if not patch:
        return data
    lines = data.decode("cp1254").split("\r\n")
    assert lines[1].startswith("MDBF;") and ";MAT 112;" in lines[1] and ";13.30;16.00;" in lines[1]
    lines[1] = lines[1].replace(";13.30;16.00;", ";14.20;16.50;")  # the department moved MAT 112 §1 later
    return "\r\n".join(lines).encode("cp1254")


async def commit(client, h, job_id: int, **body: Any) -> dict[str, Any]:
    payload = {"term": TERM, "allow_pending": True, **body}
    r = await client.post(f"/api/v1/council/jobs/{job_id}/commit", headers=h, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


async def test_dry_run_changes_nothing_and_counts_what_the_commit_then_writes(client):
    h = await login(client)
    job = await upload(client, h, ("bahar_v5.csv", bahar_csv()))
    before = await db_state()

    dry = await commit(client, h, job["id"], dry_run=True)
    assert dry["dry_run"] is True and dry["result"]["term_created"] is True
    c = dry["counts"]
    assert c["meeting_requests"] == {"create": 1524, "update": 0, "unchanged": 0, "conflict": 0}
    assert c["terms"]["create"] == 1 and c["sections"]["create"] > 1000 and c["rooms"]["create"] > 50
    assert dry["rows_total"] >= 1524 + c["sections"]["create"] and len(dry["rows"]) == 500
    assert await db_state() == before  # no term, room, request, audit event; the job is still READY/REVIEW

    real = await commit(client, h, job["id"])
    assert real["changes"] == c  # the same writer, the same counts
    after = await db_state()
    assert after["meeting_requests"] == 1524 and after["terms"] == 1
    assert after["sections"] == c["sections"]["create"] and after["rooms"] == c["rooms"]["create"]

    # the same file uploaded again in a new job: everything is unchanged
    job2 = await upload(client, h, ("bahar_v5 (1).csv", bahar_csv()))
    again = await commit(client, h, job2["id"], dry_run=True)
    assert again["counts"]["meeting_requests"] == {"create": 0, "update": 0, "unchanged": 1524, "conflict": 0}
    assert again["result"]["term_created"] is False


async def test_a_planner_edit_the_file_also_changes_is_a_conflict_keep_or_take(client):
    h = await login(client)
    job = await upload(client, h, ("bahar_v5.csv", bahar_csv()))
    await commit(client, h, job["id"])
    async with get_session_factory()() as s:  # the planner moves MAT 112 §1 to P1-P3 in the studio
        mr = (
            await s.execute(
                select(MeetingRequest)
                .options(selectinload(MeetingRequest.section))
                .join(Section)
                .join(Course)
                .where(Course.code == "MAT112", Section.label == "1", MeetingRequest.day == 4)
            )
        ).scalar_one()
        mr_id, file_periods = mr.id, (mr.start_period, mr.end_period)
        await ensure_snapshots(s, mr, await load_snapshots(s, [mr]))
        mr.start_period, mr.end_period = 1, 3
        await s.commit()
    job2 = await upload(client, h, ("bahar_v5 v2.csv", bahar_csv(patch=True)))
    before = await db_state()

    keep = await commit(client, h, job2["id"], dry_run=True)
    m = keep["counts"]["meeting_requests"]
    assert m["conflict"] == 1 and m["create"] == 0 and m["unchanged"] >= 1500
    row = next(r for r in keep["rows"] if r["change"] == "conflict")
    assert row["entity"] == "meeting_requests" and row["id"] == mr_id
    fields = {x["field"]: x for x in row["conflicts"]}
    assert fields["start_period"]["planner"] == 1 and fields["start_period"]["resolution"] == "kept"
    assert fields["start_period"]["previous_import"] == file_periods[0] and fields["start_period"]["file"] == 8

    take = await commit(client, h, job2["id"], dry_run=True, on_conflict="take")
    row = next(r for r in take["rows"] if r["id"] == mr_id)
    assert row["change"] == "conflict" and {x["resolution"] for x in row["conflicts"]} == {"taken"}
    assert {"field": "start_period", "from": 1, "to": 8} in row["fields"]
    assert await db_state() == before

    await commit(client, h, job2["id"])  # keep (default): the planner's move survives the new file
    async with get_session_factory()() as s:
        assert (await s.get(MeetingRequest, mr_id)).start_period == 1


async def test_a_real_commit_holds_the_terms_write_lock(client):
    h = await login(client)
    job = await upload(client, h, ("bahar_v5.csv", bahar_csv()))
    handle = await term_lock.acquire(term_lock.term_key("2026-bahar"), "import:99 planning-list")
    try:
        r = await client.post(
            f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"term": TERM, "allow_pending": True}
        )
        assert r.status_code == 409 and r.json()["detail"]["code"] == "term_locked"
        assert r.json()["detail"]["holder"] == "import:99 planning-list"
        # a dry-run writes nothing, so it does not need the lock
        r = await client.post(
            f"/api/v1/council/jobs/{job['id']}/commit",
            headers=h,
            json={"term": TERM, "allow_pending": True, "dry_run": True},
        )
        assert r.status_code == 200 and r.json()["counts"]["meeting_requests"]["create"] == 1524
    finally:
        await term_lock.release(handle)
    assert (await db_state())["meeting_requests"] == 0
