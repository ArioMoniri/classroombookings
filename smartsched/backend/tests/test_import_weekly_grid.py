"""Weekly grid importer on the Bahar (19 sheets), Güz (2 sheets) and Final (3 sheets) fixtures."""

from __future__ import annotations

from collections import Counter
from datetime import date

from app.importers.weekly_grid import import_weekly_grid, sheet_kind, week_start_from_name
from app.models import Assignment, Block, Room, Week
from sqlalchemy import func, select

from tests.conftest import BAHAR_GRID, BAHAR_LIST, FINAL_GRID, GUZ_GRID


def test_sheet_kind_and_week_start():
    assert sheet_kind("Final 1 - 7 Haziran") == "EXAM"
    assert sheet_kind("BÜT 22 - 24 Haziran") == "MAKEUP"
    assert sheet_kind("Yaz Dönemi") == "SUMMER"
    assert sheet_kind("9 - 15 Mart") == "LECTURE"
    assert week_start_from_name("2  - 8 Şubat Bahar Dönem Açılış", 2026) == date(2026, 2, 2)
    assert week_start_from_name("23 Şubat - 1 Mart", 2026) == date(2026, 2, 23)
    assert week_start_from_name("30 mart - 05 Nisan", 2026) == date(2026, 3, 30)
    assert week_start_from_name("28-02 Ekim 2. hafta", 2026) == date(2026, 9, 28)
    assert week_start_from_name("21-27 Eylül Dönem Başlangıç", 2026) == date(2026, 9, 21)
    assert week_start_from_name("Yaz Dönemi", 2026) is None


def test_bahar_grid_structure(parsed_bahar_grid):
    g = parsed_bahar_grid
    assert len(g.sheets) == 19
    assert len(g.rooms) >= 58
    for s in g.sheets:
        assert len(s.days) == 7, s.name
        assert [d.day for d in s.days] == [1, 2, 3, 4, 5, 6, 7]
        assert s.header_rows[:2] == [2, 22]
    wk6 = g.sheets[5]
    assert wk6.name == "9 - 15 Mart" and wk6.kind == "LECTURE" and wk6.start_date == date(2026, 3, 9)
    hits = [e for e in wk6.entries if e.room_code == "A204" and e.day == 1 and e.start_period == 2]
    assert hits and hits[0].cell.codes == ["HEM242"] and hits[0].end_period == 4
    # the term workbook's Final sheets reuse the lecture headers (exam seating lives in the Final workbook)
    fin = g.sheets[16]
    assert fin.kind == "EXAM" and fin.rooms["A204"].capacity == 156 and fin.days[0].date == date(2026, 6, 1)
    assert g.sheets[0].rooms["A204"].capacity == 156 and "TIP" in g.sheets[0].rooms["A201"].tags
    assert g.sheets[0].rooms["B207"].tags == ["PC"]
    kinds = Counter(e.cell.kind for e in g.entries)
    assert kinds["COURSE"] > 5000 and kinds["BLOCK"] > 500
    print(f"\n[bahar grid] entries={len(g.entries)} {dict(kinds)} rooms={len(g.rooms)} warnings={len(g.warnings)}")
    for w in g.warnings[:8]:
        print("   ", w)


def test_bahar_grid_combined_codes_comments_and_fills(parsed_bahar_grid):
    g = parsed_bahar_grid
    combined = [e for e in g.entries if len(e.cell.codes) >= 2]
    assert combined, "combined lectures like `HEM 334 / NRS 304` must split"
    assert any("/" in e.cell.raw or "\n" in e.cell.raw for e in combined)
    noted = [e for e in g.entries if e.note]
    assert noted, "cell comments must be attached as notes"
    assert not any(n.startswith("Fatih Demir") for n in (e.note for e in noted))
    tagged = Counter(e.tag for e in g.entries if e.tag)
    assert tagged, "fill colours must be recorded as tags"
    multi = [e for e in g.entries if e.end_period > e.start_period]
    assert len(multi) > 500, "vertically merged cells expand into multi-period occupancy"
    labels = Counter(e.cell.label for e in g.entries if e.cell.kind == "BLOCK")
    assert labels["HAZIRLIK"] > 50


