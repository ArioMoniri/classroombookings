"""HB-10 quota chain and multi-worker reservations (architecture doc §1.3, §5.9).

Order: org → feature → faculty (or ``unassigned``) → department → role (by ``role_id``, else the code) → user. The
faculty / department of each ``ai_usage`` row is a snapshot at record time. Reservations, the per-minute limit and
the concurrency gate live in ``ai_reservations``, so a second API worker (simulated by dropping the process-local
state, and on a real PostgreSQL by a second engine) sees them. Nothing configured means the old behaviour.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import pytest
from app.ai import gateway as gw
from app.ai import guardrails as g
from app.ai import pipeline
from app.ai.client import get_client
from app.ai.context import ai_scope
from app.ai.pipeline import AIGuardError
from app.core.security import hash_password
from app.models import Faculty, Role, User
from app.models.ai_usage import AIReservation, AIUsage
from app.models.catalog import Program
from app.services import ai_usage as meter
from app.services import settings_service as ss
from sqlalchemy import select

from tests.ai.conftest import text
from tests.api_fixtures import login


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    yield
    pipeline.reset_state()
    meter.reset_state()


async def _units(session) -> dict[str, int]:
    f1, f2 = Faculty(name="Eczacılık Fakültesi", canonical_name="eczacilik"), Faculty(name="Tıp", canonical_name="tip")
    session.add_all([f1, f2])
    await session.flush()
    p1 = Program(name="Eczacılık", canonical_name="eczacilik", faculty_id=f1.id)
    p2 = Program(name="Farmakoloji", canonical_name="farmakoloji", faculty_id=f1.id)
    p3 = Program(name="Tıp", canonical_name="tip", faculty_id=f2.id)
    session.add_all([p1, p2, p3])
    await session.commit()
    return {"f1": f1.id, "f2": f2.id, "p1": p1.id, "p2": p2.id, "p3": p3.id}


async def _user(session, email: str, *, department_id: int | None = None, role: str = "TEACHER", role_id=None):
    u = User(email=email, password_hash=hash_password("parola-1234"), role=role, full_name=email.split("@")[0],
             department_id=department_id, role_id=role_id)  # fmt: skip
    session.add(u)
    await session.commit()
    return u


async def _limits(session, **values) -> None:
    await gw.put_json(session, gw.LIMITS_KEY, values)
    await session.commit()


async def _used(session, user: User, tokens: int, feature: str = "chat") -> None:
    await meter.record(user_id=user.id, feature=feature, provider="anthropic", model="claude-opus-5-5",
                       outcome="ok", input_tokens=tokens)  # fmt: skip


async def _refusal(session, user: User | None, tokens: int, feature: str = "chat") -> meter.LimitRefusal:
    with pytest.raises(meter.LimitRefusal) as exc:
        await meter.reserve(session, user_id=user.id if user else None, est_tokens=tokens, est_cost=0, feature=feature)
    return exc.value


async def _passes(session, user: User | None, tokens: int, feature: str = "chat") -> None:
    res = await meter.reserve(
        session, user_id=user.id if user else None, est_tokens=tokens, est_cost=0, feature=feature
    )
    await meter.release(res)


# ------------------------------------------------------------------ unchanged without configuration


async def test_nothing_configured_changes_nothing(session):
    ids = await _units(session)
    u = await _user(session, "a@uni.edu.tr", department_id=ids["p1"])
    for _ in range(3):
        await _passes(session, u, 10_000_000)
    await _passes(session, None, 10_000_000)


# ------------------------------------------------------------------ ceilings per level


async def test_faculty_ceiling(session):
    ids = await _units(session)
    a = await _user(session, "a@uni.edu.tr", department_id=ids["p1"])
    b = await _user(session, "b@uni.edu.tr", department_id=ids["p2"])
    other = await _user(session, "c@uni.edu.tr", department_id=ids["p3"])
    await _limits(session, faculties={str(ids["f1"]): {"monthly_tokens": 1000}})
    await _used(session, a, 900)
    err = await _refusal(session, b, 200)  # b's own usage is 0: the faculty's is 900
    assert (err.code, err.scope) == ("ai_faculty_limit_reached", "faculty_monthly")
    await _passes(session, other, 200)
    await _passes(session, b, 50)


async def test_department_ceiling_and_unassigned(session):
    ids = await _units(session)
    a = await _user(session, "a@uni.edu.tr", department_id=ids["p1"])
    b = await _user(session, "b@uni.edu.tr", department_id=ids["p2"])
    loose = await _user(session, "n@uni.edu.tr")
    await _limits(session, departments={str(ids["p1"]): {"monthly_tokens": 500}}, unassigned={"monthly_tokens": 100})
    await _used(session, a, 450)
    err = await _refusal(session, a, 100)
    assert (err.code, err.scope) == ("ai_department_limit_reached", "department_monthly")
    await _passes(session, b, 100)
    err = await _refusal(session, loose, 150)
    assert (err.code, err.scope) == ("ai_unit_limit_reached", "unassigned_monthly")


async def test_feature_cap(session):
    u = await _user(session, "a@uni.edu.tr")
    await _limits(session, features={"helper": {"monthly_tokens": 300}})
    await _used(session, u, 250, feature="helper")
    err = await _refusal(session, u, 100, feature="helper")
    assert (err.code, err.scope) == ("ai_feature_limit_reached", "feature_monthly")
    await _passes(session, u, 100, feature="chat")


async def test_role_limit_by_role_id_then_by_code(session):
    r1, r2 = Role(name="Onaylayıcı"), Role(name="Asistan")
    session.add_all([r1, r2])
    await session.commit()
    a = await _user(session, "a@uni.edu.tr", role="CUSTOM", role_id=r1.id)
    b = await _user(session, "b@uni.edu.tr", role="CUSTOM", role_id=r2.id)
    t = await _user(session, "t@uni.edu.tr", role="TEACHER")
    await _limits(session, roles={str(r1.id): {"daily": 100}, "TEACHER": {"daily": 50}})
    assert (await _refusal(session, a, 150)).scope == "user_daily"
    await _passes(session, b, 150)  # another custom role is no longer caught by "CUSTOM"
    assert (await _refusal(session, t, 60)).scope == "user_daily"
    assert meter.user_limits(await gw.get_limits(session), a)["daily"] == 100


async def test_the_org_budget_still_comes_first(session):
    ids = await _units(session)
    a = await _user(session, "a@uni.edu.tr", department_id=ids["p1"])
    await _limits(session, org_monthly_tokens=100, faculties={str(ids["f1"]): {"monthly_tokens": 1000}})
    assert (await _refusal(session, a, 200)).code == "ai_budget_exceeded"


# ------------------------------------------------------------------ the snapshot


async def test_the_unit_snapshot_survives_a_department_change(session):
    ids = await _units(session)
    a = await _user(session, "a@uni.edu.tr", department_id=ids["p1"])
    await _used(session, a, 10)
    a.department_id = ids["p3"]
    await session.commit()
    await _used(session, a, 20)
    rows = list((await session.execute(select(AIUsage).order_by(AIUsage.id))).scalars())
    assert [(r.department_id, r.faculty_id, r.input_tokens) for r in rows] == [
        (ids["p1"], ids["f1"], 10),
        (ids["p3"], ids["f2"], 20),
    ]
    await _limits(session, faculties={str(ids["f1"]): {"monthly_tokens": 15}})
    await _passes(session, a, 1000)  # a is in Tıp now; Eczacılık's 10 tokens stay Eczacılık's


# ------------------------------------------------------------------ shared state (a second worker)


def _other_worker() -> None:
    """What a second uvicorn worker would see: none of this process's in-memory state."""
    meter.forget_local_state()
    pipeline.reset_state()


