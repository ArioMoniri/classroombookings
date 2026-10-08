"""Poller: git ls-remote parsing, token handling, enqueue/supersede and the statuses it posts."""

from __future__ import annotations

import base64

from podfakes import SHA_A, SHA_B, SHA_C, FakeReporter, FakeRun

from podci import gitops, runner
from podci.config import Config
from podci.state import QUEUED, SUPERSEDED, Store

LS = f"{SHA_A}\trefs/heads/claude/gracious-cerf-w1598m\n{SHA_B}\trefs/heads/claude/smartsched-universal\n"


def test_parse_ls_remote_ignores_noise() -> None:
    out = gitops.parse_ls_remote(LS + "garbage\n" + f"{SHA_C}\trefs/tags/v1\nnot-a-sha\trefs/heads/x\n")
    assert out == {"claude/gracious-cerf-w1598m": SHA_A, "claude/smartsched-universal": SHA_B}


def test_ls_remote_keeps_token_off_the_command_line() -> None:
    fake = FakeRun()
    calls = []

    def run(argv, **kw):  # type: ignore[no-untyped-def]
        calls.append((argv, kw["env"]))
        res = fake(argv, **kw)
        res.stdout = LS
        return res

    heads = gitops.ls_remote("https://github.com/o/r.git", ["claude/gracious-cerf-w1598m"], "ghp_SECRET", run=run)
    argv, env = calls[0]
    assert heads["claude/gracious-cerf-w1598m"] == SHA_A
    assert all("ghp_SECRET" not in a for a in argv)
    assert argv[:3] == ["git", "ls-remote", "--heads"] and argv[-1] == "refs/heads/claude/gracious-cerf-w1598m"
    expected = base64.b64encode(b"x-access-token:ghp_SECRET").decode()
    assert env["GIT_CONFIG_VALUE_0"] == f"AUTHORIZATION: basic {expected}"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_ls_remote_error_is_redacted() -> None:
    def run(argv, **kw):  # type: ignore[no-untyped-def]
        import subprocess

        return subprocess.CompletedProcess(argv, 128, stdout="", stderr="fatal: auth failed for ghp_SECRET")

    try:
        gitops.ls_remote("https://github.com/o/r.git", ["b"], "ghp_SECRET", run=run)
    except gitops.GitError as exc:
        assert "ghp_SECRET" not in str(exc) and "***" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected GitError")


def fake_ls(heads: dict[str, str]):  # type: ignore[no-untyped-def]
    def ls(url, branches, token):  # type: ignore[no-untyped-def]
        assert token == "tok"
        return {b: heads[b] for b in branches if b in heads}
    return ls


def test_poll_queues_new_heads_and_posts_pending(cfg: Config, store: Store) -> None:
    rep = FakeReporter()
    heads = {"claude/gracious-cerf-w1598m": SHA_A, "claude/smartsched-universal": SHA_B}
    runs = runner.poll(cfg, store, rep, "tok", ls_remote=fake_ls(heads), log=lambda _: None)
    assert [(r.branch, r.sha, r.deploy) for r in runs] == [
        ("claude/gracious-cerf-w1598m", SHA_A, True), ("claude/smartsched-universal", SHA_B, False)]
    assert rep.posts[0] == (SHA_A, "pending", "pod-ci", "queued on the SmartSched pod",
                            "https://203-0-113-10.sslip.io/ci/runs/1")
    # unchanged heads: nothing new, no extra statuses
    assert runner.poll(cfg, store, rep, "tok", ls_remote=fake_ls(heads), log=lambda _: None) == []
    assert len(rep.posts) == 2


def test_poll_supersedes_queued_commit(cfg: Config, store: Store) -> None:
    rep = FakeReporter()
    b = "claude/gracious-cerf-w1598m"
    runner.poll(cfg, store, rep, "tok", ls_remote=fake_ls({b: SHA_A}), log=lambda _: None)
    runner.poll(cfg, store, rep, "tok", ls_remote=fake_ls({b: SHA_C}), log=lambda _: None)
    old, new = store.find(b, SHA_A), store.find(b, SHA_C)
    assert old and new and old.state == SUPERSEDED and new.state == QUEUED
    assert rep.last("pod-ci", SHA_A) == "error"  # resolved, not left pending forever
    assert rep.last("pod-ci", SHA_C) == "pending"


def test_poll_missing_branch_is_logged_not_fatal(cfg: Config, store: Store) -> None:
    logs: list[str] = []
    runs = runner.poll(cfg, store, FakeReporter(), "tok", ls_remote=fake_ls({}), log=logs.append)
    assert runs == [] and any("not found" in m for m in logs)


def test_force_push_back_to_known_commit_does_not_rerun(cfg: Config, store: Store) -> None:
    rep = FakeReporter()
    b = "claude/gracious-cerf-w1598m"
    for sha in (SHA_A, SHA_B, SHA_A):
        runner.poll(cfg, store, rep, "tok", ls_remote=fake_ls({b: sha}), log=lambda _: None)
    assert len(store.recent()) == 2  # (branch, sha) is unique; `podci rerun` re-runs explicitly
