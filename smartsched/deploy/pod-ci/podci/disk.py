"""Keep the root disk under PODCI_DISK_MAX_PERCENT (default 70 %), cheapest cleanup first."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from podci.config import Config
from podci.state import Store

Exec = Callable[[list[str]], int]


def usage_percent(path: Path = Path("/")) -> float:
    u = shutil.disk_usage(path)
    return 100.0 * u.used / u.total


def cleanup_steps(cfg: Config, store: Store) -> list[tuple[str, Callable[[Exec], None]]]:
    def old_runs(_: Exec) -> None:
        ids = store.old_run_ids(cfg.keep_runs)
        for rid in ids:
            shutil.rmtree(cfg.logs_dir / str(rid), ignore_errors=True)
        store.delete_runs(ids)

    def workspaces(_: Exec) -> None:
        if cfg.work_dir.exists():
            for d in cfg.work_dir.iterdir():
                shutil.rmtree(d, ignore_errors=True)

    def caches(_: Exec) -> None:
        for sub in ("npm", "pip"):
            shutil.rmtree(cfg.cache_dir / sub, ignore_errors=True)

    def run_all(*cmds: list[str]) -> Callable[[Exec], None]:
        def step(execute: Exec) -> None:
            for cmd in cmds:
                execute(cmd)
        return step

    return [
        ("stale workspaces", workspaces),
        (f"runs beyond the last {cfg.keep_runs}", old_runs),
        ("dangling images + build cache above 4 GB", run_all(["docker", "image", "prune", "-f"],
                                                             ["docker", "builder", "prune", "-f",
                                                              "--keep-storage", "4GB"])),
        ("unused images older than 24 h", run_all(["docker", "image", "prune", "-af", "--filter", "until=24h"])),
        ("all build cache", run_all(["docker", "builder", "prune", "-af"])),
        ("npm/pip caches", caches),
        ("all unused images", run_all(["docker", "image", "prune", "-af"])),
    ]


def ensure(cfg: Config, store: Store, execute: Exec, usage: Callable[[], float] = usage_percent,
           log: Callable[[str], None] = print) -> list[str]:
    """Run cleanup steps until usage < limit. Images used by running containers are never removed
    (docker prune only removes unused ones), so the live stack is safe. Returns the steps taken."""
    taken: list[str] = []
    for name, step in cleanup_steps(cfg, store):
        pct = usage()
        if pct < cfg.disk_max_percent:
            break
        log(f"disk {pct:.0f}% >= {cfg.disk_max_percent}%: cleaning {name}")
        step(execute)
        taken.append(name)
    return taken
