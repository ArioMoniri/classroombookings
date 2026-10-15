"""Product-owner decision 2026-10-15, period snapping: an off-grid time of the planning or exam list (10:20 when
the periods start at 10:10) snaps to the period(s) the class covers for at least half of their length. Every
snapped row is listed in the data-issues report (row, original time, snapped periods) for the planner to check.

Real rows (probe of the three lists: Bahar 158 off-grid rows, 72 of them change; Güz 54 / 15; Final 658 / 320):

* Bahar 208 BME 562 11:30-14:00 -> P5-P7 (P4 11:00-11:40 is covered 10 of 40 min; P7 13:30-14:10 30 of 40)
* Bahar 145 BCT 216 09:20-12:50 -> P2-P5 (P6 12:40-13:20 covered 10 min)
* Bahar 132 SYB 256 09:00-17:00 -> P2-P10 (P1 08:30-09:10 and P11 16:50-17:30 covered 10 min each)
* Final 10 BES 368 14:00-16:00 -> P8-P9; Final 11 ACY 148 16:00-17:00 -> P10
"""

from __future__ import annotations

from datetime import time

import pytest
from app.importers import normalize as n
from sqlalchemy import select

from tests.conftest import BAHAR_LIST, EXAM_LIST
from tests.test_importer_followups import subset


@pytest.mark.parametrize(
    "start,end,periods,snapped",
    [
        ((10, 20), (11, 40), (3, 4), True),  # the decision's example: 10:20 covers 30 of P3's 40 minutes
        ((10, 35), (11, 40), (4, 4), True),  # 15 of 40 minutes of P3: not half
        ((10, 30), (11, 40), (3, 4), True),  # exactly half counts
        ((10, 10), (11, 40), (3, 4), False),  # on the grid
        ((13, 30), (16, 0), (7, 9), False),  # ends at the next period's start (15:50 / 16:00): on the grid
        ((17, 30), (18, 0), (12, 12), False),  # P12 is 30 minutes
        ((17, 40), (18, 0), (12, 12), True),  # 20 of P12's 30 minutes
        ((10, 45), (11, 5), (3, 3), True),  # no period reaches half: the one it covers most (tie: the first)
    ],
)
def test_half_period_rule(start, end, periods, snapped) -> None:
    r = n.snap_to_periods(time(*start), time(*end))
    assert (r.start_period, r.end_period) == periods
    assert r.snapped is snapped
    assert bool([w for w in r.warnings if "snapped" in w]) is snapped


def test_real_planning_rows(parsed_bahar_list) -> None:
    rows = {r.row: r for r in parsed_bahar_list.rows}
    expect = {208: (5, 7), 145: (2, 5), 132: (2, 10)}
    for row, periods in expect.items():
        p = rows[row].periods
        assert (p.start_period, p.end_period) == periods, (row, p)
        assert p.snapped and any("at least half" in w for w in p.warnings)


def test_real_exam_rows(parsed_exam_list) -> None:
    rows = {r.row: r for r in parsed_exam_list.rows}
    assert (rows[10].periods.start_period, rows[10].periods.end_period) == (8, 9)
    assert (rows[11].periods.start_period, rows[11].periods.end_period) == (10, 10)


async def test_snapped_rows_are_listed_in_the_data_issues(session, tmp_path) -> None:
    from app.importers.planning_list import import_planning_list
    from app.models import ScheduleRun, Term
    from app.services.data_issues import time_snaps

    path = subset(BAHAR_LIST, [208, 145], tmp_path / "snap.xlsx")
    await import_planning_list(session, path, "T-SNAP")
    term = (await session.execute(select(Term).where(Term.code == "T-SNAP"))).scalar_one()
    run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="WEEK", status="FEASIBLE", params={}, stats={})
    session.add(run)
    await session.commit()
    items = (await time_snaps(session, run))["time_snapped"]
    got = {it["classes"][0]["course_code"]: it["params"] for it in items}
    assert set(got) == {"BME 562", "BCT 216"}, items
    bme = got["BME 562"]
    assert bme["row"] == 3 and bme["original"] == "11:30-14:00"  # the subset keeps sheet order: 145 -> 2, 208 -> 3
    assert bme["periods"] == [5, 7] and bme["snapped"] == "11:50-14:10"
    assert any("11:30-14:00" in it["message_tr"] and "11:50-14:10" in it["message_tr"] for it in items)


async def test_snapped_exam_rows_are_listed(session, tmp_path) -> None:
    from app.importers.exam_list import import_exam_list
    from app.models import ScheduleRun, Term
    from app.services.data_issues import time_snaps

    path = subset(EXAM_LIST, [10], tmp_path / "snap_exam.xlsx")
    await import_exam_list(session, path, "T-SNAPX")
    term = (await session.execute(select(Term).where(Term.code == "T-SNAPX"))).scalar_one()
    run = ScheduleRun(term_id=term.id, kind="EXAM", horizon="TERM", status="FEASIBLE", params={}, stats={})
    session.add(run)
    await session.commit()
    items = (await time_snaps(session, run))["time_snapped"]
    assert [(it["params"]["row"], it["params"]["original"], it["params"]["periods"]) for it in items] == [
        (2, "14:00-16:00", [8, 9])  # Final row 10 is row 2 of the subset
    ]


def test_bes640_and_bes560_no_longer_share_p15(parsed_bahar_list) -> None:
    """ROADMAP: "ends 10 min into a period still claim it" - Bahar rows 435 (BES 640 17:30-19:50, C 501) and 436
    (BES 560 20:00-21:30, C 501) both claimed P15 (19:40-20:20) and were a locked overlap."""
    rows = {r.row: r for r in parsed_bahar_list.rows}
    a, b = rows[435].periods, rows[436].periods
    assert (a.start_period, a.end_period) == (12, 14) and (b.start_period, b.end_period) == (15, 16)
