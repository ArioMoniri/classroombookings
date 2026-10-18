"""AS-09: planner warnings ``peak_pressure`` and ``exam_load`` (TR/EN, with the requests).

* Bahar 2026 list + room master: a ``peak_pressure`` cell is reported exactly where the fixed-time requests alone
  need more than 85 % of the suitable rooms (the computation is asserted, not a count); a PC-lab cell exists in
  the data (Monday P8-P9: four classes for the four computer labs);
* Final 2026: ``exam_load`` flags Wednesday 3 June 2026;
* both reach ``GET /runs/{id}/data-issues``; ``precheck.py`` is untouched (read-only guard).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.db import get_session_factory
from app.importers.exam_list import import_exam_list
from app.importers.room_master import import_room_master
from app.models import ScheduleRun, Term
from app.services import exam_load as el
from app.services import forecast as fc
from sqlalchemy import select

from tests.api_fixtures import login
from tests.as_support import add_meeting, add_rooms, add_term
from tests.conftest import EXAM_LIST, FIXTURES


def test_as_09_peak_pressure_computation_on_bahar(parsed_bahar_list):
    rooms = fc.rooms_from_master_csv(FIXTURES / "room_master.csv")
    needs = fc.needs_from_planning_rows(parsed_bahar_list.rows)
    reported = fc.pressure_cells(needs, rooms, 85.0)
    every = fc.shortfall_cells(needs, rooms)
    hot = {(c["day"], c["period"], c["group"]) for c in every if c["supply"] and c["demand"] / c["supply"] > 0.85}
    covered = {(c["day"], p, c["group"]) for c in reported for p in range(c["start_period"], c["end_period"] + 1)}
    assert covered == hot
    pc = [c for c in reported if c["group"] == "PC"]
    assert pc, "the Bahar list has a PC-lab peak"
    text = fc.pressure_text(pc[0])
    assert "bilgisayar laboratuvarı isteyen" in text["tr"] and "uygun 4 oda" in text["tr"]
    assert "computer lab" in text["en"]


def test_as_09_exam_load_flags_wednesday_3_june(parsed_exam_list):
    rows = []
    for r in parsed_exam_list.rows:
        if r.date is None or not r.periods.start_period or not getattr(r.definitive, "room_codes", None):
            continue
        cohorts = frozenset(f"COH:{r.program} {y}. sınıf" for y in r.class_years or []) if r.program else frozenset()
        rows.append((r.row, r.date, r.periods.start_period, r.periods.end_period, int(r.enrolment or 0), cohorts))
    found = el.exam_issues(rows, exam_capacity=1951)
    peak = [f for f in found if f["kind"] == "peak_day"]
    assert peak and peak[0]["date"] == "2026-06-03"
    assert peak[0]["text"]["tr"].startswith("3 Haziran 2026 Çarşamba: 126 sınav")
    assert {f["kind"] for f in found} <= {"peak_day", "seats", "cohort_day"}


async def test_as_09_data_issues_report_has_both_groups(client, parsed_bahar_list):
    h = await login(client)
    rows = [r for r in parsed_bahar_list.rows if r.has_day_and_time and "PC" in (r.venue.tags or [])]
    rooms = fc.rooms_from_master_csv(FIXTURES / "room_master.csv")
    cell = next(c for c in fc.pressure_cells(fc.needs_from_planning_rows(rows), rooms) if c["group"] == "PC")
    async with get_session_factory()() as s:
        term = await add_term(s, "2026-BAHAR", week_kinds=["LECTURE"] * 14)
        rmap = await add_rooms(s, "A103", "A104", "A105", "B207")
        for r in rows:
            if (
                len(r.day.days) == 1
                and r.day.days[0] == cell["day"]
                and r.periods.start_period <= cell["end_period"]
                and cell["start_period"] <= r.periods.end_period
            ):
                await add_meeting(s, term, r, rmap)
        run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", status="FEASIBLE", params={})
        s.add(run)
        await s.commit()
        run_id = run.id
        await import_room_master(s, FIXTURES / "room_master.csv")
        await import_exam_list(s, EXAM_LIST, "2026-FINAL")
        final = (await s.execute(select(Term.id).where(Term.code == "2026-FINAL"))).scalar_one()
        exam_run = ScheduleRun(term_id=final, kind="EXAM", horizon="TERM", status="FEASIBLE", params={})
        s.add(exam_run)
        await s.commit()
        exam_id = exam_run.id
    rep = (await client.get(f"/api/v1/runs/{run_id}/data-issues", headers=h)).json()
    group = next(g for g in rep["groups"] if g["code"] == "peak_pressure")
    assert group["count"] >= 1 and group["title"]["tr"] == "Yoğun saatlerde uygun oda sıkışıklığı"
    item = next(i for i in group["items"] if i["params"]["group"] == "PC")
    assert "bilgisayar laboratuvarı isteyen" in item["message_tr"] and item["request_ids"]
    rep = (await client.get(f"/api/v1/runs/{exam_id}/data-issues", headers=h)).json()
    group = next(g for g in rep["groups"] if g["code"] == "exam_load")
    assert any(i["params"]["kind"] == "peak_day" and i["params"]["date"] == "2026-06-03" for i in group["items"])


def test_as_09_precheck_is_untouched():
    src = Path(__file__).resolve().parents[1] / "app" / "services" / "precheck.py"
    assert "peak_pressure" not in src.read_text(encoding="utf-8")
    assert hashlib.sha256(src.read_bytes()).hexdigest()
