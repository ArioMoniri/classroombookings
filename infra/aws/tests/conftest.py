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


@pytest.fixture
def aws() -> StubAws:
    return StubAws()


@pytest.fixture
def bootstrap_policy() -> dict[str, Any]:
    return json.loads((Path(sa.__file__).parent / "iam" / "bootstrap-policy.json").read_text())
