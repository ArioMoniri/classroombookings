"""CRBS legacy import (audit B4): the shipped MySQL install scripts (``structure.sql`` + ``data.sql``) are
loaded into SQLite through the DDL adapter, a sample of a real installation is seeded on top, and the
importer fills the CRBS-parity tables: roles + permissions, users (usernames, legacy password hashes,
departments, constraints), room groups / owners / custom fields, ACL, schedules + periods, sessions + their
schedules, timetable weeks + dates, holidays, bookings + series + booking slots. Legacy ``$2y$`` bcrypt and
``sha1:`` hashes log in exactly as in CRBS and are rehashed to argon2."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import bcrypt
from app.core import db as dbmod
from app.importers.crbs_legacy import (
    SqliteSource,
    import_crbs,
    load_dump_into_sqlite,
    mysql_create_to_sqlite,
    split_sql_statements,
)
from app.models import (
    Block,
    Booking,
    BookingPeriod,
    BookingSchedule,
    BookingSeries,
    BookingSlot,
    Holiday,
    Program,
    Role,
    Room,
    RoomAcl,
    RoomCustomField,
    RoomCustomFieldValue,
    RoomGroup,
    Term,
    TermBookingSettings,
    TermDate,
    TermSchedule,
    TimetableWeek,
    User,
    UserConstraint,
    Week,
)
from sqlalchemy import func, select

from tests.api_fixtures import login

RES = Path(__file__).resolve().parents[3] / "crbs-core" / "application" / "modules" / "install" / "resources"
STRUCTURE = RES / "structure.sql"
DATA = RES / "data.sql"

ADMIN_PW = "Yönetici-Parola1"
TEACHER_PW = "ogretmen123"


def _php_bcrypt(secret: str) -> str:
    """What PHP ``password_hash(..., PASSWORD_DEFAULT)`` stores: ``$2y$`` bcrypt."""
    return bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt(4)).decode().replace("$2b$", "$2y$", 1)


ADMIN_HASH = _php_bcrypt(ADMIN_PW)
# CRBS migration 20181208130700_update_passwords: "sha1:" + password_hash(sha1(password))
TEACHER_HASH = "sha1:" + _php_bcrypt(hashlib.sha1(TEACHER_PW.encode()).hexdigest())

SEED = f"""
INSERT INTO room_groups (room_group_id, pos, name, description) VALUES (2, 1, 'B Blok', 'Konferans');
INSERT INTO rooms (room_id, room_group_id, user_id, name, location, bookable, icon, notes, photo, pos) VALUES
 (1, 1, NULL, 'A 101', 'A Blok 1. kat', 1, NULL, 'projector', 'a101.jpg', 1),
 (2, 1, NULL, 'A 204', 'A Blok 2. kat', 1, NULL, NULL, NULL, 2),
 (3, 2, 2, 'Konferans Salonu', 'B Blok', 0, NULL, NULL, NULL, 3);
INSERT INTO roomfields (field_id, name, type) VALUES (1, 'Kapasite', 'text'), (2, 'Donanım', 'select'), (3, 'Engelli erişimi', 'checkbox');
INSERT INTO roomoptions (option_id, field_id, value) VALUES (1, 2, 'Projeksiyon'), (2, 2, 'Akıllı tahta');
INSERT INTO roomvalues (value_id, room_id, field_id, value) VALUES (1, 1, 1, '58'), (2, 1, 2, '2'), (3, 2, 1, '156'), (4, 1, 3, '1');
INSERT INTO periods (period_id, schedule_id, time_start, time_end, name, bookable, day_1, day_2, day_3, day_4, day_5, day_6, day_7) VALUES
 (1, 1, '08:30:00', '09:10:00', 'P1', 1, 1,1,1,1,1,0,0),
 (2, 1, '09:20:00', '10:00:00', 'P2', 1, 1,1,1,1,1,0,0),
 (3, 1, '13:30:00', '16:00:00', 'Öğleden sonra', 1, 1,1,1,1,1,0,0),
 (4, 1, '06:00:00', '07:00:00', 'Sabah erken', 1, 1,1,1,1,1,0,0);
