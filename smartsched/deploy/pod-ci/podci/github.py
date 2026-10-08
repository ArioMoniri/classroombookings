"""GitHub commit statuses: POST /repos/{owner}/{repo}/statuses/{sha} (token: Commit statuses write).

Reporting is best effort: a GitHub outage must never fail or block a CI run, so post() returns False
instead of raising. 5xx / network errors are retried with backoff; 4xx are not (bad token, no scope).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

API = "https://api.github.com"
STATES = ("error", "failure", "pending", "success")
Opener = Callable[..., Any]


class StatusReporter:
    def __init__(self, repo: str, token: Callable[[], str], opener: Opener = urllib.request.urlopen,
                 sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print,
                 api: str = API, retries: int = 3):
        self.repo = repo
        self.token = token
        self.opener = opener
        self.sleep = sleep
        self.log = log
        self.api = api.rstrip("/")
        self.retries = retries

    def post(self, sha: str, state: str, context: str, description: str, target_url: str = "") -> bool:
        if state not in STATES:
            raise ValueError(f"invalid commit status state {state!r}")
        body: dict[str, str] = {"state": state, "context": context, "description": description[:140]}
        if target_url:
            body["target_url"] = target_url
        req = urllib.request.Request(  # noqa: S310 - fixed https API base
            f"{self.api}/repos/{self.repo}/statuses/{sha}", data=json.dumps(body).encode(), method="POST",
            headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token()}",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
                     "User-Agent": "smartsched-pod-ci"})
        for attempt in range(self.retries):
            try:
                with self.opener(req, timeout=20) as resp:
                    if 200 <= int(resp.status) < 300:
                        return True
                    self.log(f"status {context}@{sha[:7]}: HTTP {resp.status}")
                    return False
            except urllib.error.HTTPError as exc:
                if exc.code < 500 and exc.code != 429:
                    self.log(f"status {context}@{sha[:7]} rejected: HTTP {exc.code} (token needs Commit statuses: "
                             "write on this repository)")
                    return False
                self.log(f"status {context}@{sha[:7]}: HTTP {exc.code}, retrying")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self.log(f"status {context}@{sha[:7]}: {exc}, retrying")
            if attempt < self.retries - 1:
                self.sleep(2 ** attempt * 2)
        return False


class NullReporter(StatusReporter):
    def __init__(self) -> None:
        super().__init__("none/none", lambda: "")

    def post(self, sha: str, state: str, context: str, description: str, target_url: str = "") -> bool:
        return True
