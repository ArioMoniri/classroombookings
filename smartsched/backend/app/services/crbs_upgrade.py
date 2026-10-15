"""Upgrade a legacy classroombookings (CRBS 2.x) database into SmartSched (ROADMAP Phase 18 part 3, P18-LEGACY).

Two steps, from the admin API (``/api/v1/crbs-upgrade``) or the CLI (``python -m app.cli crbs-upgrade``):

1. **Dry run** (:func:`dry_run`): the CRBS database -- a ``mysqldump`` / install SQL (loaded into an in-memory
   SQLite by the importer's DDL adapter) or a live MySQL DSN opened **read-only** -- is mapped onto the SmartSched
   models by the CRBS importer (:func:`app.importers.crbs_legacy.import_crbs`: users with their password hashes,
   roles + permissions, ACLs, constraints, room groups / fields, sessions / weeks / holidays, bookings + series).
   Everything happens inside one transaction that is rolled back: the report lists, per SmartSched table, the
   rows before and after, the importer's created / updated / skipped counts and warnings (unmapped rows), and the
   per-table row counts of the CRBS source. Nothing is written.
2. **Commit** (:func:`commit`): the same mapping for real, only when the caller passes the dry run's
   ``fingerprint`` (sha256 of the source's table counts and, for dumps, the dump bytes). A source that changed
   since the dry run answers :class:`SourceChanged` (HTTP 409) instead of importing something nobody reviewed.

The importer is idempotent (rows carry their ``legacy_crbs_*`` ids), so a second commit updates rather than
duplicates. Both steps hold the ``crbs-upgrade`` write lock (:mod:`app.services.term_lock`): two upgrades never
run at once. Live DSNs pass :func:`app.services.crbs_dsn.check_dsn` first (admin + host allowlist, review D16).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from sqlalchemy import func, select, table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_engine
from app.importers.crbs_legacy import CrbsSource, import_crbs, open_source
from app.services import term_lock

LOCK_KEY = "crbs-upgrade"

#: CRBS 2.x tables read by the importer (structure.sql), counted in the report's ``source`` section
SOURCE_TABLES = (
    "auth_roles",
    "auth_permissions",
    "auth_roles_permissions",
    "users",
    "users_constraints",
    "auth_acl",
    "auth_acl_permissions",
    "departments",
    "room_groups",
    "rooms",
    "roomfields",
    "roomoptions",
    "roomvalues",
    "schedules",
    "periods",
    "sessions",
    "session_schedules",
    "weeks",
    "dates",
    "holidays",
    "bookings_repeat",
    "bookings",
)

#: SmartSched tables the importer writes, in report order
TARGET_TABLES = (
    "roles",
    "permissions",
    "role_permissions",
    "users",
    "user_constraints",
    "room_acl",
    "room_acl_permissions",
    "programs",
    "buildings",
    "room_groups",
    "rooms",
    "room_custom_fields",
    "room_custom_field_options",
    "room_custom_field_values",
    "booking_schedules",
    "booking_periods",
    "terms",
    "weeks",
    "term_booking_settings",
    "term_schedules",
    "timetable_weeks",
    "term_dates",
    "holidays",
    "booking_series",
    "bookings",
    "booking_slots",
    "blocks",
)


class SourceChanged(Exception):
    """The CRBS source is not the one the dry run reviewed."""


class _DryRunSession(AsyncSession):
    """A session whose ``commit()`` only flushes: the importer runs unchanged, the caller rolls back."""

    async def commit(self) -> None:
        await self.flush()


@dataclass
class UpgradeReport:
    dry_run: bool
    fingerprint: str
    source: dict[str, int]
    tables: dict[str, dict[str, int]]
    importer: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        changed = {k: v for k, v in self.tables.items() if v["delta"]}
        return {
            "dry_run": self.dry_run,
            "fingerprint": self.fingerprint,
            "source": self.source,
            "tables": self.tables,
            "changed": changed,
            "rows_new": sum(max(0, v["delta"]) for v in self.tables.values()),
            "importer": self.importer,
            "warnings": self.warnings[:500],
        }


class ReadOnlyMysqlSource:
    """A live CRBS MySQL database, opened in a read-only transaction with a consistent snapshot: the importer
    only reads (``SHOW TABLES`` / ``SELECT``), and the server refuses any write on this connection."""

    def __init__(self, dsn: str) -> None:
        try:
            import pymysql
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("pip install pymysql to read a live CRBS MySQL server") from exc
        u = urlsplit(dsn)
        self.conn = pymysql.connect(
            host=u.hostname or "",
            port=u.port or 3306,
            user=unquote(u.username or ""),
            password=unquote(u.password or ""),
            database=u.path.lstrip("/"),
            charset="utf8mb4",
            connect_timeout=10,
            read_timeout=120,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with self.conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")

    def has_table(self, name: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (name,))
            return cur.fetchone() is not None

    def rows(self, name: str) -> list[dict[str, Any]]:
        if name not in SOURCE_TABLES or not self.has_table(name):
            return []
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT * FROM `{name}`")
            return list(cur.fetchall())

    def close(self) -> None:
        self.conn.close()


def open_crbs(source: str | Sequence[str | Path]) -> tuple[CrbsSource, list[str]]:
    """A CRBS source from a ``mysql://`` DSN (read-only) or dump / install SQL paths."""
    if isinstance(source, str) and source.lower().startswith("mysql"):
        return ReadOnlyMysqlSource(source), []
    paths = [source] if isinstance(source, str | Path) else list(source)
    return open_source(paths)


