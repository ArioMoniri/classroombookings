"""Fixtures for infra/aws tests: botocore Stubber only, no network, fake credentials."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from awsstub import StubAws

import smartsched_aws as sa


@pytest.fixture(autouse=True)
def _hermetic_aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The caller's AWS session (e.g. an expired AWS_CREDENTIAL_EXPIRATION, AWS_PROFILE) must not leak into
    the tests: tests that need these variables set them with monkeypatch."""
    for name in ("AWS_CREDENTIAL_EXPIRATION", "AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_ROLE_ARN",
                 "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def aws() -> StubAws:
    return StubAws()


@pytest.fixture
def bootstrap_policy() -> dict[str, Any]:
    return json.loads((Path(sa.__file__).parent / "iam" / "bootstrap-policy.json").read_text())


@pytest.fixture(autouse=True)
def _first_pod() -> Any:
    """main() / use_pod() rebind the module's resource names; every test starts and ends on the first pod."""
    sa.use_pod(sa.PODS["gracious"])
    yield
    sa.use_pod(sa.PODS["gracious"])
