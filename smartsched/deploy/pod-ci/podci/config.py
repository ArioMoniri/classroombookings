"""Pod CI configuration: /etc/smartsched-ci/ci.env (KEY=VALUE lines) overridden by the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_CONFIG_FILE = Path("/etc/smartsched-ci/ci.env")


def _split(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in value.split(",") if v.strip())


@dataclass(frozen=True)
class Config:
    repo: str = "ArioMoniri/classroombookings"
    branches: tuple[str, ...] = ("claude/gracious-cerf-w1598m", "claude/smartsched-universal")
    deploy_branch: str = "claude/gracious-cerf-w1598m"
    state_dir: Path = Path("/var/lib/smartsched-ci")
    deploy_dir: Path = Path("/opt/smartsched/src")
    install_dir: Path = Path("/opt/smartsched-ci")
    ssm_prefix: str = "/smartsched"
    # Local/testing alternative to SSM: a file holding the GitHub token.
    token_file: str = ""
    public_url: str = ""
    web_bind: str = "172.17.0.1"
    web_port: int = 8095
    # The app's own /auth/me through nginx on the host loopback (frontend route handler reads the cookie).
    me_url: str = "http://127.0.0.1:8080/api/v1/auth/me"
    disk_max_percent: int = 70
    keep_runs: int = 50
    status_context: str = "pod-ci"
    deploy_flags: tuple[str, ...] = ("--tls",)
    cloud: bool = True
    idle_stop: bool = True
    idle_alarm: str = "smartsched-pod-idle-stop"
    idle_minutes: int = 60
    idle_cpu: float = 5.0
    gate_cpus: str = "2"
    gate_memory: str = "3g"
    python_image: str = "python:3.12.15-slim-bookworm"
    max_attempts: int = 2
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.state_dir / "ci.sqlite3"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def work_dir(self) -> Path:
        return self.state_dir / "work"

    @property
    def cache_dir(self) -> Path:
        return self.state_dir / "cache"

    @property
    def mirror_dir(self) -> Path:
        return self.state_dir / "mirror.git"

    @property
    def gates_dir(self) -> Path:
        return self.install_dir / "gates"

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.repo}.git"

    def run_url(self, run_id: int) -> str:
        base = self.public_url.rstrip("/")
        return f"{base}/ci/runs/{run_id}" if base else ""


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def load(path: Path | None = None, environ: dict[str, str] | None = None) -> Config:
    env = dict(read_env_file(path or Path(os.environ.get("PODCI_CONFIG", str(DEFAULT_CONFIG_FILE)))))
    env.update({k: v for k, v in (os.environ if environ is None else environ).items() if k.startswith("PODCI_")})
    values: dict[str, object] = {}
    extra: dict[str, str] = {}
    known = {f.name: f for f in fields(Config) if f.name != "extra"}
    for key, raw in env.items():
        name = key.removeprefix("PODCI_").lower()
        if name == "config":
            continue
        if name not in known:
            extra[name] = raw
            continue
        default = getattr(Config, name, None)
        if isinstance(default, bool):
            values[name] = raw.strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(default, int):
            values[name] = int(raw)
        elif isinstance(default, float):
            values[name] = float(raw)
        elif isinstance(default, tuple):
            values[name] = _split(raw)
        elif isinstance(default, Path):
            values[name] = Path(raw)
        else:
            values[name] = raw
    return Config(**values, extra=extra)  # type: ignore[arg-type]
