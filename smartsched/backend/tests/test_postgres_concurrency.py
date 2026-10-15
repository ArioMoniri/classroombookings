"""Concurrency on PostgreSQL 16 (ROADMAP Phase 11 "booking race", Phase 17 "Postgres concurrency test for competing
approvals", review D4 "concurrent activation"): requests race through the real API on separate connections, and
the database constraints decide -- exactly one booking per room/date/period, exactly one approved request of
competing ones, exactly one published run per term and kind. The schema is built by Alembic and must equal the
ORM models on Postgres too.

Data: the university's real rooms and grid -- A 101 (58 seats) and A 201 (96 seats, TIP), the 18-period day
(``/periods/from-grid``), Bahar 2026 (2 Feb - 14 Jun 2026); the clock is Monday 16 Feb 2026 08:00.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from app.core import db as dbmod
from app.models import Base, Booking, ScheduleRun
from app.models.booking import BOOKED
from app.services import bookings as booking_service
from app.services.seed import seed_admin
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select

from tests.api_fixtures import login
from tests.crbs_support import make_user
from tests.pg_support import pg_server, pg_url  # noqa: F401

MON = date(2026, 2, 16)
WED = date(2026, 2, 18)


@dataclass
class PgEnv:
    client: AsyncClient
    admin: dict[str, str]
    term_id: int
    rooms: dict[str, int]
    periods: dict[str, int]


@pytest.fixture
async def pg(pg_url, monkeypatch, tmp_path) -> AsyncIterator[PgEnv]:  # noqa: F811
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    dbmod.configure_engine(pg_url)
    qmod.reset_queue()

    async def fake_now(_session):  # type: ignore[no-untyped-def]
        return datetime(2026, 2, 16, 8, 0)

    async def fake_today(_session):  # type: ignore[no-untyped-def]
        return MON

    monkeypatch.setattr(booking_service, "now_local", fake_now)
    monkeypatch.setattr(booking_service, "today", fake_today)
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        admin = await login(c)
        term = await c.post(
            "/api/v1/terms",
            json={"code": "2026-BAHAR", "name": "2026 Bahar", "start_date": "2026-02-02", "end_date": "2026-06-14"},
            headers=admin,
        )
        assert term.status_code == 201, term.text
        tid = term.json()["id"]
        rooms = {}
        for code, cap, tags in (("A 101", 58, []), ("A 201", 96, ["TIP"])):
            r = await c.post(
                "/api/v1/rooms", json={"code": code, "capacity": cap, "tags": tags, "is_bookable": True}, headers=admin
            )
            assert r.status_code == 201, r.text
            rooms[r.json()["code"]] = r.json()["id"]
        sid = (await c.post("/api/v1/booking-admin/schedules", json={"name": "Ders saatleri"}, headers=admin)).json()[
            "id"
        ]
        r = await c.post(f"/api/v1/booking-admin/schedules/{sid}/periods/from-grid", headers=admin)
        assert r.status_code == 200, r.text
        periods = {p["name"]: p["id"] for p in r.json()["periods"]}
        r = await c.put(
            f"/api/v1/booking-admin/sessions/{tid}",
            json={"is_selectable": True, "default_schedule_id": sid},
            headers=admin,
        )
        assert r.status_code == 200, r.text
        assert (
            await c.put("/api/v1/org/settings", json={"show_ungrouped_rooms": True}, headers=admin)
        ).status_code == 200
        yield PgEnv(c, admin, tid, rooms, periods)
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


def test_alembic_schema_equals_the_models_on_postgres(pg_url):  # noqa: F811
    eng = create_engine(pg_url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    eng.dispose()
    assert diff == [], diff


async def test_booking_race_one_slot_one_winner(pg):
    teachers = [await make_user(pg.client, pg.admin, f"ogretmen{i}@uni.edu.tr") for i in range(8)]
    body = {"room_id": pg.rooms["A101"], "date": MON.isoformat(), "period_id": pg.periods["P2"]}
    rs = await asyncio.gather(*(pg.client.post("/api/v1/bookings", json=body, headers=h) for _, h in teachers))
    codes = sorted(r.status_code for r in rs)
    assert codes.count(201) == 1 and set(codes) <= {201, 409}, [r.text for r in rs]
    async with dbmod.get_session_factory()() as s:
        n = (
            await s.execute(
                select(func.count(Booking.id)).where(
                    Booking.room_id == pg.rooms["A101"], Booking.date == MON, Booking.status == BOOKED
                )
            )
        ).scalar_one()
    assert n == 1


async def test_competing_requests_only_one_is_approved(pg):
    c = pg.client
    _, gozde = await make_user(
        c, pg.admin, "gozde.ayrancigil@uni.edu.tr", role="ADMIN", approves_for=[{"type": "tag", "tag": "tip"}]
    )
    r = await c.post(
        "/api/v1/approval-rules", json={"name": "TIP", "entity_type": "tag", "tag": "TIP"}, headers=pg.admin
    )
    assert r.status_code == 201, r.text
    _, ayse = await make_user(c, pg.admin, "ayse.yilmaz@uni.edu.tr")
    _, mehmet = await make_user(c, pg.admin, "mehmet.oz@uni.edu.tr")
    body = {"room_id": pg.rooms["A201"], "date": WED.isoformat(), "period_id": pg.periods["P3"]}
    for h in (ayse, mehmet):
        r = await c.post("/api/v1/bookings", json=body, headers=h)
        assert r.status_code == 202, r.text
    inbox = (await c.get("/api/v1/approvals/inbox", headers=gozde)).json()
    assert len(inbox) == 2
    rs = await asyncio.gather(
        *(c.post(f"/api/v1/approvals/{x['id']}/decide", json={"decision": "approve"}, headers=gozde) for x in inbox)
    )
    assert all(r.status_code in (200, 409) for r in rs), [r.text for r in rs]
    async with dbmod.get_session_factory()() as s:
        booked = list(
            (
                await s.execute(
                    select(Booking).where(
                        Booking.room_id == pg.rooms["A201"], Booking.date == WED, Booking.status == BOOKED
                    )
                )
            ).scalars()
        )
    assert len(booked) == 1


async def test_concurrent_activation_publishes_exactly_one_run(pg):
    async with dbmod.get_session_factory()() as s:
        runs = [
            ScheduleRun(term_id=pg.term_id, kind="COURSE", horizon="TERM", status="FEASIBLE", hard_score=100)
            for _ in range(6)
        ]
        s.add_all(runs)
        await s.commit()
        ids = [r.id for r in runs]
    rs = await asyncio.gather(*(pg.client.post(f"/api/v1/runs/{i}/activate", headers=pg.admin) for i in ids))
    assert all(r.status_code in (200, 409) for r in rs), [r.text for r in rs]
    async with dbmod.get_session_factory()() as s:
        active = (
            await s.execute(
                select(func.count(ScheduleRun.id)).where(
                    ScheduleRun.term_id == pg.term_id, ScheduleRun.kind == "COURSE", ScheduleRun.is_active.is_(True)
                )
            )
        ).scalar_one()
    assert active == 1
