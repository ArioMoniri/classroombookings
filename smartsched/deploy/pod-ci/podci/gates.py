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
    # concurrency slots (runner.py): a gate running two big containers at once (an e2e-real shard) or `next build`
    # takes 2
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
    # `next build` once per run (NEXT_PUBLIC_API_URL=http://backend:8000, the alias every shard's backend has), checked
    # for mock/demo code; the e2e-real shards copy it and only `next start` it. After vitest: nothing else writes the
    # frontend tree then. Two slots: the build's 3 GB heap (as in images)
    Gate("e2e-build", "e2e-build.sh", "next build for the e2e shards + no-mock-build check",
         needs=("frontend", "frontend-unit-1", "frontend-unit-2"), timeout=1800, weight=2),
    # three docker builds, `next build` with its own 3 GB heap. After e2e-build in this order: among the ready gates
    # the critical path (e2e-build -> the e2e shards) takes the slots first
    Gate("images", "images.sh", "docker build backend/frontend/crbs", needs=("prepare",), timeout=2700, weight=2),
    # 436 specs at ~14 s each on one worker (~100 min on 4 unthrottled cores, 2026-10-19) in one gate: three Playwright
    # shards (--shard=i/3), each with its own network, seeded backend, smtp sink, empty backend and OIDC issuer, so
    # they run at the same time (c7g.4xlarge: 6 slots, 3 x 2). Per shard ~35-50 min of specs + ~5-10 min seeding.
    # They need only the backend venv and the build: the backend pytest gates run alongside and still block the run
    # (and the deploy), they just no longer hold the shards back.
    Gate("e2e-real-1", "e2e-real.sh", "Playwright shard 1/3 vs real backend + Bahar fixtures",
         needs=("backend-deps", "e2e-build"), timeout=5400, weight=2, args=("1/3",)),
    Gate("e2e-real-2", "e2e-real.sh", "Playwright shard 2/3 vs real backend + Bahar fixtures",
         needs=("backend-deps", "e2e-build"), timeout=5400, weight=2, args=("2/3",)),
    Gate("e2e-real-3", "e2e-real.sh", "Playwright shard 3/3 vs real backend + Bahar fixtures",
         needs=("backend-deps", "e2e-build"), timeout=5400, weight=2, args=("3/3",)),
    # after every e2e-real shard so it reads this run's /w/playwright-report-<i>.json (args: the shard count); API rows
    # still run if e2e failed, a missing shard report fails the gate
    Gate("parity", "parity.sh", "CRBS superset gate (scripts/parity_check.py)",
         needs=("backend", "backend-unit-1", "backend-unit-2", "backend-unit-3"),
         after=("e2e-real-1", "e2e-real-2", "e2e-real-3"), timeout=1800, args=("3",)),
    # real workbooks, 4 solves (Bahar term ~5 min): planner-level violations fail the run
    Gate("planner", "planner.sh", "planner-level validation (tools/validate_planner.py)",
         needs=("backend", "backend-unit-1", "backend-unit-2", "backend-unit-3"), timeout=3600),
    Gate("watchdog", "watchdog.sh", "agent ledger report", blocking=False, needs=("prepare",), timeout=300),
)
# the first deploy builds every image on the pod (no image reuse yet): 1800 s was not enough
DEPLOY = Gate("deploy", "deploy.sh", "deploy.sh --update", timeout=3600)


def playwright_image(src: Path) -> str:
    """mcr.microsoft.com/playwright:v<version locked in package-lock.json>-noble (multi-arch)."""
    lock = json.loads((src / "smartsched/frontend/package-lock.json").read_text(encoding="utf-8"))
    version = lock["packages"]["node_modules/@playwright/test"]["version"]
    return f"mcr.microsoft.com/playwright:v{version}-noble"


def python_ci_image(gates_dir: Path, base: str) -> str:
    digest = hashlib.sha256((gates_dir / "python-ci.Dockerfile").read_bytes() + base.encode()).hexdigest()[:12]
    return f"smartsched-podci-python:{digest}"
