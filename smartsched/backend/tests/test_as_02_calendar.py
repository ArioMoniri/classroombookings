"""AS-02: holiday- and week-kind-aware planning and analytics, on the Bahar 2026 weekly grid (19 sheets: lecture
weeks 1-15, "Yaz Dönemi", "Final 1 - 7 Haziran", "Final 8 - 14 Haziran", "BÜT 22 - 24 Haziran").

* a TERM COURSE run plans no class in weeks 16-19 (SUMMER / EXAM / EXAM / MAKEUP);
* a holiday on Thursday 23 Nisan 2026 (week 12) leaves that date's room-periods out of the heatmap's numerator and
  denominator, and so does a HOLIDAY week;
* ``seasons.periods`` returns the dated segments; ``learning.season_of`` is ``seasons.season_of``.

Real row: Bahar planning list row 296, NUT 254 (60 students, Thursday P9-P10, every week)."""

from __future__ import annotations

from datetime import date

from app.core.db import get_session_factory
from app.models import Assignment, Holiday, ScheduleRun, Week
from app.services import learning, seasons
from app.services.solver_bridge import build_solver_input, horizon_weeks, run_schedule
from app.services.utilisation import build_scope, room_heatmap
from sqlalchemy import select

from tests.as_support import add_grid_term, add_meeting, add_rooms, row_of

THURSDAY_23_NISAN = date(2026, 4, 23)


async def _bahar(parsed_bahar_grid, parsed_bahar_list) -> tuple[int, int, dict[str, int]]:
    row = row_of(parsed_bahar_list, 296)
    assert row.course_code == "NUT254" and row.day.days == [4] and row.weeks.all_weeks
    async with get_session_factory()() as s:
        term = await add_grid_term(s, "2026-BAHAR", parsed_bahar_grid)
        rooms = await add_rooms(s, "A101", "A204")
        mr = await add_meeting(s, term, row, rooms)
        await s.commit()
        return term.id, mr, rooms


async def _run(term_id: int) -> ScheduleRun:
    factory = get_session_factory()
    async with factory() as s:
        run = ScheduleRun(term_id=term_id, kind="COURSE", horizon="TERM", params={"time_limit_s": 5, "workers": 1})
        s.add(run)
        await s.commit()
        rid = run.id
    await run_schedule(factory, rid)
    async with factory() as s:
        out = await s.get(ScheduleRun, rid)
        assert out is not None
        return out


async def test_as_02_term_course_run_plans_no_class_in_weeks_16_to_19(
    engine, stub_solver, parsed_bahar_grid, parsed_bahar_list
):
    tid, mr, _rooms = await _bahar(parsed_bahar_grid, parsed_bahar_list)
    async with get_session_factory()() as s:
        probe = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={})
        s.add(probe)
        await s.flush()
        inp, _m = await build_solver_input(s, probe)
        assert list(inp.weeks) == list(range(1, 16))
        ev = next(e for e in inp.events if e.id == mr)
        assert ev.weeks == frozenset(range(1, 16))
        assert probe.stats["horizon_skipped_weeks"] == [16, 17, 18, 19]
    run = await _run(tid)
    async with get_session_factory()() as s:
        rows = list((await s.execute(select(Assignment).where(Assignment.run_id == run.id))).scalars())
    assert rows, run.diagnosis
    weeks = {int(w) for a in rows for w in (a.weeks or [])}
    assert weeks and max(weeks) <= 15 and not weeks & {16, 17, 18, 19}
    # every consumer without the week kinds sees the planned horizon (planner check, heatmap, fix button)
    from app.models import Term

    async with get_session_factory()() as s:
        t = await s.get(Term, tid)
        r = await s.get(ScheduleRun, run.id)
        assert t is not None and r is not None
        assert horizon_weeks(r, t) == list(range(1, 16))


async def test_as_02_exam_and_week_runs_keep_their_weeks(engine, parsed_bahar_grid, parsed_bahar_list):
    tid, _mr, _rooms = await _bahar(parsed_bahar_grid, parsed_bahar_list)
    from app.models import Term

    async with get_session_factory()() as s:
        t = await s.get(Term, tid)
        assert t is not None
        kinds = seasons.week_kinds((await s.execute(select(Week).where(Week.term_id == tid))).scalars())
        exam = ScheduleRun(term_id=tid, kind="EXAM", horizon="TERM")
        assert horizon_weeks(exam, t, kinds=kinds) == list(range(1, 20))
        one = ScheduleRun(term_id=tid, kind="COURSE", horizon="WEEK", horizon_params={"week": 17})
        assert horizon_weeks(one, t, kinds=kinds) == [17]
        month = ScheduleRun(term_id=tid, kind="COURSE", horizon="MONTH", horizon_params={"start_week": 14})
        assert horizon_weeks(month, t, kinds=kinds) == [14, 15]


