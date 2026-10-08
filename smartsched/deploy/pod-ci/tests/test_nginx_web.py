"""/ci/ nginx location rendering (checked with nginx -t when available) and the results page + auth."""

from __future__ import annotations

import base64
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from podfakes import REPO, SHA_A, Clock

from podci import nginx, web
from podci.config import Config
from podci.state import RUNNING, SUCCESS, Store

CONF = (REPO / "smartsched/deploy/nginx/default.conf").read_text()


def test_render_inserts_before_catch_all_and_is_idempotent() -> None:
    out = nginx.render(CONF)
    assert out.count("location /ci/") == 1
    assert out.index("location /ci/") < out.index("    location / {")
    assert "proxy_pass http://172.17.0.1:8095;" in out
    assert nginx.render(out) == out  # re-render after every checkout: no duplicates
    assert nginx.render(out, "172.17.0.1:9000").count("location /ci/") == 1
    assert out.replace(nginx.block("172.17.0.1:8095") + "\n\n", "") == CONF


def test_api_docs_are_not_routed_to_the_backend() -> None:
    """m6: production FastAPI has no docs; nginx (repo file and the pod-rendered one) never proxies them."""
    for conf in (CONF, nginx.render(CONF)):
        for path in ("/api/docs", "/api/redoc", "/api/openapi.json"):
            assert f"location = {path} {{ proxy_pass" not in conf
        assert "location ~ ^/api/(docs|redoc|openapi\\.json)$ { return 404; }" in conf


def test_render_requires_catch_all() -> None:
    with pytest.raises(ValueError):
        nginx.render("server { listen 8080; }")


@pytest.mark.skipif(shutil.which("nginx") is None, reason="nginx not installed")
def test_rendered_config_passes_nginx_t(tmp_path: Path) -> None:
    conf = nginx.render(CONF).replace("server frontend:3000", "server 127.0.0.1:3000").replace(
        "server backend:8000", "server 127.0.0.1:8000")
    (tmp_path / "conf.d").mkdir()
    (tmp_path / "conf.d/default.conf").write_text(conf)
    t = tmp_path
    (tmp_path / "nginx.conf").write_text(
        f"pid {t}/nginx.pid; error_log stderr; events {{}} http {{ access_log off; client_body_temp_path {t}/c; "
        f"proxy_temp_path {t}/p; fastcgi_temp_path {t}/f; uwsgi_temp_path {t}/u; scgi_temp_path {t}/s; "
        f"include {t}/conf.d/*.conf; }}\n")
    proc = subprocess.run(["nginx", "-t", "-q", "-p", str(t), "-e", "stderr", "-c", str(t / "nginx.conf")],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# ---- auth ---------------------------------------------------------------------------------------
def basic(cred: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(cred.encode()).decode()}


def test_auth_basic_and_cookie(clock: Clock) -> None:
    seen: list[str] = []

    def me(token: str) -> dict[str, Any] | None:
        seen.append(token)
        return {"admin-tok": {"role": "ADMIN", "is_active": True},
                "perm-tok": {"role": "CUSTOM", "permissions": ["planning.admin"]},
                "viewer-tok": {"role": "VIEWER", "permissions": ["planning.view"]},
                "disabled": {"role": "ADMIN", "is_active": False}}.get(token)

    auth = web.Auth("ci:s3cret", me, ttl=60, clock=clock)
    assert auth.check(basic("ci:s3cret"))
    assert not auth.check(basic("ci:wrong"))
    assert not auth.check({"Authorization": "Basic !!!"})
    assert auth.check({"Cookie": "smartsched_token=admin-tok; other=1"})
    assert auth.check({"Cookie": "smartsched_token=perm-tok"})
    assert not auth.check({"Cookie": "smartsched_token=viewer-tok"})
    assert not auth.check({"Cookie": "smartsched_token=disabled"})
    assert not auth.check({"Cookie": "smartsched_token=expired"})
    assert not auth.check({})
    n = len(seen)
    auth.check({"Cookie": "smartsched_token=admin-tok"})
    assert len(seen) == n  # cached for ttl
    clock.advance(61)
    auth.check({"Cookie": "smartsched_token=admin-tok"})
    assert len(seen) == n + 1
    assert not web.Auth(None, me).check(basic("ci:"))  # no basic credentials configured -> no basic login


# ---- pages over real HTTP -----------------------------------------------------------------------
@pytest.fixture
def server(cfg: Config, store: Store):  # type: ignore[no-untyped-def]
    auth = web.Auth("ci:pw", lambda t: {"role": "ADMIN"} if t == "good" else None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(cfg, lambda: Store(cfg.db_path), auth))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def get(url: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_pages(server: str, cfg: Config, store: Store) -> None:
    run = store.enqueue("claude/gracious-cerf-w1598m", SHA_A, deploy=True)
    assert run
    store.transition(run.id, RUNNING)
    store.add_steps(run.id, [("backend", True), ("watchdog", False)])
    log = cfg.logs_dir / str(run.id) / "backend.log"
    log.parent.mkdir(parents=True)
    log.write_text("<script>alert(1)</script> ruff ok\n")
    store.step_transition(run.id, "backend", "running", log_path=str(log))
    store.step_transition(run.id, "backend", SUCCESS, exit_code=0)
    store.transition(run.id, SUCCESS, summary="all gates passed <b>")

    assert get(f"{server}/ci/healthz")[0] == 200
    code, body = get(f"{server}/ci/")
    assert code == 401 and "/login" in body
    ok = basic("ci:pw")
    code, body = get(f"{server}/ci/", ok)
    assert code == 200 and f"/ci/runs/{run.id}" in body and SHA_A[:7] in body
    assert "&lt;b&gt;" in body and "<b>" not in body.split("summary")[-1].split("</table>")[0].replace("<b>", "", 0)
    code, body = get(f"{server}/ci/runs/{run.id}", {"Cookie": "smartsched_token=good"})
    assert code == 200 and "backend" in body and "non-blocking" in body
    code, body = get(f"{server}/ci/runs/{run.id}/backend.log", ok)
    assert code == 200 and "ruff ok" in body
    assert get(f"{server}/ci/runs/{run.id}/watchdog.log", ok)[0] == 404  # no log yet
    assert get(f"{server}/ci/runs/999", ok)[0] == 404
    assert get(f"{server}/ci/runs/{run.id}/..%2F..%2Fetc.log", ok)[0] == 404


def test_log_outside_logs_dir_is_refused(cfg: Config, store: Store, tmp_path: Path) -> None:
    run = store.enqueue("b", SHA_A, deploy=False)
    assert run
    store.add_steps(run.id, [("x", True)])
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    store.step_transition(run.id, "x", "running", log_path=str(secret))
    assert web.read_log(cfg, store, run.id, "x") is None
