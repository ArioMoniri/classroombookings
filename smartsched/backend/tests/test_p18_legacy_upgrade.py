"""P18-LEGACY (ROADMAP Phase 18 part 3): upgrade a legacy classroombookings database into SmartSched with a dry-run
diff, committed only on confirmation.

The CRBS database is the repository's own legacy install: ``crbs-core/application/modules/install/resources/``
``structure.sql`` + ``data.sql`` (roles, permissions, room group, schedule, timetable week, the current session
and its dates) plus exactly what CRBS's installer (``Installer::create_user``) adds for the first administrator: a
``users`` row with ``role_id = 1``, a PHP ``password_hash`` and an empty ``users_constraints`` row.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import bcrypt
import pytest
from app.core import db as dbmod
from app.models import Role, Term, TimetableWeek, User
from app.services import crbs_upgrade as up
from app.services import term_lock
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.test_import_crbs import DATA, STRUCTURE

ADMIN_PW = "kurulum-parolası-1"


INSTALL_DAY = date(2026, 10, 15)  # the day CRBS was "installed": data.sql derives the session from CURDATE()


def _mysql_session_and_dates(today: date) -> str:
    """The two statements of data.sql that use MySQL variables (``INSERT INTO sessions SET ... = @name`` and the
    ``INSERT INTO dates ... SELECT ADDDATE(@start, INTERVAL @i:=@i+1 DAY)`` generator), evaluated as MySQL does
    on ``today``: the school year that contains it (1 Sep - 31 Jul), every day of it, ``ELT(DAYOFWEEK(...))``
    weekdays (Monday = 1) and timetable week 1. The SQLite loader skips them (and says so)."""
    start_year = today.year - 1 if today.month < 9 else today.year
    end_year = start_year + 1
    start, end = date(start_year, 9, 1), date(end_year, 7, 31)
    out = [
        "INSERT INTO sessions (session_id, default_schedule_id, name, date_start, date_end, is_current, "
        f"is_selectable) VALUES (1, 1, '{start_year} - {end_year}', '{start}', '{end}', 1, 1);"
    ]
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    values = ", ".join(f"('{d}', {d.isoweekday()}, 1, 1)" for d in days)
    out.append(f"INSERT INTO dates (date, weekday, session_id, week_id) VALUES {values};")
    return "\n".join(out) + "\n"


def _installer_sql(tmp_path: Path) -> Path:
    """data.sql's variable statements (above) + ``Installer::create_user()`` + ``INSERT INTO users_constraints
    SET user_id = ?`` for the form's user."""
    pw = bcrypt.hashpw(ADMIN_PW.encode(), bcrypt.gensalt(4)).decode().replace("$2b$", "$2y$", 1)
    path = tmp_path / "installer.sql"
    path.write_text(
        _mysql_session_and_dates(INSTALL_DAY)
        + "INSERT INTO users (user_id, username, password, role_id, department_id, enabled) "
        f"VALUES (1, 'yonetici', '{pw}', 1, NULL, 1);\n"
        "INSERT INTO users_constraints (user_id) VALUES (1);\n",
        encoding="utf-8",
    )
    return path


def _dump(tmp_path: Path) -> list[Path]:
    return [STRUCTURE, DATA, _installer_sql(tmp_path)]


async def _count(model) -> int:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(model))).scalar_one())


