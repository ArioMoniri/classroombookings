"""Owner report 2026-11-02 (live site, institution profile): regression tests for the five items.

1. room data: B 406 + B 407 merged into B 406 (80 / exam 40), D 107 removed, D 106 60 / exam 30. The room master is
   an idempotent upsert that retires rooms it no longer lists (never deletes them), moves a merged room's future
   bookings into the room it was merged into (or reports them) and files rooms into building groups;
2. faculty rule: a room owned by the Tıp faculty is booked only by Tıp academicians; admins keep full access;
3. "Boş derslik bul" answered "0 boş oda" on an install seeded from the planning files: no room was in a room
   group, so CRBS's ungrouped-room rule hid every room;
4. the occupancy heatmap was empty: the imported boards were never published (the heatmap reads published runs);
5. imports: hyphenated course codes (``BP-230``), rows without a code as info, exam times off the period grid as
   info, every course code of the boards in the catalog, the exam list's instructors in the catalog.

Accounts below are invented role names; no person's name appears (KVKK).
"""

from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.core import db as dbmod
from app.importers import normalize as n
from app.importers.report import ImportReport
from app.importers.room_master import import_room_master, parse_room_master
from app.models import Booking, Course, Faculty, Program, Room, RoomGroup, ScheduleRun, Term
from app.services import bookings as bsvc
from sqlalchemy import select

from tests.conftest import EXAM_LIST, FIXTURES
from tests.crbs_env import env  # noqa: F401  (fixture)

MON = date(2026, 2, 16)  # Bahar week 3 (the env clock)
MASTER = FIXTURES / "room_master.csv"


# ------------------------------------------------------------------------------------------------- helpers
async def _session_do(fn: Any) -> Any:
    async with dbmod.get_session_factory()() as s:
        out = await fn(s)
        await s.commit()
        return out


async def _free_period(env, codes: list[str], day: date) -> str:  # type: ignore[no-untyped-def]  # noqa: F811
    """A period (``P3``) in which every room of ``codes`` is free on ``day`` (timetable, blocks, bookings)."""

    async def find(s):  # type: ignore[no-untyped-def]
        for p in range(1, 15):
            if f"P{p}" not in env.periods:
                continue
            free = [await bsvc.find_conflict(s, env.rooms[c], day, p, p) is None for c in codes]
            if all(free):
                return f"P{p}"
        raise AssertionError(f"no common free period for {codes} on {day}")

    return await _session_do(find)


async def _apply_master(text: str, tmp_path: Path, name: str = "room_master.csv") -> ImportReport:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return await _session_do(lambda s: import_room_master(s, path))


def _master_text(drop: tuple[str, ...] = (), merged: dict[str, str] | None = None) -> str:
    """The fixture room master without the rows of ``drop``; ``merged`` = {target: source} sets merged_from."""
    out = []
    for line in MASTER.read_text(encoding="utf-8").splitlines():
        code = line.split(",", 1)[0]
        if code in drop:
            continue
        if merged and code in merged:
            line = line.rsplit(",", 1)[0] + "," + merged[code]
        out.append(line)
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------- item 1
def test_fixture_room_master_carries_the_owner_changes() -> None:
    rows, errors = parse_room_master(MASTER.read_text(encoding="utf-8"))
    assert errors == []
    by = {r["code"]: r for r in rows}
    assert "B407" not in by and "D107" not in by  # merged / removed: not listed any more
    assert (by["B406"]["capacity"], by["B406"]["exam_capacity"], by["B406"]["merged_from"]) == (80, 40, ["B407"])
    assert (by["D106"]["capacity"], by["D106"]["exam_capacity"]) == (60, 30)
    assert {c for c, r in by.items() if r["owner_faculty"]} == {"A201", "A202", "A203"}
    assert {r["owner_faculty"] for r in rows if r["owner_faculty"]} == {"Tıp Fakültesi"}
    assert all("TIP" in (by[c]["tags"] or []) for c in ("A201", "A202", "A203"))


