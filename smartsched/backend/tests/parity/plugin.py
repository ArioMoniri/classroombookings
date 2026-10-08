"""pytest plugin used by ``scripts/parity_check.py`` (``-p tests.parity.plugin --parity-json=PATH``).

Records, for every test that ran, its outcome (``passed`` / ``failed`` / ``skipped``), duration, the parity
rows named by its ``@pytest.mark.parity`` marker and, on failure, the tail of the failure text. Parametrised
tests are kept per parameter set; the checker folds them onto the function's node id."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

#: imports nothing from the app: ``-p`` loads this before tests/conftest.py sets the test environment
MARKER = "parity(*row_ids): CRBS parity inventory rows this test proves (tests/parity/inventory.py)"
_RANK = {"passed": 0, "skipped": 1, "failed": 2}
_tests: dict[str, dict[str, Any]] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--parity-json", default=None, help="write the parity results (JSON) to this file")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", MARKER)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        rows = [str(a) for m in item.iter_markers("parity") for a in m.args]
        _tests.setdefault(item.nodeid, {"outcome": "passed", "duration": 0.0, "rows": rows, "ran": False})


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    rec = _tests.setdefault(report.nodeid, {"outcome": "passed", "duration": 0.0, "rows": [], "ran": False})
    rec["ran"] = True
    rec["duration"] = round(rec["duration"] + report.duration, 3)
    outcome = "failed" if report.failed else "skipped" if report.skipped else "passed"
    if _RANK[outcome] > _RANK[rec["outcome"]]:
        rec["outcome"] = outcome
        if outcome != "passed":
            rec["phase"] = report.when
            rec["detail"] = str(report.longrepr)[-1500:]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    path = session.config.getoption("--parity-json")
    if not path:
        return
    ran = {k: v for k, v in _tests.items() if v["ran"]}
    Path(path).write_text(
        json.dumps({"exitstatus": int(exitstatus), "tests": ran}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
