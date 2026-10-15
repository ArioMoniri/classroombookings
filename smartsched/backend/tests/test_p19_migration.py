"""Alembic ``0019_publish_guard_term_locks`` (review D4 / D8): an upgraded database whose old activation raced
(two active runs of 2026-BAHAR COURSE) keeps the newest one active, the partial unique index refuses a second
active run, ``term_locks`` exists, the schema equals the ORM models, and the downgrade round-trips."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from app.models import Base
from sqlalchemy import create_engine

from tests.test_crbs_migration import _run

RUN = (
    "insert into schedule_runs (term_id, kind, horizon, horizon_params, status, params, stats, diagnosis, is_active, "
    "label, created_at) values (?, ?, 'TERM', '{}', 'FEASIBLE', '{}', '{}', '[]', ?, ?, '2026-02-16 08:00:00')"
)


def test_upgrade_keeps_the_newest_active_run_and_enforces_one(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "0018_ai_proposal_decisions")
    con = sqlite3.connect(path)
    con.execute(
        "insert into terms (id, code, name, kind, week_count, periods_json, is_active, created_at, updated_at) "
        "values (1, '2026-BAHAR', '2026 Bahar', 'REGULAR', 14, '[]', 1, '2026-02-01 00:00:00', '2026-02-01 00:00:00')"
    )
    con.execute(RUN, (1, "COURSE", 1, "Grid import: 2026 bahar derslikler takvimi.xlsx"))
    con.execute(RUN, (1, "COURSE", 1, "Bahar hafta 3"))
    con.execute(RUN, (1, "EXAM", 1, "Final"))
    con.commit()
    con.close()

    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    active = con.execute("select kind, label from schedule_runs where is_active = 1 order by id").fetchall()
    assert active == [("COURSE", "Bahar hafta 3"), ("EXAM", "Final")]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("update schedule_runs set is_active = 1 where label like 'Grid import:%'")
    con.execute("update schedule_runs set is_active = 0 where is_active = 1")  # many inactive runs are fine
    assert "term_locks" in {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()

    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"render_as_batch": True}), Base.metadata)
    eng.dispose()
    assert diff == []

    _run(url, command.downgrade, "0018_ai_proposal_decisions")
    _run(url, command.upgrade, "head")
