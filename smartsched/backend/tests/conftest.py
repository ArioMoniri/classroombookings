"""Shared fixtures: in-memory SQLite engine per test, cached parsed workbooks per session."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("APP_SECRET", "test-secret-test-secret-test-secret-0000")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "admin1234")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.core import db as dbmod  # noqa: E402

pytest_plugins = ["tests.api_fixtures"]
from app.models import Base  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
BAHAR_LIST = FIXTURES / "bahar_derslik_planlama_listesi_v5.xlsx"
GUZ_LIST = FIXTURES / "guz_derslik_planlama_2026_2027_v2.xlsx"
EXAM_LIST = FIXTURES / "final_planlama_listesi_2026_v2.xlsx"
BAHAR_GRID = FIXTURES / "bahar_derslikler_takvimi_2026.xlsx"
GUZ_GRID = FIXTURES / "guz_derslikler_takvimi_2026_2027.xlsx"
FINAL_GRID = FIXTURES / "final_derslikler_takvimi_2026_v2.xlsx"


@pytest.fixture
async def engine():
    eng = dbmod.configure_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await dbmod.dispose_engine()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    async with dbmod.get_session_factory()() as s:
        yield s


@pytest.fixture(scope="session")
def parsed_bahar_list():
    from app.importers.planning_list import parse_planning_list

    return parse_planning_list(BAHAR_LIST)


@pytest.fixture(scope="session")
def parsed_guz_list():
    from app.importers.planning_list import parse_planning_list

    return parse_planning_list(GUZ_LIST)


@pytest.fixture(scope="session")
def parsed_exam_list():
    from app.importers.exam_list import parse_exam_list

    return parse_exam_list(EXAM_LIST)


@pytest.fixture(scope="session")
def parsed_bahar_grid():
    from app.importers.weekly_grid import parse_weekly_grid

    return parse_weekly_grid(BAHAR_GRID, year=2026)


@pytest.fixture(scope="session")
def parsed_guz_grid():
    from app.importers.weekly_grid import parse_weekly_grid

    return parse_weekly_grid(GUZ_GRID, year=2026)


@pytest.fixture(scope="session")
def parsed_final_grid():
    from app.importers.weekly_grid import parse_weekly_grid

    return parse_weekly_grid(FINAL_GRID, year=2026)