async def test_dry_run_reports_the_diff_and_writes_nothing(client, tmp_path):
    dump = _dump(tmp_path)
    users, terms = await _count(User), await _count(Term)
    rep = (await up.dry_run(dump, filename="crbs-install")).to_dict()
    assert rep["dry_run"] is True and len(rep["fingerprint"]) == 64
    # the CRBS side as read from the install SQL
    assert rep["source"]["users"] == 1 and rep["source"]["sessions"] == 1 and rep["source"]["weeks"] >= 1
    assert rep["source"]["auth_roles"] >= 2 and rep["source"]["dates"] == 334  # 1 Sep 2026 - 31 Jul 2027
    # what the loader could not map is in the report, not silently dropped
    assert any("INSERT INTO sessions SET" in w for w in rep["warnings"])
    # the SmartSched side: one new user (the CRBS administrator), the session as a term, its week and dates
    changed = rep["changed"]
    assert changed["users"]["delta"] == 1
    assert changed["terms"]["delta"] == 1 and changed["timetable_weeks"]["delta"] >= 1
    assert changed["term_dates"]["delta"] == rep["source"]["dates"]
    assert rep["rows_new"] == sum(v["delta"] for v in changed.values() if v["delta"] > 0)
    assert rep["importer"]["created"]["users"] == 1
    # ... and nothing was written
    assert (await _count(User), await _count(Term)) == (users, terms)
    assert await term_lock.current(up.LOCK_KEY) is None  # the lock is released
    # the same source gives the same fingerprint
    assert (await up.dry_run(dump)).fingerprint == rep["fingerprint"]


async def test_commit_needs_the_reviewed_fingerprint_then_imports_what_was_shown(client, tmp_path):
    dump = _dump(tmp_path)
    plan = await up.dry_run(dump)
    with pytest.raises(up.SourceChanged):
        await up.commit(dump, expect="0" * 64)
    assert await _count(Term) == plan.tables["terms"]["before"]
    done = await up.commit(dump, expect=plan.fingerprint)
    assert done.dry_run is False
    assert {t: v["after"] for t, v in done.tables.items()} == {t: v["after"] for t, v in plan.tables.items()}
    assert await _count(Term) == plan.tables["terms"]["after"]
    async with dbmod.get_session_factory()() as s:
        crbs_admin = (await s.execute(select(User).where(User.username == "yonetici"))).scalar_one()
        admin_role = (await s.execute(select(Role).where(Role.code == "ADMIN"))).scalar_one()
        assert crbs_admin.role_id == admin_role.id and crbs_admin.legacy_crbs_user_id == 1
        assert (await s.execute(select(func.count()).select_from(TimetableWeek))).scalar_one() >= 1
    # the CRBS administrator signs in with the CRBS password
    r = await client.post("/api/v1/auth/login", json={"username": "yonetici", "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    # idempotent: a second dry run adds nothing
    again = (await up.dry_run(dump)).to_dict()
    assert again["rows_new"] == 0, again["changed"]


async def test_admin_api_dry_run_then_confirm(client, tmp_path):
    admin = await login(client)
    r = await client.post(
        "/api/v1/users",
        json={"email": "planlama@uni.edu.tr", "role": "PLANNER", "password": "planlama-1234"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    planner = await login(client, "planlama@uni.edu.tr", "planlama-1234")
    files = [("files", (p.name, p.read_bytes(), "application/sql")) for p in _dump(tmp_path)]
    url = "/api/v1/crbs-upgrade"
    assert (await client.post(url, files=files, headers=planner)).status_code == 403
    r = await client.post(url, files=files, headers=admin)
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["dry_run"] is True and plan["changed"]["users"]["delta"] == 1
    terms = await _count(Term)
    r = await client.post(url, files=files, data={"confirm": "true", "fingerprint": "f" * 64}, headers=admin)
    assert r.status_code == 409 and await _count(Term) == terms
    r = await client.post(url, files=files, data={"confirm": "true", "fingerprint": plan["fingerprint"]}, headers=admin)
    assert r.status_code == 200 and r.json()["dry_run"] is False, r.text
    assert await _count(Term) == terms + 1
    # a live DSN goes through the SSRF guard (review D16): no host is allowed yet
    r = await client.post(url, data={"dsn": "mysql://crbs:x@crbs-db.uni.edu.tr/crbs"}, headers=admin)
    assert r.status_code == 422 and "crbs_dsn_allowed_hosts" in r.text
    assert (await client.post(url, headers=admin)).status_code == 400  # neither files nor a DSN