async def test_room_master_upsert_retires_merges_and_is_idempotent(env, tmp_path):  # noqa: F811
    """The owner's change on a database that holds the earlier master (B 407 and D 107 listed): B 407 and D 107 are
    retired, never deleted; B 407's future booking moves to B 406, a past one stays; a second run changes nothing;
    every bookable room is in its building's group; Tıp owns A 201-A 203."""
    before = _master_text(drop=()).replace(",,B 407\n", ",,\n")  # the earlier master: no merge yet
    before = before.replace("B 406,80,40", "B 406,30,22").replace("D 106,60,30", "D 106,82,36")
    before += "B 407,30,22,,B,4,1,,,\nD 107,20,10,,D,1,1,,,\n"
    first = await _apply_master(before, tmp_path, "earlier.csv")
    assert first.extra["rooms_retired"] == []
    _, teacher = await env.user("ogretim.elemani.b407@uni.edu.tr")
    day = MON + timedelta(days=2)
    period = await _free_period(env, ["B406", "B407"], day)
    future = await env.book(teacher, "B407", day, period)
    assert future.status_code == 201, future.text
    past = await env.book(teacher, "B407", MON, period, confirm_unpublished=True)
    env.set_now(env.clock["now"].replace(day=18, hour=7))  # Wednesday: the Monday booking is in the past
    report = await _apply_master(MASTER.read_text(encoding="utf-8"), tmp_path)
    assert sorted(report.extra["rooms_retired"]) == ["B407", "D107"]
    assert report.extra["merged"] == {"B407": "B406"}
    moved = [m["booking_id"] for m in report.extra["bookings_moved"]]
    assert moved == [future.json()["id"]]

    async def check(s):  # type: ignore[no-untyped-def]
        rooms = {r.code: r for r in (await s.execute(select(Room))).scalars()}
        assert (rooms["B406"].capacity, rooms["B406"].exam_capacity) == (80, 40)
        assert (rooms["D106"].capacity, rooms["D106"].exam_capacity) == (60, 30)
        for code in ("B407", "D107"):  # retired, kept
            assert rooms[code].is_bookable is False
            assert rooms[code].custom_fields["retired"]["reason"] == ("merged" if code == "B407" else "not_listed")
        assert rooms["B407"].custom_fields["retired"]["into"] == "B406"
        b = await s.get(Booking, future.json()["id"])
        assert b.room_id == rooms["B406"].id
        if past.status_code == 201:  # a booking already in the past is history: it stays where it was
            assert (await s.get(Booking, past.json()["id"])).room_id == rooms["B407"].id
        tip = (await s.execute(select(Faculty).where(Faculty.name == "Tıp Fakültesi"))).scalar_one()
        assert {c for c, r in rooms.items() if r.owner_faculty_id == tip.id} == {"A201", "A202", "A203"}
        groups = {g.id: g.name for g in (await s.execute(select(RoomGroup))).scalars()}
        bookable = [r for r in rooms.values() if r.is_bookable]
        assert bookable and all(r.room_group_id in groups for r in bookable)
        assert groups[rooms["A101"].room_group_id] == "A Blok"

    await _session_do(check)
    again = await _apply_master(MASTER.read_text(encoding="utf-8"), tmp_path)
    assert again.updated.get("rooms", 0) == 0 and again.updated.get("rooms_retired", 0) == 0
    assert again.extra["bookings_moved"] == [] and again.extra["room_groups"] == []


async def test_merge_reports_a_booking_it_cannot_move(env, tmp_path):  # noqa: F811
    _, teacher = await env.user("ogretim.elemani.birlesim@uni.edu.tr")
    day = MON + timedelta(days=3)
    period = await _free_period(env, ["A108", "A109"], day)
    assert (await env.book(env.admin, "A108", day, period)).status_code == 201  # the target slot is taken
    held = await env.book(teacher, "A109", day, period)
    assert held.status_code == 201, held.text
    report = await _apply_master(_master_text(drop=("A 109",), merged={"A 108": "A 109"}), tmp_path)
    assert "A109" in report.extra["rooms_retired"]  # (B 407 too: the fixture master merges it into B 406)
    assert report.extra["bookings_moved"] == []
    assert [x["booking_id"] for x in report.extra["bookings_in_retired_rooms"]] == [held.json()["id"]]
    assert any("remain in retired rooms" in w for w in report.warnings)
    # listed again: back in service
    back = await _apply_master(MASTER.read_text(encoding="utf-8"), tmp_path)
    assert any("A109 was retired; listed again" in w for w in back.warnings)
    assert (await _session_do(lambda s: s.get(Room, env.rooms["A109"]))).is_bookable is True


async def test_workbook_only_rooms_are_not_retired(env, tmp_path):  # noqa: F811
    """A room no master ever listed (only a workbook names it) is left alone by a master that does not list it."""
    report = await _apply_master("code,capacity\nA 101,58\n", tmp_path)
    assert report.extra["rooms_retired"] == []
    assert (await _session_do(lambda s: s.get(Room, env.rooms["A102"]))).is_bookable is True


