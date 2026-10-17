"""Security follow-up (wave3-sec2, docs/SECURITY.md R12): the org-wide AI usage aggregates on PostgreSQL with RLS on.

``ai_usage`` rows are owner-scoped for a teacher (alembic 0035). The org budget check in :func:`ai_usage.reserve`, the
budget ratio of ``GET /ai/me/usage`` and the admin reports are deliberate cross-user aggregates: they run inside
``rls.system_scope`` and must count everyone's rows, while the per-user totals and the rest of the request stay
scoped. Runs on a real PostgreSQL (tests/pg_support.py); skipped without one.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

if os.environ.get("SMARTSCHED_PG_URL"):
    os.environ.setdefault("TEST_POSTGRES_URL", os.environ["SMARTSCHED_PG_URL"])

from app.ai import gateway as gw  # noqa: E402
from app.core import db as dbmod  # noqa: E402
from app.services import ai_usage  # noqa: E402

from tests.pg_support import pg_server, pg_url  # noqa: E402, F401
from tests.test_w3_sec_rls_postgres import _as, _seed_people  # noqa: E402


@pytest.fixture
async def pg(pg_url) -> AsyncIterator[str]:  # noqa: F811
    dbmod.configure_engine(pg_url)
    ai_usage.reset_state()
    yield pg_url
    ai_usage.reset_state()
    await dbmod.dispose_engine()


async def _usage(user_id: int, tokens: int, outcome: str = "ok") -> None:
    async with dbmod.get_session_factory()() as s:
        await s.execute(
            text(
                "insert into ai_usage (created_at, user_id, feature, provider, model, outcome, input_tokens, cost_usd) "
                "values (now(), :u, 'chat', 'anthropic', 'claude', :o, :t, 0.5)"
            ),
            {"u": user_id, "t": tokens, "o": outcome},
        )
        await gw.put_json(s, gw.LIMITS_KEY, {"org_monthly_tokens": 1500})
        await s.commit()


async def test_org_totals_and_budget_count_everyone_inside_a_teachers_request(pg):  # type: ignore[no-untyped-def]
    ids = await _seed_people()  # one 0-token row per teacher
    a, b = ids["a"], ids["b"]
    await _usage(b, 1000)
    s = await _as(a)
    try:
        org = await ai_usage.totals(s)
        assert org["month_calls"] == 3 and org["month_tokens"] == 1000
        # the teacher's own totals stay their own
        mine = await ai_usage.totals(s, user_id=a)
        assert mine["month_calls"] == 1 and mine["month_tokens"] == 0
        # the budget ratio of GET /ai/me/usage is the org's, not the teacher's slice
        state = await ai_usage.org_state(s)
        assert state["pct"] is not None and round(state["pct"]) == 67
        # B's 1000 tokens count against the 1500 budget: A cannot spend 600 more
        with pytest.raises(ai_usage.LimitRefusal) as refused:
            await ai_usage.reserve(s, user_id=a, est_tokens=600, est_cost=0.0)
        assert refused.value.code == "ai_budget_exceeded"
        # after the aggregates the request is scoped again
        got = {r[0] for r in (await s.execute(text("select user_id from ai_usage"))).all()}
        assert got == {a}
    finally:
        await s.close()


async def test_admin_reports_count_everyone(pg):  # type: ignore[no-untyped-def]
    ids = await _seed_people()
    await _usage(ids["b"], 1000, outcome="refused_limit")
    s = await _as(ids["admin"])
    try:
        rows = await ai_usage.report(s, "user")
        assert {r["key"] for r in rows} >= {ids["a"], ids["b"]}
        days = await ai_usage.report(s, "day")
        assert sum(d["calls"] for d in days) == 3
        assert [r["user_id"] for r in await ai_usage.refusals(s)] == [ids["b"]]
    finally:
        await s.close()
