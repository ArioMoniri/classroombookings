"""`up --org-name ... --smtp-host ...` (plus AI_API_KEY / SMTP_PASSWORD / *_CLIENT_SECRET from the environment):
the deploy-time settings land in SSM {prefix}/bootstrap/<KEY> before the pod boots (SecureString for secrets), the
pod hands them to deploy.sh, which writes each group into the database once (smartsched/deploy/seed/
bootstrap_settings.py). Secret values are never printed nor written to the JSON result."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from awsstub import StubAws
from botocore.stub import ANY

import smartsched_aws as sa

REPO = Path(sa.__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("deploy_bootstrap_aws",
                                              REPO / "smartsched/deploy/seed/bootstrap_settings.py")
assert _spec and _spec.loader
boot = importlib.util.module_from_spec(_spec)
sys.modules["deploy_bootstrap_aws"] = boot
_spec.loader.exec_module(boot)

KEY = "sk-ant-api03-" + "z" * 40


def args(*extra: str) -> Any:
    return sa.build_parser().parse_args(["up", *extra])


def test_flags_and_env_become_bootstrap_values() -> None:
    a = args("--org-name", "Örnek Üniversitesi", "--smtp-host", "smtp.uni.edu.tr", "--smtp-port", "587",
             "--security-contact", "security@uni.edu.tr", "--ai-provider", "anthropic", "--observability")
    got = sa.bootstrap_values(a, {"AI_API_KEY": KEY, "SMTP_PASSWORD": "pw", "GOOGLE_CLIENT_ID": "g.apps",
                                  "GOOGLE_CLIENT_SECRET": "gs", "HOME": "/root"})
    assert got["ORG_NAME"] == ("Örnek Üniversitesi", False) and got["SMTP_PORT"] == ("587", False)
    assert got["AI_API_KEY"] == (KEY, True) and got["SMTP_PASSWORD"] == ("pw", True)
    assert got["GOOGLE_CLIENT_SECRET"] == ("gs", True) and got["GOOGLE_CLIENT_ID"] == ("g.apps", False)
    assert got["OBSERVABILITY"] == ("1", False) and "HOME" not in got
    assert sa.bootstrap_values(args(), {}) == {}
    assert sa.bootstrap_values(args("--no-observability"), {})["OBSERVABILITY"] == ("0", False)


def test_bootstrap_keys_are_what_the_pod_accepts() -> None:
    assert set(sa.BOOTSTRAP_KEYS) == {*boot.ALL_KEYS, "OBSERVABILITY"}
    assert sa.BOOTSTRAP_SECRETS == boot.SECRET_KEYS


def test_bad_values_are_refused_before_any_aws_call() -> None:
    with pytest.raises(sa.BootstrapError) as exc:
        sa.bootstrap_values(args("--smtp-port", "587"), {"SMTP_PASSWORD": "pw-hidden"})
    assert "SMTP_HOST" in str(exc.value) and "pw-hidden" not in str(exc.value)


def test_store_bootstrap_writes_secure_strings_for_secrets(aws: StubAws) -> None:
    ssm = aws.stub("ssm")
    ssm.add_response("put_parameter", {"Version": 1}, {"Name": "/smartsched/bootstrap/ORG_NAME", "Value": "Uni",
                                                       "Type": "String", "Tags": ANY})
    ssm.add_response("put_parameter", {"Version": 1}, {"Name": "/smartsched/bootstrap/AI_API_KEY", "Value": KEY,
                                                       "Type": "SecureString", "Tags": ANY})
    names = sa.store_bootstrap(aws, {"ORG_NAME": ("Uni", False), "AI_API_KEY": (KEY, True)})
    aws.assert_done()
    assert names == ["/smartsched/bootstrap/ORG_NAME", "/smartsched/bootstrap/AI_API_KEY"]


def test_up_stores_the_values_before_the_instance_launches(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(sa, "ensure_pod_role", lambda *a, **k: "profile")
    monkeypatch.setattr(sa, "default_subnet", lambda *a, **k: ("vpc", "subnet"))
    monkeypatch.setattr(sa, "ensure_security_group", lambda *a, **k: "sg")
    monkeypatch.setattr(sa, "find_instances", lambda *a, **k: [])
    monkeypatch.setattr(sa, "ensure_eip", lambda *a, **k: ("alloc", "203.0.113.10"))
    monkeypatch.setattr(sa, "store_bootstrap",
                        lambda aws, v: order.append("bootstrap") or [f"/smartsched/bootstrap/{k}" for k in v])
    monkeypatch.setattr(sa, "launch_instance", lambda *a, **k: order.append("launch") or {"InstanceId": "i-1"})
    monkeypatch.setattr(sa, "wait_for", lambda *a, **k: None)
    for name in ("associate_eip", "ensure_idle_alarm", "ensure_budget", "put_parameter"):
        monkeypatch.setattr(sa, name, lambda *a, **k: None)
    monkeypatch.setattr(sa, "ec2_hourly_price", lambda *a, **k: (0.07, "x"))
    monkeypatch.setattr(sa, "gp3_price", lambda *a, **k: (0.08, "x"))
    s = sa.Settings(budget_action=False, bootstrap=(("ORG_NAME", "Uni", False), ("AI_API_KEY", KEY, True)))
    res = sa.cmd_up(object(), s, "123456789012", sleep=lambda _: None)  # type: ignore[arg-type]
    assert order == ["bootstrap", "launch"]
    text = json.dumps(res.as_dict())
    assert KEY not in text, text
    assert "/smartsched/bootstrap/AI_API_KEY" in text


def test_plan_lists_bootstrap_parameter_names_not_values(capsys: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", KEY)
    assert sa.main(["plan", "--pod", "universal", "--region", "eu-central-1", "--org-name", "Uni"]) == 0
    out = capsys.readouterr().out
    plan = json.loads(out)
    assert plan["bootstrap_parameters"] == ["/smartsched-universal/bootstrap/AI_API_KEY",
                                            "/smartsched-universal/bootstrap/ORG_NAME"]
    assert KEY not in out
    sa.use_pod(sa.PODS["gracious"])


def test_secret_flags_are_refused() -> None:
    with pytest.raises(SystemExit):
        sa.build_parser().parse_args(["up", "--ai-api-key", KEY])
