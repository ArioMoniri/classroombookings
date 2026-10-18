"""The gates fit a 2 vCPU / 8 GB arm64 pod that also runs the app (run #51: node heap out of memory).

Node containers get NODE_MEMORY and an explicit V8 heap below it; e2e-real's side containers are capped so the
whole e2e stack stays inside the pod; Playwright runs one worker; vitest caps its forks under CI; the image build
sets the heap for `next build`. Nothing is skipped: the frontend gate still runs `npm run check`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from podfakes import POD_CI, REPO
from test_e2e_stack import gate_env

GATES = POD_CI / "gates"


def docker_runs(tmp_path: Path) -> list[str]:
    return [c for c in (tmp_path / "docker.log").read_text().splitlines() if c.startswith("run ")]


def test_frontend_gate_sets_heap_and_memory_and_runs_the_full_check(tmp_path: Path) -> None:
    r = subprocess.run(["bash", str(GATES / "frontend.sh")], env=gate_env(tmp_path), capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    run = docker_runs(tmp_path)[0]
    assert "-e NODE_OPTIONS=--max-old-space-size=3072" in run
    # the later --memory wins over docker_common's GATE_MEMORY (3g)
    assert run.index("--memory 3g") < run.index("--memory 4g")
    assert "npm run check" in (tmp_path / "docker.log").read_text()


def test_node_memory_is_configurable(tmp_path: Path) -> None:
    env = {**gate_env(tmp_path), "NODE_MEMORY": "5g", "NODE_HEAP_MB": "4096"}
    subprocess.run(["bash", str(GATES / "frontend.sh")], env=env, capture_output=True, text=True, timeout=60,
                   check=True)
    run = docker_runs(tmp_path)[0]
    assert "--memory 5g --memory-swap 5g" in run and "--max-old-space-size=4096" in run


def test_e2e_real_caps_side_containers_and_runs_one_playwright_worker(tmp_path: Path) -> None:
    r = subprocess.run(["bash", str(GATES / "e2e-real.sh")], env=gate_env(tmp_path), capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    runs = docker_runs(tmp_path)
    smtp = next(c for c in runs if "--network-alias smtp " in c)
    empty = next(c for c in runs if "--network-alias backend-empty " in c)
    seeded = next(c for c in runs if "--network-alias backend " in c)
    assert "--memory 256m --memory-swap 256m" in smtp and "--memory 1g --memory-swap 1g" in empty
    assert "--memory 1g " not in seeded  # the seeded backend solves the full term: GATE_MEMORY
    assert "--max-old-space-size=3072" in runs[-1]
    log = (tmp_path / "docker.log").read_text()
    assert "npx playwright test --workers=1 " in log


def test_vitest_ci_caps_workers_heap_and_timeout() -> None:
    cfg = (REPO / "smartsched/frontend/vitest.config.mts").read_text()
    for needle in ("maxWorkers: TINY ? 1 : 2", '"--max-old-space-size=1536"', "cgroupLimitBytes", "testTimeout: 30_000", "process.env.CI"):
        assert needle in cfg, needle
    assert "workers: 1," in (REPO / "smartsched/frontend/playwright.config.ts").read_text()


def test_frontend_image_build_sets_the_heap_for_next_build() -> None:
    df = (REPO / "smartsched/frontend/Dockerfile").read_text()
    build = df[df.index("AS build"):df.index("AS runtime")]
    assert "NODE_OPTIONS=--max-old-space-size=${NODE_BUILD_HEAP_MB}" in build
    assert build.index("NODE_OPTIONS") < build.index("npm run build")


def test_gates_run_one_at_a_time() -> None:
    runner_src = (POD_CI / "podci/runner.py").read_text()
    assert "for g in self.gates:\n                results[g.name] = self._run_gate(" in runner_src
