"""Board-only data checks of the data-issues report (planner comparison §7.3 / §7.5, item 4)."""

from __future__ import annotations

from typing import Any

from app.models import Assignment, Room, ScheduleRun, Term
from app.services.data_issues import board_checks, build_data_issues
from sqlalchemy import select

from tests.conftest import BAHAR_LIST, GUZ_GRID, GUZ_LIST
from tests.test_importer_followups import subset


async def _run(session: Any, term_code: str, weeks: list[int] | None, kind: str = "COURSE") -> ScheduleRun:
    term = (await session.execute(select(Term).where(Term.code == term_code))).scalar_one()
    run = ScheduleRun(
        term_id=term.id,
        kind=kind,
        horizon="WEEK" if weeks else "TERM",
        horizon_params={"weeks": weeks} if weeks else {},
        params={},
        status="FEASIBLE",
    )
    session.add(run)
    await session.flush()
    return run


async def test_guz_board_checks_on_the_real_workbooks(session) -> None:
    from app.importers.planning_list import import_planning_list
    from app.importers.weekly_grid import import_weekly_grid

    await import_weekly_grid(session, GUZ_GRID, "2026-GUZ", year=2026)
    await import_planning_list(session, GUZ_LIST, "2026-GUZ")
    out = await board_checks(session, await _run(session, "2026-GUZ", [2]))
    # ADB 501 (Monday evening, A 102) is on the board, not in the list
    adb = next(it for it in out["board_unknown_code"] if "ADB 501" in it["message"])
    assert "A102" in adb["message"] and "'28-02 Ekim 2. hafta'!C15" in adb["params"]["cells"]
    assert "planlama listesinde yok" in adb["message_tr"]
    # one item per class, not per period row
    assert sum("ADB 501" in it["message"] for it in out["board_unknown_code"]) == 1
    # ENG 105 §1 (row 281, 50 students) alone in B 201 (30 seats) on Tuesday 09:20-10:50
    eng = next(it for it in out["board_capacity"] if "ENG 105" in it["message"])
    assert eng["params"]["seats"] == 30 and eng["params"]["size"] == 50
    assert eng["classes"][0]["source_row"] == 281 and eng["classes"][0]["board_rooms"] == "B201"
    # FZT 149 is listed, but not on Thursday 15:10-16:40
    assert any("FZT 149" in it["message"] for it in out["board_time_not_in_list"])
    assert out["board_missing_week"] == []
    # week 3 has no sheet: one item, with the board's coverage
    out3 = await board_checks(session, await _run(session, "2026-GUZ", [3]))
    assert [it["params"]["weeks"] for it in out3["board_missing_week"]] == [[3]]
    assert "covers only 2 week(s)" in out3["board_missing_week"][0]["message"]
    assert out3["board_unknown_code"] == [] and out3["board_capacity"] == []


async def _bahar_rows(session: Any, tmp_path: Any, rows: list[int], term: str) -> dict[str, int]:
    from app.importers.planning_list import import_planning_list

    await import_planning_list(session, subset(BAHAR_LIST, rows, tmp_path / "rows.xlsx"), term)
    return {r.code: r.id for r in (await session.execute(select(Room))).scalars()}


async def _board(session: Any, term: str, cells: list[dict[str, Any]]) -> None:
    t = (await session.execute(select(Term).where(Term.code == term))).scalar_one()
    board = ScheduleRun(
        term_id=t.id, kind="COURSE", horizon="TERM", status="FEASIBLE", params={"source": "GRID_IMPORT"}
    )
    session.add(board)
    await session.flush()
    for i, c in enumerate(cells):
        session.add(
            Assignment(
                run_id=board.id, week=3, weeks=[3], origin="IMPORT", source_key=f"GRID:{term}:b.xlsx:3:{c['cell']}:{i}",
                **{k: v for k, v in c.items() if k != "cell"},
            )
        )  # fmt: skip
    await session.flush()


async def test_instructor_clash_caused_by_board_times(session, tmp_path) -> None:
    """Bahar rows 1179 (ENG 106 §2, Tuesday 08:30-10:00) and 1214 (EHM 402 §1, Tuesday 10:10-12:30), both
    Elvira Vakhitova: the list times do not overlap, the board week 3 has ENG 106 in A 305 at 09:20-10:50 and
    EHM 402 in A 307 at 10:10-12:30."""
    rooms = await _bahar_rows(session, tmp_path, [1179, 1214], "T-INS")
    for code in ("A305", "A307"):
        if code not in rooms:
            session.add(Room(code=code, display_name=code, capacity=64, is_bookable=True))
    await session.flush()
    rooms = {r.code: r.id for r in (await session.execute(select(Room))).scalars()}
    await _board(
        session,
        "T-INS",
        [
            dict(day=2, start_period=2, end_period=3, room_ids=[rooms["A305"]], label="ENG 106", course_codes=["ENG106"], cell="AR5"),
            dict(day=2, start_period=3, end_period=5, room_ids=[rooms["A307"]], label="EHM 402", course_codes=["EHM402"], cell="AT4"),
        ],
    )  # fmt: skip
    out = await board_checks(session, await _run(session, "T-INS", [3]))
    [item] = out["board_instructor_clash"]
    assert "Elvira Vakhitova" in item["message"] and "ENG 106 and EHM 402" in item["message"]
    assert "aynı anda" in item["message_tr"] and item["params"]["weeks"] == [3]
    assert {c["course_code"] for c in item["classes"]} == {"ENG 106", "EHM 402"}


async def test_two_classes_in_one_board_cell(session, tmp_path) -> None:
    """Bahar rows 722 (NRS 442) and 683 (NRS 448): different instructors, one board cell (W24, B 202,
    Monday 09:20-12:30)."""
    rooms = await _bahar_rows(session, tmp_path, [722, 683], "T-CELL")
    if "B202" not in rooms:
        session.add(Room(code="B202", display_name="B 202", capacity=64, is_bookable=True))
        await session.flush()
        rooms = {r.code: r.id for r in (await session.execute(select(Room))).scalars()}
    await _board(
        session,
        "T-CELL",
        [dict(day=1, start_period=2, end_period=5, room_ids=[rooms["B202"]], label="NRS 442 / NRS 448", course_codes=["NRS442", "NRS448"], cell="W24")],
    )  # fmt: skip
    run = await _run(session, "T-CELL", [3])
    out = await board_checks(session, run)
    [item] = out["board_two_classes"]
    assert "NRS 442 / NRS 448" in item["message"] and "bir hücrede iki ders" in item["message_tr"]
    assert {c["course_code"] for c in item["classes"]} == {"NRS 442", "NRS 448"}
    # the report carries the group with its TR / EN title
    rep = await build_data_issues(session, run)
    group = next(g for g in rep["groups"] if g["code"] == "board_two_classes")
    assert group["count"] == 1 and group["title"]["tr"] == "Panoda bir hücrede iki ders"
