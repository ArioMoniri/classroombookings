"""The council's general path, forced on the user's own files, gives the importers' results; and the same
real records in other shapes and languages give the same entities ("metamorphic" checks)."""

from __future__ import annotations

import csv
from collections import Counter

import pytest
from app.council import fastpath
from app.importers.exam_list import parse_exam_list
from app.importers.planning_list import parse_planning_list
from app.importers.room_master import parse_room_master
from app.importers.weekly_grid import parse_weekly_grid

from tests.council.conftest import (
    BAHAR_GRID,
    BAHAR_LIST,
    EN_CSV,
    EXAM_LIST,
    EXAM_PDF,
    FINAL_GRID,
    GUZ_GRID,
    GUZ_LIST,
    MEMO_DOCX,
    ROOM_MASTER,
    TRANSPOSED,
    gen,
)


@pytest.mark.parametrize("path", [BAHAR_LIST, GUZ_LIST])
def test_planning_lists_general_equals_fast(path):
    fast = parse_planning_list(path)
    _, _, recs = gen(path)
    meet = [r for r in recs if r["type"] == "meeting"]
    assert abs(len(meet) - len(fast.rows)) <= max(2, len(fast.rows) // 200)  # within 0.5 %
    fc, gc = Counter(r.course_code for r in fast.rows), Counter(r["course_code"] for r in meet)
    assert len(set(fc) & set(gc)) >= 0.99 * len(fc)
    by_row = {r["source"]["row"]: r for r in meet}
    same = [
        f
        for f in fast.rows
        if f.row in by_row
        and by_row[f.row]["days"] == f.day.days
        and by_row[f.row]["start"] == (f.start_time.strftime("%H:%M") if f.start_time else None)
        and by_row[f.row]["rooms"] == f.definitive.room_codes
    ]
    assert len(same) >= 0.97 * len(fast.rows), len(same)


def test_exam_list_general_equals_fast():
    fast = parse_exam_list(EXAM_LIST)
    _, _, recs = gen(EXAM_LIST)
    ex = {r["source"]["row"]: r for r in recs if r["type"] == "exam"}
    assert abs(len(ex) - len(fast.rows)) <= 2
    same = [
        f
        for f in fast.rows
        if f.row in ex
        and ex[f.row]["date"] == (f.date.isoformat() if f.date else None)
        and ex[f.row]["start"] == (f.start_time.strftime("%H:%M") if f.start_time else None)
        and ex[f.row]["course_code"] == f.course_code
    ]
    assert len(same) >= 0.95 * len(fast.rows), len(same)


def _cells_fast(sheet):
    return {(e.room_code, e.day, p) for e in sheet.entries for p in range(e.start_period, e.end_period + 1)}


def _cells_gen(recs, sheet_name):
    return {
        (b["room_code"], b["day"], p)
        for b in recs
        if b["type"] == "booking" and b["sheet"] == sheet_name
        for p in range(b["slot_start"], b["slot_end"] + 1)
    }


@pytest.mark.parametrize("path", [FINAL_GRID, GUZ_GRID, BAHAR_GRID])
def test_weekly_grids_general_occupancy_equals_fast(path):
    fast = parse_weekly_grid(path, year=2026)
    rendered, _, recs = gen(path)
    sheets = fast.sheets if path != BAHAR_GRID else fast.sheets[:4]
    for i, s in enumerate(sheets):
        assert _cells_gen(recs, rendered.grids[i].name) == _cells_fast(s), s.name


def test_transposed_board_gives_the_same_bookings():
    rendered, _, original = gen(BAHAR_GRID)
    _, _, transposed = gen(TRANSPOSED)

    def key(b):
        return (b["room_code"], b["day"], b["start"], b["end"], b["text"])

    week1 = [b for b in original if b["type"] == "booking" and b["sheet"] == rendered.grids[0].name]
    assert len(week1) > 600
    assert sorted(map(key, transposed)) == sorted(map(key, week1))
    # provenance points into the transposed sheet: row = original column
    first = next(b for b in transposed if b["text"] == week1[0]["text"])
    assert first["source"]["sheet"] == rendered.grids[0].name and "cell" in first["source"]


def test_english_csv_gives_the_bahar_meetings():
    fast = parse_planning_list(BAHAR_LIST)
    _, _, recs = gen(EN_CSV)
    meet = [r for r in recs if r["type"] == "meeting"]
    with EN_CSV.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(meet) >= 0.99 * len(rows)
    fast_keys = Counter(
        (r.course_code, tuple(r.day.days), r.start_time.strftime("%H:%M") if r.start_time else None) for r in fast.rows
    )
    gen_keys = Counter((r["course_code"], tuple(r["days"]), r["start"]) for r in meet)
    common = sum((fast_keys & gen_keys).values())
    assert common >= 0.97 * len(meet), common
    assert all(r["source"]["file"] == EN_CSV.name and r["source"]["row"] >= 2 for r in meet)


def test_pdf_gives_the_first_exam_rows():
    fast = parse_exam_list(EXAM_LIST)
    _, _, recs = gen(EXAM_PDF)
    exams = [r for r in recs if r["type"] == "exam"]
    assert len(exams) == 120
    same = sum(
        1
        for f, g in zip(fast.rows[:120], exams, strict=True)
        if f.course_code == g["course_code"]
        and (f.date.isoformat() if f.date else None) == g["date"]
        and (f.start_time.strftime("%H:%M") if f.start_time else None) == g["start"]
    )
    assert same >= 114, same  # >= 95 %
    assert exams[-1]["source"]["page"] == 3


def test_docx_room_table_matches_the_room_master():
    master, errors = parse_room_master(ROOM_MASTER.read_text(encoding="utf-8"))
    assert not [e for e in errors if "line" in e]
    by_code = {r["code"]: r for r in master}
    _, analyses, recs = gen(MEMO_DOCX)
    rooms = [r for r in recs if r["type"] == "room"]
    assert len(rooms) == 36
    for r in rooms:
        assert by_code[r["code"]]["capacity"] == r["capacity"]
        assert by_code[r["code"]]["exam_capacity"] == r["exam_capacity"]
    assert any(a.kind == "rules" for a in analyses)


def test_fast_path_records_carry_the_importer_results():
    recs, _ = fastpath.records_for("room-master", ROOM_MASTER, ROOM_MASTER.name, 2026)
    assert len(recs) == 87 and recs[0]["code"] == "A101" and recs[0]["capacity"] == 58
    recs, _ = fastpath.records_for("exam-list", EXAM_LIST, EXAM_LIST.name, 2026)
    assert len(recs) == len(parse_exam_list(EXAM_LIST).rows)
