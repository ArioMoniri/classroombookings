"""The gates pod CI runs for every new commit: the jobs of .github/workflows/smartsched.yml, in Docker.

Each gate is a bash script in ../gates (host side; it starts its own containers). `needs` lists gates that
must have succeeded first (otherwise the gate is skipped), `after` lists gates that must merely have finished. Gates
whose needs are met run concurrently (podci/runner.py, PODCI_PARALLEL slots; `weight` slots each). Non-blocking
gates never fail a run. `args` are passed to the script.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Gate:
    name: str
    script: str
    description: str
    blocking: bool = True
    needs: tuple[str, ...] = ()
    timeout: int = 1800
    args: tuple[str, ...] = ()
    # gates that must have finished (any result) before this one starts: ordering without a success dependency
    after: tuple[str, ...] = ()
    # concurrency slots (runner.py): a gate running two big containers at once (e2e-real) or `next build` takes 2
    weight: int = 1


GATES: tuple[Gate, ...] = (
    Gate("prepare", "prepare.sh", "CI images (python CI image, Playwright image)", timeout=1200),
    Gate("validate", "validate.sh", "deploy/validate.sh", needs=("prepare",), timeout=300),
    # ruff + format + mypy + pytest in one gate ran past 2400 s on the 2-CPU pod (runs #81, #82; pytest ~90 min at
    # 2 CPUs): the static checks, solver tests and migrations stay here, pytest runs in three shards
    # the backend venv (/w/venv) is built once here; backend and the shards only read it (they may run concurrently)
    Gate("backend-deps", "backend-deps.sh", "backend venv from the hash-pinned locks", needs=("prepare",),
         timeout=900),
    Gate("backend", "backend.sh", "ruff + format + mypy + solver + migrations", needs=("backend-deps",),
         timeout=1800),
    Gate("backend-unit-1", "backend-unit.sh", "pytest shard 1/3", needs=("backend-deps",), timeout=3600,
         args=("1/3",)),
    Gate("backend-unit-2", "backend-unit.sh", "pytest shard 2/3", needs=("backend-deps",), timeout=3600,
         args=("2/3",)),
    Gate("backend-unit-3", "backend-unit.sh", "pytest shard 3/3", needs=("backend-deps",), timeout=3600,
         args=("3/3",)),
    Gate("infra", "infra.sh", "pod CI + AWS bootstrap tests", needs=("prepare",), timeout=600),
    # tsc + eslint + vitest in one gate ran past 1800 s on the 2-CPU pod (runs #70, #81): the static checks and
    # two vitest shards are separate gates now, each well under its limit (2 CPUs: ~3-6 min / ~4-8 min per shard)
    Gate("frontend", "frontend.sh", "npm ci + tsc + eslint + check-design", needs=("prepare",), timeout=1800),
    # literal values only: scripts/docs/sync_docs.py reads this list without importing it
    Gate("frontend-unit-1", "frontend-unit.sh", "vitest shard 1/2", needs=("frontend",), timeout=1800,
         args=("1/2",)),
    Gate("frontend-unit-2", "frontend-unit.sh", "vitest shard 2/2", needs=("frontend",), timeout=1800,
         args=("2/2",)),
    # 436 specs at ~14 s each on one worker (~100 min on 4 unthrottled cores, 2026-10-19), so 3600 s could never pass
    Gate("e2e-real", "e2e-real.sh", "Playwright (all specs) vs real backend + Bahar fixtures",
         needs=("frontend", "frontend-unit-1", "frontend-unit-2", "backend", "backend-unit-1", "backend-unit-2",
                "backend-unit-3"), timeout=10800, weight=2),
    # after e2e-real so it reads this run's /w/playwright-report.json; API rows still run if e2e failed
    Gate("parity", "parity.sh", "CRBS superset gate (scripts/parity_check.py)",
         needs=("backend", "backend-unit-1", "backend-unit-2", "backend-unit-3"), after=("e2e-real",), timeout=1800),
    # real workbooks, 4 solves (Bahar term ~5 min): planner-level violations fail the run
    Gate("planner", "planner.sh", "planner-level validation (tools/validate_planner.py)",
         needs=("backend", "backend-unit-1", "backend-unit-2", "backend-unit-3"), timeout=3600),
    # three docker builds, `next build` with its own 3 GB heap
    Gate("images", "images.sh", "docker build backend/frontend/crbs", needs=("prepare",), timeout=2700, weight=2),
    Gate("watchdog", "watchdog.sh", "agent ledger report", blocking=False, needs=("prepare",), timeout=300),
)
DEPLOY = Gate("deploy", "deploy.sh", "deploy.sh --update", timeout=1800)


def playwright_image(src: Path) -> str:
    """mcr.microsoft.com/playwright:v<version locked in package-lock.json>-noble (multi-arch)."""
    lock = json.loads((src / "smartsched/frontend/package-lock.json").read_text(encoding="utf-8"))
    version = lock["packages"]["node_modules/@playwright/test"]["version"]
    return f"mcr.microsoft.com/playwright:v{version}-noble"


def python_ci_image(gates_dir: Path, base: str) -> str:
    digest = hashlib.sha256((gates_dir / "python-ci.Dockerfile").read_bytes() + base.encode()).hexdigest()[:12]
    return f"smartsched-podci-python:{digest}"