async def test_as_02_holiday_thursday_leaves_numerator_and_denominator(
    engine, stub_solver, parsed_bahar_grid, parsed_bahar_list
):
    tid, _mr, rooms = await _bahar(parsed_bahar_grid, parsed_bahar_list)
    run = await _run(tid)
    async with get_session_factory()() as s:
        before = await room_heatmap(s, run_id=run.id, group_by="building", week=12)
    col_before = _col(before, "d4")
    assert col_before["occupied"] > 0 and col_before["capacity"] == len(rooms) * 18
    async with get_session_factory()() as s:
        s.add(
            Holiday(
                term_id=tid,
                name="Ulusal Egemenlik ve Çocuk Bayramı",
                date_start=THURSDAY_23_NISAN,
                date_end=THURSDAY_23_NISAN,
            )
        )
        await s.commit()
    async with get_session_factory()() as s:
        after = await room_heatmap(s, run_id=run.id, group_by="building", week=12)
        sc = await build_scope(s, run_id=run.id, week=12)
    col_after = _col(after, "d4")
    assert col_after["occupied"] == 0 and col_after["capacity"] == 0
    assert after["overall"]["total"]["capacity"] == before["overall"]["total"]["capacity"] - len(rooms) * 18
    assert after["overall"]["total"]["occupied"] == before["overall"]["total"]["occupied"] - col_before["occupied"]
    assert (12, 4) in sc.occ.closed
    assert "holidays" in after["definitions"]
    # another Thursday (week 11) is untouched
    async with get_session_factory()() as s:
        wk11 = await room_heatmap(s, run_id=run.id, group_by="building", week=11)
    assert _col(wk11, "d4")["occupied"] == col_before["occupied"]


async def test_as_02_holiday_week_is_closed_in_the_heatmap(engine, stub_solver, parsed_bahar_grid, parsed_bahar_list):
    tid, _mr, rooms = await _bahar(parsed_bahar_grid, parsed_bahar_list)
    async with get_session_factory()() as s:
        wk = (await s.execute(select(Week).where(Week.term_id == tid, Week.index == 10))).scalar_one()
        wk.kind = "HOLIDAY"
        await s.commit()
    run = await _run(tid)
    async with get_session_factory()() as s:
        hm = await room_heatmap(s, run_id=run.id, group_by="building", scope="term")
    days = len({c["day"] for c in hm["columns"]})
    # the course run skips the HOLIDAY week, and the heatmap's term scope follows the planned horizon
    assert hm["weeks"] == [w for w in range(1, 16) if w != 10]
    assert hm["overall"]["total"]["capacity"] == len(rooms) * 18 * days * 14
    async with get_session_factory()() as s:
        wk10 = await room_heatmap(s, run_id=run.id, group_by="building", week=10)
    assert wk10["overall"]["total"]["capacity"] == 0 and wk10["overall"]["total"]["occupied"] == 0


def _col(hm, key):
    totals = {}
    for row in hm["rows"]:
        for c in row["by_col"]:
            if c["col"] == key:
                for k in ("occupied", "capacity", "blocked"):
                    totals[k] = totals.get(k, 0) + c[k]
    return totals


async def test_as_02_periods_are_dated_segments(engine, parsed_bahar_grid, parsed_bahar_list):
    tid, _mr, _rooms = await _bahar(parsed_bahar_grid, parsed_bahar_list)
    from app.models import Term

    async with get_session_factory()() as s:
        s.add(Holiday(term_id=tid, name="23 Nisan", date_start=THURSDAY_23_NISAN, date_end=THURSDAY_23_NISAN))
        await s.commit()
        t = await s.get(Term, tid)
        assert t is not None
        segs = await seasons.load_periods(s, t)
    kinds = [(x.kind, x.week_from, x.week_to, x.source) for x in segs]
    assert ("LECTURE", 1, 15, "week") in kinds
    assert ("SUMMER", 16, 16, "week") in kinds
    assert ("EXAM", 17, 18, "week") in kinds
    assert ("MAKEUP", 19, 19, "week") in kinds
    hol = next(x for x in segs if x.source == "holiday")
    assert (hol.kind, hol.week_from, hol.date_from) == ("HOLIDAY", 12, THURSDAY_23_NISAN)
    lecture = next(x for x in segs if x.kind == "LECTURE")
    assert lecture.date_from == date(2026, 2, 2) and lecture.date_to == date(2026, 5, 17)
    exam = next(x for x in segs if x.kind == "EXAM")
    assert exam.date_from == date(2026, 6, 1) and exam.label["tr"] == "Sınav dönemi (17–18. haftalar)"
    assert exam.as_dict()["kind_label"] == {"tr": "Sınav dönemi", "en": "Exam period"}


def test_as_02_season_of_has_one_definition():
    from app.models import Term

    assert learning.season_of is seasons.season_of
    assert seasons.season_of(Term(code="2026-2027-GÜZ", kind="REGULAR")) == "GUZ"
    assert seasons.season_of(Term(code="2026-BAHAR", kind="REGULAR")) == "BAHAR"
    assert seasons.season_of(Term(code="2026 Bütünleme", kind="BUT")) == "BUT"
    assert seasons.season_of(Term(code="2026-YAZ", kind="SUMMER")) == "YAZ"
    assert seasons.season_of(Term(code="X", kind="regular")) == "REGULAR"
