"""git over HTTPS with the read-only token passed as an HTTP header through GIT_CONFIG_* env vars.

The token never appears on a command line (visible in /proc to every local user) or in .git/config.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
Run = Callable[..., Any]


class GitError(RuntimeError):
    pass


def auth_env(token: str, base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
    })
    return env


def redact(text: str, token: str) -> str:
    if not token:
        return text
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return text.replace(token, "***").replace(basic, "***")


def parse_ls_remote(output: str) -> dict[str, str]:
    """`<sha>\\trefs/heads/<branch>` lines -> {branch: sha}."""
    heads: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 2:
            continue
        sha, ref = parts
        if SHA_RE.match(sha) and ref.startswith("refs/heads/"):
            heads[ref.removeprefix("refs/heads/")] = sha
    return heads


def ls_remote(repo_url: str, branches: Iterable[str], token: str, run: Run = subprocess.run,
              timeout: float = 60) -> dict[str, str]:
    refs = [f"refs/heads/{b}" for b in branches]
    proc = run(["git", "ls-remote", "--heads", repo_url, *refs], env=auth_env(token), capture_output=True,
               text=True, timeout=timeout)
    if proc.returncode != 0:
        raise GitError(f"git ls-remote failed ({proc.returncode}): {redact(proc.stderr or '', token).strip()[-500:]}")
    return parse_ls_remote(proc.stdout)


def git(args: list[str], token: str, cwd: Path | None = None, run: Run = subprocess.run,
        timeout: float = 600) -> str:
    proc = run(["git", *args], env=auth_env(token), cwd=str(cwd) if cwd else None, capture_output=True, text=True,
               timeout=timeout)
    if proc.returncode != 0:
        raise GitError(f"git {args[0]} failed ({proc.returncode}): {redact(proc.stderr or '', token).strip()[-800:]}")
    return str(proc.stdout)


def fetch_into_mirror(mirror: Path, repo_url: str, branch: str, sha: str, token: str,
                      run: Run = subprocess.run) -> None:
    if not (mirror / "HEAD").exists():
        mirror.mkdir(parents=True, exist_ok=True)
        git(["init", "--bare", "-q", str(mirror)], token, run=run)
    git(["--git-dir", str(mirror), "fetch", "--quiet", "--no-tags", "--force", repo_url,
         f"+refs/heads/{branch}:refs/heads/{branch}"], token, run=run)
    try:
        git(["--git-dir", str(mirror), "cat-file", "-e", f"{sha}^{{commit}}"], token, run=run)
    except GitError:  # the branch moved on; fetch the commit itself (GitHub allows reachable SHAs)
        git(["--git-dir", str(mirror), "fetch", "--quiet", "--no-tags", repo_url, sha], token, run=run)


def export_tree(mirror: Path, sha: str, dest: Path, run: Run = subprocess.run) -> None:
    """`git archive <sha> | tar -x` into dest (no .git, no credentials in the workspace)."""
    if not SHA_RE.match(sha):
        raise GitError(f"refusing to export non-sha {sha!r}")
    dest.mkdir(parents=True, exist_ok=True)
    archive = run(["git", "--git-dir", str(mirror), "archive", "--format=tar", sha], capture_output=True, timeout=600)
    if archive.returncode != 0:
        raise GitError(f"git archive failed: {archive.stderr!r}"[-500:])
    untar = run(["tar", "-x", "-C", str(dest)], input=archive.stdout, capture_output=True, timeout=600)
    if untar.returncode != 0:
        raise GitError(f"tar failed: {untar.stderr!r}"[-500:])
