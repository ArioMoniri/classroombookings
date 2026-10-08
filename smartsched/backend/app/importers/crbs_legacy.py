"""Importer for the legacy CRBS (classroombookings) MySQL database.

Source can be a live MySQL DSN (``mysql://user:pass@host/db``, needs the optional ``pymysql`` package) or
one or more SQL dump files (``structure.sql`` + ``data.sql`` or a ``mysqldump`` output) which are loaded
into an in-memory SQLite database through a tiny MySQL->SQLite DDL adapter, so tests need no MySQL.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import clean_email, fold_username
from app.importers import normalize as n
from app.importers.catalog import Catalog
from app.importers.report import ImportReport
from app.models import (
    Block,
    Booking,
    BookingPeriod,
    BookingSchedule,
    BookingSeries,
    BookingSlot,
    Holiday,
    Permission,
    Program,
    Role,
    RoomAcl,
    RoomCustomField,
    RoomCustomFieldOption,
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
from app.models.base import utcnow
from app.models.booking import BOOKED, CANCELLED
from app.models.catalog import Room
from app.services.bookings_perms import LIMIT_KEYS, ensure_permissions_and_roles, set_user_role

# ---------------------------------------------------------------------------
# MySQL dump -> SQLite
# ---------------------------------------------------------------------------


def split_sql_statements(sql: str) -> Iterator[str]:
    """Split on ';' outside quotes/comments (good enough for mysqldump / Adminer output)."""
    buf: list[str] = []
    quote: str | None = None
    i = 0
    length = len(sql)
    while i < length:
        ch = sql[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < length:
                buf.append(sql[i + 1])
                i += 2
                continue
            if ch == quote:
                if i + 1 < length and sql[i + 1] == quote:  # doubled quote escape
                    buf.append(quote)
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif ch == "-" and sql.startswith("--", i):
            end = sql.find("\n", i)
            i = length if end == -1 else end
            continue
        elif ch == "/" and sql.startswith("/*", i):
            end = sql.find("*/", i)
            i = length if end == -1 else end + 2
            continue
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                yield stmt
            buf = []
        else:
            buf.append(ch)
        i += 1
    stmt = "".join(buf).strip()
    if stmt:
        yield stmt


_TYPE_MAP = [
    (re.compile(r"\b(tiny|small|medium|big)?int(eger)?\b(\(\d+\))?\s*(unsigned)?", re.I), "INTEGER"),
    (re.compile(r"\bvarchar\(\d+\)", re.I), "TEXT"),
    (re.compile(r"\b(long|medium|tiny)?text\b", re.I), "TEXT"),
    (re.compile(r"\bchar\(\d+\)", re.I), "TEXT"),
    (re.compile(r"\bdatetime\b", re.I), "TEXT"),
    (re.compile(r"\btimestamp\b", re.I), "TEXT"),
    (re.compile(r"\bdate\b", re.I), "TEXT"),
    (re.compile(r"\btime\b", re.I), "TEXT"),
    (re.compile(r"\benum\([^)]*\)", re.I), "TEXT"),
    (re.compile(r"\bdecimal\(\d+,\s*\d+\)", re.I), "REAL"),
    (re.compile(r"\b(double|float)\b", re.I), "REAL"),
]


def mysql_create_to_sqlite(stmt: str) -> str:
    stmt = stmt.replace("`", '"')
    head, _, body = stmt.partition("(")
    body = body.rsplit(")", 1)[0]
    lines = [ln.strip().rstrip(",") for ln in body.split("\n") if ln.strip()]
    kept: list[str] = []
    for ln in lines:
        up = ln.upper()
        if up.startswith(("KEY ", "UNIQUE KEY ", "CONSTRAINT ", "INDEX ", "FULLTEXT ", "SPATIAL ")):
            if up.startswith("UNIQUE KEY "):
                cols = ln[ln.index("(") :]
                kept.append(f"UNIQUE {cols}")
            continue
        ln = re.sub(r"\s+CHARACTER SET \w+", "", ln, flags=re.I)
        ln = re.sub(r"\s+COLLATE \w+", "", ln, flags=re.I)
        ln = re.sub(r"\s+AUTO_INCREMENT", "", ln, flags=re.I)
        ln = re.sub(r"\s+ON UPDATE CURRENT_TIMESTAMP", "", ln, flags=re.I)
        if not up.startswith("PRIMARY KEY"):
            name, _, rest = ln.partition(" ")  # column name first, then its type/qualifiers
            for rx, repl in _TYPE_MAP:
                rest = rx.sub(repl, rest, count=1)
            ln = f"{name} {rest}"
        kept.append(ln)
    head = re.sub(r"CREATE TABLE(?: IF NOT EXISTS)?", "CREATE TABLE IF NOT EXISTS", head.strip(), flags=re.I)
    return f"{head} (\n  " + ",\n  ".join(kept) + "\n)"


_SKIP_PREFIXES = (
    "SET ",
    "LOCK ",
    "UNLOCK ",
    "USE ",
    "DROP ",
    "START TRANSACTION",
    "COMMIT",
    "SELECT ",
    "ALTER ",
    "DELIMITER",
)


def load_dump_into_sqlite(
    paths: Iterable[str | Path], conn: sqlite3.Connection | None = None
) -> tuple[sqlite3.Connection, list[str]]:
    """Execute MySQL dump files against SQLite. Returns (connection, warnings about skipped statements)."""
    conn = conn or sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    warnings: list[str] = []
    for path in paths:
        sql = Path(path).read_text(encoding="utf-8")
        for stmt in split_sql_statements(sql):
            up = stmt.lstrip().upper()
            if up.startswith(_SKIP_PREFIXES):
                continue
            try:
                if up.startswith("CREATE TABLE"):
                    conn.execute(mysql_create_to_sqlite(stmt))
                elif up.startswith("INSERT") or up.startswith("REPLACE"):
                    if re.match(r"INSERT\s+INTO\s+\S+\s+SET\s", stmt, re.I) or re.search(r"\bSELECT\b", stmt, re.I):
                        warnings.append(f"skipped unsupported statement: {stmt[:60]!r}")
                        continue
                    s = stmt.replace("`", '"')
                    s = re.sub(r"^REPLACE", "INSERT OR REPLACE", s, flags=re.I)
                    s = re.sub(r"^INSERT\s+IGNORE", "INSERT OR IGNORE", s, flags=re.I)
                    conn.execute(s)
                else:
                    warnings.append(f"skipped statement: {stmt[:60]!r}")
            except sqlite3.Error as exc:
                warnings.append(f"{Path(path).name}: {exc}: {stmt[:80]!r}")
    conn.commit()
    return conn, warnings


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


class CrbsSource(Protocol):
    def rows(self, table: str) -> list[dict[str, Any]]: ...

    def has_table(self, table: str) -> bool: ...


class SqliteSource:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def has_table(self, table: str) -> bool:
        cur = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        return cur.fetchone() is not None

    def rows(self, table: str) -> list[dict[str, Any]]:
        if not self.has_table(table):
            return []
        return [dict(r) for r in self.conn.execute(f'SELECT * FROM "{table}"')]


class MysqlSource:
    def __init__(self, dsn: str):
        try:
            import pymysql
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install pymysql to import from a live CRBS MySQL server") from exc
        u = urlparse(dsn)
        self.conn = pymysql.connect(
            host=u.hostname or "localhost",
            port=u.port or 3306,
            user=unquote(u.username or ""),
            password=unquote(u.password or ""),
            database=u.path.lstrip("/"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    def has_table(self, table: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (table,))
            return cur.fetchone() is not None

    def rows(self, table: str) -> list[dict[str, Any]]:
        if not self.has_table(table):
            return []
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT * FROM `{table}`")
            return list(cur.fetchall())


def open_source(dsn_or_paths: str | Iterable[str | Path]) -> tuple[CrbsSource, list[str]]:
    if isinstance(dsn_or_paths, str) and dsn_or_paths.startswith("mysql"):
        return MysqlSource(dsn_or_paths), []
    paths = [dsn_or_paths] if isinstance(dsn_or_paths, str | Path) else list(dsn_or_paths)
    conn, warnings = load_dump_into_sqlite(paths)
    return SqliteSource(conn), warnings


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _as_time(v: Any) -> time | None:
    if v is None:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, timedelta):
        return (datetime.min + v).time()
    try:
        return time.fromisoformat(str(v)[:8])
    except ValueError:
        return n.parse_time(v)


def _fields(**kw: Any) -> dict[str, Any]:
    return dict(kw)


def term_code_for_session(name: str, session_id: int) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "-", n.tr_upper(name)).strip("-")
    return f"CRBS-{slug or session_id}"


@dataclass
class _PeriodMap:
    by_id: dict[int, tuple[int, int]]  # period_id -> (start_period, end_period) on the 18-grid


def _map_periods(periods: list[dict[str, Any]], report: ImportReport) -> _PeriodMap:
    out: dict[int, tuple[int, int]] = {}
    for p in periods:
        ts, te = _as_time(p.get("time_start")), _as_time(p.get("time_end"))
        if ts is None or te is None:
            report.warn(f"period {p.get('period_id')} has no times")
            continue
        rng = n.time_range_to_periods(ts, te)
        if rng.start_period is None:
            report.warn(f"period {p.get('name')} {ts}-{te} outside the grid")
            continue
        out[int(p["period_id"])] = (rng.start_period, rng.end_period or rng.start_period)
    return _PeriodMap(out)


# ---------------------------------------------------------------------------
# Import (CRBS 2.x schema -> SmartSched CRBS-parity tables, docs/CRBS_PARITY.md §3)
# ---------------------------------------------------------------------------

#: CRBS ``Bookings_model::STATUS_BOOKED`` / ``STATUS_CANCELLED``
CRBS_BOOKED = 10
#: CRBS field types (``roomfields.type``) -> ``room_custom_fields.type``
FIELD_TYPES = {"text": "TEXT", "checkbox": "CHECKBOX", "select": "SELECT"}
#: the stored hash formats a CRBS installation can hold (``Auth_local::verify``); anything else is dropped
_HASH_PREFIXES = ("$2y$", "$2a$", "$2b$", "sha1:", "$argon2")


def _as_datetime(v: Any) -> datetime | None:
    if v in (None, "", "0000-00-00 00:00:00"):
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("T", " ")[:19])
    except ValueError:
        return None


def _int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _hex(v: Any) -> str | None:
    text = (n.clean_text(v) or "").lstrip("#").upper()
    return text if len(text) == 6 and all(c in "0123456789ABCDEF" for c in text) else None


class _Importer:
    """One run of :func:`import_crbs`. Every CRBS row is matched by its CRBS id first (``legacy_crbs_*``
    columns), so a second import updates the rows the first one created."""

    def __init__(self, session: AsyncSession, src: CrbsSource, report: ImportReport) -> None:
        self.s = session
        self.src = src
        self.r = report
        self.cat = Catalog(session, report)
        self.perm_names: dict[int, str] = {}
        self.perms: dict[str, Permission] = {}
        self.roles: dict[int, Role] = {}
        self.groups: dict[int, RoomGroup] = {}
        self.rooms: dict[int, Room] = {}
        self.depts: dict[int, Program] = {}
        self.users: dict[int, User] = {}
        self.schedules: dict[int, BookingSchedule] = {}
        self.periods: dict[int, BookingPeriod] = {}
        self.weeks: dict[int, TimetableWeek] = {}
        self.terms: dict[int, Term] = {}
        self.series: dict[int, BookingSeries] = {}

    async def _by_legacy(self, model: Any, legacy_id: int) -> Any:
        return (await self.s.execute(select(model).where(model.legacy_crbs_id == legacy_id))).scalars().first()

    def _count(self, created: bool, key: str) -> None:
        (self.r.created if created else self.r.updated)[key] += 1

    # --- roles and permissions ---------------------------------------------------------------------

    async def roles_and_permissions(self) -> None:
        await ensure_permissions_and_roles(self.s)
        self.perms = {p.name: p for p in (await self.s.execute(select(Permission))).scalars()}
        self.perm_names = {int(p["permission_id"]): str(p["name"]) for p in self.src.rows("auth_permissions")}
        granted: dict[int, set[str]] = {}
        for rp in self.src.rows("auth_roles_permissions"):
            name = self.perm_names.get(int(rp["permission_id"]))
            if name in self.perms:
                granted.setdefault(int(rp["role_id"]), set()).add(name)
        by_name = {n.tr_casefold(r.name): r for r in (await self.s.execute(select(Role))).scalars()}
        for row in self.src.rows("auth_roles"):
            rid = int(row["role_id"])
            name = (n.clean_text(row.get("name")) or f"CRBS role {rid}")[:100]
            role = await self._by_legacy(Role, rid) or by_name.get(n.tr_casefold(name))
            created = role is None
            if role is None:
                role = Role(name=name)
                self.s.add(role)
                by_name[n.tr_casefold(name)] = role
            role.legacy_crbs_id = rid
            role.description = n.clean_text(row.get("description"))
            for key in LIMIT_KEYS:
                setattr(role, key, _int(row.get(key)))
            if role.code != "ADMIN":  # Administrator always holds everything (lock-out guard)
                keep = (
                    {p.name for p in (role.permissions or []) if p.name.startswith("planning.")} if role.code else set()
                )
                role.permissions = [self.perms[x] for x in sorted(granted.get(rid, set()) | keep)]
            self.roles[rid] = role
            self._count(created, "roles")
        await self.s.flush()

    # --- rooms, groups, custom fields ----------------------------------------------------------------

    async def room_groups(self) -> None:
        by_name = {g.name: g for g in (await self.s.execute(select(RoomGroup))).scalars()}
        for row in self.src.rows("room_groups"):
            gid = int(row["room_group_id"])
            name = (n.clean_text(row.get("name")) or f"Grup {gid}")[:32]
            g = await self._by_legacy(RoomGroup, gid) or by_name.get(name)
            created = g is None
            if g is None:
                g = RoomGroup(name=name)
                self.s.add(g)
            g.legacy_crbs_id = gid
            g.name, g.description, g.pos = name, n.clean_text(row.get("description")), _int(row.get("pos")) or 0
            self.groups[gid] = g
            self._count(created, "room_groups")
        await self.s.flush()

    async def rooms_and_fields(self) -> None:
        fields = {int(f["field_id"]): f for f in self.src.rows("roomfields")}
        options = {int(o["option_id"]): o for o in self.src.rows("roomoptions")}
        # parity tables: room_custom_fields (+ options)
        field_rows: dict[int, RoomCustomField] = {}
        option_ids: dict[int, int] = {}
        by_name = {f.name: f for f in (await self.s.execute(select(RoomCustomField))).scalars()}
        for fid, f in fields.items():
            name = (n.clean_text(f.get("name")) or f"Alan {fid}")[:64]
            ftype = FIELD_TYPES.get(str(f.get("type") or "text").lower(), "TEXT")
            row = await self._by_legacy(RoomCustomField, fid) or by_name.get(name)
            created = row is None
            if row is None:
                row = RoomCustomField(name=name, type=ftype, options=[])
                self.s.add(row)
            row.legacy_crbs_id, row.name, row.type = fid, name, ftype
            await self.s.flush()
            have = {o.value: o for o in row.options}
            for _oid, o in sorted(options.items()):
                if int(o["field_id"]) != fid:
                    continue
                value = (n.clean_text(o.get("value")) or "")[:64]
                opt = have.get(value)
                if opt is None:
                    opt = RoomCustomFieldOption(value=value, pos=len(row.options))
                    row.options.append(opt)
                    have[value] = opt
            await self.s.flush()
            for oid, o in options.items():
                if int(o["field_id"]) == fid:
                    value = (n.clean_text(o.get("value")) or "")[:64]
                    option_ids[oid] = have[value].id
            field_rows[fid] = row
            self._count(created, "room_fields")
        # legacy mirror by name (rooms.custom_fields) and capacity from a "Kapasite" field
        values_by_room: dict[int, dict[int, Any]] = {}
        for v in self.src.rows("roomvalues"):
            if int(v["field_id"]) in fields:
                values_by_room.setdefault(int(v["room_id"]), {})[int(v["field_id"])] = v.get("value")
        existing = {
            r.legacy_crbs_room_id: r
            for r in (await self.s.execute(select(Room).where(Room.legacy_crbs_room_id.is_not(None)))).scalars()
        }
        for row in self.src.rows("rooms"):
            rid = int(row["room_id"])
            name = n.clean_text(row.get("name")) or f"ROOM {rid}"
            codes = n.parse_room_codes(name)
            code = codes[0] if codes else re.sub(r"[^A-Z0-9]+", "-", n.tr_upper(name)).strip("-")[:32]
            raw = values_by_room.get(rid, {})
            mirror: dict[str, Any] = {}
            capacity = None
            for fid, val in raw.items():
                f = fields[fid]
                fname = str(f["name"])
                shown = val
                if str(f.get("type")).lower() == "select" and val is not None and str(val).isdigit():
                    shown = (options.get(int(val)) or {}).get("value", val)
                if shown is not None:
                    mirror[fname] = shown
                if "kapasite" in n.tr_casefold(fname) or "capacity" in fname.lower():
                    capacity = n.parse_int_loose(val)
            room = existing.get(rid)
            if room is None:
                room = await self.cat.room(
                    code, display_name=name, capacity=capacity, notes=n.clean_text(row.get("notes"))
                )
                assert room is not None
                if room.legacy_crbs_room_id is None:
                    room.legacy_crbs_room_id = rid
            else:
                room.display_name = name
                if capacity:
                    room.capacity = capacity
                self.r.updated["rooms"] += 1
            gid = _int(row.get("room_group_id"))
            group = self.groups.get(gid) if gid is not None else None
            room.room_group_id = group.id if group else None
            room.room_group = group.name if group else None
            room.is_bookable = bool(_int(row.get("bookable")) or 0)
            room.location = (n.clean_text(row.get("location")) or None) and str(n.clean_text(row.get("location")))[:64]
            room.icon = n.clean_text(row.get("icon"))
            if row.get("notes") is not None:
                room.notes = n.clean_text(row.get("notes"))
            if row.get("photo"):
                photo = str(row["photo"])
                room.photo_url = photo if photo.startswith(("http", "/")) else f"uploads/{photo}"
            room.custom_fields = {**(room.custom_fields or {}), **mirror}
            room.pos = _int(row.get("pos")) or 0
            self.rooms[rid] = room
        await self.s.flush()
        # parity values: TEXT text, CHECKBOX "1"/"0", SELECT the new option id
        for crbs_room, vals in values_by_room.items():
            room = self.rooms.get(crbs_room)
            if room is None:
                continue
            have_vals = {
                v.field_id: v
                for v in (
                    await self.s.execute(select(RoomCustomFieldValue).where(RoomCustomFieldValue.room_id == room.id))
                ).scalars()
            }
            for fid, val in vals.items():
                frow = field_rows.get(fid)
                if frow is None:
                    continue
                stored: str | None
                if frow.type == "SELECT":
                    stored = str(option_ids[int(val)]) if val is not None and _int(val) in option_ids else None
                elif frow.type == "CHECKBOX":
                    stored = "1" if str(val).strip() in ("1", "true", "on", "yes") else "0"
                else:
                    stored = n.clean_text(val)
                cur = have_vals.get(frow.id)
                if cur is None:
                    self.s.add(RoomCustomFieldValue(room_id=room.id, field_id=frow.id, value=stored))
                else:
                    cur.value = stored
        self.r.extra["rooms"] = len(self.rooms)
        await self.s.flush()

    # --- calendar: schedules, periods, timetable weeks, sessions, dates, holidays ---------------------

    async def schedules_and_periods(self) -> None:
        for row in self.src.rows("schedules"):
            sid = int(row["schedule_id"])
            name = (n.clean_text(row.get("name")) or f"Schedule {sid}")[:32]
            sched = await self._by_legacy(BookingSchedule, sid)
            created = sched is None
            if sched is None:
                sched = BookingSchedule(name=name)
                self.s.add(sched)
            sched.legacy_crbs_id, sched.name = sid, name
            sched.description = n.clean_text(row.get("description"))
            sched.type = str(row.get("type") or "periods")[:20]
            self.schedules[sid] = sched
            self._count(created, "schedules")
        await self.s.flush()
        for row in self.src.rows("periods"):
            pid = int(row["period_id"])
            sched = self.schedules.get(int(row["schedule_id"]))
            ts, te = _as_time(row.get("time_start")), _as_time(row.get("time_end"))
            name = (n.clean_text(row.get("name")) or f"P{pid}")[:30]
            rng = n.time_range_to_periods(ts, te) if ts and te else None
            if sched is None or ts is None or te is None or rng is None or rng.start_period is None:
                self.r.warn(f"period {name} ({ts}-{te}) is outside the 08:30-22:50 grid; its bookings are skipped")
                continue
            per = await self._by_legacy(BookingPeriod, pid)
            created = per is None
            if per is None:
                per = BookingPeriod(
                    schedule_id=sched.id, name=name, time_start=ts, time_end=te, start_period=1, end_period=1
                )
                self.s.add(per)
            per.legacy_crbs_id, per.schedule_id, per.name = pid, sched.id, name
            per.time_start, per.time_end = ts, te
            per.start_period, per.end_period = rng.start_period, rng.end_period or rng.start_period
            per.bookable = bool(_int(row.get("bookable")) or 0)
            per.days = [d for d in range(1, 8) if _int(row.get(f"day_{d}"))]
            self.periods[pid] = per
            self._count(created, "periods")
        await self.s.flush()

    async def timetable_weeks(self) -> None:
        for row in self.src.rows("weeks"):
            wid = int(row["week_id"])
            w = await self._by_legacy(TimetableWeek, wid)
            created = w is None
            name = (n.clean_text(row.get("name")) or f"Week {wid}")[:20]
            if w is None:
                w = TimetableWeek(name=name, bgcol="FFFFFF")
                self.s.add(w)
            w.legacy_crbs_id, w.name = wid, name
            w.bgcol = _hex(row.get("bgcol")) or w.bgcol or "FFFFFF"
            w.icon = n.clean_text(row.get("icon"))
            self.weeks[wid] = w
            self._count(created, "timetable_weeks")
        await self.s.flush()

    async def sessions(self) -> None:
        periods_json: dict[int, list[dict[str, Any]]] = {}
        for p in self.src.rows("periods"):
            periods_json.setdefault(int(p["schedule_id"]), []).append(
                {
                    "legacy_period_id": int(p["period_id"]),
                    "name": p.get("name"),
                    "start": str(_as_time(p.get("time_start")) or ""),
                    "end": str(_as_time(p.get("time_end")) or ""),
                    "bookable": bool(p.get("bookable", 0)),
                    "days": [d for d in range(1, 8) if p.get(f"day_{d}")],
                }
            )
        crbs_schedules = {int(x["schedule_id"]): x for x in self.src.rows("schedules")}
        holidays = self.src.rows("holidays")
        for row in self.src.rows("sessions"):
            sid = int(row["session_id"])
            code = term_code_for_session(str(row.get("name") or sid), sid)
            start, end = _as_date(row.get("date_start")), _as_date(row.get("date_end"))
            term = (await self.s.execute(select(Term).where(Term.legacy_crbs_session_id == sid))).scalars().first()
            term = term or (await self.s.execute(select(Term).where(Term.code == code))).scalar_one_or_none()
            created = term is None
            if term is None:
                term = Term(code=code, name=str(row.get("name") or code), kind="REGULAR")
                self.s.add(term)
            term.start_date, term.end_date = start, end
            term.is_active = bool(_int(row.get("is_current")) or 0)
            term.legacy_crbs_session_id = sid
            default_sid = _int(row.get("default_schedule_id"))
            if default_sid is not None and default_sid in periods_json:
                term.periods_json = [
                    {"schedule": crbs_schedules[default_sid]["name"], "periods": periods_json[default_sid]}
                ]
            await self.s.flush()
            self._count(created, "terms")
            self.terms[sid] = term
            settings = await self.s.get(TermBookingSettings, term.id)
            if settings is None:
                settings = TermBookingSettings(term_id=term.id)
                self.s.add(settings)
            settings.is_selectable = bool(_int(row.get("is_selectable")) or 0)
            sched = self.schedules.get(default_sid) if default_sid is not None else None
            settings.default_schedule_id = sched.id if sched else None
            if start and end:
                await self._calendar_weeks(term, sid, start, end, holidays)
        await self.s.flush()
        for row in self.src.rows("session_schedules"):
            term = self.terms.get(int(row["session_id"]))
            group = self.groups.get(int(row["room_group_id"]))
            sched = self.schedules.get(int(row["schedule_id"]))
            if term is None or group is None or sched is None:
                continue
            ts = await self.s.get(TermSchedule, (term.id, group.id))
            if ts is None:
                self.s.add(TermSchedule(term_id=term.id, room_group_id=group.id, schedule_id=sched.id))
            else:
                ts.schedule_id = sched.id
        await self.s.flush()

    async def _calendar_weeks(
        self, term: Term, sid: int, start: date, end: date, holidays: list[dict[str, Any]]
    ) -> None:
        """SmartSched calendar weeks of the term (week index for the solver); whole holiday weeks marked."""
        monday = start - timedelta(days=start.weekday())
        existing = {w.index: w for w in (await self.s.execute(select(Week).where(Week.term_id == term.id))).scalars()}
        idx = 0
        while monday <= end:
            idx += 1
            wk_end = monday + timedelta(days=6)
            kind, label = "LECTURE", None
            for h in holidays:
                if _int(h.get("session_id")) not in (None, sid):
                    continue
                hs, he = _as_date(h.get("date_start")), _as_date(h.get("date_end"))
                if hs and he and hs <= monday and he >= wk_end:
                    kind, label = "HOLIDAY", str(h.get("name"))
                    break
                if hs and he and hs <= wk_end and he >= monday:
                    label = f"holiday: {h.get('name')}"
            w = existing.get(idx)
            if w is None:
                self.s.add(Week(term_id=term.id, index=idx, start_date=monday, kind=kind, label=label))
                self.r.created["weeks"] += 1
            else:
                w.start_date, w.kind, w.label = monday, kind, label
            monday += timedelta(days=7)
        term.week_count = idx

    async def dates_and_holidays(self) -> None:
        for row in self.src.rows("dates"):
            term = self.terms.get(_int(row.get("session_id")) or -1)
            d = _as_date(row.get("date"))
            if term is None or d is None:
                continue
            week = self.weeks.get(_int(row.get("week_id")) or -1)
            td = await self.s.get(TermDate, (term.id, d))
            if td is None:
                self.s.add(TermDate(term_id=term.id, date=d, timetable_week_id=week.id if week else None))
                self.r.created["term_dates"] += 1
            else:
                td.timetable_week_id = week.id if week else None
        for row in self.src.rows("holidays"):
            hid = int(row["holiday_id"])
            term = self.terms.get(_int(row.get("session_id")) or -1)
            hs, he = _as_date(row.get("date_start")), _as_date(row.get("date_end"))
            if term is None or hs is None or he is None:
                self.r.skip(hid, "holiday without session or dates")
                continue
            h = await self._by_legacy(Holiday, hid)
            created = h is None
            if h is None:
                h = Holiday(term_id=term.id, name="", date_start=hs, date_end=he)
                self.s.add(h)
            h.legacy_crbs_id, h.term_id = hid, term.id
            h.name = (n.clean_text(row.get("name")) or "Tatil")[:50]
            h.date_start, h.date_end = hs, he
            self._count(created, "holidays")
        await self.s.flush()

    # --- departments, users, constraints, owners, ACL --------------------------------------------------

    async def departments(self) -> None:
        for row in self.src.rows("departments"):
            prog = await self.cat.program(row.get("name"))
            if prog is None:
                continue
            prog.legacy_crbs_department_id = int(row["department_id"])
            if row.get("description") is not None:
                prog.description = n.clean_text(row.get("description"))
            if row.get("icon") is not None:
                prog.icon = n.clean_text(row.get("icon"))
            self.depts[int(row["department_id"])] = prog
        await self.s.flush()

    async def import_users(self) -> None:
        for row in self.src.rows("users"):
            uid = int(row["user_id"])
            try:
                username = fold_username(str(row.get("username") or ""))
            except ValueError as exc:
                self.r.skip(uid, "invalid username", f"{row.get('username')!r}: {exc}")
                continue
            email: str | None = None
            if n.clean_text(row.get("email")):
                try:
                    email = clean_email(str(row["email"]))
                except ValueError:
                    self.r.warn(f"user {username}: invalid e-mail {row.get('email')!r} dropped")
            user = (await self.s.execute(select(User).where(User.legacy_crbs_user_id == uid))).scalars().first()
            user = user or (await self.s.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if user is None and email:
                user = (await self.s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            created = user is None
            if user is None:
                user = User(username=username)
                self.s.add(user)
            if email and email != user.email:
                clash = (
                    await self.s.execute(select(User.id).where(User.email == email, User.id != (user.id or 0)))
                ).scalar_one_or_none()
                if clash is not None:
                    self.r.warn(f"user {username}: e-mail {email} belongs to another user; not copied")
                    email = None
            user.username = username
            if email or created:
                user.email = email
            first, last = n.clean_text(row.get("firstname")), n.clean_text(row.get("lastname"))
            user.firstname, user.lastname = first, last
            user.full_name = n.clean_text(row.get("displayname")) or " ".join(x for x in (first, last) if x) or username
            user.ext = n.clean_text(row.get("ext"))
            user.is_active = bool(_int(row.get("enabled")) if row.get("enabled") is not None else 1)
            user.force_password_reset = bool(_int(row.get("force_password_reset")) or 0)
            user.last_login_at = _as_datetime(row.get("lastlogin")) or user.last_login_at
            user.legacy_crbs_user_id = uid
            dept = self.depts.get(_int(row.get("department_id")) or -1)
            user.department_id = dept.id if dept else None
            role = self.roles.get(_int(row.get("role_id")) or -1)
            set_user_role(user, role)
            pw = str(row.get("password") or "")
            if pw and not pw.startswith(_HASH_PREFIXES):
                self.r.warn(f"user {username}: unknown password hash format; the password must be reset")
                pw = ""
            if pw and not user.password_hash:  # never overwrite a password set or rehashed in SmartSched
                user.password_hash = pw
            self.users[uid] = user
            self._count(created, "users")
        await self.s.flush()
        for row in self.src.rows("users_constraints"):
            user = self.users.get(int(row["user_id"]))
            if user is None:
                continue
            uc = await self.s.get(UserConstraint, user.id)
            if uc is None:
                uc = UserConstraint(user_id=user.id)
                self.s.add(uc)
            for key in LIMIT_KEYS:
                kind = str(row.get(f"{key}_type") or "R").upper()
                setattr(uc, f"{key}_type", kind if kind in ("R", "U", "X") else "R")
                setattr(uc, f"{key}_value", _int(row.get(f"{key}_value")) if kind == "U" else None)
            self.r.updated["user_constraints"] += 1
        for row in self.src.rows("rooms"):
            room = self.rooms.get(int(row["room_id"]))
            owner = self.users.get(_int(row.get("user_id")) or -1)
            if room is not None:
                room.owner_user_id = owner.id if owner else None
        await self.s.flush()

    async def acl(self) -> None:
        perms: dict[int, list[str]] = {}
        for row in self.src.rows("auth_acl_permissions"):
            name = self.perm_names.get(int(row["permission_id"]))
            if name in self.perms:
                perms.setdefault(int(row["acl_id"]), []).append(name)
        for row in self.src.rows("auth_acl"):
            aid = int(row["acl_id"])
            etype, ctype = str(row.get("entity_type")), str(row.get("context_type"))
            entity: Any = (self.rooms if etype == "room" else self.groups if etype == "room_group" else {}).get(
                int(row["entity_id"])
            )
            ctx_map: dict[str, dict[int, Any]] = {"user": self.users, "role": self.roles, "department": self.depts}
            ctx: Any = ctx_map.get(ctype, {}).get(int(row["context_id"]))
            if entity is None or ctx is None:
                self.r.skip(aid, "ACL entry for a room, group, user, role or department that was not imported")
                continue
            acl = await self._by_legacy(RoomAcl, aid)
            created = acl is None
            if acl is None:
                acl = RoomAcl(entity_type=etype, entity_id=entity.id, context_type=ctype, context_id=ctx.id)
                self.s.add(acl)
            acl.legacy_crbs_id = aid
            acl.entity_type, acl.entity_id, acl.context_type, acl.context_id = etype, entity.id, ctype, ctx.id
            acl.permissions = [self.perms[x] for x in sorted(set(perms.get(aid, [])))]
            self._count(created, "acl")
        await self.s.flush()

    # --- bookings ----------------------------------------------------------------------------------------

    def _term_for(self, sid: Any, d: date | None) -> Term | None:
        if _int(sid) is not None and _int(sid) in self.terms:
            return self.terms[int(sid)]
        if d is not None:
            for t in self.terms.values():
                if t.start_date and t.end_date and t.start_date <= d <= t.end_date:
                    return t
        return None

    def _audit(self, obj: Any, row: dict[str, Any]) -> None:
        def uid(key: str) -> int | None:
            u = self.users.get(_int(row.get(key)) or -1)
            return u.id if u else None

        booked = (_int(row.get("status")) or CRBS_BOOKED) == CRBS_BOOKED and not row.get("cancelled_at")
        obj.status = BOOKED if booked else CANCELLED
        obj.notes = (n.clean_text(row.get("notes")) or None) and str(n.clean_text(row.get("notes")))[:255]
        obj.cancel_reason = n.clean_text(row.get("cancel_reason")) if not booked else None
        obj.cancelled_at = _as_datetime(row.get("cancelled_at")) if not booked else None
        obj.cancelled_by = uid("cancelled_by") if not booked else None
        obj.created_at = _as_datetime(row.get("created_at")) or obj.created_at or utcnow()
        obj.created_by = uid("created_by")
        obj.updated_at = _as_datetime(row.get("updated_at"))
        obj.updated_by = uid("updated_by")
        user = self.users.get(_int(row.get("user_id")) or -1)
        obj.user_id = user.id if user else None
        dept = self.depts.get(_int(row.get("department_id")) or -1)
        obj.department_id = dept.id if dept else None

    async def bookings(self) -> None:
        for row in self.src.rows("bookings_repeat"):
            rid = int(row["repeat_id"])
            room = self.rooms.get(int(row["room_id"]))
            period = self.periods.get(int(row["period_id"]))
            term = self._term_for(row.get("session_id"), None)
            if room is None or period is None or term is None:
                self.r.skip(rid, "recurring booking without an imported room, grid period or session")
                continue
            series = await self._by_legacy(BookingSeries, rid)
            created = series is None
            if series is None:
                series = BookingSeries(term_id=term.id, period_id=period.id, room_id=room.id, weekday=1)
                self.s.add(series)
            series.legacy_crbs_id = rid
            series.term_id, series.period_id, series.room_id = term.id, period.id, room.id
            week = self.weeks.get(_int(row.get("week_id")) or -1)
            series.timetable_week_id = week.id if week else None
            series.weekday = _int(row.get("weekday")) or 1
            self._audit(series, row)
            self.series[rid] = series
            self._count(created, "booking_series")
        await self.s.flush()
        occupied: dict[tuple[int, date, int], int] = {
            (s.room_id, s.date, s.period): s.booking_id for s in (await self.s.execute(select(BookingSlot))).scalars()
        }
        for row in self.src.rows("bookings"):
            bid = int(row["booking_id"])
            room = self.rooms.get(int(row["room_id"]))
            period = self.periods.get(int(row["period_id"]))
            d = _as_date(row.get("date"))
            term = self._term_for(row.get("session_id"), d)
            if room is None or period is None or d is None or term is None:
                self.r.skip(bid, "booking without an imported room, grid period, date or session")
                continue
            b = await self._by_legacy(Booking, bid)
            created = b is None
            if b is None:
                b = Booking(term_id=term.id, period_id=period.id, room_id=room.id, date=d, start_period=1, end_period=1)
                self.s.add(b)
            b.legacy_crbs_id = bid
            series = self.series.get(_int(row.get("repeat_id")) or -1)
            b.series_id = series.id if series else None
            b.term_id, b.period_id, b.room_id, b.date = term.id, period.id, room.id, d
            b.start_period, b.end_period = period.start_period, period.end_period
            self._audit(b, row)
            await self.s.flush()
            for slot in (await self.s.execute(select(BookingSlot).where(BookingSlot.booking_id == b.id))).scalars():
                occupied.pop((slot.room_id, slot.date, slot.period), None)
                await self.s.delete(slot)
            await self.s.flush()
            if b.status == BOOKED:
                keys = [(room.id, d, p) for p in range(b.start_period, b.end_period + 1)]
                clash = next((occupied[k] for k in keys if k in occupied and occupied[k] != b.id), None)
                if clash is not None:
                    self.r.warn(
                        f"booking {bid}: {room.display_name} {d:%d.%m.%Y} {period.name} overlaps booking #{clash}; "
                        "kept without slot rows (resolve it in GET /bookings/conflicts)"
                    )
                else:
                    for k in keys:
                        self.s.add(BookingSlot(booking_id=b.id, period=k[2], room_id=room.id, date=d))
                        occupied[k] = b.id
            self._count(created, "bookings")
            self.r.rows_imported += 1
        await self.s.flush()
        # bookings were imported as solver blocks before (source CRBS): the bookings replace them
        for blk in (
            await self.s.execute(select(Block).where(Block.source == "CRBS", Block.archived.is_(False)))
        ).scalars():
            blk.archived = True
            self.r.updated["blocks_archived"] += 1


async def import_crbs(
    session: AsyncSession,
    source: CrbsSource | str | Iterable[str | Path],
    *,
    filename: str | None = None,
    include_bookings: bool = True,
) -> ImportReport:
    """Import a CRBS 2.x database into the CRBS-parity tables (audit B4). Users keep their usernames and
    password hashes (legacy ``$2y$`` / ``sha1:`` hashes are verified at login as CRBS does, then rehashed to
    argon2), roles keep their permissions and limits, bookings become bookings (not solver blocks)."""
    report = ImportReport(kind="crbs", filename=filename)
    if not hasattr(source, "rows"):
        source, warns = open_source(source)
        report.warnings.extend(warns)
    src: CrbsSource = source  # type: ignore[assignment]
    run = _Importer(session, src, report)
    await run.roles_and_permissions()
    await run.room_groups()
    await run.rooms_and_fields()
    await run.schedules_and_periods()
    await run.timetable_weeks()
    await run.sessions()
    await run.dates_and_holidays()
    await run.departments()
    await run.import_users()
    await run.acl()
    if include_bookings:
        await run.bookings()
    report.rows_total = report.rows_imported + report.rows_skipped_count
    report.extra.update(terms=len(run.terms), programs=len(run.depts))
    await session.commit()
    return report
