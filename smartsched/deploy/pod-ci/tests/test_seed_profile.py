"""Deploy seed profiles (smartsched/deploy/profile.env + seed/seed.py + deploy.sh): parsing, the idempotent
marker, the branch-specific merge attribute, both profiles planned against the repo's seed files."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from podfakes import REPO

DEPLOY = REPO / "smartsched/deploy"
_spec = importlib.util.spec_from_file_location("deploy_seed", DEPLOY / "seed/seed.py")
assert _spec and _spec.loader
seed = importlib.util.module_from_spec(_spec)
sys.modules["deploy_seed"] = seed
_spec.loader.exec_module(seed)

ALL = [s.name for s in seed.INSTITUTION]
IMPORTS = [s.name for s in seed.INSTITUTION if not s.optional_cli]


@pytest.mark.parametrize(
    ("text", "want"),
    [
        (None, "empty"),
        ("", "empty"),
        ("# only a comment\n", "empty"),
        ("SEED_PROFILE=institution\n", "institution"),
        ("SEED_PROFILE='empty'  # universal\n", "empty"),
        ('export SEED_PROFILE="institution"\n', "institution"),
        ("SEED_PROFILE=empty\nSEED_PROFILE=institution\n", "institution"),  # last wins, like deploy.sh
        ("SEED_PROFILE=\n", "empty"),
    ],
)
def test_parse_profile(text: str | None, want: str) -> None:
    assert seed.parse_profile(text) == want


def test_unknown_profile_is_refused() -> None:
    with pytest.raises(ValueError, match="expected one of"):
        seed.parse_profile("SEED_PROFILE=demo\n")


def _deploy_profile(tmp_path: Path, text: str | None, env: str = "") -> subprocess.CompletedProcess[str]:
    f = tmp_path / "profile.env"
    if text is not None:
        f.write_text(text)
    fn = subprocess.run(["sed", "-n", "/^seed_profile()/,/^}/p", str(DEPLOY / "deploy.sh")], capture_output=True,
                        text=True, check=True).stdout
    script = f'die() {{ echo "$*" >&2; exit 1; }}\nPROFILE_FILE={f}\n{fn}\nseed_profile\n'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "SEED_PROFILE": env})


@pytest.mark.parametrize("text", [None, "SEED_PROFILE=institution\n", "SEED_PROFILE='empty'  # x\n",
                                  "export SEED_PROFILE=institution\n", "SEED_PROFILE=\n"])
def test_deploy_sh_reads_the_profile_like_seed_py(tmp_path: Path, text: str | None) -> None:
    r = _deploy_profile(tmp_path, text)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == seed.parse_profile(text)


def test_deploy_sh_env_override_and_refusal(tmp_path: Path) -> None:
    assert _deploy_profile(tmp_path, "SEED_PROFILE=institution\n", env="empty").stdout.strip() == "empty"
    bad = _deploy_profile(tmp_path, "SEED_PROFILE=demo\n")
    assert bad.returncode == 1 and "expected empty or institution" in bad.stderr


def test_deploy_sh_seeds_after_up_and_update() -> None:
    text = (DEPLOY / "deploy.sh").read_text()
    up, update = text.split("\n  up)\n")[1], text.split("\n  update)\n")[1].split("\n  up)\n")[0]
    for body in (up, update):
        assert body.index("wait_healthy") < body.index("run_seed") < body.index("print_summary")
    assert "-v \"$SEED_FILES_DIR:/seed/files:ro\"" in text and "RUN_MIGRATIONS=0" in text


# ---- the idempotent marker --------------------------------------------------------------------------------------
class FakeStore:
    def __init__(self, marker: dict[str, Any] | None = None, terms: bool = False) -> None:
        self.marker, self.terms, self.puts = marker, terms, 0

    def get(self) -> dict[str, Any] | None:
        return self.marker

    def put(self, marker: dict[str, Any]) -> None:
        self.marker, self.puts = marker, self.puts + 1

    def has_terms(self) -> bool:
        return self.terms or self.marker is not None


class FakeCli:
    def __init__(self, commands: set[str], fail: str | None = None) -> None:
        self.commands, self.fail, self.calls = commands, fail, []  # type: ignore[var-annotated]

    def __call__(self, argv: Sequence[str]) -> int:
        self.calls.append(list(argv))
        if argv[0] not in self.commands:
            return seed.MISSING_CLI
        if self.fail and self.fail in " ".join(argv):
            return 1
        return 0

    def imports(self) -> list[list[str]]:
        return [c for c in self.calls if c[0] == "import"]


def test_institution_seed_runs_once_and_resumes_only_missing_steps() -> None:
    store, cli = FakeStore(), FakeCli({"import"})
    out = seed.run("institution", store, cli, "/seed/files", log=lambda _m: None)
    assert out.ran == IMPORTS and out.skipped == ["learning"]
    assert len(cli.imports()) == 7 and cli.imports()[0][2] == "/seed/files/bahar_derslikler_takvimi_2026.xlsx"
    assert store.marker and set(store.marker["steps"]) == set(IMPORTS) and store.marker["profile"] == "institution"
    # a second deploy: nothing is imported again
    cli2 = FakeCli({"import"})
    out2 = seed.run("institution", store, cli2, "/seed/files", log=lambda _m: None)
    assert out2.ran == [] and out2.already == IMPORTS and cli2.imports() == []
    # the learning CLI lands later: only that step runs
    cli3 = FakeCli({"import", "learning-refresh"})
    out3 = seed.run("institution", store, cli3, "/seed/files", log=lambda _m: None)
    assert out3.ran == ["learning"] and cli3.imports() == [] and set(store.marker["steps"]) == set(ALL)


def test_failed_step_keeps_finished_steps_for_the_next_deploy() -> None:
    store = FakeStore()
    with pytest.raises(RuntimeError, match="guz-planning failed"):
        seed.run("institution", store, FakeCli({"import"}, fail="guz_derslik_planlama"), "/f", log=lambda _m: None)
    assert store.marker and list(store.marker["steps"]) == ["bahar-grid", "bahar-planning", "guz-grid"]
    cli = FakeCli({"import"})
    out = seed.run("institution", store, cli, "/f", log=lambda _m: None)
    assert out.ran[0] == "guz-planning" and len(cli.imports()) == 4


def test_hand_loaded_data_and_other_profiles_are_left_alone() -> None:
    cli = FakeCli({"import"})
    out = seed.run("institution", FakeStore(terms=True), cli, "/f", log=lambda _m: None)
    assert cli.calls == [] and "loaded by hand" in out.note
    assert seed.run("institution", FakeStore(terms=True), FakeCli({"import"}), "/f", force=True,
                    log=lambda _m: None).ran == IMPORTS
    other = FakeStore({"profile": "empty", "version": 1, "steps": {}})
    assert "not changing" in seed.run("institution", other, cli, "/f", log=lambda _m: None).note and cli.calls == []


def test_empty_profile_touches_nothing() -> None:
    store, cli = FakeStore(), FakeCli({"import"})
    out = seed.run("empty", store, cli, "/f", log=lambda _m: None)
    assert out.ran == [] and cli.calls == [] and store.puts == 0 and store.marker is None


# ---- repository wiring ------------------------------------------------------------------------------------------
def test_both_profiles_plan_against_the_repo_seed_files(tmp_path: Path) -> None:
    fixtures = REPO / "smartsched/backend/tests/fixtures"
    assert seed.plan("institution", fixtures) == [] and seed.plan("empty", fixtures) == []
    assert seed.plan("institution", tmp_path) and seed.plan("empty", tmp_path) == []


def test_profile_file_is_valid_and_merge_ours() -> None:
    assert seed.read_profile(DEPLOY / "profile.env") in seed.PROFILES
    assert seed.read_profile(DEPLOY / "does-not-exist.env") == "empty"
    attrs = (REPO / ".gitattributes").read_text().splitlines()
    assert "smartsched/deploy/profile.env merge=ours" in attrs
    r = subprocess.run(["git", "-C", str(REPO), "check-attr", "merge", "smartsched/deploy/profile.env"],
                       capture_output=True, text=True)
    if r.returncode == 0:  # a git checkout (the pod's workspace is a git archive)
        assert r.stdout.strip().endswith("merge: ours")


def test_seed_steps_match_the_record_stack() -> None:
    """The seed loads exactly the files the e2e / record stacks import (scripts/record/stack.sh)."""
    stack = (REPO / "scripts/record/stack.sh").read_text()
    for s in seed.INSTITUTION:
        for f in s.files:
            assert f in stack, f
