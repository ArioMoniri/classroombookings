"""Helpers for pod CI tests: in-process fakes for GitHub statuses, subprocess and the clock."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

POD_CI = Path(__file__).resolve().parents[1]
REPO = POD_CI.parents[2]
sys.path.insert(0, str(POD_CI))

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


class Clock:
    def __init__(self, t: float = 1_760_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


class FakeReporter:
    def __init__(self) -> None:
        self.posts: list[tuple[str, str, str, str, str]] = []

    def post(self, sha: str, state: str, context: str, description: str, target_url: str = "") -> bool:
        self.posts.append((sha, state, context, description, target_url))
        return True

    def last(self, context: str, sha: str | None = None) -> str | None:
        for p in reversed(self.posts):
            if p[2] == context and (sha is None or p[0] == sha):
                return p[1]
        return None


class FakeRun:
    """Stands in for subprocess.run (git, docker prune, ...): records argv, returns success."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[Any]:
        self.calls.append(list(argv))
        self.envs.append(kw.get("env"))
        return subprocess.CompletedProcess(argv, 0, stdout="" if kw.get("text") else b"", stderr="")
