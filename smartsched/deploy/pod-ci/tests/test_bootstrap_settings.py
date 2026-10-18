"""Deploy-time settings (smartsched/deploy/seed/bootstrap_settings.py): values given on the deploy CLI
(./deploy.sh flags / env, smartsched_aws.py up) are written into the database once, through the same handlers the
admin panel uses, and never overwrite what an administrator set in the panel."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from podfakes import REPO

DEPLOY = REPO / "smartsched/deploy"
BACKEND = REPO / "smartsched/backend"
_spec = importlib.util.spec_from_file_location("deploy_bootstrap", DEPLOY / "seed/bootstrap_settings.py")
assert _spec and _spec.loader
boot = importlib.util.module_from_spec(_spec)
sys.modules["deploy_bootstrap"] = boot
_spec.loader.exec_module(boot)

SECRET = "sk-ant-api03-" + "x" * 40


# ---- collecting values from the environment ---------------------------------------------------------------------
def test_collect_takes_only_the_groups_that_have_values() -> None:
    got = boot.collect({"ORG_NAME": "  Örnek Üniversitesi ", "SMTP_HOST": "smtp.uni.edu.tr", "SMTP_PORT": "587",
                        "UNRELATED": "x"})
    assert set(got) == {"org", "smtp"}
    assert got["org"] == {"ORG_NAME": "Örnek Üniversitesi"}
    assert got["smtp"]["SMTP_PORT"] == "587"


def test_collect_ai_defaults_to_anthropic_and_needs_a_key_or_url() -> None:
    assert boot.collect({"AI_PROVIDER": "openai"}) == {}  # a provider alone configures nothing
    got = boot.collect({"AI_API_KEY": SECRET})
    assert got["ai"]["AI_PROVIDER"] == "anthropic"


@pytest.mark.parametrize(("env", "needle"), [
    ({"AI_API_KEY": SECRET, "AI_PROVIDER": "nope"}, "AI_PROVIDER"),
    ({"SMTP_HOST": "smtp.x.tr", "SMTP_PORT": "abc"}, "SMTP_PORT"),
    ({"SMTP_HOST": "smtp.x.tr", "SMTP_SECURITY": "tls13"}, "SMTP_SECURITY"),
    ({"SMTP_USERNAME": "u"}, "SMTP_HOST"),
    ({"SECURITY_CONTACT": "not-an-address"}, "SECURITY_CONTACT"),
    ({"GOOGLE_CLIENT_ID": "abc.apps.googleusercontent.com"}, "GOOGLE_CLIENT_SECRET"),
])
def test_collect_refuses_bad_input_without_echoing_secrets(env: dict[str, str], needle: str) -> None:
    with pytest.raises(boot.BootstrapError) as exc:
        boot.collect({**env, "SMTP_PASSWORD": "hunter2-secret"})
    assert needle in str(exc.value) and "hunter2" not in str(exc.value) and SECRET not in str(exc.value)


def test_describe_never_prints_secret_values() -> None:
    text = boot.describe(boot.collect({"AI_API_KEY": SECRET, "SMTP_HOST": "smtp.x.tr", "SMTP_PASSWORD": "pw-123456",
                                       "ORG_NAME": "Uni"}))
    assert SECRET not in text and "pw-123456" not in text
    assert "AI_API_KEY=<set>" in text and "ORG_NAME=Uni" in text


# ---- the marker: once per group, admin edits win ----------------------------------------------------------------
class FakeBackend:
    def __init__(self, configured: set[str] | None = None, fail: set[str] | None = None) -> None:
        self.marker: dict[str, Any] | None = None
        self.state: set[str] = set(configured or ())
        self.fail = fail or set()
        self.applied: list[tuple[str, dict[str, str]]] = []

    async def has_admin(self) -> bool:
        return True

    async def get_marker(self) -> dict[str, Any] | None:
        return self.marker

    async def put_marker(self, marker: dict[str, Any]) -> None:
        import copy

        self.marker = copy.deepcopy(marker)

    async def configured(self, group: str) -> bool:
        return group in self.state

    async def apply(self, group: str, values: dict[str, str]) -> None:
        if group in self.fail:
            raise boot.BootstrapError(f"{group}: refused")
        self.applied.append((group, values))
        self.state.add(group)


def _run(values: dict[str, dict[str, str]], b: FakeBackend, force: bool = False) -> Any:
    return asyncio.run(boot.run(values, b, force=force, log=lambda _m: None))


def test_first_deploy_applies_and_redeploy_skips() -> None:
    b = FakeBackend()
    values = boot.collect({"ORG_NAME": "Uni", "SECURITY_CONTACT": "security@uni.edu.tr"})
    out = _run(values, b)
    assert sorted(out.applied) == ["org", "security"] and not out.kept
    assert set(b.marker["groups"]) == {"org", "security"}
    # the admin renames the organisation in the panel; the next deploy (same or other CLI value) leaves it
    b.applied.clear()
    again = _run(boot.collect({"ORG_NAME": "Other name", "SECURITY_CONTACT": "security@uni.edu.tr"}), b)
    assert b.applied == [] and sorted(again.already) == ["org", "security"]


def test_values_set_in_the_panel_before_the_first_bootstrap_are_kept() -> None:
    b = FakeBackend(configured={"smtp"})
    out = _run(boot.collect({"SMTP_HOST": "smtp.x.tr", "ORG_NAME": "Uni"}), b)
    assert out.kept == ["smtp"] and out.applied == ["org"]
    assert b.marker["groups"]["smtp"]["result"] == "kept"
    assert [g for g, _ in b.applied] == ["org"]


def test_a_group_added_on_a_later_deploy_is_applied() -> None:
    b = FakeBackend()
    _run(boot.collect({"ORG_NAME": "Uni"}), b)
    out = _run(boot.collect({"ORG_NAME": "Uni", "AI_API_KEY": SECRET}), b)
    assert out.applied == ["ai"] and out.already == ["org"]


def test_force_reapplies() -> None:
    b = FakeBackend()
    _run(boot.collect({"ORG_NAME": "Uni"}), b)
    out = _run(boot.collect({"ORG_NAME": "Uni 2"}), b, force=True)
    assert out.applied == ["org"] and b.applied[-1] == ("org", {"ORG_NAME": "Uni 2"})


def test_a_refused_group_is_reported_not_recorded_and_others_still_apply() -> None:
    b = FakeBackend(fail={"smtp"})
    out = _run(boot.collect({"SMTP_HOST": "smtp.x.tr", "ORG_NAME": "Uni"}), b)
    assert out.applied == ["org"] and out.failed == ["smtp"]
    assert "smtp" not in b.marker["groups"]  # retried on the next deploy


def test_no_values_touch_nothing() -> None:
    b = FakeBackend()
    out = _run({}, b)
    assert out.applied == [] and b.marker is None


def test_marker_never_holds_values() -> None:
    b = FakeBackend()
    _run(boot.collect({"AI_API_KEY": SECRET, "ORG_NAME": "Uni"}), b)
    assert SECRET not in repr(b.marker) and "Uni" not in repr(b.marker)


# ---- through the real backend handlers (SQLite) ------------------------------------------------------------------
def _backend_python() -> bool:
    probe = "import aiosqlite, fastapi, sqlalchemy"
    return subprocess.run([sys.executable, "-c", probe], capture_output=True).returncode == 0


def _tool(db: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k not in boot.ALL_KEYS}
    full = {**base, "DATABASE_URL": f"sqlite+aiosqlite:///{db}", "ENVIRONMENT": "test",
            "APP_SECRET": "t" * 40, "JWT_SECRET": "j" * 40, **env}
    return subprocess.run([sys.executable, str(DEPLOY / "seed/bootstrap_settings.py"), *(args or ("run",))],
                          cwd=BACKEND, env=full, capture_output=True, text=True, timeout=300)


def _seed_admin(db: Path) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db}", "ENVIRONMENT": "test",
           "ADMIN_EMAIL": "admin@uni.edu.tr", "ADMIN_PASSWORD": "a-long-test-password", "APP_SECRET": "t" * 40,
           "JWT_SECRET": "j" * 40}
    r = subprocess.run([sys.executable, "-m", "app.cli", "seed-admin"], cwd=BACKEND, env=env, capture_output=True,
                       text=True, timeout=300)
    assert r.returncode == 0, r.stderr


def _rows(db: Path) -> dict[str, str | None]:
    import sqlite3

    with sqlite3.connect(db) as c:
        return dict(c.execute("SELECT key, value FROM settings").fetchall())


@pytest.mark.skipif(not _backend_python(), reason="backend dependencies not installed (the backend gate covers it)")
def test_real_handlers_store_values_once_and_keep_admin_edits(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    _seed_admin(db)
    env = {"ORG_NAME": "Örnek Üniversitesi", "AI_API_KEY": SECRET, "SMTP_HOST": "smtp.uni.edu.tr",
           "SMTP_PORT": "587", "SMTP_USERNAME": "noreply@uni.edu.tr", "SMTP_PASSWORD": "smtp-pass-123",
           "SMTP_FROM": "noreply@uni.edu.tr", "SECURITY_CONTACT": "security@uni.edu.tr",
           "GOOGLE_CLIENT_ID": "123.apps.googleusercontent.com", "GOOGLE_CLIENT_SECRET": "g-secret-xyz"}
    r = _tool(db, env)
    assert r.returncode == 0, r.stdout + r.stderr
    for secret in (SECRET, "smtp-pass-123", "g-secret-xyz"):
        assert secret not in r.stdout + r.stderr
    rows = _rows(db)
    assert rows["org.name"] == "Örnek Üniversitesi"
    assert rows["smtp.host"] == "smtp.uni.edu.tr" and rows["smtp.port"] == "587"
    assert rows["security.contact_email"] == "security@uni.edu.tr"
    assert rows["integrations.google_client_id"] == "123.apps.googleusercontent.com"
    # secrets are stored encrypted, never in clear text
    assert rows["anthropic_api_key"] and SECRET not in rows["anthropic_api_key"]
    assert "smtp-pass-123" not in (rows.get("smtp.password") or "")
    assert "deploy.bootstrap_settings" in rows
    # the admin edits the name in the panel; a redeploy with a different CLI value keeps the admin's
    import sqlite3

    with sqlite3.connect(db) as c:
        c.execute("UPDATE settings SET value = 'Panelde değişti' WHERE key = 'org.name'")
    r2 = _tool(db, {**env, "ORG_NAME": "CLI again"})
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert _rows(db)["org.name"] == "Panelde değişti"


@pytest.mark.skipif(not _backend_python(), reason="backend dependencies not installed (the backend gate covers it)")
def test_real_handlers_refuse_bad_values_and_exit_nonzero(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    _seed_admin(db)
    r = _tool(db, {"SMTP_HOST": "smtp.uni.edu.tr", "SMTP_SECURITY": "none", "SMTP_USERNAME": "u",
                   "SMTP_PASSWORD": "pw-not-printed", "ORG_NAME": "Uni"})
    assert r.returncode == 3, r.stdout + r.stderr  # partly applied
    assert "smtp" in r.stderr and "pw-not-printed" not in r.stdout + r.stderr
    rows = _rows(db)
    assert rows["org.name"] == "Uni" and not rows.get("smtp.host")


@pytest.mark.skipif(not _backend_python(), reason="backend dependencies not installed (the backend gate covers it)")
def test_without_an_admin_nothing_is_written(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    r = _tool(db, {"ORG_NAME": "Uni"})
    assert r.returncode == 1 and "administrator" in r.stderr


def test_plan_lists_groups_without_a_database() -> None:
    r = subprocess.run([sys.executable, str(DEPLOY / "seed/bootstrap_settings.py"), "plan"],
                       env={"PATH": os.environ["PATH"], "ORG_NAME": "Uni", "AI_API_KEY": SECRET},
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "org" in r.stdout and "ai" in r.stdout and SECRET not in r.stdout