INSERT INTO sessions (session_id, default_schedule_id, name, date_start, date_end, is_current, is_selectable) VALUES
 (1, 1, '2025 - 2026', '2025-09-01', '2026-07-31', 1, 1);
INSERT INTO session_schedules (session_id, room_group_id, schedule_id) VALUES (1, 1, 1), (1, 2, 1);
INSERT INTO weeks (week_id, name, fgcol, bgcol, icon) VALUES (2, 'B Haftası', '', 'FFD966', NULL);
INSERT INTO dates (date, weekday, session_id, week_id, holiday_id) VALUES
 ('2025-09-01', 1, 1, 1, NULL), ('2025-09-02', 2, 1, 1, NULL), ('2025-09-03', 3, 1, 1, NULL),
 ('2025-09-04', 4, 1, 1, NULL), ('2025-09-09', 2, 1, 2, NULL), ('2025-09-16', 2, 1, 1, NULL),
 ('2025-09-23', 2, 1, 1, NULL);
INSERT INTO holidays (holiday_id, session_id, name, date_start, date_end) VALUES (1, 1, 'Yarıyıl tatili', '2026-01-26', '2026-02-01');
INSERT INTO departments (department_id, name, description, icon) VALUES (1, 'Psikoloji', 'Psikoloji Bölümü', NULL), (2, 'Hemşirelik', NULL, NULL);
INSERT INTO auth_roles (role_id, name, description, max_active_bookings, range_min, range_max, recur_max_instances) VALUES
 (3, 'Bölüm Sekreteri', 'Bölüm adına rezervasyon', 5, NULL, 30, NULL);
INSERT INTO auth_roles_permissions (role_id, permission_id) VALUES (3, 14), (3, 15), (3, 18);
INSERT INTO users (user_id, role_id, department_id, username, firstname, lastname, email, password, displayname, ext, lastlogin, enabled, created, force_password_reset) VALUES
 (1, 1, NULL, 'admin', 'Fatih', 'Demir', 'Fatih@Example.com', '{ADMIN_HASH}', 'Fatih Demir', '4073', '2025-09-01 08:00:00', 1, NULL, 0),
 (2, 2, 1, 'ayse.yilmaz', 'Ayşe', 'Yılmaz', NULL, '{TEACHER_HASH}', NULL, NULL, NULL, 1, NULL, 1),
 (3, 3, 2, 'SEKRETER', 'İlknur', 'Işık', 'sekreter@uni.edu.tr', NULL, 'İlknur Işık', NULL, NULL, 0, NULL, 0);
INSERT INTO users_constraints (user_id, max_active_bookings_type, max_active_bookings_value, range_min_type, range_min_value, range_max_type, range_max_value, recur_max_instances_type, recur_max_instances_value) VALUES
 (3, 'U', 2, 'R', NULL, 'X', NULL, 'R', NULL);
INSERT INTO auth_acl (acl_id, entity_type, entity_id, context_type, context_id) VALUES
 (1, 'room', 3, 'user', 2), (2, 'room_group', 2, 'department', 1), (3, 'room', 99, 'user', 2);
INSERT INTO auth_acl_permissions (acl_id, permission_id) VALUES (1, 17), (2, 14), (2, 15), (3, 14);
INSERT INTO bookings_repeat (repeat_id, session_id, period_id, room_id, user_id, department_id, week_id, weekday, status, notes, created_by) VALUES
 (1, 1, 2, 2, 2, 2, 1, 2, 10, 'HEM 101 – İç Hastalıkları', 1);