def source_counts(src: CrbsSource) -> dict[str, int]:
    return {t: len(src.rows(t)) for t in SOURCE_TABLES if src.has_table(t)}


def fingerprint(counts: dict[str, int], paths: Iterable[str | Path] = ()) -> str:
    h = hashlib.sha256(json.dumps(counts, sort_keys=True).encode())
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()


async def _counts(session: AsyncSession) -> dict[str, int]:
    out: dict[str, int] = {}
    for name in TARGET_TABLES:
        out[name] = int((await session.execute(select(func.count()).select_from(table(name)))).scalar_one())
    return out


async def _run(
    source: str | Sequence[str | Path], *, apply: bool, expect: str | None, filename: str | None
) -> UpgradeReport:
    src, warnings = open_crbs(source)
    try:
        counts = source_counts(src)
        paths = [] if isinstance(source, str) and source.lower().startswith("mysql") else list(source)
        fp = fingerprint(counts, paths)
        if apply and expect != fp:
            raise SourceChanged(
                "the CRBS source differs from the reviewed dry run (fingerprint mismatch); run the dry run again"
            )
        factory = async_sessionmaker(get_engine(), class_=AsyncSession if apply else _DryRunSession)
        async with factory() as session:
            before = await _counts(session)
            rep = await import_crbs(session, src, filename=filename)  # its commit() is a flush in a dry run
            after = await _counts(session)
            if not apply:
                await session.rollback()
        tables = {t: {"before": before[t], "after": after[t], "delta": after[t] - before[t]} for t in TARGET_TABLES}
        importer = rep.to_dict()
        return UpgradeReport(
            dry_run=not apply,
            fingerprint=fp,
            source=counts,
            tables=tables,
            importer={k: importer[k] for k in ("created", "updated", "rows_skipped_count", "skip_reasons", "extra")},
            warnings=[*warnings, *rep.warnings],
        )
    finally:
        close = getattr(src, "close", None)
        if callable(close):
            close()


async def dry_run(source: str | Sequence[str | Path], *, filename: str | None = None) -> UpgradeReport:
    """Map the CRBS database onto SmartSched and report the diff; nothing is written."""
    async with term_lock.term_write_lock(LOCK_KEY, f"crbs-upgrade dry run {filename or ''}".strip()):
        return await _run(source, apply=False, expect=None, filename=filename)


async def commit(source: str | Sequence[str | Path], *, expect: str, filename: str | None = None) -> UpgradeReport:
    """Import for real; ``expect`` is the fingerprint of the reviewed dry run (:class:`SourceChanged` otherwise)."""
    async with term_lock.term_write_lock(LOCK_KEY, f"crbs-upgrade commit {filename or ''}".strip()):
        return await _run(source, apply=True, expect=expect, filename=filename)


__all__ = [
    "LOCK_KEY",
    "ReadOnlyMysqlSource",
    "SourceChanged",
    "UpgradeReport",
    "commit",
    "dry_run",
    "fingerprint",
    "open_crbs",
    "source_counts",
]
