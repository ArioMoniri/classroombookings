"""FIX-A F-ASB-1 (e2e results 2026-10-18): a TERM COURSE run of the Bahar 2026 term imported from the real weekly grid
(``bahar_derslikler_takvimi_2026.xlsx``) records ``stats.horizon_skipped_weeks``.

The importer sets ``week_count`` 15 (the lecture weeks) but writes 19 week rows: 16 "Yaz Dönemi" (stored as LECTURE,
no date), 17-18 "Final" (EXAM), 19 "BÜT" (MAKEUP). The horizon of a TERM run is the term's real calendar (its week
rows), not ``week_count``; exam / make-up / holiday weeks and the weeks past the teaching length are skipped and
listed, so the run header can say which weeks were left out. Week 16 is not planned.

Real row: Bahar planning list row 296, NUT 254 (60 students, Thursday P9-P10, every week)."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.importers.weekly_grid import import_weekly_grid
from app.models import Room, ScheduleRun, Term, Week
from app.services.solver_bridge import build_solver_input, horizon_weeks
from sqlalchemy import select

from tests.as_support import add_meeting, row_of
from tests.conftest import BAHAR_GRID


async def _imported_bahar(parsed_bahar_list) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    row = row_of(parsed_bahar_list, 296)
    assert row.course_code == "NUT254"
    async with get_session_factory()() as s:
        await import_weekly_grid(s, BAHAR_GRID, "2026-BAHAR", year=2026)
        term = (await s.execute(select(Term).where(Term.code == "2026-BAHAR"))).scalar_one()
        rooms = {r.code: r.id for r in (await s.execute(select(Room))).scalars()}
        mr = await add_meeting(s, term, row, rooms)
        await s.commit()
        return term.id, mr


async def test_term_run_of_the_imported_bahar_lists_the_skipped_weeks(engine, parsed_bahar_list) -> None:  # type: ignore[no-untyped-def]
    tid, mr = await _imported_bahar(parsed_bahar_list)
    async with get_session_factory()() as s:
        term = await s.get(Term, tid)
        assert term is not None and term.week_count == 15  # the real import: lecture weeks only
        kinds = {w.index: w.kind for w in (await s.execute(select(Week).where(Week.term_id == tid))).scalars()}
        assert kinds[16] == "LECTURE" and kinds[17] == "EXAM" and kinds[19] == "MAKEUP"
        probe = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={})
        s.add(probe)
        await s.flush()
        inp, _m = await build_solver_input(s, probe)
        assert list(inp.weeks) == list(range(1, 16))
        ev = next(e for e in inp.events if e.id == mr)
        assert ev.weeks == frozenset(range(1, 16))
        assert probe.stats["horizon_skipped_weeks"] == [16, 17, 18, 19]
        assert probe.stats["horizon_weeks"] == list(range(1, 16))
        assert horizon_weeks(probe, term) == list(range(1, 16))  # the stored horizon


async def test_a_holiday_week_inside_the_term_is_skipped_and_listed(engine, parsed_bahar_list) -> None:  # type: ignore[no-untyped-def]
    tid, _mr = await _imported_bahar(parsed_bahar_list)
    async with get_session_factory()() as s:
        w12 = (await s.execute(select(Week).where(Week.term_id == tid, Week.index == 12))).scalar_one()
        w12.kind = "HOLIDAY"
        probe = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={})
        s.add(probe)
        await s.flush()
        inp, _m = await build_solver_input(s, probe)
        assert 12 not in inp.weeks and len(inp.weeks) == 14
        assert probe.stats["horizon_skipped_weeks"] == [12, 16, 17, 18, 19]


async def test_an_exam_run_keeps_its_horizon(engine, parsed_bahar_list) -> None:  # type: ignore[no-untyped-def]
    tid, _mr = await _imported_bahar(parsed_bahar_list)
    async with get_session_factory()() as s:
        term = await s.get(Term, tid)
        assert term is not None
        probe = ScheduleRun(term_id=tid, kind="EXAM", horizon="TERM", params={})
        kinds = {w.index: w.kind for w in (await s.execute(select(Week).where(Week.term_id == tid))).scalars()}
        assert horizon_weeks(probe, term, kinds=kinds) == list(range(1, 16))
