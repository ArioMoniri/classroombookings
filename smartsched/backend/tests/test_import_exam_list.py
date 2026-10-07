"""Exam-list importer on the real 2026 Final fixture."""

from __future__ import annotations

from collections import Counter
from datetime import date, time

from sqlalchemy import func, select

from app.importers.exam_list import import_exam_list
from app.models import ExamRequest
from tests.conftest import EXAM_LIST


def test_parse_exam_list_counts(parsed_exam_list):
    p = parsed_exam_list
    assert abs(p.rows_total - 926) <= 10
    assert len(p.skipped) < 0.01 * p.rows_total
    dated = [r for r in p.rows if r.date is not None]
    assert len(dated) > 0.9 * len(p.rows)
    timed = [r for r in dated if r.start_time and r.end_time]
    with_p = [r for r in timed if r.periods.start_period is not None]
    assert len(with_p) >= 0.99 * len(timed)
    print(f"\n[exam] rows={p.rows_total} dated={len(dated)} timed={len(timed)} periods={len(with_p)}")
    wc = Counter("".join("#" if ch.isdigit() else ch for ch in w) for r in p.rows for w in r.warnings)
    for w, c in wc.most_common(10):
        print(f"   {c:4d}  {w}")


def test_bme419_rows_share_merge_key(parsed_exam_list):
    rows = [r for r in parsed_exam_list.rows if r.course_code == "BME419"]
    assert len(rows) >= 3
    keys = {r.merge_key for r in rows}
    assert keys == {"BME419:2026-05-13:1300"}
    assert sum(r.enrolment or 0 for r in rows) >= 70
    assert rows[0].date == date(2026, 5, 13) and rows[0].start_time == time(13, 0)
    assert rows[0].definitive.room_codes == ["C201"]
    assert (rows[0].periods.start_period, rows[0].periods.end_period) == (6, 8)


def test_exam_quirks(parsed_exam_list):
    rows = parsed_exam_list.rows
    ranged = [r for r in rows if r.date_end is not None]
    assert ranged and ranged[0].date == date(2026, 6, 11) and ranged[0].date_end == date(2026, 6, 12)
    dotted = [r for r in rows if r.raw.get("Sınav Başlangıç Saati") == "11.00"]
    assert dotted and all(r.start_time == time(11, 0) for r in dotted)
    on_campus = [r for r in rows if r.on_campus_written]
    assert 70 <= len(on_campus) <= 90
    no_exam = [r for r in rows if r.no_exam]
    assert 10 <= len(no_exam) <= 25 and all(r.needs_room is False for r in no_exam)
    invig = [r for r in rows if r.venue.invigilators]
    assert invig
    multi = [r for r in rows if len(r.definitive.room_codes) >= 3]
    assert multi, "multi-room definitive assignments (A 101 - A 102 - A 106)"
    classes = [r for r in rows if r.class_years == [1, 2]]
    assert classes


async def test_import_exam_list_idempotent_and_merges(session):
    rep1 = await import_exam_list(session, EXAM_LIST, "2026-FINAL")
    assert rep1.rows_imported > 900 and rep1.created["exam_requests"] == rep1.rows_imported
    assert rep1.extra["merge_groups"] > 500 and rep1.extra["merged_rows"] > 100
    n1 = (await session.execute(select(func.count(ExamRequest.id)))).scalar_one()
    rep2 = await import_exam_list(session, EXAM_LIST, "2026-FINAL")
    assert rep2.created["exam_requests"] == 0 and rep2.updated["exam_requests"] == rep1.rows_imported
    assert (await session.execute(select(func.count(ExamRequest.id)))).scalar_one() == n1
    # merged cohort: BME 419 on 2026-05-13 13:00 sums enrolment across programmes
    rows = (
        await session.execute(select(ExamRequest).where(ExamRequest.merge_key == "2026-FINAL:BME419:2026-05-13:1300"))
    ).scalars().all()
    assert len(rows) >= 3 and sum(r.enrolment or 0 for r in rows) >= 70
    assert all(r.status == "LOCKED" and r.definitive_room_ids for r in rows)