async def test_room_detail_apis_carry_exam_capacity_and_owner(env, tmp_path):  # noqa: F811
    """The Çizelge room panel reads ``exam_capacity`` ("Sınav kapasitesi") from the run's calendar index; the booking
    room sheet and the room admin carry it too, with the owner faculty."""
    await _apply_master(MASTER.read_text(encoding="utf-8"), tmp_path)
    c = env.client
    idx = (await c.get(f"/api/v1/runs/{env.run_id}/calendar-index", headers=env.planner)).json()
    b406 = next(r for r in idx["rooms"] if r["code"] == "B406")
    assert (b406["capacity"], b406["exam_capacity"]) == (80, 40)
    info = (await c.get(f"/api/v1/bookings/rooms/{env.rooms['A201']}", headers=env.admin)).json()
    assert info["exam_capacity"] == 48 and info["owner_faculty"] == "Tıp Fakültesi"
    room = (await c.get(f"/api/v1/rooms/{env.rooms['D106']}", headers=env.admin)).json()
    assert (room["capacity"], room["exam_capacity"], room["owner_faculty_id"]) == (60, 30, None)
    # admins edit the owner and the exam capacity in the room admin
    r = await c.put(
        f"/api/v1/room-admin/rooms/{env.rooms['D106']}",
        json={"owner_faculty_id": info["owner_faculty_id"], "exam_capacity": 28},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    assert (r.json()["owner_faculty_name"], r.json()["exam_capacity"]) == ("Tıp Fakültesi", 28)
    r = await c.put(
        f"/api/v1/room-admin/rooms/{env.rooms['D106']}", json={"owner_faculty_id": 99999}, headers=env.admin
    )
    assert r.status_code == 422
    r = await c.put(f"/api/v1/room-admin/rooms/{env.rooms['D106']}", json={"owner_faculty_id": None}, headers=env.admin)
    assert r.json()["owner_faculty_id"] is None


# ------------------------------------------------------------------------------------------------- item 2
async def _faculty_users(env, tmp_path):  # type: ignore[no-untyped-def]  # noqa: F811
    """The room master (Tıp owns A 201-A 203), a Tıp department and a non-Tıp one, one academician in each."""
    await _apply_master(MASTER.read_text(encoding="utf-8"), tmp_path)

    async def deps(s):  # type: ignore[no-untyped-def]
        tip = (await s.execute(select(Faculty).where(Faculty.name == "Tıp Fakültesi"))).scalar_one()
        tip_prog = Program(name="Tıp", canonical_name="tıp (test)", faculty_id=tip.id)
        other = await s.execute(select(Program).where(Program.faculty_id.is_not(None), Program.faculty_id != tip.id))
        s.add(tip_prog)
        await s.flush()
        return tip_prog.id, other.scalars().first().id

    tip_dep, other_dep = await _session_do(deps)
    _, tip_user = await env.user("tip.akademisyen@uni.edu.tr", department_id=tip_dep)
    _, other_user = await env.user("muhendislik.akademisyen@uni.edu.tr", department_id=other_dep)
    return tip_user, other_user


async def test_tip_rooms_are_reserved_for_tip_academicians(env, tmp_path):  # noqa: F811
    tip_user, other_user = await _faculty_users(env, tmp_path)
    day = MON + timedelta(days=1)
    p = await _free_period(env, ["A201", "A202", "A101", "A102"], day)
    # a Tıp academician reserves a Tıp room and a non-Tıp room
    assert (await env.book(tip_user, "A201", day, p)).status_code == 201
    assert (await env.book(tip_user, "A101", day, p)).status_code == 201
    # a non-Tıp academician is refused a Tıp room, with a Turkish message
    r = await env.book(other_user, "A202", day, p)
    assert r.status_code == 403, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "room_faculty" and detail["owner_faculty"] == "Tıp Fakültesi"
    assert "yalnızca Tıp Fakültesi öğretim elemanları rezerve edebilir" in detail["message_tr"]
    # ... and may reserve a non-Tıp room
    assert (await env.book(other_user, "A102", day, p)).status_code == 201
    # administrators keep full access
    assert (await env.book(env.admin, "A202", day, p)).status_code == 201


async def test_recurring_and_multi_bookings_follow_the_faculty_rule(env, tmp_path):  # noqa: F811
    _, other_user = await _faculty_users(env, tmp_path)
    day = MON + timedelta(days=1)
    p = await _free_period(env, ["A203"], day)
    for path in ("/api/v1/bookings/recurring/preview", "/api/v1/bookings/recurring"):
        r = await env.client.post(
            path,
            json={"room_id": env.rooms["A203"], "date": day.isoformat(), "period_id": env.periods[p]},
            headers=other_user,
        )
        assert r.status_code == 403 and r.json()["detail"]["code"] == "room_faculty", r.text
    r = await env.client.post(
        "/api/v1/bookings/multi",
        json={"slots": [{"date": day.isoformat(), "period_id": env.periods[p], "room_id": env.rooms["A203"]}]},
        headers=other_user,
    )
    assert r.status_code == 403 and r.json()["detail"]["code"] == "room_faculty", r.text


async def test_search_and_grid_hide_tip_rooms_from_other_faculties(env, tmp_path):  # noqa: F811
    tip_user, other_user = await _faculty_users(env, tmp_path)
    body = {"date": (MON + timedelta(days=1)).isoformat(), "start": 1, "end": 2, "headcount": 30}
    other = (await env.client.post("/api/v1/rooms/find", json=body, headers=other_user)).json()
    assert not {"A201", "A202", "A203"} & {x["code"] for x in other["results"]}
    assert other["summary"]["faculty_hidden"] == 3
    tip = (await env.client.post("/api/v1/rooms/find", json=body, headers=tip_user)).json()
    assert {"A201", "A202", "A203"} <= {x["code"] for x in tip["results"]}
    assert tip["summary"]["faculty_hidden"] == 0
    grid = (
        await env.client.get(
            "/api/v1/bookings/grid",
            params={"display": "room", "date": MON.isoformat(), "room_id": env.rooms["A201"]},
            headers=other_user,
        )
    ).json()
    open_slots = [s for s in grid["slots"] if s["status"] == "available"]
    assert open_slots == []
    assert any(s.get("reason") == "permissions" for s in grid["slots"])


# ------------------------------------------------------------------------------------------------- item 3
async def test_find_room_finds_rooms_after_the_room_master_groups_them(env, tmp_path):  # noqa: F811
    """The live install: CRBS hides ungrouped rooms and no importer made a group, so every search answered
    "0 boş oda · 1/1 tarih açık". The room master now files the rooms into building groups."""
    c = env.client
    r = await c.put("/api/v1/org/settings", json={"show_ungrouped_rooms": False}, headers=env.admin)
    assert r.status_code == 200, r.text
    _, teacher = await env.user("bos.derslik@uni.edu.tr")
    body = {"date": MON.isoformat(), "start": 1, "end": 2, "headcount": 58}
    before = (await c.post("/api/v1/rooms/find", json=body, headers=teacher)).json()
    assert before["summary"]["rooms"] == 0 and before["summary"]["text_tr"].startswith("0 boş oda")
    await _apply_master(MASTER.read_text(encoding="utf-8"), tmp_path)
    after = (await c.post("/api/v1/rooms/find", json=body, headers=teacher)).json()
    assert after["summary"]["free"] > 0, after["summary"]
    free = [x for x in after["results"] if x["status"] == "free"]
    assert free and all(x["capacity"] >= 58 for x in free)
    assert not any(x["code"] in ("B407", "D107") for x in after["results"])  # retired rooms are not offered


# ------------------------------------------------------------------------------------------------- item 4
@pytest.fixture
async def unpublished(tmp_path_factory, tmp_path):  # type: ignore[no-untyped-def]
    """The Bahar template (grid + planning list imported, nothing published), like the live install."""
    from tests.studio_support import bahar_template

    db = tmp_path / "unpublished.db"
    shutil.copy(bahar_template(tmp_path_factory), db)
    dbmod.configure_engine(f"sqlite+aiosqlite:///{db}")
    yield
    await dbmod.dispose_engine()


async def test_heatmap_of_an_unpublished_term_shows_the_imported_board(unpublished):
    from app.services import utilisation as util
    from app.services.board_publish import publish_imported_boards

    async def heat(s):  # type: ignore[no-untyped-def]
        term = (await s.execute(select(Term).where(Term.code == "2026-BAHAR"))).scalar_one()
        return await util.room_heatmap(s, term_id=term.id)

    async def published(s):  # type: ignore[no-untyped-def]
        return (await s.execute(select(ScheduleRun).where(ScheduleRun.is_active.is_(True)))).first()

    assert await _session_do(published) is None  # like the live install: imported, never published
    data = await _session_do(heat)
    assert data["empty"] is False and data["overall"]["total"]["occupied"] > 0
    assert [x["code"] for x in data["notes"]] == ["board_unpublished"]
    assert data["source"] == "board" and {r["kind"] for r in data["runs"]} == {"COURSE", "EXAM"}

    rows = await _session_do(publish_imported_boards)
    assert {(x["term"], x["kind"], x["action"]) for x in rows} == {
        ("2026-BAHAR", "COURSE", "published"),
        ("2026-BAHAR", "EXAM", "published"),
    }
    data2 = await _session_do(heat)
    assert data2["notes"] == [] and all(r["is_active"] for r in data2["runs"])
    assert data2["overall"]["total"]["occupied"] == data["overall"]["total"]["occupied"]
    again = await _session_do(publish_imported_boards)  # idempotent: a published term is kept
    assert {x["action"] for x in again} == {"kept"}


async def test_publish_keeps_a_planner_published_run(unpublished):
    from app.services.board_publish import publish_imported_boards

    async def solver_run(s):  # type: ignore[no-untyped-def]
        term = (await s.execute(select(Term).where(Term.code == "2026-BAHAR"))).scalar_one()
        run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", status="FEASIBLE", is_active=True, params={})
        s.add(run)
        await s.flush()
        return run.id

    rid = await _session_do(solver_run)
    rows = {x["kind"]: x for x in await _session_do(publish_imported_boards)}
    assert rows["COURSE"] == {"term": "2026-BAHAR", "kind": "COURSE", "action": "kept", "run_id": rid}
    assert rows["EXAM"]["action"] == "published"


# ------------------------------------------------------------------------------------------------- item 5
@pytest.mark.parametrize(
    ("text", "codes"),
    [
        ("BP-230", ["BP230"]),
        ("MDF-516", ["MDF516"]),
        ("MDF - 516", ["MDF516"]),
        ("BP 230", ["BP230"]),
        ("PHAR 231-233", ["PHAR231", "PHAR233"]),
        # the placeholders canon_course_code_loose makes are never read as course numbers
        ("ACU-8917", []),
        ("ACU-B14F", []),
    ],
)
def test_hyphenated_course_codes(text: str, codes: list[str]) -> None:
    assert n.extract_course_codes(text) == codes
    if codes:
        assert n.display_course_code(codes[0]) == f"{codes[0][:-3]} {codes[0][-3:]}"


def test_exam_list_reads_bp_230_and_lists_rows_without_a_code_as_info(parsed_exam_list) -> None:
    row = next(r for r in parsed_exam_list.rows if r.row == 568)
    assert row.course_code == "BP230"
    reasons = {row_: reason for row_, reason, _detail in parsed_exam_list.skipped}
    assert 568 not in reasons
    assert set(reasons.values()) == {"no course code"}  # meetings, UZEM, staj: no code cell at all
    report = ImportReport(kind="exam-list")
    for row_, reason, detail in parsed_exam_list.skipped:
        report.skip(row_, reason, detail)
    report.skip(1, "unreadable course code", "c")
    d = report.to_dict()
    assert d["skip_severity"] == {"info": len(parsed_exam_list.skipped), "warning": 1}
    assert d["rows_skipped"][0]["severity"] == "info"


def test_planning_lists_read_mdf_516(parsed_bahar_list) -> None:
    assert any(r.course_code == "MDF516" for r in parsed_bahar_list.rows)
    skipped = {reason for _row, reason, _detail in parsed_bahar_list.skipped}
    assert skipped <= {"no course code", "unreadable course code"}


async def test_exam_import_keeps_expected_time_notes_out_of_the_warnings(session) -> None:
    """The 582 "uyarı" of the live Final import were 552 exam times that do not align with the period grid (expected
    for exam lists): now info, with one summary line first; the warnings left are the rows to look at."""
    from app.importers.exam_list import import_exam_list

    report = await import_exam_list(session, EXAM_LIST, "2026-FINAL")
    d = report.to_dict()
    assert d["warnings_count"] < 60, d["warning_groups"]
    assert not any(g["code"] == "exam_time_partial" for g in d["warning_groups"])
    assert d["info_count"] > 500 and d["info"][0].endswith("expected for exam lists")
    assert d["info_items"][0]["code"] == "exam_time_partial"
    assert d["info_groups"][0]["code"] == "exam_time_partial"
    assert d["rows_imported"] == d["rows_total"] - d["rows_skipped_count"]
    assert d["skip_reasons"] == {"no course code": d["rows_skipped_count"]}
    codes = {c.code for c in (await session.execute(select(Course))).scalars()}
    assert "BP230" in codes
    # the exam list's instructors join the catalog (counted, never named here)
    assert report.created["instructors"] > 0


async def test_grid_course_codes_join_the_catalog(unpublished) -> None:
    """Every course code a weekly board names is in the catalog (EMED 14 was on the Bahar board only)."""

    async def keys(s):  # type: ignore[no-untyped-def]
        return {n.course_key(c.code) for c in (await s.execute(select(Course))).scalars()}

    assert {"EMED14", "EMED205", "PSI156"} <= await _session_do(keys)
