"""Importer follow-ups of the planner comparison (docs/testing/2026-10-08-schedule-vs-planner.md §6, §7, §10).

Every case is a real row of the planner's workbooks: the row is copied with its header into a small
workbook (``subset``) so the import runs in a second, not on the whole list.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import openpyxl
import pytest
from app.importers import normalize as n
from sqlalchemy import select

from tests.conftest import BAHAR_LIST, GUZ_GRID


def subset(src: Path, rows: list[int], dst: Path) -> Path:
    """Header row + the given Excel rows of the first sheet of ``src`` (values only) -> ``dst``."""
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    wanted = {1, *rows}
    out = openpyxl.Workbook()
    ows = out.active
    assert ows is not None
    ows.title = ws.title
    for idx, values in enumerate(ws.iter_rows(min_row=1, max_row=max(wanted), max_col=40, values_only=True), 1):
        if idx in wanted:
            ows.append(list(values))
    wb.close()
    out.save(dst)
    return dst


# --------------------------------------------------------------------------- 1f room ranges


@pytest.mark.parametrize(
    "raw,codes",
    [
        ("C 501-502", ["C501", "C502"]),
        ("C 403-404", ["C403", "C404"]),  # Final list row 223
        ("A 206 veya C 403-404 veya A 106-107", ["A206", "C403", "C404", "A106", "A107"]),  # Final row 19
        ("C 501 - 502", ["C501", "C502"]),
        ("A 101-A 106", ["A101", "A106"]),
        ("C blok 601-602", ["C601", "C602"]),
        ("min 50-60 kişilik iki sınıf", []),
        ("A 204", ["A204"]),
    ],
)
def test_room_ranges_return_both_rooms(raw: str, codes: list[str]) -> None:
    assert n.parse_room_codes(raw) == codes


def test_definitive_room_range_returns_both_rooms() -> None:
    parsed = n.parse_definitive_rooms("C 501-502")
    assert parsed.status == "ROOMS"
    assert parsed.room_codes == ["C501", "C502"]


def test_capital_online_is_turkish_folded() -> None:
    """``"ONLINE".lower()`` in Turkish is ``"onlıne"``: keyword matching must fold ı and i."""
    assert n.parse_definitive_rooms("ONLINE").status == "NO_ROOM"
    assert n.parse_venue_request("ONLINE").needs_room is False


# --------------------------------------------------------------------------- 1a non-room venues


@pytest.mark.parametrize(
    "raw",
    [
        "CASE",
        "CASE 4. Kat",
        "Case -1.kat",
        "CASE+VETLAB",
        "Öğretim Üyesi Odası",
        "ÖĞRETİM ÜYESİ ODASI",
        "Ofis B5",
        "ONLINE",
        "Uzaktan Eğitim",
        "Zoom",
        "MS Teams",
        "Instructor's office",
    ],
)
def test_non_room_venues_need_no_room(raw: str) -> None:
    parsed = n.parse_definitive_rooms(raw)
    assert parsed.status == "NO_ROOM", raw
    assert parsed.room_codes == []


@pytest.mark.parametrize(
    "raw", ["Yabancı Diller Tarafından Paylaşılacak", "İNG BÖLÜMÜ", "C 501", "CASE / A 101", "Uygulama Merkezi"]
)
def test_rooms_and_other_texts_are_not_non_room_venues(raw: str) -> None:
    assert n.non_room_venue(raw) is None or n.parse_room_codes(raw)


def test_non_room_venue_list_is_configurable() -> None:
    assert n.non_room_venue("Astronomi Klubü") == "klubü"
    assert n.non_room_venue("CASE", venues=("kütüphane",)) is None
    assert n.non_room_venue("Merkez Kütüphane", venues=("kütüphane",)) == "kütüphane"
    from app.importers.settings import DEFAULT_NON_ROOM_VENUES, importer_settings

    assert "case" in DEFAULT_NON_ROOM_VENUES and "online" in DEFAULT_NON_ROOM_VENUES
    assert importer_settings().non_room_venues == list(DEFAULT_NON_ROOM_VENUES)


def test_real_non_room_venue_rows_need_no_room(parsed_bahar_list, parsed_guz_list, parsed_exam_list) -> None:
    """8 Bahar, 14 Güz and 19 Final events of the comparison got a classroom although the planner wrote CASE,
    an office or ONLINE in the definitive column."""
    bahar = {r.row: r for r in parsed_bahar_list.rows}
    for row in (365, 567, 640, 650, 835, 839, 840, 900, 1133):  # CASE / CASE 4. Kat / CASE -1. Kat
        assert bahar[row].needs_room is False, row
        assert bahar[row].definitive.venue == "case"
    guz = {r.row: r for r in parsed_guz_list.rows}
    for row in (30, 31, 51, 88, 184, 247, 254, 325, 436, 481, 580, 581, 610, 630, 645, 648, 736, 738):
        assert guz[row].needs_room is False, row
    exams = {r.row: r for r in parsed_exam_list.rows}
    for row in (61, 141, 157, 159, 219, 231, 285, 340, 349, 403, 409, 434, 483, 498, 503, 550, 773, 793, 905):
        assert exams[row].needs_room is False, row
    # rooms the language department shares out are still classrooms
    assert guz[11].needs_room is True  # ENG 105 §1 "Yabancı Diller Tarafından Paylaşılacak"


async def test_non_room_venue_import_writes_a_data_note(session, tmp_path) -> None:
    from app.importers.planning_list import import_planning_list
    from app.models import MeetingRequest

    path = subset(BAHAR_LIST, [365, 640], tmp_path / "case.xlsx")  # ANS 214 §1 "CASE 4. Kat", DYZ 146 "CASE"
    report = await import_planning_list(session, path, "T-CASE")
    rows = list((await session.execute(select(MeetingRequest))).scalars())
    assert len(rows) == 2
    assert all(m.needs_room is False for m in rows)
    assert all("CASE" in (m.notes or "") and "derslik gerekmez" in (m.notes or "") for m in rows)
    assert report.extra["non_room_venues"] == 2
    assert any("not a classroom" in w for w in report.warnings)


# --------------------------------------------------------------------------- 1b leading zeros


def test_course_key_drops_leading_zeros_like_the_solver_merge() -> None:
    from app.services.solver_bridge import _course_code

    assert n.course_key("SYS018") == n.course_key("SYS18") == "SYS18"
    assert n.course_key("SYS 019") == "SYS19"
    assert n.course_key("BİF111") == "BIF111"
    assert n.course_key("MBG100") == "MBG100"  # inner zeros stay
    assert _course_code("SYS 018 §1") == "SYS 18"
    # the canonical code keeps the planner's spelling (display)
    assert n.canon_course_code("SYS 018") == "SYS018"


async def test_sys18_and_sys018_are_one_course_with_the_original_spelling(session, tmp_path) -> None:
    """Bahar rows 68 (``SYS 18``) and 92 (``SYS018 §1``): one lecture in A 204, Friday 14:20."""
    from app.importers.planning_list import import_planning_list
    from app.models import Course, Section

    path = subset(BAHAR_LIST, [68, 92], tmp_path / "sys.xlsx")
    await import_planning_list(session, path, "T-SYS")
    courses = list((await session.execute(select(Course))).scalars())
    assert len(courses) == 1
    assert courses[0].display_code == "SYS 18"  # the first spelling of the file, never a rewritten code
    secs = list((await session.execute(select(Section))).scalars())
    assert {s.course_id for s in secs} == {courses[0].id} and len(secs) == 2
    # the row's own spelling is kept in the section key (re-import identity) and the source row
    assert sorted(s.source_key.split("|")[0] for s in secs) == ["SYS018", "SYS18"]


def test_exam_merge_key_ignores_leading_zeros(parsed_exam_list) -> None:
    rows = [r for r in parsed_exam_list.rows if n.course_key(r.course_code or "") == "SYS18" and r.merge_key]
    spellings = {r.course_code for r in rows}
    assert {"SYS18", "SYS018"} <= spellings
    by_slot: dict[tuple[object, object], set[str]] = {}
    for r in rows:
        by_slot.setdefault((r.date, r.start_time), set()).add(r.merge_key or "")
    assert all(len(keys) == 1 for keys in by_slot.values())  # one merge key per slot whatever the spelling


def test_course_key_migration_merges_duplicate_courses(tmp_path) -> None:
    import importlib.util

    import sqlalchemy as sa

    spec = importlib.util.spec_from_file_location(
        "m0016", Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0016_course_code_keys.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    eng = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE courses (id INTEGER PRIMARY KEY, code TEXT, display_code TEXT)"))
        c.execute(sa.text("CREATE TABLE sections (id INTEGER PRIMARY KEY, course_id INTEGER)"))
        c.execute(sa.text("CREATE TABLE exam_requests (id INTEGER PRIMARY KEY, merge_key TEXT)"))
        c.execute(
            sa.text("INSERT INTO courses VALUES (1,'SYS18','SYS 18'),(2,'SYS018','SYS 018'),(3,'MAT112','MAT 112')")
        )
        c.execute(sa.text("INSERT INTO sections VALUES (10,1),(11,2),(12,3)"))
        c.execute(sa.text("INSERT INTO exam_requests VALUES (5,'2026-FINAL:SYS018:2026-06-02:1400'),(6,NULL)"))
        mod.merge_course_keys(c)
        assert c.execute(sa.text("SELECT id, code FROM courses ORDER BY id")).all() == [(1, "SYS18"), (3, "MAT112")]
        assert c.execute(sa.text("SELECT course_id FROM sections ORDER BY id")).scalars().all() == [1, 1, 3]
        assert c.execute(sa.text("SELECT merge_key FROM exam_requests WHERE id=5")).scalar() == (
            "2026-FINAL:SYS18:2026-06-02:1400"
        )


# --------------------------------------------------------------------------- 1c non-person instructors


@pytest.mark.parametrize(
    "raw",
    [
        "Yüz yüze",
        "UZEM",
        "Uzem",
        "Online",
        "Hibrit/Online",
        "Asenkron",
        "yok",
        "Yabancı Diller",
        "Yabancı Diller Böl.Baş.",
        "Yabancı Diller Bölümü",
        "Ortak Dersler",
        "Fizyoloji ABD",
        "Biyofizik Anabilim Dalı",
        "Rektörlük",
        "daha sonra belirlenecek",
        "Öğt. Gör. Dr",
        "Bu ders 2024 müfredat güncellemesi sırasında eklenmiştir. Giriş yılı fark etmeksizin 3. ve 4. sınıf",
        "Dersliğin B blokta olmasını talep ediyor hocamız.",
        "Tüm Doktora Danışmanları",
    ],
)
def test_non_person_instructor_values(raw: str) -> None:
    assert n.non_person_reason(raw) is not None, raw


@pytest.mark.parametrize(
    "raw",
    [
        "Öğr. Gör. Özge Kovan",
        "Uğur Sezerman",
        "Perim Fatma TÜRKER",
        "T. Kocagöz",
        "Prof. Dr. Gönül ACAR(Dış Hoca)",
        "Dr. Öğr. Üyesi Nafiye Çiğdem Aktekin",
        "Psk. Özgenur Taşkın",
    ],
)
def test_people_are_people(raw: str) -> None:
    assert n.non_person_reason(raw) is None, raw


async def test_yuz_yuze_is_no_shared_instructor(session, tmp_path) -> None:
    """Bahar rows 1057 (RAD 282) and 1089 (RAD 106) both name "Yüz yüze" as the 2nd instructor: the run
    reported them as one instructor in two rooms on Tuesday."""
    from app.importers.planning_list import import_planning_list
    from app.models import Instructor, ScheduleRun, Term
    from app.services.solver_bridge import build_solver_input

    path = subset(BAHAR_LIST, [1057, 1089], tmp_path / "rad.xlsx")
    report = await import_planning_list(session, path, "T-RAD")
    names = set((await session.execute(select(Instructor.full_name))).scalars())
    assert "Yüz yüze" not in names
    assert report.extra["non_person_instructors"] == {"Yüz yüze": 2}
    term = (await session.execute(select(Term))).scalar_one()
    run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]}, params={})
    session.add(run)
    await session.flush()
    inp, _members = await build_solver_input(session, run)
    rad = {e.label: e for e in inp.events}
    assert set(rad) == {"RAD 282", "RAD 106"}
    assert not rad["RAD 282"].instructor_keys & rad["RAD 106"].instructor_keys


async def test_stored_non_person_instructor_is_ignored_by_the_bridge(session, tmp_path) -> None:
    """A database imported before the check still links "Yüz yüze": the bridge drops it and says so."""
    from app.importers.planning_list import import_planning_list
    from app.models import Instructor, ScheduleRun, Section, SectionInstructor, Term
    from app.services.solver_bridge import build_solver_input

    path = subset(BAHAR_LIST, [1057, 1089], tmp_path / "rad.xlsx")
    await import_planning_list(session, path, "T-RAD2")
    ghost = Instructor(full_name="Yüz yüze", canonical_name="yüz yüze")
    session.add(ghost)
    await session.flush()
    for sec in (await session.execute(select(Section))).scalars():
        session.add(SectionInstructor(section_id=sec.id, instructor_id=ghost.id, role="SECONDARY"))
    await session.commit()
    term = (await session.execute(select(Term))).scalar_one()
    run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]}, params={})
    session.add(run)
    await session.flush()
    inp, _ = await build_solver_input(session, run)
    assert all(f"INS:{ghost.id}" not in e.instructor_keys for e in inp.events)
    diags = [d for d in run.stats["bridge_diagnoses"] if d["code"] == "instructor_not_person"]
    assert len(diags) == 1 and diags[0]["params"]["names"] == ["Yüz yüze"]
    from app.services.data_issues import classify

    assert classify(diags[0]) == ["instructor_not_person"]


# --------------------------------------------------------------------------- 1d sheet-name dates


def test_final_sheet_three_uses_the_sheet_name_dates(parsed_final_grid) -> None:
    """``15 - 21 Haziran`` carries the day headers of the week before (9-14 June)."""
    sheet = next(s for s in parsed_final_grid.sheets if s.name == "15 - 21 Haziran")
    assert [(d.day, d.date) for d in sheet.days] == [(i, date(2026, 6, 14 + i)) for i in range(1, 8)]
    assert {e.date for e in sheet.entries} <= {date(2026, 6, 14 + i) for i in range(1, 8)}
    assert any("15 - 21 Haziran" in w and "sheet name" in w for w in sheet.warnings)
    assert len(sheet.date_conflicts) == 6
    # sheets whose headers agree keep them and get no warning
    first = next(s for s in parsed_final_grid.sheets if s.name == "1 - 5 Haziran")
    assert first.date_conflicts == []


# --------------------------------------------------------------------------- 1e missing week sheets


async def test_missing_week_sheets_are_reported_and_optionally_carried_forward(session, monkeypatch) -> None:
    """The Güz board has weeks 1-2 only (``28-02 Ekim 2. hafta`` is the last sheet)."""
    from app.importers.weekly_grid import import_weekly_grid
    from app.models import Block

    report = await import_weekly_grid(session, GUZ_GRID, "2026-GUZ", year=2026)
    assert report.extra["missing_weeks"] == list(range(3, 15))
    assert any("weeks 3-14" in w for w in report.warnings)
    blocks = list((await session.execute(select(Block).where(Block.archived.is_(False)))).scalars())
    assert all(b.weeks in ([1], [2]) for b in blocks)  # off by default: nothing is invented

    monkeypatch.setenv("IMPORT_GRID_CARRY_FORWARD", "1")
    report2 = await import_weekly_grid(session, GUZ_GRID, "2026-GUZ", year=2026)
    assert report2.extra["carried_forward_weeks"] == list(range(3, 15))
    blocks = list((await session.execute(select(Block).where(Block.archived.is_(False)))).scalars())
    last = [b for b in blocks if 2 in (b.weeks or [])]
    assert last and all(b.weeks == [2, *range(3, 15)] for b in last)
    assert all(b.weeks == [1] for b in blocks if 1 in (b.weeks or []))
