"""Base images pinned by digest (ROADMAP Phase 5): smartsched/deploy/pins.py checks and refreshes the pins that
validate.sh, the images gate and pin-digests.sh share."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from podfakes import POD_CI, REPO

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pins", REPO / "smartsched/deploy/pins.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pins"] = mod
    spec.loader.exec_module(mod)
    return mod


pins = load()


def tree(tmp: Path, *, db: str = f"postgres:16.15-alpine3.24@{D1}", py_arg: str = f"python:3.12.15-slim@{D1}",
         py_default: str = "python:3.12.15-slim", ci: str | None = None) -> Path:
    ci = ci or py_arg
    (tmp / "smartsched/deploy/pod-ci/podci").mkdir(parents=True)
    (tmp / "smartsched/deploy/pod-ci/gates").mkdir(parents=True)
    (tmp / "smartsched/backend").mkdir(parents=True)
    (tmp / "smartsched/frontend").mkdir(parents=True)
    (tmp / "smartsched/deploy/legacy").mkdir(parents=True)
    (tmp / "smartsched/deploy/docker-compose.yml").write_text(f"""services:
  db:
    image: {db}
  backend:
    build:
      context: ../backend
      args:
        EXTRA_PIP: ${{BACKEND_EXTRA_PIP:-}}
        PYTHON_IMAGE: {py_arg}
    image: smartsched-backend:${{SMARTSCHED_TAG:-0.1.0}}
  frontend:
    build:
      context: ../frontend
      args:
        NODE_IMAGE: node:22.23.3-alpine3.24@{D1}
        NEXT_PUBLIC_API_URL: ${{NEXT_PUBLIC_API_URL:-http://backend:8000}}
    image: smartsched-frontend:${{SMARTSCHED_TAG:-0.1.0}}
  crbs:
    build:
      context: ../..
      dockerfile: smartsched/deploy/legacy/Dockerfile
      args:
        PHP_IMAGE: php:8.3.35-apache-bookworm@{D1}
    image: smartsched-crbs:${{SMARTSCHED_TAG:-0.1.0}}
""")
    files = {
        "smartsched/deploy/docker-compose.caddy.yml": f"services:\n  caddy:\n    image: caddy:2.11.7-alpine@{D1}\n",
        "smartsched/backend/Dockerfile": f"ARG PYTHON_IMAGE={py_default}\nFROM ${{PYTHON_IMAGE}} AS base\n",
        "smartsched/frontend/Dockerfile": "ARG NODE_IMAGE=node:22.23.3-alpine3.24\nFROM ${NODE_IMAGE}\n",
        "smartsched/deploy/legacy/Dockerfile": "ARG PHP_IMAGE=php:8.3.35-apache-bookworm\nFROM ${PHP_IMAGE}\n",
        "smartsched/deploy/pod-ci/podci/config.py": f'    python_image: str = "{ci}"\n',
        "smartsched/deploy/pod-ci/gates/python-ci.Dockerfile": f"ARG PYTHON_IMAGE={ci}\nFROM ${{PYTHON_IMAGE}}\n",
    }
    for rel, text in files.items():
        (tmp / rel).write_text(text)
    return tmp


def test_fully_pinned_tree_passes(tmp_path: Path) -> None:
    assert pins.check(tree(tmp_path)) == []


@pytest.mark.parametrize(("kw", "needle"), [
    ({"db": "postgres:16.15-alpine3.24"}, "db: image postgres:16.15-alpine3.24 has no @sha256 digest"),
    ({"py_arg": "python:3.12.15-slim"}, "backend: build arg PYTHON_IMAGE=python:3.12.15-slim has no @sha256 digest"),
    ({"py_default": "python:3.12.16-slim"}, "PYTHON_IMAGE: compose python:3.12.15-slim, Dockerfile default "
                                            "python:3.12.16-slim"),
    ({"ci": f"python:3.12.15-slim@{D2}"}, "pod CI python image"),
])
def test_unpinned_or_drifting_refs_fail(tmp_path: Path, kw: dict[str, str], needle: str) -> None:
    errors = pins.check(tree(tmp_path, **kw))
    assert any(needle in e for e in errors), errors


def test_build_args_for_the_images_gate(tmp_path: Path) -> None:
    root = tree(tmp_path)
    assert pins.build_args(root, "backend") == ["--build-arg", "EXTRA_PIP=",
                                                 "--build-arg", f"PYTHON_IMAGE=python:3.12.15-slim@{D1}"]
    assert pins.build_args(root, "frontend")[-1] == "NEXT_PUBLIC_API_URL=http://backend:8000"


def test_refresh_rewrites_every_occurrence_with_the_resolved_digest(tmp_path: Path) -> None:
    root = tree(tmp_path)
    seen: list[str] = []

    def resolve(ref: str) -> str:
        seen.append(ref)
        return D2 if ref.startswith("python:") else D1

    changed = pins.refresh(root, resolve)
    assert "python:3.12.15-slim" in seen and all("@" not in r for r in seen)
    assert changed == {f"python:3.12.15-slim@{D1}": f"python:3.12.15-slim@{D2}"}
    assert pins.check(root) == []  # compose, pod CI config and the CI Dockerfile moved together
    assert D2 in (root / "smartsched/deploy/pod-ci/podci/config.py").read_text()


def test_the_repository_is_pinned() -> None:
    assert pins.check(REPO) == []


def test_images_gate_builds_with_the_compose_args(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$FAKE_LOG"\n')
    (bin_dir / "docker").chmod(0o755)
    src = tree(tmp_path / "ws/src")
    (src / "smartsched/deploy/pins.py").write_text((REPO / "smartsched/deploy/pins.py").read_text())
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "log"), "WS": str(tmp_path / "ws"),
           "CACHE_DIR": str(tmp_path / "c"), "RUN_TAG": "5-x", "CI_UID": "1", "CI_GID": "1",
           "GATES_DIR": str(POD_CI / "gates")}
    r = subprocess.run(["bash", str(POD_CI / "gates/images.sh")], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    builds = [c for c in (tmp_path / "log").read_text().splitlines() if c.startswith("build ")]
    assert f"--build-arg PYTHON_IMAGE=python:3.12.15-slim@{D1}" in builds[0]
    assert f"--build-arg NODE_IMAGE=node:22.23.3-alpine3.24@{D1}" in builds[1]
    assert "--build-arg NEXT_PUBLIC_API_URL=http://backend:8000" in builds[1]
    assert f"--build-arg PHP_IMAGE=php:8.3.35-apache-bookworm@{D1}" in builds[2]