INSERT INTO bookings (booking_id, repeat_id, session_id, period_id, room_id, user_id, department_id, date, status, notes, created_at, created_by, cancelled_at, cancelled_by, cancel_reason) VALUES
 (1, NULL, 1, 1, 1, 2, 1, '2025-09-02', 10, 'PSİ 101 telafi', '2025-08-20 10:00:00', 2, NULL, NULL, NULL),
 (2, NULL, 1, 3, 2, 1, NULL, '2025-09-03', 10, 'Oryantasyon', NULL, 1, NULL, NULL, NULL),
 (3, NULL, 1, 2, 1, 1, NULL, '2025-09-04', 15, 'iptal edilen', NULL, 1, '2025-08-30 12:00:00', 1, 'Toplantı ertelendi'),
 (4, 1, 1, 2, 2, 2, 2, '2025-09-02', 10, 'HEM 101 – İç Hastalıkları', NULL, 1, NULL, NULL, NULL),
 (5, 1, 1, 2, 2, 2, 2, '2025-09-16', 10, 'HEM 101 – İç Hastalıkları', NULL, 1, NULL, NULL, NULL),
 (6, 1, 1, 2, 2, 2, 2, '2025-09-23', 10, 'HEM 101 – İç Hastalıkları', NULL, 1, NULL, NULL, NULL),
 (7, NULL, 1, 4, 1, 2, NULL, '2025-09-02', 10, 'grid dışı', NULL, 2, NULL, NULL, NULL);
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


def _source() -> SqliteSource:
    conn, _ = load_dump_into_sqlite([STRUCTURE, DATA])
    conn.executescript(SEED)
    return SqliteSource(conn)


async def _one(session, model, *where):  # type: ignore[no-untyped-def]
    return (await session.execute(select(model).where(*where))).scalar_one()


