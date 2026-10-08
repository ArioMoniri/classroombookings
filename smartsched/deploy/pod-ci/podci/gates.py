"""The gates pod CI runs for every new commit: the jobs of .github/workflows/smartsched.yml, in Docker.

Each gate is a bash script in ../gates (host side; it starts its own containers). `needs` lists gates that
must have succeeded first (otherwise the gate is skipped). Non-blocking gates never fail a run.
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


GATES: tuple[Gate, ...] = (
    Gate("prepare", "prepare.sh", "CI images (python CI image, Playwright image)", timeout=1200),
    Gate("validate", "validate.sh", "deploy/validate.sh", needs=("prepare",), timeout=300),
    Gate("backend", "backend.sh", "ruff + mypy + pytest + solver + migrations", needs=("prepare",), timeout=2400),
    Gate("infra", "infra.sh", "pod CI + AWS bootstrap tests", needs=("prepare",), timeout=600),
    Gate("frontend", "frontend.sh", "tsc + eslint + vitest", needs=("prepare",), timeout=1800),
    Gate("e2e-real", "e2e-real.sh", "Playwright (all specs) vs real backend + Bahar fixtures",
         needs=("frontend", "backend"), timeout=3600),
    Gate("images", "images.sh", "docker build backend/frontend/crbs", needs=("prepare",), timeout=2700),
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
