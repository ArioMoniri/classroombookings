"""Room master (F2): capacities and tags from the real workbooks, the room master CSV, unbookable rooms."""

from __future__ import annotations

from pathlib import Path

from app.importers import normalize as n
from app.importers.planning_list import parse_capacity_buckets
from app.importers.room_master import import_room_master, parse_room_master
from app.importers.weekly_grid import consolidate_rooms, import_weekly_grid
from app.models import Room
from sqlalchemy import select

from tests.conftest import BAHAR_GRID, BAHAR_LIST, FINAL_GRID, FIXTURES

ROOM_MASTER = FIXTURES / "room_master.csv"


def test_computer_lab_aliases_and_pc_inference():
    for text in ("B Blok Bilg. Lab.", "B BİLGİ LAB", "B Blok Bilgisayar lab.", "B 207 Bilg. Lab."):
        assert n.parse_room_codes(text) == ["B207"], text
    assert n.parse_definitive_rooms("B Blok Bilg. Lab.").status == "ROOMS"  # was NO_ROOM ("lab")
    assert n.pc_lab_rooms("C 202 BİLG. LAB. ZORUNLU PLANLANDI") == ["C202"]
    assert n.pc_lab_rooms("A 101 / A 106") == []  # not a lab phrase
    assert n.pc_lab_rooms("bilgisayar mühendisliği ile aynı derslik") == []
    h = n.parse_room_header("B Blok Bilgisayar lab.")
    assert h is not None and h.code == "B207" and h.tags == ["PC"] and h.capacity is None


def test_bahar_grid_consolidated_capacities(parsed_bahar_grid):
    """Lecture capacity = most frequent lecture-week header; exam-week headers never set it (the old importer
    let the last sheet win: A 103 = 33, A 104 = 28, A 307 = 28)."""
    facts, warnings = consolidate_rooms(parsed_bahar_grid, exam_workbook=False)
    assert (facts["A103"].capacity, facts["A104"].capacity, facts["A307"].capacity) == (47, 41, 70)
    assert facts["A204"].capacity == 156 and facts["A101"].capacity == 58
    # exam-week headers that differ (and are smaller) are exam seating
    assert facts["A103"].exam_capacity == 33 and facts["A307"].exam_capacity == 28
    assert facts["A101"].exam_capacity is None  # Final sheets just copy "(58)"
    assert facts["A306"].exam_capacity is None or facts["A306"].exam_capacity < 38
    assert facts["B207"].capacity is None and "PC" in facts["B207"].tags
    assert "TIP" in facts["A203"].tags
    assert any("A103" in w for w in warnings)


def test_final_grid_exam_capacities(parsed_final_grid):
    facts, _w = consolidate_rooms(parsed_final_grid, exam_workbook=True)
    assert all(f.capacity is None for f in facts.values())
    assert facts["A204"].exam_capacity == 74 and facts["A101"].exam_capacity == 30
    assert facts["B207"].exam_capacity == 60


def test_bahar_sayfa2_capacity_buckets():
    entries = parse_capacity_buckets(BAHAR_LIST)
    caps = {e.code: e.capacity for e in entries}
    assert caps["A204"] == 156 and caps["A307"] == 70 and caps["B406"] == 30 and caps["CZ01"] == 30
    assert {e.code for e in entries if e.pc_lab} == {"A103", "A104", "A105", "B207"}
    assert caps["B207"] is None  # "B BİLGİ LAB" has no number in Sayfa2


def test_parse_room_master_csv_rows_and_errors():
    text = (
        "# comment\ncode;capacity;exam_capacity;tags;building;floor;bookable\n"
        "A 101;58;30;;A;1;1\nB Blok Bilg. Lab.;60;;PC|LAB;B;2;evet\nX 1;;;;;;\nA 102;abc;;;;;\nC z01;;;-;;0;\n"
    )
    rows, errors = parse_room_master(text)
    assert [r["code"] for r in rows] == ["A101", "B207", "CZ01"]
    assert rows[1]["tags"] == ["PC", "LAB"] and rows[1]["bookable"] is True and rows[1]["exam_capacity"] is None
    assert rows[2]["tags"] == [] and rows[2]["floor"] == "0" and rows[2]["capacity"] is None
    assert any("line 4" in e for e in errors) and any("line 5" in e for e in errors)


def test_shipped_room_master_fixture_parses():
    rows, errors = parse_room_master(Path(ROOM_MASTER).read_text(encoding="utf-8"))
    assert errors == []
    by = {r["code"]: r for r in rows}
    assert by["B207"]["capacity"] == 60 and "PC" in by["B207"]["tags"]
    assert {c for c, r in by.items() if r["tags"] and "PC" in r["tags"]} >= {"A103", "A104", "A105", "B207"}
    assert by["A204"]["capacity"] == 156 and by["A204"]["exam_capacity"] == 74
    assert by["A701"]["bookable"] is False


async def test_real_bahar_import_room_master_end_to_end(session):
    """Bahar grid + list -> PC labs tagged, A 103 = 47, rooms without capacity reported and not bookable
    (not dropped); room master CSV fixes B 207; a later workbook import never overwrites master values."""
    from app.importers.planning_list import import_planning_list

    rep_g = await import_weekly_grid(session, BAHAR_GRID, "2026-BAHAR", year=2026)
    rep_l = await import_planning_list(session, BAHAR_LIST, "2026-BAHAR")
    rooms = {r.code: r for r in (await session.execute(select(Room))).scalars()}
    for code in ("A103", "A104", "A105", "B207"):
        assert "PC" in rooms[code].tags, code
    assert (rooms["A103"].capacity, rooms["A104"].capacity, rooms["A307"].capacity) == (47, 41, 70)
    assert rooms["B207"].capacity == 0 and rooms["B207"].is_bookable is False
    no_cap = rep_l.extra["rooms_without_capacity"]
    assert "B207" in no_cap and "A701" in no_cap and "A204" not in no_cap
    assert all(not rooms[c].is_bookable for c in no_cap)
    assert any("no capacity in any source" in w for w in rep_l.warnings)
    assert all(r.is_bookable for r in rooms.values() if r.capacity)
    assert rep_g.extra["capacity_kind"] == "lecture"

    rep_m = await import_room_master(session, ROOM_MASTER)
    assert rep_m.rows_imported == len(parse_room_master(ROOM_MASTER.read_text(encoding="utf-8"))[0])
    b207 = (await session.execute(select(Room).where(Room.code == "B207"))).scalar_one()
    assert (b207.capacity, b207.exam_capacity, b207.is_bookable) == (60, 60, True)
    assert set(b207.custom_fields["master"]) == {"capacity", "exam_capacity"}

    # a later Final workbook import: its headers are exam seating; the master keeps its numbers
    b207.exam_capacity = 61
    await session.commit()
    rep_f = await import_weekly_grid(session, FINAL_GRID, "2026-FINAL", year=2026)
    await session.refresh(b207)
    assert b207.exam_capacity == 61
    assert any("room master keeps" in w and "B207" in w for w in rep_f.warnings)