async def test_reservations_are_shared_rows(session):
    await _limits(session, org_monthly_tokens=1000)
    first = await meter.reserve(session, user_id=None, est_tokens=600, est_cost=0)
    _other_worker()
    rows = list((await session.execute(select(AIReservation))).scalars())
    assert [(r.kind, r.tokens) for r in rows] == [("call", 600)]
    err = await _refusal(session, None, 600)
    assert err.code == "ai_budget_exceeded"
    await meter.release(first)
    await _passes(session, None, 600)
    assert list((await session.execute(select(AIReservation).where(AIReservation.kind == "call")))) == []


async def test_expired_reservations_are_ignored(session):
    await _limits(session, org_monthly_tokens=1000)
    await meter.reserve(session, user_id=None, est_tokens=600, est_cost=0, timeout_s=-61)  # a crashed worker's row
    await _passes(session, None, 600)


async def test_concurrency_gate_counts_open_rows(session):
    u = await _user(session, "a@uni.edu.tr")
    one = await meter.reserve(session, user_id=u.id, est_tokens=1, est_cost=0, max_concurrent=1)
    _other_worker()
    err = await _refusal_concurrent(session, u)
    assert (err.code, err.scope) == ("too_many_concurrent", "concurrent")
    await meter.release(one)
    await meter.release(await meter.reserve(session, user_id=u.id, est_tokens=1, est_cost=0, max_concurrent=1))


