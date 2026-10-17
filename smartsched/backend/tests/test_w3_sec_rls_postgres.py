"""W3-SEC: PostgreSQL row-level security (alembic 0035_rls_policies, app/core/rls.py).

A user's own SQL cannot read or change another person's rows on the per-person tables, while the API paths still
work. Runs on a real PostgreSQL: ``SMARTSCHED_PG_URL`` (e.g. ``docker run --rm -d -p 19525:5432 postgres:16`` →
``postgresql+psycopg://postgres:pw@127.0.0.1:19525/postgres``), else ``TEST_POSTGRES_URL`` (the pod CI backend gate)
or the local PostgreSQL binaries (tests/pg_support.py); skipped without any of them.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

if os.environ.get("SMARTSCHED_PG_URL"):
    os.environ.setdefault("TEST_POSTGRES_URL", os.environ["SMARTSCHED_PG_URL"])

from app.core import db as dbmod  # noqa: E402
from app.core import rls  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import ConstraintRow, InAppNotification, User  # noqa: E402
from app.models.integrations import CalendarFeedToken  # noqa: E402
from app.models.kvkk import Consent, DsrRequest  # noqa: E402
from app.services.bookings_perms import load_access  # noqa: E402
from app.services.seed import seed_admin  # noqa: E402
from app.workers import queue as qmod  # noqa: E402

from tests.api_fixtures import login  # noqa: E402
from tests.pg_support import pg_server, pg_url  # noqa: E402, F401

NOW = datetime(2026, 10, 17, 9, 0)


def _async(url: str) -> str:
    return url  # postgresql+psycopg is async-capable as it is


async def _seed_people() -> dict[str, int]:
    """Admin (seeded), two teachers (Ayşe, İsmail) and their per-person rows, written in the system context."""
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
        from app.models import Role

        teacher = (await s.execute(select(Role).where(Role.code == "TEACHER"))).scalar_one()
        ids: dict[str, int] = {}
        for key, email, name in (
            ("a", "ayse.yilmaz@uni.edu.tr", "Ayşe Yılmaz"),
            ("b", "ismail.oz@uni.edu.tr", "İsmail Öz"),
        ):
            u = User(email=email, full_name=name, password_hash=hash_password("parola-1234"), role="TEACHER")
            u.role_id = teacher.id
            s.add(u)
            await s.flush()
            ids[key] = u.id
            s.add(InAppNotification(user_id=u.id, kind="approval.decided", title=f"Talep · {name}", body="Onaylandı"))
            s.add(Consent(user_id=u.id, purpose="sms", granted_at=NOW))
            s.add(Consent(user_id=u.id, purpose="ai_personal", granted_at=NOW, withdrawn_at=NOW))
            s.add(DsrRequest(user_id=u.id, kind="export", due_at=NOW + timedelta(days=30)))
            s.add(CalendarFeedToken(user_id=u.id, token_hash=f"{u.id:064d}", hint=str(u.id)))
            s.add(ConstraintRow(kind="room_preference", source="TEACHER", created_by=u.id, enabled=False, params={}))
            await s.execute(
                text(
                    "insert into ai_usage (created_at, user_id, feature, provider, model, outcome) "
                    "values (now(), :u, 'chat', 'anthropic', 'claude', 'ok')"
                ),
                {"u": u.id},
            )
        s.add(ConstraintRow(kind="max_daily_hours", source="FILE", params={}))
        ids["admin"] = (await s.execute(select(User.id).where(User.email == "admin@example.com"))).scalar_one()
        await s.commit()
        return ids


async def _as(user_id: int):  # type: ignore[no-untyped-def]
    s = dbmod.get_session_factory()()
    user = await s.get(User, user_id)
    access = await load_access(s, user)
    await rls.bind_user(s, user, access.perms)
    return s


PER_PERSON = {
    "inapp_notifications": "user_id",
    "dsr_requests": "user_id",
    "calendar_feed_tokens": "user_id",
    "ai_usage": "user_id",
}


@pytest.fixture
async def pg(pg_url) -> AsyncIterator[str]:  # noqa: F811
    dbmod.configure_engine(_async(pg_url))
    yield pg_url
    await dbmod.dispose_engine()


async def test_a_users_direct_sql_sees_only_their_rows(pg):  # type: ignore[no-untyped-def]
    ids = await _seed_people()
    a, b = ids["a"], ids["b"]
    s = await _as(a)
    try:
        for table, col in PER_PERSON.items():
            got = {r[0] for r in (await s.execute(text(f"select {col} from {table}"))).all()}
            assert got == {a}, (table, got)
        # consents: own rows, plus the ai_personal switch of everyone (the AI redactor needs it)
        rows = set((await s.execute(text("select user_id, purpose from consents"))).all())
        assert rows == {(a, "sms"), (a, "ai_personal"), (b, "ai_personal")}
        # teacher wishes: only the own one; planning rules of other sources stay readable
        rows = set((await s.execute(text("select source, created_by from constraints"))).all())
        assert rows == {("TEACHER", a), ("FILE", None)}
        # writes on someone else's rows touch nothing, inserts in their name are refused
        r = await s.execute(text("update inapp_notifications set read_at = now() where user_id = :b"), {"b": b})
        assert r.rowcount == 0
        r = await s.execute(text("delete from calendar_feed_tokens where user_id = :b"), {"b": b})
        assert r.rowcount == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            await s.execute(
                text("insert into consents (user_id, purpose, granted_at) values (:b, 'sms', now())"), {"b": b}
            )
        await s.rollback()
        # the context survives commit / rollback: the next transaction is scoped again
        got = {r[0] for r in (await s.execute(text("select user_id from dsr_requests"))).all()}
        assert got == {a}
        # TRUNCATE (which skips row security) is not granted
        with pytest.raises(DBAPIError, match="permission denied"):
            await s.execute(text("truncate inapp_notifications"))
        await s.rollback()
        # a table a later migration created (0036 error_events) is reachable through the default privileges
        await s.execute(text("select count(*) from error_events"))
    finally:
        await s.close()


async def test_admins_and_system_see_everyone(pg):  # type: ignore[no-untyped-def]
    ids = await _seed_people()
    s = await _as(ids["admin"])  # Administrator: setup.users (DSR handling) and setup.settings (retention)
    try:
        for table in ("inapp_notifications", "dsr_requests", "calendar_feed_tokens", "ai_usage"):
            got = {r[0] for r in (await s.execute(text(f"select user_id from {table}"))).all()}
            assert got == {ids["a"], ids["b"]}, table
    finally:
        await s.close()
    async with dbmod.get_session_factory()() as sys_session:  # workers / migrations: the system context
        n = (await sys_session.execute(text("select count(*) from consents"))).scalar_one()
        assert n == 4


async def test_no_context_means_no_rows(pg):  # type: ignore[no-untyped-def]
    """A connection under the RLS role without the app's settings (a forgotten hook, a hand-made session) is
    fail-closed."""
    await _seed_people()
    eng = create_engine(pg)
    try:
        with eng.begin() as c:
            c.execute(text(f"set local role {rls.RLS_ROLE}"))
            for table in ("inapp_notifications", "consents", "dsr_requests", "calendar_feed_tokens", "ai_usage"):
                assert c.execute(text(f"select count(*) from {table}")).scalar_one() == 0, table
            n = c.execute(text("select count(*) from constraints where source = 'TEACHER'")).scalar_one()
            assert n == 0
    finally:
        eng.dispose()


async def test_fan_out_notification_for_someone_else(pg):  # type: ignore[no-untyped-def]
    """An approver's decision notifies the requester in the approver's request (INSERT ... RETURNING): allowed,
    and the actor still cannot read the row afterwards."""
    ids = await _seed_people()
    s = await _as(ids["a"])
    try:
        s.add(InAppNotification(user_id=ids["b"], kind="approval.decided", title="Talebiniz onaylandı", body="İ/ı"))
        await s.commit()
        mine = (await s.execute(text("select count(*) from inapp_notifications where user_id = :b"), ids)).scalar_one()
        assert mine == 0
        assert (await s.execute(text("select current_setting('app.system', true)"))).scalar_one() == "off"
    finally:
        await s.close()
    async with dbmod.get_session_factory()() as sys_session:
        titles = (
            await sys_session.execute(select(InAppNotification.title).where(InAppNotification.user_id == ids["b"]))
        ).scalars()
        assert "Talebiniz onaylandı" in set(titles)


async def test_system_scope_inside_a_user_request(pg):  # type: ignore[no-untyped-def]
    ids = await _seed_people()
    s = await _as(ids["a"])
    try:
        async with rls.system_scope(s):
            assert (await s.execute(text("select count(*) from dsr_requests"))).scalar_one() == 2
        assert (await s.execute(text("select count(*) from dsr_requests"))).scalar_one() == 1
    finally:
        await s.close()


# ----------------------------------------------------------------------------------------------- API paths


@pytest.fixture
async def pg_client(pg, tmp_path, monkeypatch) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    qmod.reset_queue()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await qmod.get_queue().shutdown()


async def test_api_paths_work_and_run_as_the_user(pg_client, monkeypatch):  # type: ignore[no-untyped-def]
    ids = await _seed_people()
    c = pg_client
    ha = await login(c, "ayse.yilmaz@uni.edu.tr", "parola-1234")
    hb = await login(c, "ismail.oz@uni.edu.tr", "parola-1234")

    r = await c.get("/api/v1/me/notifications", headers=ha)
    assert r.status_code == 200, r.text
    assert [n["title"] for n in r.json()] == ["Talep · Ayşe Yılmaz"]
    r = await c.post("/api/v1/me/consents/calendar_sync", headers=ha)
    assert r.status_code == 200, r.text
    r = await c.get("/api/v1/me/privacy", headers=ha)
    assert r.status_code == 200 and r.json()["ai_excluded"] is True, r.text
    r = await c.post("/api/v1/me/notifications/read", json={}, headers=hb)
    assert r.status_code in (200, 204), r.text

    # the request's session is bound: an unfiltered query in the service returns the caller's rows only
    from app.services import kvkk

    async def unfiltered(session, _user):  # type: ignore[no-untyped-def]
        return list((await session.execute(select(DsrRequest).order_by(DsrRequest.id))).scalars())

    monkeypatch.setattr(kvkk, "mine", unfiltered)
    r = await c.get("/api/v1/me/data-requests", headers=hb)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    admin = await login(c)
    r = await c.get("/api/v1/me/data-requests", headers=admin)
    assert len(r.json()) == 2  # the Administrator handles every request (setup.users)

    # B's rows are untouched by A's read-all call
    async with dbmod.get_session_factory()() as s:
        unread = (
            await s.execute(
                select(InAppNotification).where(
                    InAppNotification.user_id == ids["a"], InAppNotification.read_at.is_(None)
                )
            )
        ).scalars()
        assert len(list(unread)) == 1
    assert datetime.now(UTC)  # keeps the import used on every path
