"""SECURITY F13 / W3E-05: hash-pinned backend locks, installed with ``pip install --require-hashes``.

Three files in smartsched/backend, regenerated together by ``make lock`` (uv, from the existing pins):
``requirements.lock`` (what the image ships), ``requirements-build.lock`` (setuptools, the build backend, so the
package is built without an unverified isolated build environment) and ``requirements-dev.lock`` (the runtime pins
plus pytest / ruff / mypy for pod CI). Every pin carries at least one sha256 hash, the runtime versions are the
same in the dev lock, and both the Dockerfile and the pod CI backend gate install in hash-checking mode.
"""

from __future__ import annotations

import re

from podfakes import REPO

BACKEND = REPO / "smartsched/backend"
LOCKS = ("requirements.lock", "requirements-build.lock", "requirements-dev.lock")
PIN = re.compile(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;\\]+)", re.M)


def pins(name: str) -> dict[str, str]:
    """``{distribution: version}`` of one lock; each requirement block must end in at least one hash."""
    text = (BACKEND / name).read_text(encoding="utf-8")
    blocks = re.split(r"\n(?=[A-Za-z0-9])", text.split("\n", 2)[-1])
    out: dict[str, str] = {}
    for block in blocks:
        m = PIN.match(block)
        if not m:
            continue
        assert "--hash=sha256:" in block, f"{name}: {m.group(1)} has no hash"
        assert all(len(h) == 64 for h in re.findall(r"--hash=sha256:([0-9a-f]+)", block)), f"{name}: {m.group(1)}"
        out[m.group(1).lower().replace("_", "-")] = m.group(2)
    return out


def test_every_lock_pins_with_hashes() -> None:
    for name in LOCKS:
        found = pins(name)
        assert found, f"{name} pins nothing"
        text = (BACKEND / name).read_text(encoding="utf-8")
        assert not re.search(r"^[A-Za-z0-9_.\-]+(?:\[[^\]]*\])?\s*(?:>=|<=|~=|>|<)", text, re.M), f"{name}: unpinned"


def test_dev_lock_carries_the_runtime_versions_unchanged() -> None:
    runtime, dev = pins("requirements.lock"), pins("requirements-dev.lock")
    for dist, version in runtime.items():
        assert dev.get(dist) == version, f"{dist}: runtime {version}, dev {dev.get(dist)}"
    for tool in ("pytest", "pytest-asyncio", "ruff", "mypy"):
        assert tool in dev, f"{tool} missing from requirements-dev.lock"


def test_build_lock_is_only_the_build_backend_and_does_not_overlap() -> None:
    build = pins("requirements-build.lock")
    assert set(build) == {"setuptools"}
    assert not set(build) & set(pins("requirements.lock"))
    assert not set(build) & set(pins("requirements-dev.lock"))


def test_dockerfile_installs_in_hash_checking_mode() -> None:
    df = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY pyproject.toml README.md requirements.lock requirements-build.lock ./" in df
    assert "pip install --require-hashes -r requirements.lock -r requirements-build.lock" in df
    # the package itself: no deps (all came hashed) and no isolated build env fetched from the index
    assert "pip install --no-deps --no-build-isolation ." in df
    assert "-c requirements.lock" not in df


def test_pod_ci_backend_gate_installs_in_hash_checking_mode() -> None:
    # the backend venv install of backend.sh and backend-unit.sh lives in gates/backend-lib.sh
    gate = (REPO / "smartsched/deploy/pod-ci/gates/backend-lib.sh").read_text(encoding="utf-8")
    for script in ("backend.sh", "backend-unit.sh"):
        text = (REPO / "smartsched/deploy/pod-ci/gates" / script).read_text(encoding="utf-8")
        assert 'source "$(dirname "${BASH_SOURCE[0]}")/backend-lib.sh"' in text and '"$PY_VENV"' in text
        assert "pip install" not in text
    assert (
        "pip install -q --require-hashes -r smartsched/backend/requirements-dev.lock"
        " -r smartsched/backend/requirements-build.lock" in gate
    )
    assert 'pip install -q --no-deps --no-build-isolation -e "./smartsched/backend"' in gate
    assert "-c smartsched/backend/requirements.lock" not in gate


def test_make_lock_regenerates_all_three_from_the_existing_pins() -> None:
    mk = (BACKEND / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^lock:", mk, re.M)
    assert "--generate-hashes" in mk
    for name in LOCKS:
        assert f"-o {name}" in mk
    assert "-c requirements.lock" in mk  # the dev lock keeps the runtime versions


def test_github_workflow_installs_in_hash_checking_mode() -> None:
    wf = (REPO / ".github/workflows/smartsched.yml").read_text(encoding="utf-8")
    assert "pip install --require-hashes -r requirements-dev.lock -r requirements-build.lock" in wf
    assert 'pip install -e ".[dev]"' not in wf
