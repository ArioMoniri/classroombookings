"""Sweeper 2026-10-18: the KVKK inventory counts every person's rows, not only the admin's own.

On PostgreSQL the owner-only tables (``welcome_progress``, the MFA and helper tables, alembic 0040/0043/0044) show a
signed-in administrator only their own rows, so ``kvkk.inventory`` counts inside ``rls.system_scope``. The
PostgreSQL test runs on the local binaries / ``TEST_POSTGRES_URL`` (tests/pg_support.py) and is skipped without
them; the SQLite test checks the scope call itself.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import pytest
from app.core import db as dbmod
from app.core import rls
from app.core.security import hash_password
from app.models import Role, User
from app.models.welcome import WelcomeProgress
from app.services import kvkk
from app.services.bookings_perms import load_access
from app.services.seed import seed_admin
from sqlalchemy import select

from tests.pg_support import pg_server, pg_url  # noqa: F401


def _rows(inv: dict[str, Any], code: str) -> dict[str, int]:
    return next(c["rows"] for c in inv["classes"] if c["code"] == code)


def test_welcome_progress_is_in_the_processing_inventory() -> None:
    assert "welcome_progress" in kvkk.DATA_CLASSES["welcome"]["tables"]


async def test_inventory_counts_inside_system_scope(session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """SQLite has no row security, so this checks that every count runs inside the scope."""
    seen: list[bool] = []
    inside = {"on": False}
    real_execute = session.execute

    @contextlib.asynccontextmanager
    async def fake_scope(_s: Any) -> AsyncIterator[None]:
        inside["on"] = True
        try:
            yield
        finally:
            inside["on"] = False

    async def spy(stmt: Any, *a: Any, **kw: Any) -> Any:
        if str(stmt).startswith("select count(*) from "):
            seen.append(inside["on"])
        return await real_execute(stmt, *a, **kw)

    monkeypatch.setattr(kvkk.rls, "system_scope", fake_scope)
    monkeypatch.setattr(session, "execute", spy)
    inv = await kvkk.inventory(session)
    assert seen and all(seen), seen
    assert "welcome_progress" in _rows(inv, "welcome")


@pytest.fixture
async def pg(pg_url) -> AsyncIterator[str]:  # noqa: F811
    dbmod.configure_engine(pg_url)
    yield pg_url
    await dbmod.dispose_engine()


async def test_inventory_counts_everyone_on_postgres(pg) -> None:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:  # the system context
        await seed_admin(s)
        teacher = (await s.execute(select(Role).where(Role.code == "TEACHER"))).scalar_one()
        for email, name in (("ayse.yilmaz@uni.edu.tr", "Ayşe Yılmaz"), ("ismail.oz@uni.edu.tr", "İsmail Öz")):
            u = User(email=email, full_name=name, password_hash=hash_password("parola-1234"), role="TEACHER")
            u.role_id = teacher.id
            s.add(u)
            await s.flush()
            s.add(WelcomeProgress(user_id=u.id, guide_key="sheet", audience="teacher"))
        admin_id = (await s.execute(select(User.id).where(User.email == "admin@example.com"))).scalar_one()
        await s.commit()

    s = dbmod.get_session_factory()()
    try:
        admin = await s.get(User, admin_id)
        assert admin is not None
        await rls.bind_user(s, admin, (await load_access(s, admin)).perms)
        inv = await kvkk.inventory(s)
        assert _rows(inv, "welcome")["welcome_progress"] == 2
        # the admin's own context comes back after the inventory
        assert (await s.execute(select(WelcomeProgress))).scalars().all() == []
    finally:
        await s.close()
