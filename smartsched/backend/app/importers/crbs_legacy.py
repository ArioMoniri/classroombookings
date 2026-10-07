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

from app.importers import normalize as n
from app.importers.catalog import Catalog
from app.importers.report import ImportReport
from app.models import Block, Program, Room, Term, User, Week

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
# Import
# ---------------------------------------------------------------------------


async def import_crbs(
    session: AsyncSession,
    source: CrbsSource | str | Iterable[str | Path],
    *,
    filename: str | None = None,
    include_bookings: bool = True,
) -> ImportReport:
    report = ImportReport(kind="crbs", filename=filename)
    if not hasattr(source, "rows"):
        source, warns = open_source(source)
        report.warnings.extend(warns)
    src: CrbsSource = source  # type: ignore[assignment]
    cat = Catalog(session, report)

    # --- rooms -------------------------------------------------------------
    groups = {int(g["room_group_id"]): g["name"] for g in src.rows("room_groups")}
    fields = {int(f["field_id"]): f for f in src.rows("roomfields")}
    options = {int(o["option_id"]): o["value"] for o in src.rows("roomoptions")}
    values_by_room: dict[int, dict[str, Any]] = {}
    for v in src.rows("roomvalues"):
        f = fields.get(int(v["field_id"]))
        if not f:
            continue
        val = v.get("value")
        if f.get("type") == "select" and val is not None and str(val).isdigit():
            val = options.get(int(val), val)
        values_by_room.setdefault(int(v["room_id"]), {})[str(f["name"])] = val
    room_by_legacy: dict[int, Room] = {}
    existing_legacy = {
        r.legacy_crbs_room_id: r
        for r in (await session.execute(select(Room).where(Room.legacy_crbs_room_id.is_not(None)))).scalars()
    }
    for r in src.rows("rooms"):
        rid = int(r["room_id"])
        name = n.clean_text(r.get("name")) or f"ROOM {rid}"
        codes = n.parse_room_codes(name)
        code = codes[0] if codes else re.sub(r"[^A-Z0-9]+", "-", n.tr_upper(name)).strip("-")[:32]
        custom = values_by_room.get(rid, {})
        capacity = None
        for key, val in custom.items():
            if "kapasite" in n.tr_casefold(key) or "capacity" in key.lower():
                capacity = n.parse_int_loose(val)
        room = existing_legacy.get(rid)
        if room is None:
            room = await cat.room(code, display_name=name, capacity=capacity, notes=n.clean_text(r.get("notes")))
            assert room is not None
            if room.legacy_crbs_room_id is None:
                room.legacy_crbs_room_id = rid
        else:
            room.display_name = name
            if capacity:
                room.capacity = capacity
            report.updated["rooms"] += 1
        room.room_group = groups.get(int(r["room_group_id"])) if r.get("room_group_id") is not None else room.room_group
        room.is_bookable = bool(r.get("bookable", 1))
        if r.get("photo"):
            room.photo_url = (
                f"uploads/{r['photo']}" if not str(r["photo"]).startswith(("http", "/")) else str(r["photo"])
            )
        room.custom_fields = {**(room.custom_fields or {}), **{k: v for k, v in custom.items() if v is not None}}
        if r.get("location") and not custom.get("location"):
            room.custom_fields = {**room.custom_fields, "location": r["location"]}
        room.pos = int(r.get("pos") or 0)
        room_by_legacy[rid] = room
    report.extra["rooms"] = len(room_by_legacy)

    # --- schedules / periods ------------------------------------------------
    periods = src.rows("periods")
    pmap = _map_periods(periods, report)
    schedules = {int(s["schedule_id"]): s for s in src.rows("schedules")}
    periods_json: dict[int, list[dict[str, Any]]] = {}
    for p in periods:
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

    # --- sessions -> terms, weeks, holidays ---------------------------------
    terms_by_session: dict[int, Term] = {}
    holidays = src.rows("holidays")
    for s in src.rows("sessions"):
        sid = int(s["session_id"])
        code = term_code_for_session(str(s.get("name") or sid), sid)
        start, end = _as_date(s.get("date_start")), _as_date(s.get("date_end"))
        term = (await session.execute(select(Term).where(Term.code == code))).scalar_one_or_none()
        if term is None:
            term = Term(code=code, name=str(s.get("name") or code), kind="REGULAR")
            session.add(term)
            report.created["terms"] += 1
        else:
            report.updated["terms"] += 1
        term.start_date, term.end_date = start, end
        term.is_active = bool(s.get("is_current", 0))
        term.legacy_crbs_session_id = sid
        sched_id = s.get("default_schedule_id")
        if sched_id is not None and int(sched_id) in periods_json:
            term.periods_json = [{"schedule": schedules[int(sched_id)]["name"], "periods": periods_json[int(sched_id)]}]
        await session.flush()
        terms_by_session[sid] = term
        if start and end:
            monday = start - timedelta(days=start.weekday())
            idx = 0
            existing_weeks = {
                w.index: w for w in (await session.execute(select(Week).where(Week.term_id == term.id))).scalars()
            }
            while monday <= end:
                idx += 1
                wk_end = monday + timedelta(days=6)
                kind = "LECTURE"
                label = None
                for h in holidays:
                    if h.get("session_id") not in (None, sid) and int(h.get("session_id") or 0) != sid:
                        continue
                    hs, he = _as_date(h.get("date_start")), _as_date(h.get("date_end"))
                    if hs and he and hs <= monday and he >= wk_end:
                        kind, label = "HOLIDAY", str(h.get("name"))
                        break
                    if hs and he and hs <= wk_end and he >= monday:
                        label = f"holiday: {h.get('name')}"
                w = existing_weeks.get(idx)
                if w is None:
                    session.add(Week(term_id=term.id, index=idx, start_date=monday, kind=kind, label=label))
                    report.created["weeks"] += 1
                else:
                    w.start_date, w.kind, w.label = monday, kind, label
                monday += timedelta(days=7)
            term.week_count = idx
    await session.flush()

    # --- departments -> programs --------------------------------------------
    prog_by_dept: dict[int, Program] = {}
    for dep in src.rows("departments"):
        prog = await cat.program(dep.get("name"))
        if prog is None:
            continue
        prog.legacy_crbs_department_id = int(dep["department_id"])
        prog_by_dept[int(dep["department_id"])] = prog

    # --- users -----------------------------------------------------------------
    roles = {int(r["role_id"]): str(r["name"]) for r in src.rows("auth_roles")}
    user_names: dict[int, str] = {}
    for u in src.rows("users"):
        uid = int(u["user_id"])
        email = n.clean_text(u.get("email")) or f"{u.get('username')}@crbs.local"
        display = (
            n.clean_text(u.get("displayname"))
            or " ".join(x for x in (n.clean_text(u.get("firstname")), n.clean_text(u.get("lastname"))) if x)
            or str(u.get("username"))
        )
        user_names[uid] = display
        role_name = roles.get(int(u["role_id"]) if u.get("role_id") is not None else -1, "")
        role = "ADMIN" if "admin" in role_name.lower() else "VIEWER"
        existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is None:
            session.add(
                User(
                    email=email,
                    full_name=display,
                    role=role,
                    is_active=bool(u.get("enabled", 1)),
                    legacy_crbs_user_id=uid,
                )
            )
            report.created["users"] += 1
        else:
            existing.full_name = display
            existing.legacy_crbs_user_id = uid
            report.updated["users"] += 1
    await session.flush()

    # --- bookings -> blocks ----------------------------------------------------
    if include_bookings:
        existing_blocks = {
            b.source_key: b for b in (await session.execute(select(Block).where(Block.source == "CRBS"))).scalars()
        }
        weekdates: dict[int, set[date]] = {}
        for wd in src.rows("weekdates"):
            wd_date = _as_date(wd.get("date"))
            if wd_date:
                weekdates.setdefault(int(wd["week_id"]), set()).add(wd_date)
        seen: set[str] = set()

        def _term_for_date(d: date | None, sid: Any) -> Term | None:
            if sid is not None and int(sid) in terms_by_session:
                return terms_by_session[int(sid)]
            if d:
                for t in terms_by_session.values():
                    if t.start_date and t.end_date and t.start_date <= d <= t.end_date:
                        return t
            return None

        def _week_index(term: Term, d: date) -> int | None:
            if not term.start_date:
                return None
            monday = term.start_date - timedelta(days=term.start_date.weekday())
            return (d - monday).days // 7 + 1

        def _label(b: dict[str, Any]) -> str:
            parts = [n.clean_text(b.get("notes"))]
            if b.get("department_id") is not None and int(b["department_id"]) in prog_by_dept:
                parts.append(prog_by_dept[int(b["department_id"])].name)
            if b.get("user_id") is not None:
                parts.append(user_names.get(int(b["user_id"])))
            return " / ".join(p for p in parts if p) or "CRBS booking"

        for b in src.rows("bookings"):
            if int(b.get("status", 10)) != 10 or b.get("cancelled_at"):
                continue
            room = room_by_legacy.get(int(b["room_id"]))
            pr = pmap.by_id.get(int(b["period_id"]))
            bdate = _as_date(b.get("date"))
            term = _term_for_date(bdate, b.get("session_id"))
            if room is None or pr is None or bdate is None or term is None:
                report.skip(int(b["booking_id"]), "booking without room/period/date/term")
                continue
            key = f"CRBS:booking:{b['booking_id']}"
            seen.add(key)
            wk = _week_index(term, bdate)
            fields_ = _fields(
                term_id=term.id,
                room_id=room.id,
                day=bdate.isoweekday(),
                date=bdate,
                start_period=pr[0],
                end_period=pr[1],
                weeks=[wk] if wk else [],
                label=_label(b),
                tags=["CRBS"],
                notes=n.clean_text(b.get("notes")),
                source="CRBS",
                source_key=key,
                archived=False,
            )
            blk = existing_blocks.get(key)
            if blk is None:
                session.add(Block(**fields_))
                report.created["blocks"] += 1
            else:
                for k, v in fields_.items():
                    setattr(blk, k, v)
                report.updated["blocks"] += 1
            report.rows_imported += 1
        for b in src.rows("bookings_repeat"):
            if int(b.get("status", 10)) != 10 or b.get("cancelled_at"):
                continue
            room = room_by_legacy.get(int(b["room_id"]))
            pr = pmap.by_id.get(int(b["period_id"]))
            term = _term_for_date(None, b.get("session_id"))
            if room is None or pr is None or term is None:
                report.skip(int(b["repeat_id"]), "repeat booking without room/period/term")
                continue
            dates = weekdates.get(int(b["week_id"]), set())
            weeks = sorted(
                {
                    w
                    for w in (
                        _week_index(term, d)
                        for d in dates
                        if term.start_date and term.end_date and term.start_date <= d <= term.end_date
                    )
                    if w
                }
            )
            if not weeks:
                weeks = list(range(1, (term.week_count or 0) + 1))
            key = f"CRBS:repeat:{b['repeat_id']}"
            seen.add(key)
            fields_ = _fields(
                term_id=term.id,
                room_id=room.id,
                day=int(b["weekday"]),
                date=None,
                start_period=pr[0],
                end_period=pr[1],
                weeks=weeks,
                label=_label(b),
                tags=["CRBS"],
                notes=n.clean_text(b.get("notes")),
                source="CRBS",
                source_key=key,
                archived=False,
            )
            blk = existing_blocks.get(key)
            if blk is None:
                session.add(Block(**fields_))
                report.created["blocks"] += 1
            else:
                for k, v in fields_.items():
                    setattr(blk, k, v)
                report.updated["blocks"] += 1
            report.rows_imported += 1
        for skey, blk in existing_blocks.items():
            if skey and skey not in seen and not blk.archived:
                blk.archived = True
                report.updated["blocks_archived"] += 1
    report.rows_total = report.rows_imported + report.rows_skipped_count
    report.extra.update(terms=len(terms_by_session), programs=len(prog_by_dept))
    await session.commit()
    return report
