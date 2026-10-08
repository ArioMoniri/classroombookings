"""Booking test environment on the real Bahar 2026 import (``tests/studio_support.bahar_template``: the
weekly room grid + the planning list). The imported weekly grid run is **published** (activated), so
its assignments are the timetable bookings must respect. Booking setup is done through the API with the
university's real 18-period grid; the clock is fixed inside the term (Monday 16 Feb 2026, 08:00).

    from tests.crbs_env import env  # noqa: F401  (fixture)
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.models import Room, ScheduleRun, Term
from app.services import bookings as booking_service
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.api_fixtures import login
from tests.crbs_support import make_user
from tests.studio_support import PLANNER, bahar_template

TODAY = date(2026, 2, 16)  # Monday of Bahar week 3


@dataclass
class Env:
    client: AsyncClient
    admin: dict[str, str]
    planner: dict[str, str]
    term_id: int
    run_id: int
    schedule_id: int
    periods: dict[str, int]  # "P1" -> period id
    rooms: dict[str, int]  # canonical code -> room id
    clock: dict[str, datetime] = field(default_factory=dict)

    def set_now(self, when: datetime) -> None:
        self.clock["now"] = when

    async def user(self, email: str, role: str = "TEACHER", **extra: object) -> tuple[int, dict[str, str]]:
        return await make_user(self.client, self.admin, email, role=role, **extra)

    async def book(self, headers: dict[str, str], room: str, day: date, period: str, **extra: object):  # type: ignore[no-untyped-def]
        return await self.client.post(
            "/api/v1/bookings",
            json={"room_id": self.rooms[room], "date": day.isoformat(), "period_id": self.periods[period], **extra},
            headers=headers,
        )


@pytest.fixture
async def env(tmp_path_factory, tmp_path, monkeypatch) -> AsyncIterator[Env]:
    template = bahar_template(tmp_path_factory)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    db = tmp_path / "crbs.db"
    shutil.copy(template, db)
    dbmod.configure_engine(f"sqlite+aiosqlite:///{db}")
    qmod.reset_queue()
    clock = {"now": datetime(2026, 2, 16, 8, 0)}

    async def fake_now(_session):  # type: ignore[no-untyped-def]
        return clock["now"]

    async def fake_today(_session):  # type: ignore[no-untyped-def]
        return clock["now"].date()

    monkeypatch.setattr(booking_service, "now_local", fake_now)
    monkeypatch.setattr(booking_service, "today", fake_today)
    from app.main import app

    async with dbmod.get_session_factory()() as s:
        term_id = (await s.execute(select(Term.id).where(Term.code == "2026-BAHAR"))).scalar_one()
        run_id = (
            await s.execute(
                select(ScheduleRun.id).where(
                    ScheduleRun.term_id == term_id,
                    ScheduleRun.kind == "COURSE",
                    ScheduleRun.label.like("Grid import:%"),
                )
            )
        ).scalar_one()
        rooms = {r.code: r.id for r in (await s.execute(select(Room))).scalars()}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        admin = await login(c)
        planner = await login(c, *PLANNER)
        r = await c.post(f"/api/v1/runs/{run_id}/activate", headers=planner)
        assert r.status_code == 200, r.text
        r = await c.post("/api/v1/booking-admin/schedules", json={"name": "Ders saatleri"}, headers=admin)
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        r = await c.post(f"/api/v1/booking-admin/schedules/{sid}/periods/from-grid", headers=admin)
        assert r.status_code == 200, r.text
        periods = {p["name"]: p["id"] for p in r.json()["periods"]}
        r = await c.put(
            f"/api/v1/booking-admin/sessions/{term_id}",
            json={"is_selectable": True, "default_schedule_id": sid},
            headers=admin,
        )
        assert r.status_code == 200, r.text
        yield Env(c, admin, planner, term_id, run_id, sid, periods, rooms, clock)
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()
