"""Planning-list importer on the real Güz and Bahar fixtures."""

from __future__ import annotations

from collections import Counter

import pytest
from app.importers.planning_list import import_planning_list
from app.models import Course, MeetingRequest, Program, Section
from sqlalchemy import func, select

from tests.conftest import BAHAR_LIST, GUZ_LIST


def _summary(parsed, name):
    rows = parsed.rows
    with_dt = [r for r in rows if r.has_day_and_time]
    with_p = [r for r in with_dt if r.periods.start_period is not None]
    wc: Counter[str] = Counter()
    for r in rows:
        for w in r.warnings:
            wc["".join("#" if ch.isdigit() else ch for ch in w)] += 1
    print(
        f"\n[{name}] rows_total={parsed.rows_total} parsed={len(rows)} skipped={len(parsed.skipped)} "
        f"day+time={len(with_dt)} with_periods={len(with_p)} ({len(with_p) / max(len(with_dt), 1):.1%})"
    )
    print(f"[{name}] skip reasons: {Counter(s[1] for s in parsed.skipped).most_common()}")
    print(f"[{name}] top warnings:")
    for w, c in wc.most_common(12):
        print(f"   {c:4d}  {w}")
    return with_dt, with_p


@pytest.mark.parametrize(
    "fixture_name,expected_rows",
    [("parsed_guz_list", 1037), ("parsed_bahar_list", 1529)],
)
def test_parse_counts_and_period_coverage(request, fixture_name, expected_rows):
    parsed = request.getfixturevalue(fixture_name)
    assert abs(parsed.rows_total - expected_rows) <= expected_rows * 0.01
    with_dt, with_p = _summary(parsed, fixture_name)
    assert len(with_dt) > 0.7 * parsed.rows_total
    assert len(with_p) >= 0.99 * len(with_dt)
    # skipped rows are only those without a course code
    assert all(s[1] == "no course code" for s in parsed.skipped)
    assert len(parsed.skipped) < 0.01 * parsed.rows_total


def test_first_bahar_row_parsed_exactly(parsed_bahar_list):
    r = parsed_bahar_list.rows[0]
    assert r.course_code == "MAT112" and r.course_name == "Kalkülüs II"
    assert r.faculty == "MDBF" and r.program == "Bilgisayar Mühendisliği (İngilizce)"
    assert r.class_years == [1] and r.semester == 2 and r.label == "1"
    assert (r.t, r.u, r.l, r.credits, r.ects) == (3, 2, 0, 4.0, 6.0)
    assert r.enrolment == 180
    assert r.day.days == [4]
    assert (r.periods.start_period, r.periods.end_period) == (7, 9)
    assert r.definitive.room_codes == ["A204"]
    assert r.instructors == ["Dr.Öğr.Üyesi Elçim Elgün Kırımlı"]


def test_guz_rows_quirks(parsed_guz_list):
    by_code = {}
    for r in parsed_guz_list.rows:
        by_code.setdefault(r.course_code, []).append(r)
    psi = by_code["PSI155"][0]
    assert psi.day.days == [1] and (psi.periods.start_period, psi.periods.end_period) == (4, 6)
    assert psi.weeks.weeks == list(range(1, 15)) and psi.definitive.room_codes == ["A204"]
    ana = by_code["ANA111"][0]
    assert ana.program == "PTL - ENT - DYZ" and ana.enrolment == 111
    assert ana.definitive.room_codes == ["C201"]
    # a row whose definitive room is an alternate pair
    alts = [r for r in parsed_guz_list.rows if r.definitive.raw == "A 107/ B 207"]
    assert alts and alts[0].definitive.room_codes == ["A107", "B207"]


def test_modes_and_needs_room_distribution(parsed_bahar_list):
    modes = Counter(r.mode.mode for r in parsed_bahar_list.rows)
    assert modes["F2F"] > 900 and modes["ONLINE"] > 150
    needs = sum(1 for r in parsed_bahar_list.rows if r.needs_room)
    assert 900 < needs < 1400  # 480 rows are explicit no-room (online/hospital/lab)
    multi = [r for r in parsed_bahar_list.rows if len(r.definitive.room_codes) >= 4]
    assert multi, "large cohorts split across adjacent rooms must be parsed"


async def test_import_bahar_into_db_is_idempotent(session, parsed_bahar_list):
    rep1 = await import_planning_list(session, BAHAR_LIST, "2026-BAHAR")
    assert rep1.rows_total == parsed_bahar_list.rows_total
    assert rep1.rows_imported == len(parsed_bahar_list.rows)
    assert rep1.created["meeting_requests"] == rep1.rows_imported
    assert rep1.created["sections"] > 900
    assert rep1.created["courses"] > 900 and rep1.created["programs"] > 80
    assert rep1.created["instructors"] > 400
    assert rep1.created["rooms"] >= 58
    assert rep1.extra["period_coverage"] >= 0.99
    n_sec = (await session.execute(select(func.count(Section.id)))).scalar_one()
    n_mr = (await session.execute(select(func.count(MeetingRequest.id)))).scalar_one()

    rep2 = await import_planning_list(session, BAHAR_LIST, "2026-BAHAR")
    assert rep2.created["meeting_requests"] == 0 and rep2.created["sections"] == 0
    assert rep2.updated["meeting_requests"] == rep1.rows_imported
    assert (await session.execute(select(func.count(Section.id)))).scalar_one() == n_sec
    assert (await session.execute(select(func.count(MeetingRequest.id)))).scalar_one() == n_mr
    assert rep2.updated.get("meeting_requests_archived", 0) == 0

    # locked rows carry definitive rooms; MAT 112 §1 -> A 204
    mat = (await session.execute(select(Course).where(Course.code == "MAT112"))).scalar_one()
    sec = (await session.execute(select(Section).where(Section.course_id == mat.id))).scalars().first()
    mr = (await session.execute(select(MeetingRequest).where(MeetingRequest.section_id == sec.id))).scalars().first()
    assert mr.status == "LOCKED" and mr.day == 4 and (mr.start_period, mr.end_period) == (7, 9)
    assert len(mr.definitive_room_ids) == 1
    prog = (
        (await session.execute(select(Program).where(Program.canonical_name.like("%bilgisayar müh%"))))
        .scalars()
        .first()
    )
    assert prog is not None and prog.faculty_id is not None
    d = rep1.to_dict()
    assert d["rows_total"] == rep1.rows_total and "warning_summary" in d


async def test_import_guz_then_bahar_share_catalog(session):
    rep_g = await import_planning_list(session, GUZ_LIST, "2026-GUZ")
    rep_b = await import_planning_list(session, BAHAR_LIST, "2026-BAHAR")
    assert rep_g.rows_imported > 1000 and rep_b.rows_imported > 1480
    # shared courses are not duplicated
    codes = (await session.execute(select(Course.code))).scalars().all()
    assert len(codes) == len(set(codes))
    assert rep_b.created["rooms"] < rep_g.created["rooms"]
