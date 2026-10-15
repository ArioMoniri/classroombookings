"""Structured intake through the council API (P19-I1..I3): exports of the real files are uploaded, read by the
same importers as the originals, committed, and bombs are refused at upload."""

from __future__ import annotations

import json
import re
from collections import Counter

from app.core.db import get_session_factory
from app.importers.normalize import PERIODS
from app.importers.planning_list import import_planning_list
from app.importers.weekly_grid import import_weekly_grid, parse_weekly_grid
from app.models import CouncilJob, MeetingRequest, Room, ScheduleRun, Section, Term
from app.services.exports import export_ics
from app.workers import queue as qmod
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.council import exports
from tests.council.conftest import BAHAR_GRID, BAHAR_LIST
from tests.council.test_formats import BILLION_LAUGHS, intake_v1_doc


async def upload(client, headers, *files: tuple[str, bytes], **form) -> dict:
    data = {"lang": "tr", "year_hint": "2026", **{k: str(v) for k, v in form.items()}}
    parts = [("files", (name, body, "application/octet-stream")) for name, body in files]
    r = await client.post("/api/v1/council/jobs", headers=headers, files=parts, data=data)
    assert r.status_code == 202, r.text
    await qmod.get_queue().wait_idle(600)
    r = await client.get(f"/api/v1/council/jobs/{r.json()['id']}", headers=headers)
    assert r.status_code == 200
    return r.json()


async def refused(client, headers, name: str, body: bytes) -> tuple[int, str]:
    r = await client.post(
        "/api/v1/council/jobs",
        headers=headers,
        files=[("files", (name, body, "application/octet-stream"))],
        data={"lang": "en"},
    )
    return r.status_code, r.text


async def count(model, *where) -> int:
    async with get_session_factory()() as s:
        q = select(func.count()).select_from(model)
        for w in where:
            q = q.where(w)
        return int((await s.execute(q)).scalar_one())


async def test_cp1254_csv_export_commits_like_the_workbook(client):
    """P19-I1: Turkish Excel's ;-CSV of the Bahar list goes through the planning-list importer."""
    h = await login(client)
    cp = exports.csv_bytes(BAHAR_LIST, delimiter=";", encoding="cp1254", decimal=",", dotted_times=True)
    job = await upload(client, h, ("Bahar Derslik Planlama Listesi v5.csv", cp))
    f = job["files"][0]
    assert f["status"] == "DONE" and f["route"] == "fast:planning-list", f
    assert f["format"] == "csv" and f["route_kind"] == "structured"
    assert f["counts"]["meeting"] == 1524  # = the xlsx (tests/council/test_formats.py)
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/commit",
        headers=h,
        json={"group": 0, "term": {"code": "2026-BAHAR-CSV", "week_count": 14}, "allow_pending": True},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["fast_path"][0]["route"] == "fast:planning-list"
    async with get_session_factory()() as s:
        csv_term = (await s.execute(select(Term).where(Term.code == "2026-BAHAR-CSV"))).scalar_one()
        rep = await import_planning_list(s, BAHAR_LIST, "2026-BAHAR-XLSX")
        xlsx_term = (await s.execute(select(Term).where(Term.code == "2026-BAHAR-XLSX"))).scalar_one()
    n_csv = await count(
        MeetingRequest, MeetingRequest.section_id.in_(select(Section.id).where(Section.term_id == csv_term.id))
    )
    n_xlsx = await count(
        MeetingRequest, MeetingRequest.section_id.in_(select(Section.id).where(Section.term_id == xlsx_term.id))
    )
    assert n_xlsx == rep.created["meeting_requests"] and n_csv >= 0.99 * n_xlsx, (n_csv, n_xlsx)


