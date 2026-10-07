"""CRBS legacy import: the shipped MySQL install scripts are loaded into SQLite through the DDL adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.importers.crbs_legacy import (
    SqliteSource,
    import_crbs,
    load_dump_into_sqlite,
    mysql_create_to_sqlite,
    split_sql_statements,
)
from app.models import Block, Program, Room, Term, User, Week
from sqlalchemy import func, select

RES = Path(__file__).resolve().parents[3] / "crbs-core" / "application" / "modules" / "install" / "resources"
STRUCTURE = RES / "structure.sql"
DATA = RES / "data.sql"

SEED = """
INSERT INTO rooms (room_id, room_group_id, user_id, name, location, bookable, icon, notes, photo, pos) VALUES
 (1, 1, NULL, 'A 101', 'A Blok 1. kat', 1, NULL, 'projector', 'a101.jpg', 1),
 (2, 1, NULL, 'A 204', 'A Blok 2. kat', 1, NULL, NULL, NULL, 2),
 (3, 1, NULL, 'Konferans Salonu', 'B Blok', 0, NULL, NULL, NULL, 3);
INSERT INTO roomfields (field_id, name, type) VALUES (1, 'Kapasite', 'text'), (2, 'Donanım', 'select');
INSERT INTO roomoptions (option_id, field_id, value) VALUES (1, 2, 'Projeksiyon'), (2, 2, 'Akıllı tahta');
INSERT INTO roomvalues (value_id, room_id, field_id, value) VALUES (1, 1, 1, '58'), (2, 1, 2, '2'), (3, 2, 1, '156');
INSERT INTO periods (period_id, schedule_id, time_start, time_end, name, bookable, day_1, day_2, day_3, day_4, day_5, day_6, day_7) VALUES
 (1, 1, '08:30:00', '09:10:00', 'P1', 1, 1,1,1,1,1,0,0),
 (2, 1, '09:20:00', '10:00:00', 'P2', 1, 1,1,1,1,1,0,0),
 (3, 1, '13:30:00', '16:00:00', 'Afternoon', 1, 1,1,1,1,1,0,0);
INSERT INTO sessions (session_id, default_schedule_id, name, date_start, date_end, is_current, is_selectable) VALUES
 (1, 1, '2025 - 2026', '2025-09-01', '2026-07-31', 1, 1);
INSERT INTO holidays (holiday_id, session_id, name, date_start, date_end) VALUES (1, 1, 'Yarıyıl tatili', '2026-01-26', '2026-02-01');
INSERT INTO departments (department_id, name, description, icon) VALUES (1, 'Psikoloji', NULL, NULL), (2, 'Hemşirelik', NULL, NULL);
INSERT INTO users (user_id, role_id, department_id, username, firstname, lastname, email, password, displayname, ext, lastlogin, enabled, created, force_password_reset) VALUES
 (1, 1, NULL, 'admin', 'Fatih', 'Demir', 'fatih@example.com', '$2y$10$x', 'Fatih Demir', NULL, NULL, 1, NULL, 0),
 (2, 2, 1, 'teacher', 'Ayşe', 'Yılmaz', NULL, NULL, NULL, NULL, NULL, 1, NULL, 0);
INSERT INTO weekdates (week_id, date) VALUES (1, '2025-09-01'), (1, '2025-09-08'), (1, '2025-09-15');
INSERT INTO bookings (booking_id, repeat_id, session_id, period_id, room_id, user_id, department_id, date, status, notes) VALUES
 (1, NULL, 1, 1, 1, 2, 1, '2025-09-02', 10, 'PSI 101 makeup'),
 (2, NULL, 1, 3, 2, 1, NULL, '2025-09-03', 10, 'Oryantasyon'),
 (3, NULL, 1, 2, 1, 1, NULL, '2025-09-04', 20, 'cancelled one');
INSERT INTO bookings_repeat (repeat_id, session_id, period_id, room_id, user_id, department_id, week_id, weekday, status, notes) VALUES
 (1, 1, 2, 2, 2, 2, 1, 2, 10, 'HEM 101');
