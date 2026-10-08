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


@pytest.fixture
def stub_solver(monkeypatch):  # type: ignore[no-untyped-def]
    """Fast greedy runs for API tests: the bridge's CP-SAT entry points at ``app.solver.stub``.  The stub is
    no run option in production (audit M1: ``params.solver="stub"`` answers 422); call ``.undo()`` on the
    returned monkeypatch to switch back to CP-SAT inside a test."""
    from app.services import solver_bridge

    monkeypatch.setitem(solver_bridge.SOLVER_MODULES, "cpsat", "app.solver.stub")
    return monkeypatch


@pytest.fixture(autouse=True)
def _fresh_login_limiter():
    """The in-process login failure limiter (app/core/ratelimit.py) must not leak between tests."""
    from app.core import ratelimit

    ratelimit.reset()
    yield
    ratelimit.reset()


#: the heaviest tests (each >~15 s on the real workbooks, ~4.5 min together). ``make check`` runs
#: ``-m "not slow"``; ``make test-slow`` (a separate CI step) runs exactly these, so CI keeps full coverage.
SLOW_TESTS = frozenset(
    {
        "tests/test_real_feasibility.py::test_real_final_locked_plan_validates",
        "tests/test_real_feasibility.py::test_real_bahar_week3_static_check_has_no_blockers_from_locks_or_fixed_clashes",
        "tests/test_api_diagnosis_apply.py::test_apply_unlock_on_real_cpsat_diagnosis",
        "tests/test_import_weekly_grid.py::test_import_bahar_grid_links_requests",
        "tests/test_import_room_master.py::test_real_bahar_import_room_master_end_to_end",
        "tests/test_api_exam_share.py::test_final_fixture_locked_single_room_exams_no_longer_clash",
        "tests/test_review_import.py::test_m4_reimport_keeps_identity_edits_and_remaps",
        "tests/test_review_import.py::test_m4_unchanged_reimport_writes_nothing_and_legacy_keys_migrate",
        "tests/test_import_planning_list.py::test_import_bahar_into_db_is_idempotent",
        "tests/test_import_planning_list.py::test_import_guz_then_bahar_share_catalog",
        # planner-level regression tests of the strict solver review (B1, B2, M1, M2; orchestrator R2)
        "tests/test_planner_level_real.py::test_bahar_week3_is_valid_at_planner_level",
        "tests/test_planner_level_real.py::test_bahar_week3_is_deterministic",
        "tests/test_planner_level_real.py::test_final_is_valid_at_planner_level",
        "tests/test_planner_level_real.py::test_fix_button_cases_leave_planner_valid_runs",
        "tests/test_planner_level_real.py::test_bahar_term_is_valid_at_planner_level",
    }
)


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    for item in items:
        if item.nodeid in SLOW_TESTS:
            item.add_marker(pytest.mark.slow)
