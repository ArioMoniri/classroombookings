"""Alembic ``0027_p19_gaps``: ``program_drafts`` and ``priority_overrides`` appear, the schema equals the ORM models
(autogenerate diff empty), existing rows are kept and the downgrade round-trips."""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.test_crbs_migration import _run
from tests.test_p19_learning_migration import _diff

REVISION = "0027_p19_gaps"
PREVIOUS = "0026_sso_entra"


def _tables(path) -> set[str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type = 'table'")}
    finally:
        con.close()


def test_upgrade_adds_the_tables_matches_the_models_and_round_trips(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREVIOUS)
    con = sqlite3.connect(path)
    con.execute(
        "insert into terms (id, code, name, kind, week_count, periods_json, is_active, created_at, updated_at) "
        "values (1, '2026-BAHAR', '2026 Bahar', 'REGULAR', 14, '[]', 1, '2026-02-01 00:00:00', '2026-02-01 00:00:00')"
    )
    con.commit()
    con.close()
    assert not {"program_drafts", "priority_overrides"} & _tables(path)
    _run(url, command.upgrade, REVISION)
    assert {"program_drafts", "priority_overrides"} <= _tables(path)
    con = sqlite3.connect(path)
    assert con.execute("select code from terms").fetchall() == [("2026-BAHAR",)]
    con.execute(
        "insert into priority_overrides (term_id, subject_type, subject_id, priority, updated_at) "
        "values (1, 'person', 7, 1, '2026-10-16 09:00:00')"
    )
    con.commit()
    con.close()
    _run(url, command.upgrade, "heads")  # whatever other agents put on top
    assert [d for d in _diff(path) if "program_drafts" in repr(d) or "priority_overrides" in repr(d)] == []
    _run(url, command.downgrade, PREVIOUS)
    assert not {"program_drafts", "priority_overrides"} & _tables(path)
    _run(url, command.upgrade, REVISION)
    assert {"program_drafts", "priority_overrides"} <= _tables(path)
