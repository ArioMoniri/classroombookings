"""Commit status posting (mock HTTP): request shape, retries, no retry on 4xx, never raises."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from podci.github import StatusReporter


class Resp:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self) -> Resp:
        return self

    def __exit__(self, *a: Any) -> None:
        return None


class Opener:
    def __init__(self, outcomes: list[Any]):
        self.outcomes = outcomes
        self.requests: list[Any] = []

    def __call__(self, req: Any, timeout: float) -> Resp:
        self.requests.append(req)
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return Resp(out)


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", {}, io.BytesIO(b"{}"))  # type: ignore[arg-type]


def reporter(opener: Opener, sleeps: list[float]) -> StatusReporter:
    return StatusReporter("ArioMoniri/classroombookings", lambda: "ghp_tok", opener=opener, sleep=sleeps.append,
                          log=lambda _: None)


def test_post_builds_the_statuses_request() -> None:
    op = Opener([201])
    sha = "f" * 40
    assert reporter(op, []).post(sha, "success", "pod-ci/backend", "x" * 200, "https://h/ci/runs/3")
    req = op.requests[0]
    assert req.full_url == f"https://api.github.com/repos/ArioMoniri/classroombookings/statuses/{sha}"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer ghp_tok"
    assert req.get_header("Accept") == "application/vnd.github+json"
    assert req.get_header("X-github-api-version") == "2022-11-28"
    body = json.loads(req.data)
    assert body == {"state": "success", "context": "pod-ci/backend", "description": "x" * 140,
                    "target_url": "https://h/ci/runs/3"}


def test_retries_5xx_and_network_errors_then_succeeds() -> None:
    sleeps: list[float] = []
    op = Opener([http_error(502), urllib.error.URLError("reset"), 201])
    assert reporter(op, sleeps).post("a" * 40, "pending", "pod-ci", "queued")
    assert len(op.requests) == 3 and sleeps == [2, 4]


@pytest.mark.parametrize("code", [401, 403, 404, 422])
def test_no_retry_on_client_errors(code: int) -> None:
    op = Opener([http_error(code)])
    assert reporter(op, []).post("a" * 40, "failure", "pod-ci", "x") is False
    assert len(op.requests) == 1


def test_gives_up_quietly_after_retries() -> None:
    op = Opener([http_error(500)] * 3)
    assert reporter(op, []).post("a" * 40, "error", "pod-ci", "x") is False


def test_rejects_unknown_state() -> None:
    with pytest.raises(ValueError):
        reporter(Opener([]), []).post("a" * 40, "neutral", "pod-ci", "x")


def test_no_target_url_when_public_url_unset() -> None:
    op = Opener([201])
    reporter(op, []).post("a" * 40, "pending", "pod-ci", "x", "")
    assert "target_url" not in json.loads(op.requests[0].data)
