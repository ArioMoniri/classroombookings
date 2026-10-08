"""Fixtures for pod CI tests: temp state dir, in-process fakes for GitHub HTTP, git, docker and AWS."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from podfakes import POD_CI, REPO, Clock

from podci.config import Config
from podci.state import Store


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    deploy = tmp_path / "deploy-checkout"
    (deploy / "smartsched/deploy/nginx").mkdir(parents=True)
    (deploy / "smartsched/deploy/nginx/default.conf").write_text(
        (REPO / "smartsched/deploy/nginx/default.conf").read_text())
    return Config(state_dir=tmp_path / "state", deploy_dir=deploy, install_dir=POD_CI, cloud=False,
                  public_url="https://203-0-113-10.sslip.io", token_file="")


@pytest.fixture
def store(cfg: Config, clock: Clock) -> Store:
    return Store(cfg.db_path, clock=clock)
