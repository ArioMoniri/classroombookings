"""Ingestion Council deploy settings (app/council, merged from claude/smartsched-universal): once the backend
declares ``council_*`` settings, every one is passed to the backend container by docker-compose.yml, documented
in .env.example, and the council job SSE stream is proxied unbuffered like the solver events. Before the merge
lands there is nothing to check; the guard then fails the infra gate if a setting is missing."""

from __future__ import annotations

import re

import pytest
import yaml
from podfakes import REPO

CONFIG = REPO / "smartsched/backend/app/core/config.py"
DEPLOY = REPO / "smartsched/deploy"


def council_settings(text: str) -> list[str]:
    return sorted(set(re.findall(r"^\s{4}(council_[a-z0-9_]+)\s*:", text, re.M)))


def test_parser_finds_settings() -> None:
    sample = "class Settings:\n    council_ai: bool = True\n    council_max_job_mb: int = 50\n    other: int = 1\n"
    assert council_settings(sample) == ["council_ai", "council_max_job_mb"]


def test_every_council_setting_reaches_the_backend_container() -> None:
    names = council_settings(CONFIG.read_text(encoding="utf-8"))
    if not names:
        pytest.skip("app/council has not landed on this branch yet (no council_* settings)")
    compose = yaml.safe_load((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"))
    env = compose["services"]["backend"]["environment"]
    env_example = (DEPLOY / ".env.example").read_text(encoding="utf-8")
    for name in names:
        var = name.upper()
        assert var in env, f"{var} missing from the backend environment in docker-compose.yml"
        assert f"${{{var}" in str(env[var]), f"{var} must come from .env (${{{var}:-default}})"
        assert re.search(rf"^{var}=", env_example, re.M), f"{var} missing from .env.example"
    nginx = (DEPLOY / "nginx/default.conf").read_text(encoding="utf-8")
    assert re.search(r"location ~ \^/api/v1/\([^)]*council/jobs[^)]*\)/\[\^/\]\+/events\$", nginx), \
        "council job events must use the unbuffered SSE location"