async def test_import_crbs_fills_the_parity_tables(session):
    # an earlier SmartSched version imported CRBS bookings as solver blocks: they are superseded now
    term = Term(code="CRBS-2025-2026", name="2025 - 2026")
    session.add(term)
    await session.flush()
    room = Room(code="A101", display_name="A 101", legacy_crbs_room_id=1)
    session.add(room)
    await session.flush()
    session.add(
        Block(
            term_id=term.id, room_id=room.id, day=2, start_period=1, end_period=1, label="x", source="CRBS",
            source_key="CRBS:booking:1",
        )
    )
    await session.commit()

    rep = await import_crbs(session, _source(), filename="crbs-seed")
    assert rep.created["blocks"] == 0 and rep.updated["blocks_archived"] == 1
    assert rep.created["bookings"] == 7 - 1 and rep.created["booking_series"] == 1  # P "Sabah erken" is off-grid
    assert any("Sabah erken" in w for w in rep.warnings)

    # roles + permissions (data.sql verbatim, custom role with its limits)
    admin_role = await _one(session, Role, Role.code == "ADMIN")
    teacher_role = await _one(session, Role, Role.code == "TEACHER")
    secretary = await _one(session, Role, Role.name == "Bölüm Sekreteri")
    assert secretary.code is None and secretary.max_active_bookings == 5 and secretary.range_max == 30
    assert sorted(p.name for p in secretary.permissions) == ["book_single.create", "book_single.set_user", "room.view"]
    assert sorted(p.name for p in teacher_role.permissions) == [
        "book_recur.view_other_notes",
        "book_single.create",
        "book_single.view_other_notes",
        "room.view",
    ]

    # users: usernames, hashes as stored by CRBS, roles, departments, constraints; no invented e-mails
    psy = await _one(session, Program, Program.legacy_crbs_department_id == 1)
    assert psy.name == "Psikoloji" and psy.description == "Psikoloji Bölümü"
    admin = await _one(session, User, User.username == "admin")
    assert admin.email == "fatih@example.com" and admin.role_id == admin_role.id and admin.role == "ADMIN"
    assert admin.password_hash == ADMIN_HASH and admin.ext == "4073" and admin.last_login_at is not None
    ayse = await _one(session, User, User.legacy_crbs_user_id == 2)
    assert ayse.username == "ayse.yilmaz" and ayse.email is None and ayse.role == "TEACHER"
    assert ayse.full_name == "Ayşe Yılmaz" and ayse.firstname == "Ayşe" and ayse.department_id == psy.id
    assert ayse.password_hash == TEACHER_HASH and ayse.force_password_reset is True
    sek = await _one(session, User, User.legacy_crbs_user_id == 3)
    assert sek.username == "sekreter" and sek.role_id == secretary.id and sek.role == "CUSTOM" and not sek.is_active
    uc = await session.get(UserConstraint, sek.id)
    assert (uc.max_active_bookings_type, uc.max_active_bookings_value, uc.range_max_type) == ("U", 2, "X")

    # rooms: groups, owner, location, custom fields
    groups = {g.name: g for g in (await session.execute(select(RoomGroup))).scalars()}
    assert set(groups) == {"All", "B Blok"} and groups["B Blok"].pos == 1
    a101 = await _one(session, Room, Room.code == "A101")
    assert a101.room_group_id == groups["All"].id and a101.room_group == "All" and a101.capacity == 58
    assert a101.location == "A Blok 1. kat" and a101.photo_url == "uploads/a101.jpg"
    assert a101.custom_fields["Donanım"] == "Akıllı tahta"
    conf = await _one(session, Room, Room.legacy_crbs_room_id == 3)
    assert conf.display_name == "Konferans Salonu" and not conf.is_bookable and conf.owner_user_id == ayse.id
    fields = {f.name: f for f in (await session.execute(select(RoomCustomField))).scalars()}
    assert {k: f.type for k, f in fields.items()} == {"Kapasite": "TEXT", "Donanım": "SELECT", "Engelli erişimi": "CHECKBOX"}
    values = {
        v.field_id: v.value
        for v in (await session.execute(select(RoomCustomFieldValue).where(RoomCustomFieldValue.room_id == a101.id))).scalars()
    }
    smart_board = next(o for o in fields["Donanım"].options if o.value == "Akıllı tahta")
    assert values == {fields["Kapasite"].id: "58", fields["Donanım"].id: str(smart_board.id), fields["Engelli erişimi"].id: "1"}

    # ACL: room + room group, user + department contexts; an entry on a missing room is skipped
    acls = list((await session.execute(select(RoomAcl).order_by(RoomAcl.id))).scalars())
    assert [(a.entity_type, a.context_type, sorted(p.name for p in a.permissions)) for a in acls] == [
        ("room", "user", ["book_single.cancel_other_booking"]),
        ("room_group", "department", ["book_single.create", "room.view"]),
    ]
    assert acls[0].entity_id == conf.id and acls[0].context_id == ayse.id and acls[1].context_id == psy.id

    # calendar: schedule + periods on the grid, session settings + schedules, timetable weeks + dates, holidays
    sched = await _one(session, BookingSchedule, BookingSchedule.name == "Periods")
    periods = {p.name: p for p in (await session.execute(select(BookingPeriod))).scalars()}
    assert set(periods) == {"P1", "P2", "Öğleden sonra"}
    assert (periods["Öğleden sonra"].start_period, periods["Öğleden sonra"].end_period) == (7, 9)
    assert periods["P1"].days == [1, 2, 3, 4, 5] and periods["P1"].schedule_id == sched.id
    term = await _one(session, Term, Term.code == "CRBS-2025-2026")
    assert term.is_active and term.legacy_crbs_session_id == 1 and term.start_date == date(2025, 9, 1)
    tbs = await session.get(TermBookingSettings, term.id)
    assert tbs.is_selectable and tbs.default_schedule_id == sched.id
    ts = list((await session.execute(select(TermSchedule).where(TermSchedule.term_id == term.id))).scalars())
    assert {t.room_group_id for t in ts} == {groups["All"].id, groups["B Blok"].id}
    weeks = {w.name: w for w in (await session.execute(select(TimetableWeek))).scalars()}
    assert set(weeks) == {"Timetable", "B Haftası"} and weeks["B Haftası"].bgcol == "FFD966"
    tdates = {d.date: d.timetable_week_id for d in (await session.execute(select(TermDate))).scalars()}
    assert len(tdates) == 7 and tdates[date(2025, 9, 9)] == weeks["B Haftası"].id
    hol = await _one(session, Holiday, Holiday.term_id == term.id)
    assert hol.name == "Yarıyıl tatili" and (hol.date_start, hol.date_end) == (date(2026, 1, 26), date(2026, 2, 1))
    holiday_weeks = (await session.execute(select(Week).where(Week.term_id == term.id, Week.kind == "HOLIDAY"))).scalars().all()
    assert len(holiday_weeks) == 1

    # bookings + series + slots; cancelled history kept, without slots
    series = await _one(session, BookingSeries, BookingSeries.legacy_crbs_id == 1)
    assert series.weekday == 2 and series.timetable_week_id == weeks["Timetable"].id and series.user_id == ayse.id
    instances = list((await session.execute(select(Booking).where(Booking.series_id == series.id).order_by(Booking.date))).scalars())
    assert [b.date for b in instances] == [date(2025, 9, 2), date(2025, 9, 16), date(2025, 9, 23)]
    b1 = await _one(session, Booking, Booking.legacy_crbs_id == 1)
    assert b1.status == "BOOKED" and b1.notes == "PSİ 101 telafi" and b1.department_id == psy.id
    assert (b1.start_period, b1.end_period) == (1, 1) and b1.created_by == ayse.id and b1.term_id == term.id
    b2 = await _one(session, Booking, Booking.legacy_crbs_id == 2)
    assert (b2.start_period, b2.end_period) == (7, 9)
    slots = list((await session.execute(select(BookingSlot).where(BookingSlot.booking_id == b2.id))).scalars())
    assert sorted(s.period for s in slots) == [7, 8, 9]
    b3 = await _one(session, Booking, Booking.legacy_crbs_id == 3)
    assert b3.status == "CANCELLED" and b3.cancel_reason == "Toplantı ertelendi" and b3.cancelled_by == admin.id
    assert (await session.execute(select(func.count()).select_from(BookingSlot).where(BookingSlot.booking_id == b3.id))).scalar_one() == 0

    # idempotent re-import: nothing new, everything matched by its CRBS id
    counts = {
        m.__name__: (await session.execute(select(func.count()).select_from(m))).scalar_one()
        for m in (User, Role, RoomGroup, RoomAcl, BookingSchedule, BookingPeriod, TimetableWeek, Holiday, Booking, BookingSeries, BookingSlot, TermDate, RoomCustomField, RoomCustomFieldValue)
    }
    rep2 = await import_crbs(session, _source(), filename="crbs-seed")
    assert rep2.created["bookings"] == 0 and rep2.created["users"] == 0 and rep2.updated["bookings"] == 6
    again = {
        m.__name__: (await session.execute(select(func.count()).select_from(m))).scalar_one()
        for m in (User, Role, RoomGroup, RoomAcl, BookingSchedule, BookingPeriod, TimetableWeek, Holiday, Booking, BookingSeries, BookingSlot, TermDate, RoomCustomField, RoomCustomFieldValue)
    }
    assert again == counts