async def test_native_intake_v1_commits_through_the_council_writer(client):
    h = await login(client)
    data = json.dumps(intake_v1_doc(), ensure_ascii=False).encode()
    job = await upload(client, h, ("intake.json", data))
    f = job["files"][0]
    assert f["route"] == "fast:intake-v1" and f["counts"] == {"room": 1, "meeting": 1, "booking": 1}
    body = {"files": [0], "term": {"code": "2026-INTAKE", "week_count": 14}, "allow_pending": True}
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["general"]["meeting_requests"] == 1
    async with get_session_factory()() as s:
        mr = (await s.execute(select(MeetingRequest))).scalar_one()
        a101 = (await s.execute(select(Room).where(Room.code == "A101"))).scalar_one()
    assert mr.day == 4 and mr.start_period is not None and mr.status == "LOCKED"
    assert a101.capacity == 58 and a101.exam_capacity == 30


async def test_unreadable_and_dangerous_uploads_are_refused_before_a_job_exists(client):
    h = await login(client)
    deep = ("[" * 40 + "]" * 40).encode()
    status, text = await refused(client, h, "deep.json", deep)
    assert status == 413 and "levels deep" in text
    status, text = await refused(client, h, "memo.xls", exports.ole2_with_stream("WordDocument"))
    assert status == 400 and "save the file as .docx" in text
    status, text = await refused(client, h, "odalar.xml", BILLION_LAUGHS)
    assert status == 400 and "DTD" in text
    bomb = exports.ods_from_content(
        '<table:table table:name="S"><table:table-row><table:table-cell table:number-columns-repeated="16384">'
        "<text:p>x</text:p></table:table-cell></table:table-row></table:table>"
    )
    status, text = await refused(client, h, "liste.ods", bomb)
    assert status == 413 and "number-columns-repeated" in text
    assert await count(CouncilJob) == 0


def norm(t: str | None) -> str:
    return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()


async def week_ics(week: int) -> tuple[bytes, Counter]:
    """SmartSched's own ICS export of the imported Bahar board, cut to one week, and that week's grid cells."""
    async with get_session_factory()() as s:
        rep = await import_weekly_grid(s, BAHAR_GRID, "2026-BAHAR", year=2026)
        run = await s.get(ScheduleRun, rep.extra["run_ids"]["COURSE"])
        assert run is not None
        ics = await export_ics(s, run)
    head = ics.split("BEGIN:VEVENT", 1)[0]
    events = [e for e in re.findall(r"BEGIN:VEVENT\r\n.*?END:VEVENT\r\n", ics, re.S) if f"-w{week}@" in e]
    parsed = parse_weekly_grid(BAHAR_GRID, 2026)
    idx = next(i for i, sh in enumerate(parsed.sheets, start=1) if sh.week_index == week and sh.kind == "LECTURE")
    cells = Counter(
        (
            e.room_code,
            e.date.isoformat(),
            PERIODS[e.start_period - 1].start.strftime("%H:%M"),
            PERIODS[e.end_period - 1].end.strftime("%H:%M"),
            norm(e.cell.raw),
        )
        for e in parsed.entries
        if e.sheet_index == idx and e.cell.kind == "COURSE"
    )
    return (head + "".join(events) + "END:VCALENDAR\r\n").encode(), cells


async def test_ics_of_a_bahar_week_from_our_own_export_equals_the_grid_cells(client):
    """P19-I3 acceptance: export week 3 of the imported Bahar board as ICS, upload it: the booking records
    are exactly the board's course cells of week 3 (room, date, start, end, text)."""
    h = await login(client)
    data, cells = await week_ics(3)
    assert sum(cells.values()) == 601
    job = await upload(client, h, ("bahar_hafta3.ics", data))
    f = job["files"][0]
    assert f["route"] == "fast:ics" and f["format"] == "ics" and f["counts"] == {"booking": 601}
    items = (
        await client.get(
            f"/api/v1/council/jobs/{job['id']}/records", headers=h, params={"file": 0, "limit": 500, "offset": 0}
        )
    ).json()["items"]
    items += (
        await client.get(
            f"/api/v1/council/jobs/{job['id']}/records", headers=h, params={"file": 0, "limit": 500, "offset": 500}
        )
    ).json()["items"]
    got = Counter((r["room_code"], r["date"], r["start"], r["end"], norm(r["text"])) for r in items)
    assert got == cells
