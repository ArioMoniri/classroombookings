"""Faster "green -> live": first boot only prepares images, the boot unit waits for the first deploy, the deploy gate
reuses the images gate's images (full-sha keyed) and checks the public URL, e2e failure context outlives the
workspace (capped, last 3 runs)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from podfakes import POD_CI, SHA_A, SHA_B, FakeReporter, FakeRun
from test_worker import CheckoutStubWorker, FakeExecute, queue

from podci import disk
from podci.cloud import NoCloud
from podci.config import Config
from podci.gates import DEPLOY, GATES
from podci.state import Store

GATES_DIR = POD_CI / "gates"

FAKE = """#!/usr/bin/env bash
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$FAKE_LOG"
case "$(basename "$0") $1 $2" in
  "docker image inspect") for img in $FAKE_IMAGES; do [[ "$3" == "$img" ]] && exit 0; done; exit 1 ;;
esac
[[ "$(basename "$0")" == curl ]] && { [[ "$*" == *127.0.0.1* || -n "${FAKE_PUBLIC_OK:-}" ]] && echo '{"db":true}'; }
exit 0
"""


def fake_bin(tmp_path: Path, names: tuple[str, ...] = ("docker", "git", "curl")) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in names:
        (bin_dir / name).write_text(FAKE)
        (bin_dir / name).chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "calls.log")}


def deploy_checkout(tmp_path: Path, env_text: str) -> Path:
    deploy = tmp_path / "src/smartsched/deploy"
    deploy.mkdir(parents=True)
    (deploy / ".env").write_text(env_text)
    (deploy / "deploy.sh").write_text('#!/usr/bin/env bash\nprintf "deploy.sh %s\\n" "$*" >> "$FAKE_LOG"\n')
    (deploy / "deploy.sh").chmod(0o755)
    return deploy


def run_deploy_gate(tmp_path: Path, env_text: str, images: list[str], **extra: str) -> tuple[int, str, list[str]]:
    deploy_checkout(tmp_path, env_text)
    env = {**fake_bin(tmp_path), "DEPLOY_DIR": str(tmp_path / "src"), "DEPLOY_FLAGS": "--tls",
           "DEPLOY_SHA": SHA_A, "FAKE_IMAGES": " ".join(images), **extra}
    r = subprocess.run(["bash", str(GATES_DIR / "deploy.sh")], env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr, (tmp_path / "calls.log").read_text().splitlines()


CI_IMAGES = [f"smartsched-{s}:ci-{SHA_A}" for s in ("backend", "frontend", "crbs")]


def test_deploy_gate_reuses_the_images_gate_images_for_the_same_full_sha(tmp_path: Path) -> None:
    code, out, calls = run_deploy_gate(tmp_path, "PROXY_PORT=8080\nTLS_DOMAIN=pod.example.test\n", CI_IMAGES,
                                       FAKE_PUBLIC_OK="1")
    assert code == 0, out
    for svc in ("backend", "frontend", "crbs"):
        assert f"docker tag smartsched-{svc}:ci-{SHA_A} smartsched-{svc}:0.1.0" in calls
    assert "deploy.sh --update --no-pull --no-build --tls" in calls
    assert "public check: https://pod.example.test/api/v1/health healthy" in out


def test_deploy_gate_builds_when_an_image_is_missing_or_the_env_changes_build_args(tmp_path: Path) -> None:
    code, out, calls = run_deploy_gate(tmp_path / "a", "PROXY_PORT=8080\n", CI_IMAGES[:2])
    assert code == 0, out
    assert "deploy.sh --update --no-pull --tls" in calls and not any(c.startswith("docker tag") for c in calls)
    assert "public check: no TLS_DOMAIN" in out
    code, out, calls = run_deploy_gate(tmp_path / "b", "NEXT_PUBLIC_API_URL=https://other.example.test\n", CI_IMAGES)
    assert code == 0 and "deploy.sh --update --no-pull --tls" in calls  # compose would bake another URL in
    code, out, calls = run_deploy_gate(tmp_path / "c", "PROXY_PORT=8080\n", [f"smartsched-{s}:ci-{SHA_B}"
                                                                           for s in ("backend", "frontend", "crbs")])
    assert "deploy.sh --update --no-pull --tls" in calls  # another commit's images are never used


def test_deploy_gate_public_check_is_report_only_and_shows_the_proxy_log(tmp_path: Path) -> None:
    code, out, calls = run_deploy_gate(tmp_path, "TLS_DOMAIN=pod.example.test\n", [])
    assert code == 0, out
    assert "NOT healthy (report only" in out and "proxy / caddy log (tail)" in out
    assert any("logs --no-color --tail 40 caddy" in c for c in calls)


def test_deploy_timeout_and_no_build_support() -> None:
    assert DEPLOY.timeout == 3600
    deploy_sh = (POD_CI.parent / "deploy.sh").read_text()
    update = deploy_sh[deploy_sh.index("  update)"):deploy_sh.index("  prepare)")]
    assert "NO_BUILD -eq 1" in update and "missing_local_images" in update and "build --pull" in update
    images = (GATES_DIR / "images.sh").read_text()
    assert 'ci-${RUN_SHA}' in images and "RUN_DEPLOY" in images
    order = [g.name for g in GATES]
    assert order.index("e2e-build") < order.index("images") < order.index("e2e-real-1")


def test_deploy_step_gets_the_sha_and_gates_get_the_artifact_dir(cfg: Config, store: Store) -> None:
    rid = queue(store)
    ex = FakeExecute()
    CheckoutStubWorker(cfg, store, FakeReporter(), NoCloud(), lambda: "tok", execute=ex, run_cmd=FakeRun(),
                       log=lambda _: None, disk_usage=lambda: 10.0).work()
    deploy_env = ex.envs[ex.scripts.index("deploy.sh")]
    assert deploy_env["DEPLOY_SHA"] == SHA_A
    gate_env = ex.envs[ex.scripts.index("e2e-real.sh")]
    assert gate_env["ARTIFACT_DIR"] == str(cfg.logs_dir / str(rid) / "artifacts")
    assert gate_env["RUN_SHA"] == SHA_A and gate_env["RUN_DEPLOY"] == "1"


# ---- boot ------------------------------------------------------------------------------------------------
def test_boot_before_the_first_deploy_starts_nothing_and_succeeds(tmp_path: Path) -> None:
    deploy_checkout(tmp_path, "PROXY_PORT=8080\n")
    env = {**fake_bin(tmp_path, ("docker", "git")), "PODCI_DEPLOY_DIR": str(tmp_path / "src"),
           "PODCI_STATE_DIR": str(tmp_path / "state")}
    r = subprocess.run(["bash", str(GATES_DIR / "stack-up.sh")], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "first deploy pending" in r.stdout
    log = tmp_path / "calls.log"
    assert not log.exists() or "docker" not in log.read_text()


# ---- e2e failure context --------------------------------------------------------------------------------
def keep_fn() -> str:
    text = (GATES_DIR / "e2e-real.sh").read_text()
    m = re.search(r"^keep_failure_context\(\) \{.*?^\}", text, re.S | re.M)
    assert m
    return m.group(0)


def test_e2e_keeps_only_error_context_files_capped(tmp_path: Path) -> None:
    ws, art = tmp_path / "ws", tmp_path / "logs/7/artifacts"
    res = ws / "e2e-shard-2/test-results"
    for i in range(3):
        d = res / f"spec-{i}-chromium"
        d.mkdir(parents=True)
        (d / "error-context.md").write_text("# Page snapshot\n" + "x" * 40_000)
        (d / "trace.zip").write_bytes(b"0" * 1000)
    script = keep_fn() + "\nkeep_failure_context\n"
    env = {"PATH": os.environ["PATH"], "WS": str(ws), "sdir": "e2e-shard-2", "idx": "2", "ARTIFACT_DIR": str(art),
           "ARTIFACT_MAX_BYTES": "10000000"}
    r = subprocess.run(["bash", "-c", "set -euo pipefail; WS=$WS; sdir=$sdir; idx=$idx\n" + script], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    kept = sorted(p.relative_to(art).as_posix() for p in art.rglob("*") if p.is_file())
    assert kept == [f"e2e-shard-2/spec-{i}-chromium/error-context.md" for i in range(3)]
    # the cap: room for two 40 kB files (plus directories), not three
    art2 = tmp_path / "logs/8/artifacts"
    env.update(ARTIFACT_DIR=str(art2), ARTIFACT_MAX_BYTES="100000")
    r = subprocess.run(["bash", "-c", "set -euo pipefail; WS=$WS; sdir=$sdir; idx=$idx\n" + script], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "reached" in r.stdout
    assert 1 <= len([p for p in art2.rglob("error-context.md")]) < 3
    # no ARTIFACT_DIR: nothing happens
    env.pop("ARTIFACT_DIR")
    r = subprocess.run(["bash", "-c", "set -euo pipefail; WS=$WS; sdir=$sdir; idx=$idx\nARTIFACT_DIR=\n" + script],
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0


def test_cleanup_copies_the_context_before_the_workspace_goes() -> None:
    text = (GATES_DIR / "e2e-real.sh").read_text()
    cleanup = text[text.index("cleanup() {"):]
    assert cleanup.index("keep_failure_context") < cleanup.index("docker rm -f")
    assert "trap 'exit 143' TERM INT" in text


def test_artifacts_are_kept_for_the_last_three_runs(cfg: Config) -> None:
    for rid in (3, 5, 9, 12, 13):
        (cfg.logs_dir / str(rid) / "artifacts").mkdir(parents=True)
        (cfg.logs_dir / str(rid) / "backend.log").write_text("log")
    (cfg.logs_dir / "14").mkdir()  # a run without artifacts does not count
    assert disk.prune_artifacts(cfg) == [5, 3]
    assert sorted(int(d.name) for d in cfg.logs_dir.iterdir() if (d / "artifacts").exists()) == [9, 12, 13]
    assert (cfg.logs_dir / "3" / "backend.log").exists()  # the gate logs stay (keep_runs trims those)