def test_guz_grid_prep_school_blocks(parsed_guz_grid):
    g = parsed_guz_grid
    assert len(g.sheets) == 2 and len(g.sheets[0].days) == 7
    wk1 = g.sheets[0]
    hz = [e for e in wk1.entries if e.cell.label == "HAZIRLIK"]
    assert len(hz) >= 600
    assert all(e.tag == "YELLOW" for e in hz[:50])
    assert wk1.start_date == date(2026, 9, 21)
    assert "NAFİYE HOCA" in {e.cell.label for e in wk1.entries}
    assert g.sheets[1].start_date == date(2026, 9, 28)


def test_final_grid(parsed_final_grid):
    g = parsed_final_grid
    assert len(g.sheets) == 3
    s1 = g.sheets[0]
    assert s1.days[0].date == date(2026, 6, 1) and s1.days[6].date == date(2026, 6, 7)
    assert s1.rooms["A101"].capacity == 30 and s1.rooms["D107"].capacity == 10
    uzem = [e for e in s1.entries if e.cell.label == "UZEM"]
    assert len(uzem) > 50
    assert any("Hemşirelik Bitirme Sınavı" == e.cell.label for e in s1.entries)
    assert any(e.cell.codes == ["MAT102", "MAT112"] for e in s1.entries)


async def test_import_guz_grid_into_db_idempotent(session):
    rep1 = await import_weekly_grid(session, GUZ_GRID, "2026-GUZ", year=2026)
    assert rep1.created["rooms"] >= 56 and rep1.created["weeks"] == 2  # Güz board lists 29 + 27 rooms
    assert rep1.created["blocks"] >= 600 and rep1.created["assignments"] > 500
    assert rep1.extra["sheets"] == 2
    a204 = (await session.execute(select(Room).where(Room.code == "A204"))).scalar_one()
    assert a204.capacity == 156 and a204.building_id is not None
    n_a = (await session.execute(select(func.count(Assignment.id)))).scalar_one()
    n_b = (await session.execute(select(func.count(Block.id)))).scalar_one()
    rep2 = await import_weekly_grid(session, GUZ_GRID, "2026-GUZ", year=2026)
    assert rep2.created["assignments"] == 0 and rep2.created["blocks"] == 0
    assert rep2.updated["assignments"] == rep1.created["assignments"]
    assert (await session.execute(select(func.count(Assignment.id)))).scalar_one() == n_a
    assert (await session.execute(select(func.count(Block.id)))).scalar_one() == n_b
    weeks = (await session.execute(select(Week).order_by(Week.index))).scalars().all()
    assert [w.index for w in weeks] == [1, 2] and weeks[0].start_date == date(2026, 9, 21)


async def test_import_bahar_grid_links_requests(session):
    from app.importers.planning_list import import_planning_list

    await import_planning_list(session, BAHAR_LIST, "2026-BAHAR")
    rep = await import_weekly_grid(session, BAHAR_GRID, "2026-BAHAR", year=2026)
    assert rep.extra["linked_assignments"] > 1000
    assert rep.created["weeks"] == 19 and rep.extra["capacity_kind"] == "lecture"
    rep_f = await import_weekly_grid(session, FINAL_GRID, "2026-FINAL", year=2026)
    assert rep_f.extra["capacity_kind"] == "exam" and rep_f.created["rooms"] == 0
    a204 = (await session.execute(select(Room).where(Room.code == "A204"))).scalar_one()
    assert a204.capacity == 156 and a204.exam_capacity == 74
    linked = (
        await session.execute(select(func.count(Assignment.id)).where(Assignment.meeting_request_id.is_not(None)))
    ).scalar_one()
    assert linked > 1000
