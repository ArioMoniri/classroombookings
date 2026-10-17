"""Alembic ``0031_invigilation``: the invigilator pool, plans and duties tables appear on the single head, equal the
ORM models (autogenerate diff empty), keep existing rows, and the downgrade round-trips."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic import command

from tests.test_crbs_migration import _run
from tests.test_p19_learning_migration import _diff

TABLES = {"invigilator_pool", "invigilation_plans", "invigilation_duties"}


def _tables(path: Path) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type = 'table'")}
    finally:
        con.close()


def test_invigilation_migration_roundtrip(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "0030_booking_conflicts")
    con = sqlite3.connect(path)
    con.execute(
        "insert into terms (id, code, name, kind, week_count, periods_json, is_active, created_at, updated_at) "
        "values (1, '2026-FINAL', '2026 Final', 'FINAL', 3, '[]', 1, '2026-06-01 00:00:00', '2026-06-01 00:00:00')"
    )
    con.commit()
    con.close()
    assert not TABLES & _tables(path)
    _run(url, command.upgrade, "0031_invigilation")
    assert TABLES <= _tables(path)
    con = sqlite3.connect(path)
    assert con.execute("select code from terms").fetchall() == [("2026-FINAL",)]
    con.execute(
        "insert into invigilator_pool (term_id, full_name, canonical_name, kind, load_factor, unavailable, active, "
        "created_at, updated_at) values (1, 'Arş. Gör. Deniz Ak', 'deniz ak', 'ASSISTANT', 150, '[]', 1, "
        "'2026-10-16 12:00:00', '2026-10-16 12:00:00')"
    )
    con.commit()
    con.close()
    _run(url, command.upgrade, "heads")
    assert [d for d in _diff(path) if any(t in repr(d) for t in TABLES)] == []
    _run(url, command.downgrade, "0030_booking_conflicts")
    assert not TABLES & _tables(path)
    assert "terms" in _tables(path)


def test_single_alembic_head():
    backend = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"], cwd=backend, capture_output=True, text=True, check=True
    ).stdout
    assert len([ln for ln in out.splitlines() if ln.strip()]) == 1, out
