"""Backend image dependencies (review P19-Q3, ROADMAP Phase 5 "commit requirements.lock"): the intake parsers are
main dependencies, the image build is pinned by smartsched/backend/requirements.lock, and the images gate imports
them in the freshly built backend image."""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from pathlib import Path

from podfakes import POD_CI, REPO

BACKEND = REPO / "smartsched/backend"
INTAKE = {"xlrd": "2.0.1", "defusedxml": None, "pdfplumber": None, "pypdfium2": None, "icalendar": None}
# distribution -> import name, for the image smoke import
MODULES = ("xlrd", "defusedxml", "pdfplumber", "pypdfium2", "icalendar", "docx", "pypdf", "openpyxl", "ortools")


def _name(req: str) -> str:
    return re.split(r"[\s<>=!~\[;]", req, maxsplit=1)[0].lower()


def project() -> dict[str, object]:
    return tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_intake_parsers_are_main_dependencies() -> None:
    proj = project()
    main = {_name(r): r for r in proj["dependencies"]}  # type: ignore[union-attr]
    dev = {_name(r) for r in proj["optional-dependencies"]["dev"]}  # type: ignore[index]
    for dist, floor in INTAKE.items():
        assert dist in main, f"{dist} must be a main dependency"
        assert ">=" in main[dist], f"{dist} needs a lower bound: {main[dist]}"
        if floor:
            assert f">={floor}" in main[dist]
    assert "icalendar" not in dev  # moved dev -> main


def test_requirements_lock_pins_every_main_dependency() -> None:
    lock = (BACKEND / "requirements.lock").read_text(encoding="utf-8")
    pinned = {m.group(1).lower().replace("_", "-") for m in re.finditer(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==", lock,
                                                                         re.M)}
    for req in project()["dependencies"]:  # type: ignore[union-attr]
        assert _name(req).replace("_", "-") in pinned, f"{req} is not pinned in requirements.lock"
    assert "--hash" not in lock  # used as a pip constraints file (-c) by the Dockerfile
    assert "requirements.lock" in (BACKEND / "Dockerfile").read_text(encoding="utf-8")


def test_images_gate_imports_the_parsers_in_the_built_backend_image(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$FAKE_LOG"\n')
    (bin_dir / "docker").chmod(0o755)
    (tmp_path / "ws/src").mkdir(parents=True)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "docker.log"),
           "WS": str(tmp_path / "ws"), "CACHE_DIR": str(tmp_path / "c"), "RUN_TAG": "3-abc", "CI_UID": "1",
           "CI_GID": "1", "GATES_DIR": str(POD_CI / "gates")}
    r = subprocess.run(["bash", str(POD_CI / "gates/images.sh")], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    calls = (tmp_path / "docker.log").read_text().splitlines()
    builds = [i for i, c in enumerate(calls) if c.startswith("build ") and "smartsched-backend:ci-3-abc" in c]
    smoke = [i for i, c in enumerate(calls) if c.startswith("run ") and "smartsched-backend:ci-3-abc" in c]
    assert builds and smoke and smoke[0] > builds[0]
    line = calls[smoke[0]]
    assert "--entrypoint python" in line and "--rm" in line
    for mod in MODULES:
        assert re.search(rf"\b{mod}\b", line), f"{mod} not imported by the image smoke test"