async def _refusal_concurrent(session, u):
    with pytest.raises(meter.LimitRefusal) as exc:
        await meter.reserve(session, user_id=u.id, est_tokens=1, est_cost=0, max_concurrent=1)
    return exc.value


async def test_per_minute_limit_counts_rows_of_every_worker(session):
    u = await _user(session, "a@uni.edu.tr")
    assert await meter.rate_hit(u.id, per_minute=2)
    _other_worker()
    assert await meter.rate_hit(u.id, per_minute=2)
    _other_worker()
    assert not await meter.rate_hit(u.id, per_minute=2)
    assert await meter.rate_hit(u.id + 1, per_minute=2)  # per person
    assert await meter.rate_hit(u.id, per_minute=0)  # 0 = no limit


async def test_settle_without_await_is_seen_at_once(session):
    """``settle`` stays synchronous for old callers: the next check in this worker no longer counts the row."""
    await _limits(session, org_monthly_tokens=1000)
    first = await meter.reserve(session, user_id=None, est_tokens=600, est_cost=0)
    meter.settle(first)
    await _passes(session, None, 600)


# ------------------------------------------------------------------ through the gateway


async def test_gateway_refuses_with_a_faculty_message_and_records_the_units(session, fake_sdk):
    ids = await _units(session)
    await ss.set_value(session, "anthropic_api_key", "sk-ant-test-0000")
    a = await _user(session, "a@uni.edu.tr", department_id=ids["p1"])
    await _limits(session, faculties={str(ids["f1"]): {"monthly_tokens": 5000}})
    fake_sdk.script = [text("Tamam.")]
    client = await get_client(session, feature="explain", user_id=a.id)
    with ai_scope("explain", user_id=a.id):
        await client.complete(system="x", messages=[{"role": "user", "content": "PHAR 240"}], max_tokens=100)
    q = select(AIUsage).order_by(AIUsage.id).execution_options(populate_existing=True)
    [row] = list((await session.execute(q)).scalars())
    assert (row.department_id, row.faculty_id) == (ids["p1"], ids["f1"])
    await _used(session, a, 5000)
    client = await get_client(session, feature="explain", user_id=a.id)
    with ai_scope("explain", user_id=a.id), pytest.raises(AIGuardError) as exc:
        await client.complete(system="x", messages=[{"role": "user", "content": "PHAR 240"}], max_tokens=100)
    assert exc.value.status_code == 429 and exc.value.code == "ai_faculty_limit_reached"
    assert "Fakülte" in exc.value.detail["message_tr"] and "faculty" in exc.value.detail["message_en"]
    assert list((await session.execute(select(AIReservation).where(AIReservation.kind == "call")))) == []


