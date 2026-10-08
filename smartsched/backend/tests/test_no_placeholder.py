"""No-placeholder audit (docs/review/2026-10-08-no-placeholder-audit.md): M2 production secrets, M3 seeded
admin password + forced reset, m6 API docs off in prod, m7 version from package metadata / no solver in
/health, m1 + m3 deploy configuration."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from app.core.config import DEFAULT_APP_SECRET, Settings, app_version, assert_secure, get_settings
from app.models import User
from app.services.seed import seed_admin
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "smartsched/deploy"
GOOD_A = "3f1c9e0b7a2d4c6e8f0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f6a"
GOOD_J = "9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d"
GOOD_PW = "Kx7pQ2mZr9TfLw4Hs8Nb"  # same shape as the pod's generated ADMIN_PASSWORD (20 alphanumerics)


def prod(**kw: object) -> Settings:
    # admin_password=None: tests/conftest.py exports ADMIN_PASSWORD=admin1234 for the test environment
    base: dict[str, object] = {"environment": "prod", "app_secret": GOOD_A, "jwt_secret": GOOD_J, "admin_password": None}
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


# ---- M2: ENVIRONMENT is dev | test | prod, checks run for everything but dev/test ----------------------


@pytest.mark.parametrize("value", ["production", "staging", "", "prd"])
def test_m2_unknown_environment_fails_at_startup(value):
    with pytest.raises(ValidationError):
        Settings(environment=value)


@pytest.mark.parametrize("value,expected", [(" Prod ", "prod"), ("PROD", "prod"), ("Test\xa0", "test"), ("DEV", "dev")])
def test_m2_environment_is_trimmed_and_case_folded(value, expected):
    assert Settings(environment=value).environment == expected


def test_m2_unknown_environment_from_env_var_fails(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValidationError):
        Settings()


def test_m2_prod_is_the_default_check_and_dev_test_are_exempt():
    assert prod().insecure_reasons() == []
    assert Settings(environment="dev").insecure_reasons() == []  # default secret allowed only in dev/test
    assert Settings(environment="test", app_secret="x").insecure_reasons() == []
    assert prod(app_secret=DEFAULT_APP_SECRET).insecure_reasons()


@pytest.mark.parametrize(
    "placeholder",
    [
        DEFAULT_APP_SECRET,
        DEFAULT_APP_SECRET.upper(),
        "CHANGEME" + "0123456789abcdef0123456789abcdef",
        "please-Change-Me-0123456789abcdef0123456789",
        "__GENERATE__",
        "__generate__0123456789abcdef0123456789abcdef",
        "my-SECRET-value-0123456789abcdef0123456789",
        "ci-only-secret-0123456789abcdef0123456789abcdef",
        "a" * 31,
    ],
)
@pytest.mark.parametrize("key", ["app_secret", "jwt_secret"])
def test_m2_prod_refuses_each_placeholder_secret(key, placeholder):
    s = prod(**{key: placeholder})
    name = key.upper()
    assert any(r.startswith(name) for r in s.insecure_reasons()), s.insecure_reasons()
    with pytest.raises(RuntimeError, match=name):
        assert_secure(s)


def test_m2_jwt_rules_kept():
    assert "JWT_SECRET is not set" in prod(jwt_secret=None).insecure_reasons()
    assert "JWT_SECRET must differ from APP_SECRET" in prod(jwt_secret=GOOD_A).insecure_reasons()


# ---- M3: admin password ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    [
        "change-me",
        "CHANGE-ME",
        "changeme",
        "admin",
        "ADMİN",  # Turkish dotted capital I
        "admın",  # Turkish dotless i
        "__GENERATE__",
        "admin1234567",  # placeholder word + digits only, 12 chars
        "Admin!2026!!!",
        "password12345",
        "please-change-me-now",
        "Kx7pQ2mZr9T",  # 11 characters
        "  Kx7pQ2mZr9\xa0",  # NBSP / spaces do not count
    ],
)
def test_m3_prod_refuses_placeholder_admin_password(password):
    s = prod(admin_email="planner@university.edu.tr", admin_password=password)
    assert any(r.startswith("ADMIN_PASSWORD") for r in s.insecure_reasons()), s.insecure_reasons()


def test_m3_strong_admin_password_and_unset_password_pass():
    assert prod(admin_email="planner@university.edu.tr", admin_password=GOOD_PW).insecure_reasons() == []
    assert prod(admin_email="planner@university.edu.tr", admin_password="ci-only-admin-password").insecure_reasons() == []
    assert prod(admin_password=None).insecure_reasons() == []  # nothing to seed
    assert Settings(environment="dev", admin_password="admin").insecure_reasons() == []


@pytest.fixture
def prod_settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "environment", "prod")
    monkeypatch.setattr(s, "admin_email", "Planner@University.edu.tr")
    monkeypatch.setattr(s, "admin_password", GOOD_PW)
    return s


async def test_m3_prod_seed_refuses_a_placeholder_password(session, prod_settings, monkeypatch):
    monkeypatch.setattr(prod_settings, "admin_password", "change-me")
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        await seed_admin(session)
    assert (await session.execute(select(User))).first() is None


async def test_m3_prod_seed_forces_reset_on_first_creation_only(session, prod_settings):
    user = await seed_admin(session)
    assert user is not None and user.force_password_reset is True and user.email == "planner@university.edu.tr"
    user.force_password_reset = False  # the admin changed the password
    await session.commit()
    assert await seed_admin(session) is None  # later starts never touch the account
    again = (await session.execute(select(User))).scalar_one()
    assert again.force_password_reset is False


async def test_m3_test_environment_seed_does_not_force_reset(session):
    user = await seed_admin(session)
    assert user is not None and user.force_password_reset is False


# ---- generated pod / deploy.sh secrets pass the prod checks -------------------------------------------


def _load_pod_envfile():
    spec = importlib.util.spec_from_file_location("podci_envfile", DEPLOY / "pod-ci/podci/envfile.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("attempt", range(5))
def test_pod_generated_env_passes_prod_checks(tmp_path, attempt):
    envfile = _load_pod_envfile()
    env = tmp_path / ".env"
    envfile.prepare(env, DEPLOY / ".env.example", {"ENVIRONMENT": "prod", "ADMIN_EMAIL": "planner@university.edu.tr"})
    v = envfile.parse(env.read_text(encoding="utf-8"))
    assert "AUTH_SECRET" not in v  # m3: dead config is gone
    s = Settings(
        environment=v["ENVIRONMENT"],
        app_secret=v["APP_SECRET"],
        jwt_secret=v["JWT_SECRET"],
        admin_email=v["ADMIN_EMAIL"],
        admin_password=v["ADMIN_PASSWORD"],
    )
    assert s.environment == "prod" and s.insecure_reasons() == []
    assert_secure(s)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash needed")
def test_deploy_sh_generators_pass_prod_checks():
    text = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    funcs = "\n".join(re.findall(r"^(?:die|random_secret|random_password)\(\) \{.*?^\}$", text, re.M | re.S))
    funcs += "\n" + re.search(r"^die\(\).*$", text, re.M).group(0)  # type: ignore[union-attr]
    for _ in range(5):
        out = subprocess.run(
            ["bash", "-c", funcs + "\nrandom_secret; random_secret; random_password"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        app, jwt_secret, password = out
        s = prod(app_secret=app, jwt_secret=jwt_secret, admin_email="a@university.edu.tr", admin_password=password)
        assert s.insecure_reasons() == [], (out, s.insecure_reasons())


def test_m1_env_example_has_no_seeded_example_admin_and_no_auth_secret():
    text = (DEPLOY / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^ADMIN_EMAIL=$", text, re.M)
    assert not re.search(r"^AUTH_SECRET=", text, re.M)
    assert "AUTH_SECRET" not in (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")


# ---- m6: API docs are not served in prod --------------------------------------------------------------


async def _docs_status(monkeypatch, environment: str) -> dict[str, int]:
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "environment", environment)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return {p: (await c.get(p)).status_code for p in ("/api/docs", "/api/redoc", "/api/openapi.json", "/redoc")}


async def test_m6_docs_disabled_in_prod(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    assert await _docs_status(monkeypatch, "prod") == {
        "/api/docs": 404,
        "/api/redoc": 404,
        "/api/openapi.json": 404,
        "/redoc": 404,
    }
    dev = await _docs_status(monkeypatch, "dev")
    assert dev["/api/docs"] == 200 and dev["/api/openapi.json"] == 200 and dev["/api/redoc"] == 200
    assert dev["/redoc"] == 404  # only under /api


# ---- m7: version from package metadata, no solver in /health ------------------------------------------


async def test_m7_health_reports_metadata_version_without_solver(client):
    from app.main import app

    expected = importlib.metadata.version("smartsched-backend")
    assert app_version() == expected and app.version == expected
    body = (await client.get("/api/v1/health")).json()
    assert body["version"] == expected and "solver" not in body and body["db"] is True
