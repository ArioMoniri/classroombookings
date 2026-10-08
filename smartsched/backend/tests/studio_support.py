"""Shared fixtures for the Generator Studio tests (``tests/test_studio_*.py``).

The real Bahar 2026 workbooks (room grid + planning list) take ~25 s to import, so they are imported
once per session into a template SQLite file; every test gets its own copy. Use in a test module:

    from tests import studio_support
    bahar = studio_support.bahar
"""

from __future__ import annotations

import asyncio
import shutil
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.core.security import hash_password
from app.importers.planning_list import import_planning_list
from app.importers.weekly_grid import import_weekly_grid
from app.models import Base, Room, Term, User
from app.services.seed import seed_admin
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.api_fixtures import login
from tests.conftest import BAHAR_GRID, BAHAR_LIST

PLANNER = ("planner@example.com", "planner1234")


async def _build(path: Path) -> None:
    eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
        s.add(User(email=PLANNER[0], password_hash=hash_password(PLANNER[1]), role="PLANNER", full_name="Fatih Bey"))
        await s.commit()
        await import_weekly_grid(s, BAHAR_GRID, "2026-BAHAR", year=2026)  # room master with capacities
        await import_planning_list(s, BAHAR_LIST, "2026-BAHAR")
    await dbmod.dispose_engine()


_TEMPLATE: list[Path] = []


def bahar_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Path of the imported Bahar template DB, built once per test process (a module-level cache, so
    every test module that re-exports the fixture shares it)."""
    if _TEMPLATE:
        return _TEMPLATE[0]
    path = tmp_path_factory.mktemp("studio") / "bahar.db"
    errors: list[BaseException] = []

    def target() -> None:  # own thread + loop: never collides with pytest-asyncio's loop
        try:
            asyncio.run(_build(path))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if errors:
        raise errors[0]
    _TEMPLATE.append(path)
    return path


@dataclass
class Bahar:
    client: AsyncClient
    admin: dict[str, str]
    planner: dict[str, str]
    term_id: int


@pytest.fixture
async def bahar(tmp_path_factory, tmp_path, monkeypatch) -> AsyncIterator[Bahar]:
    template = bahar_template(tmp_path_factory)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    db = tmp_path / "api.db"
    shutil.copy(template, db)
    dbmod.configure_engine(f"sqlite+aiosqlite:///{db}")
    qmod.reset_queue()
    from app.main import app

    async with dbmod.get_session_factory()() as s:
        term_id = (await s.execute(select(Term.id).where(Term.code == "2026-BAHAR"))).scalar_one()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield Bahar(c, await login(c), await login(c, *PLANNER), term_id)
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


async def meeting_id(code: str, day: int | None = None, start: int | None = None, label: str | None = None) -> int:
    """Id of the Bahar meeting request of ``code`` (e.g. ``"PHAR 240"``) on ``day`` / ``start`` period."""
    from app.importers.normalize import canon_course_code
    from app.models import Course, MeetingRequest, Section

    async with dbmod.get_session_factory()() as s:
        q = (
            select(MeetingRequest.id)
            .join(Section, Section.id == MeetingRequest.section_id)
            .join(Course, Course.id == Section.course_id)
            .where(Course.code == canon_course_code(code))
            .order_by(MeetingRequest.id)
        )
        if day is not None:
            q = q.where(MeetingRequest.day == day)
        if start is not None:
            q = q.where(MeetingRequest.start_period == start)
        if label is not None:
            q = q.where(Section.label == label)
        ids = list((await s.execute(q)).scalars())
    assert ids, f"no meeting for {code} day={day} start={start}"
    return ids[0]


async def bahar_counts(term_id: int) -> dict[str, int]:
    """Counts of the imported Bahar term, so tests do not hard-code importer output."""
    from app.models import MeetingRequest, Room, Section
    from sqlalchemy import func

    async with dbmod.get_session_factory()() as s:
        base = (
            select(func.count(MeetingRequest.id))
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == term_id, MeetingRequest.archived.is_(False))
        )
        term = await s.get(Term, term_id)
        assert term is not None
        return {
            "meetings": (await s.execute(base)).scalar_one(),
            "locked": (await s.execute(base.where(MeetingRequest.status == "LOCKED"))).scalar_one(),
            "needs_room": (await s.execute(base.where(MeetingRequest.needs_room.is_(True)))).scalar_one(),
            "rooms": (
                await s.execute(select(func.count(Room.id)).where(Room.is_bookable.is_(True), Room.capacity > 0))
            ).scalar_one(),
            "weeks": int(term.week_count),
        }


async def room(code: str) -> Room:
    """Room row by canonical code (``"A206"``); ids depend on the importer, never hard-code them."""
    async with dbmod.get_session_factory()() as s:
        return (await s.execute(select(Room).where(Room.code == code))).scalar_one()


async def largest_room(exclude_tag: str = "TIP") -> Room:
    async with dbmod.get_session_factory()() as s:
        rooms = [r for r in (await s.execute(select(Room).where(Room.is_bookable.is_(True)))).scalars()]
    return max((r for r in rooms if exclude_tag not in (r.tags or [])), key=lambda r: (r.capacity, r.code))