"""


def test_split_statements_respects_quotes():
    stmts = list(split_sql_statements("INSERT INTO t VALUES ('a;b', 'it''s');\n-- c;\nSELECT 1;"))
    assert stmts == ["INSERT INTO t VALUES ('a;b', 'it''s')", "SELECT 1"]


def test_ddl_adapter_strips_mysql_specifics():
    stmt = (STRUCTURE.read_text(encoding="utf-8").split("CREATE TABLE `bookings` ")[1]).split(";")[0]
    out = mysql_create_to_sqlite("CREATE TABLE `bookings` " + stmt)
    assert "CONSTRAINT" not in out and "unsigned" not in out and "ENGINE" not in out and "`" not in out
    sqlite3.connect(":memory:").execute(out)


def test_install_scripts_load_into_sqlite():
    conn, warnings = load_dump_into_sqlite([STRUCTURE, DATA])
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"rooms", "bookings", "bookings_repeat", "periods", "sessions", "weeks", "departments", "users"} <= tables
    assert conn.execute("SELECT COUNT(*) FROM auth_permissions").fetchone()[0] == 28
    assert conn.execute("SELECT COUNT(*) FROM room_groups").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 1
    # the MySQL-variable based session/date inserts are skipped with a warning, not an error
    assert any("skipped" in w for w in warnings)
    assert not any("error" in w.lower() for w in warnings)


async def test_import_crbs_from_dump(session):
    conn, _ = load_dump_into_sqlite([STRUCTURE, DATA])
    conn.executescript(SEED)
    src = SqliteSource(conn)
    rep = await import_crbs(session, src, filename="crbs-seed")
    assert rep.created["rooms"] == 3 and rep.created["terms"] == 1 and rep.created["users"] == 2
    assert rep.created["programs"] == 2 and rep.created["blocks"] == 3  # 2 single + 1 repeat; cancelled skipped
    assert rep.created["weeks"] >= 45
    a101 = (await session.execute(select(Room).where(Room.code == "A101"))).scalar_one()
    assert a101.legacy_crbs_room_id == 1 and a101.capacity == 58 and a101.photo_url == "uploads/a101.jpg"
    assert a101.custom_fields["Donanım"] == "Akıllı tahta" and a101.room_group == "All" and a101.is_bookable
    conf = (await session.execute(select(Room).where(Room.legacy_crbs_room_id == 3))).scalar_one()
    assert conf.display_name == "Konferans Salonu" and not conf.is_bookable
    term = (await session.execute(select(Term).where(Term.code == "CRBS-2025-2026"))).scalar_one()
    assert term.is_active and term.legacy_crbs_session_id == 1 and term.periods_json[0]["periods"][0]["name"] == "P1"
    hol = (await session.execute(select(Week).where(Week.term_id == term.id, Week.kind == "HOLIDAY"))).scalars().all()
    assert len(hol) == 1 and hol[0].label == "Yarıyıl tatili"
    prog = (await session.execute(select(Program).where(Program.legacy_crbs_department_id == 1))).scalar_one()
    assert prog.name == "Psikoloji"
    admin = (await session.execute(select(User).where(User.email == "fatih@example.com"))).scalar_one()
    assert admin.role == "ADMIN" and admin.password_hash is None
    teacher = (await session.execute(select(User).where(User.legacy_crbs_user_id == 2))).scalar_one()
    assert teacher.role == "VIEWER" and teacher.email.endswith("@crbs.local")
    blocks = (
        (await session.execute(select(Block).where(Block.source == "CRBS").order_by(Block.source_key))).scalars().all()
    )
    single = [b for b in blocks if b.date is not None]
    assert len(single) == 2
    b1 = next(b for b in single if b.source_key == "CRBS:booking:1")
    assert (
        b1.day == 2 and (b1.start_period, b1.end_period) == (1, 1) and b1.weeks == [1] and "PSI 101 makeup" in b1.label
    )
    b2 = next(b for b in single if b.source_key == "CRBS:booking:2")
    assert (b2.start_period, b2.end_period) == (7, 9)
    rep_b = next(b for b in blocks if b.source_key == "CRBS:repeat:1")
    assert rep_b.day == 2 and rep_b.weeks == [1, 2, 3] and "HEM 101" in rep_b.label and rep_b.date is None

    # idempotent re-import
    n_rooms = (await session.execute(select(func.count(Room.id)))).scalar_one()
    rep2 = await import_crbs(session, src, filename="crbs-seed")
    assert rep2.created["rooms"] == 0 and rep2.created["blocks"] == 0 and rep2.updated["blocks"] == 3
    assert (await session.execute(select(func.count(Room.id)))).scalar_one() == n_rooms
    assert (await session.execute(select(func.count(Block.id)))).scalar_one() == 3


async def test_import_crbs_from_paths(session):
    rep = await import_crbs(session, [STRUCTURE, DATA])
    assert rep.extra["rooms"] == 0 and rep.created.get("terms", 0) == 0