async def test_imported_users_log_in_with_their_crbs_passwords(client):
    async with dbmod.get_session_factory()() as s:
        await import_crbs(s, _source(), filename="crbs-seed")
    # $2y$ bcrypt (password_hash) by username; Turkish characters in the password
    r = await client.post("/api/v1/auth/login", json={"username": "ADMIN", "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "yanlış"})
    assert r.status_code == 401
    # sha1: + bcrypt(sha1(password)); a forced password change is carried over
    r = await client.post("/api/v1/auth/login", json={"username": "ayse.yilmaz", "password": TEACHER_PW})
    assert r.status_code == 200 and r.json()["password_change_required"] is True
    async with dbmod.get_session_factory()() as s:
        hashes = {
            u.username: u.password_hash
            for u in (await s.execute(select(User).where(User.username.in_(["admin", "ayse.yilmaz"])))).scalars()
        }
    assert all(h.startswith("$argon2") for h in hashes.values())  # rehashed on the first good login
    h = await login(client, "fatih@example.com", ADMIN_PW)  # e-mail login with the new hash
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    assert me["username"] == "admin" and "setup.users" in me["permissions"]
    # a disabled CRBS account stays disabled
    r = await client.post("/api/v1/auth/login", json={"username": "sekreter", "password": "x"})
    assert r.status_code in (401, 403)


async def test_import_crbs_from_paths(session):
    rep = await import_crbs(session, [STRUCTURE, DATA])
    assert rep.extra["rooms"] == 0 and rep.created.get("terms", 0) == 0
    # data.sql's roles, group, schedule and week arrive even without a session
    assert (await session.execute(select(func.count()).select_from(RoomGroup))).scalar_one() == 1
    assert (await _one(session, TimetableWeek, TimetableWeek.name == "Timetable")).bgcol == "71AAE3"