def test_refusal_texts_per_scope():
    for code in ("ai_faculty_limit_reached", "ai_department_limit_reached", "ai_feature_limit_reached",
                 "ai_unit_limit_reached"):  # fmt: skip
        tr, en = g.message_for(code)
        assert tr != g.message_for("unknown")[0] and en and pipeline._STATUS[code] == 429


def test_rate_limiter_docstring_no_longer_claims_one_worker():
    assert "one worker per instance" not in (g.RateLimiter.__doc__ or "")


# ------------------------------------------------------------------ admin API: allocations


async def test_department_sum_must_fit_the_faculty_and_strict_mode(client, session):
    ids = await _units(session)
    h = await login(client)
    put = "/api/v1/ai/admin/limits"
    r = await client.put(
        put,
        json={
            "faculties": {str(ids["f1"]): {"monthly_tokens": 1000}},
            "departments": {str(ids["p1"]): {"monthly_tokens": 600}, str(ids["p2"]): {"monthly_tokens": 500}},
        },
        headers=h,
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "department_sum_exceeds_faculty"
    assert r.json()["detail"]["message_tr"] and r.json()["detail"]["message_en"]
    r = await client.put(
        put,
        json={
            "org_monthly_tokens": 1500,
            "faculties": {str(ids["f1"]): {"monthly_tokens": 1000}, str(ids["f2"]): {"monthly_tokens": 1000}},
            "departments": {str(ids["p1"]): {"monthly_tokens": 600}},
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert [w["code"] for w in r.json()["warnings"]] == ["faculty_sum_exceeds_org"]
    r = await client.put(put, json={"strict": True}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "faculty_sum_exceeds_org"
    r = await client.put(put, json={"strict": True, "faculties": {str(ids["f1"]): {"monthly_tokens": 700}}}, headers=h)
    assert r.status_code == 200 and r.json()["warnings"] == []
    bad = await client.put(put, json={"faculties": {"999999": {"monthly_tokens": 10}}}, headers=h)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "unknown_unit"


# ------------------------------------------------------------------ two engines on one PostgreSQL

if os.environ.get("SMARTSCHED_PG_URL"):
    os.environ.setdefault("TEST_POSTGRES_URL", os.environ["SMARTSCHED_PG_URL"])

from tests.pg_support import pg_server, pg_url  # noqa: E402, F401


async def test_two_workers_on_one_postgres_cannot_both_pass_the_last_reservation(pg_url):  # noqa: F811
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # two engines = two API workers (each has its own in-process lock; only PostgreSQL's advisory lock is shared)
    engines = [create_async_engine(pg_url), create_async_engine(pg_url)]
    try:
        async with async_sessionmaker(engines[0])() as s:
            await gw.put_json(s, gw.LIMITS_KEY, {"org_monthly_tokens": 1000})
            await s.commit()

        async def one(engine) -> str:
            async with async_sessionmaker(engine)() as s:
                try:
                    await meter.reserve(s, user_id=None, est_tokens=600, est_cost=0)
                    return "ok"
                except meter.LimitRefusal as exc:
                    return exc.code

        for _ in range(3):
            meter.forget_local_state()
            async with async_sessionmaker(engines[0])() as s:
                await s.execute(AIReservation.__table__.delete())
                await s.commit()
            got = sorted(await asyncio.gather(one(engines[0]), one(engines[1])))
            assert got == ["ai_budget_exceeded", "ok"]
    finally:
        for e in engines:
            await e.dispose()


async def test_moment_helper_is_naive_utc():
    assert meter.utc_naive(datetime(2026, 1, 1, 12, tzinfo=UTC)).tzinfo is None
