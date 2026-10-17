"""W3-OPS: Prometheus metrics, error ingestion (scrubbing, grouping, rate limit), forward-auth, ops panel API."""

from __future__ import annotations

import json

import pytest
from app.core import observability as obs
from httpx import ASGITransport, AsyncClient

from tests.api_fixtures import login
from tests.crbs_support import make_user


@pytest.fixture(autouse=True)
def _fresh_ops_state(monkeypatch):
    obs.report_limiter.reset()
    obs.reset_ring()
    for k in ("OPS_GRAFANA_URL", "OPS_PROMETHEUS_URL", "OPS_LOKI_URL", "OPS_PODCI_URL", "RELEASE_SHA"):
        monkeypatch.delenv(k, raising=False)
    yield
    obs.report_limiter.reset()


def _sample(text: str, name: str, **labels: str) -> float | None:
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        head, _, value = line.rpartition(" ")
        if head.split("{")[0] != name:
            continue
        if all(f'{k}="{v}"' in head for k, v in labels.items()):
            return float(value)
    return None


# ---- scrubbing / fingerprints (pure) ---------------------------------------------------------------------------------


def test_scrub_removes_personal_data_and_secrets():
    raw = (
        "user ayse.yilmaz@uni.edu.tr failed with token=abc123secretvalue Authorization: Bearer eyJhbGciOiJIUzI1NiJ9."
        "eyJ1aWQiOjF9.c2lnbmF0dXJlc2ln phone 0532 123 45 67 tc 12345678901 from 10.1.2.3 "
        "url https://x.edu.tr/rooms?q=Ahmet+Hoca&page=2 password: hunter22"
    )
    out = obs.scrub(raw)
    for leaked in (
        "ayse.yilmaz",
        "abc123secretvalue",
        "eyJhbGci",
        "0532 123",
        "12345678901",
        "10.1.2.3",
        "Ahmet",
        "hunter22",
    ):
        assert leaked not in out, (leaked, out)
    assert "[email]" in out and "?[query]" in out and "/rooms" in out


def test_scrub_keeps_stack_line_numbers():
    line = 'File "/app/app/services/x.py", line 123, in solve'
    assert obs.scrub(line) == line


def test_fingerprint_groups_by_frames_not_values():
    frames = ["app.services.x:solve", "app.api.v1.runs:create"]
    a = obs.fingerprint("backend", "KeyError", "KeyError: 'room 12'", frames, "/api/v1/runs")
    b = obs.fingerprint("backend", "KeyError", "KeyError: 'room 99'", frames, "/api/v1/runs")
    c = obs.fingerprint("backend", "KeyError", "KeyError: 'room 99'", ["app.services.y:other"], "/api/v1/runs")
    assert a == b != c


def test_fingerprint_without_frames_uses_normalised_message_and_folds_ids():
    a = obs.fingerprint("frontend", "TypeError", "x is undefined at 1234", [], "/runs/42")
    b = obs.fingerprint("frontend", "TypeError", "x is undefined at 9", [], "/runs/77")
    assert a == b


def test_js_frames_strip_hash_line_and_column():
    chrome = (
        "TypeError: boom\n    at Grid (https://p.edu.tr/_next/static/chunks/app/page-3f2a9c1d.js:1:2345)\n"
        "    at https://p.edu.tr/_next/static/chunks/main-abcdef12.js:9:10"
    )
    firefox = "Grid@https://p.edu.tr/_next/static/chunks/app/page-77aa88bb.js:1:99"
    assert obs.js_frames(chrome) == ["Grid@page.js", "?@main.js"]
    assert obs.js_frames(firefox) == ["Grid@page.js"]


def test_sliding_window_per_key_and_total():
    w = obs.SlidingWindow(per_key=2, total=3, window=60)
    assert w.hit("a", now=0) == 0 and w.hit("a", now=1) == 0
    assert w.hit("a", now=2) > 0  # third from the same key
    assert w.hit("b", now=3) == 0
    assert w.hit("c", now=4) > 0  # total cap
    assert w.hit("a", now=70) == 0  # window passed


def test_record_ai_call_never_raises_and_counts():
    before = obs.AI_CALLS.labels("anthropic", "claude-x", "chat", "ok")._value.get()
    obs.record_ai_call(
        provider="anthropic", model="claude-x", feature="chat", input_tokens=10, output_tokens=5, latency_s=0.3
    )
    obs.record_ai_call(provider=None, model=object(), feature="x" * 500, input_tokens=-1)  # type: ignore[arg-type]
    assert obs.AI_CALLS.labels("anthropic", "claude-x", "chat", "ok")._value.get() == before + 1


# ---- metrics endpoint --------------------------------------------------------------------------------------------------


async def test_metrics_by_route_template_status_and_db_gauges(client):
    admin = await login(client)
    await client.get("/api/v1/terms", headers=admin)
    await client.get("/api/v1/runs/999999", headers=admin)
    await client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "wrong-password"})
    r = await client.get("/metrics")
    assert r.status_code == 200, r.text
    text = r.text
    assert _sample(text, "smartsched_http_requests_total", route="/api/v1/terms", status="200")
    # the template, never the concrete id
    assert _sample(text, "smartsched_http_requests_total", route="/api/v1/runs/{run_id}") is not None
    assert "/api/v1/runs/999999" not in text
    assert (_sample(text, "smartsched_login_failures_total", reason="bad_credentials") or 0) >= 1
    assert _sample(text, "smartsched_db_up") == 1.0
    assert "smartsched_http_request_duration_seconds_bucket" in text
    assert _sample(text, "smartsched_build_info") == 1.0
    assert "smartsched_mail_outbox" in text or "smartsched_solver_runs" in text or "smartsched_db_ping_seconds" in text
    assert "admin@example.com" not in text


async def test_metrics_token_required_when_configured(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "metrics_token", "scrape-token-123")
    assert (await client.get("/metrics")).status_code == 403
    r = await client.get("/metrics", headers={"Authorization": "Bearer scrape-token-123"})
    assert r.status_code == 200 and "smartsched_http_requests" in r.text


async def test_metrics_refused_from_public_address(client):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app, client=("8.8.8.8", 4000)), base_url="http://t") as c:
        assert (await c.get("/metrics")).status_code == 403


async def test_healthz_and_readyz(client):
    assert (await client.get("/healthz")).text == "ok\n"
    r = await client.get("/readyz")
    body = r.json()
    assert r.status_code == 200, body
    assert body["db"] is True and body["workers"] == "ok" and body["migrations"] in ("head", "unmanaged")


def test_alembic_head_is_this_lane_or_later():
    head = obs.alembic_head()
    assert head and head >= "0036_error_events"


# ---- backend exceptions -> error events --------------------------------------------------------------------------------


async def test_unhandled_exception_and_5xx_become_grouped_events(client):
    from app.core.db import get_session_factory
    from app.models.error_event import ErrorEvent
    from fastapi import FastAPI, HTTPException
    from sqlalchemy import select

    mini = FastAPI()
    obs.install(mini)

    @mini.get("/boom/{item_id}")
    async def boom(item_id: int) -> None:
        raise RuntimeError(f"broken for ayse@uni.edu.tr item {item_id}")

    @mini.get("/unavailable")
    async def unavailable() -> None:
        raise HTTPException(503, "down")

    async with AsyncClient(transport=ASGITransport(app=mini, raise_app_exceptions=False), base_url="http://t") as c:
        for i in (1, 2, 3):
            assert (await c.get(f"/boom/{i}", headers={"X-Request-ID": f"req-{i}"})).status_code == 500
        assert (await c.get("/unavailable")).status_code == 503

    async with get_session_factory()() as s:
        rows = (await s.execute(select(ErrorEvent).order_by(ErrorEvent.id))).scalars().all()
    boom_rows = [r for r in rows if r.kind == "RuntimeError"]
    assert len(boom_rows) == 1
    g = boom_rows[0]
    assert g.count == 3 and g.route == "/boom/{item_id}" and g.status_code == 500 and g.source == "backend"
    assert "ayse@" not in g.message and "[email]" in g.message
    assert g.sample_stack and "RuntimeError" in g.sample_stack and "ayse@" not in g.sample_stack
    assert g.last_request_id == "req-3"
    assert any(r.kind == "http_503" and r.route == "/unavailable" for r in rows)


# ---- browser reports ---------------------------------------------------------------------------------------------------


REPORT = {
    "message": "Cannot read properties of undefined (reading 'name') for mehmet@uni.edu.tr",
    "kind": "TypeError",
    "stack": "TypeError: x\n    at RoomCard (https://p.edu.tr/_next/static/chunks/app/page-3f2a9c1d.js:1:2345)",
    "url": "https://p.edu.tr/rooms/42?search=Ahmet",
    "origin": "window.onerror",
}


async def test_client_error_ingest_scrub_group_and_role(client):
    admin = await login(client)
    _uid, teacher = await make_user(client, admin, "ogretmen@example.com")
    r1 = await client.post("/api/v1/ops/errors", json=REPORT, headers=teacher)
    assert r1.status_code == 202, r1.text
    r2 = await client.post("/api/v1/ops/client-errors", json={**REPORT, "url": "https://p.edu.tr/rooms/77"})
    assert r2.status_code == 202, r2.text
    assert r1.json()["group"] == r2.json()["group"]  # same page (ids folded), same frames
    lst = (await client.get("/api/v1/ops/errors?source=frontend", headers=admin)).json()
    assert len(lst["items"]) == 1
    item = lst["items"][0]
    assert item["count"] == 2 and item["route"] == "/rooms/:id" and item["status"] == "open"
    assert "mehmet@" not in item["message"] and "Ahmet" not in json.dumps(item)
    assert item["user_role"] == "TEACHER"
    full = (await client.get(f"/api/v1/ops/errors/{item['id']}", headers=admin)).json()
    assert "RoomCard" in full["sample_stack"]


async def test_client_error_size_and_rate_limit(client):
    big = {**REPORT, "stack": "x" * 7900, "message": "m" * 900}
    assert (await client.post("/api/v1/ops/errors", json=big)).status_code == 413
    codes = [(await client.post("/api/v1/ops/errors", json=REPORT)).status_code for _ in range(25)]
    assert codes[:20] == [202] * 20
    assert 429 in codes[20:]
    r = await client.post("/api/v1/ops/errors", json=REPORT)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert r.json()["detail"]["message_tr"]


async def test_error_status_flow_and_regression(client):
    admin = await login(client)
    await client.post("/api/v1/ops/errors", json=REPORT)
    eid = (await client.get("/api/v1/ops/errors", headers=admin)).json()["items"][0]["id"]
    bad = await client.post(f"/api/v1/ops/errors/{eid}/status", json={"status": "done"}, headers=admin)
    assert bad.status_code == 422
    for st in ("acknowledged", "resolved"):
        r = await client.post(f"/api/v1/ops/errors/{eid}/status", json={"status": st}, headers=admin)
        assert r.status_code == 200 and r.json()["status"] == st
    await client.post("/api/v1/ops/errors", json=REPORT)  # comes back -> reopened
    item = (await client.get(f"/api/v1/ops/errors/{eid}", headers=admin)).json()
    assert item["status"] == "open" and item["reopened"] == 1 and item["count"] == 2
    await client.post(f"/api/v1/ops/errors/{eid}/status", json={"status": "ignored"}, headers=admin)
    await client.post("/api/v1/ops/errors", json=REPORT)
    item = (await client.get(f"/api/v1/ops/errors/{eid}", headers=admin)).json()
    assert item["status"] == "ignored" and item["count"] == 3
    only_open = (await client.get("/api/v1/ops/errors?status=open", headers=admin)).json()
    assert only_open["items"] == [] and only_open["counts"]["ignored"] == 1


async def test_error_retention_purge(client):
    from datetime import timedelta

    from app.core.db import get_session_factory
    from app.models.base import utcnow
    from app.models.error_event import ErrorEvent
    from sqlalchemy import func, select

    await client.post("/api/v1/ops/errors", json=REPORT)
    async with get_session_factory()() as s:
        row = (await s.execute(select(ErrorEvent))).scalar_one()
        row.last_seen = utcnow() - timedelta(days=91)
        await s.commit()
    assert await obs.purge_old_errors(force=True) == 1
    async with get_session_factory()() as s:
        assert (await s.execute(select(func.count()).select_from(ErrorEvent))).scalar_one() == 0


# ---- access + forward-auth -----------------------------------------------------------------------------------------------


async def test_grafana_forward_auth(client):
    admin = await login(client)
    _uid, teacher = await make_user(client, admin, "ogretmen2@example.com")
    assert (await client.get("/api/v1/ops/grafana-auth")).status_code == 401
    assert (await client.get("/api/v1/ops/grafana-auth", headers={"Authorization": "Bearer nope"})).status_code == 401
    r = await client.get("/api/v1/ops/grafana-auth", headers=teacher)
    assert r.status_code == 403 and r.json()["detail"]["message_tr"]
    ok = await client.get("/api/v1/ops/grafana-auth", headers=admin)
    assert ok.status_code == 204 and ok.headers["cache-control"] == "no-store"


async def test_ops_admin_endpoints_refuse_non_admins(client):
    admin = await login(client)
    _uid, teacher = await make_user(client, admin, "ogretmen3@example.com")
    for path in (
        "/api/v1/ops/status",
        "/api/v1/ops/errors",
        "/api/v1/ops/logs",
        "/api/v1/ops/dashboards",
        "/api/v1/ops/requests",
    ):
        assert (await client.get(path, headers=teacher)).status_code == 403, path
        assert (await client.get(path)).status_code == 401, path


# ---- status / chart / logs / dashboards ------------------------------------------------------------------------------


async def test_ops_status_cards_with_mocked_reachability(client, monkeypatch):
    admin = await login(client)
    # Grafana "reachable": the backend's own app answers the probe; Loki on a closed port: down; Prometheus unset: off
    calls: list[str] = []

    async def fake_probe(url: str, timeout: float = 2.0, headers=None):  # noqa: ANN001
        calls.append(url)
        if not url:
            return {"configured": False, "reachable": False, "status": "off"}
        if "grafana" in url:
            return {"configured": True, "reachable": True, "status": "ok", "latency_ms": 3.0, "_body": ""}
        if "ci" in url:
            page = (
                "<tr><td><a href='/ci/runs/7'>#7</a></td><td class='success'>&#10003; success</td><td>main</td>"
                "<td><a href='https://github.com/o/r/commit/abc'><code>abc1234</code></a></td><td>deploy</td>"
                "<td>2026-10-17 18:00:00 UTC</td><td>9m</td><td>ok</td></tr>"
            )
            return {"configured": True, "reachable": True, "status": "ok", "_body": page}
        return {"configured": True, "reachable": False, "status": "down", "error": "ConnectError"}

    from app.api.v1 import ops

    monkeypatch.setattr(ops, "_probe", fake_probe)
    monkeypatch.setenv("OPS_GRAFANA_URL", "http://grafana:3000/grafana")
    monkeypatch.setenv("OPS_LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("OPS_PODCI_URL", "http://172.17.0.1:8095/ci/")
    monkeypatch.setenv("RELEASE_SHA", "0123abcd")
    r = await client.get("/api/v1/ops/status", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["api"]["status"] == "ok" and d["db"]["status"] == "ok"
    assert d["services"]["grafana"]["status"] == "ok"
    assert d["services"]["loki"]["status"] == "down"
    assert d["services"]["prometheus"]["status"] == "off"
    assert d["podci"]["last_run"] == {
        "state": "success",
        "branch": "main",
        "sha": "abc1234",
        "started": "2026-10-17 18:00:00 UTC",
    }
    assert d["release"]["sha"] == "0123abcd"
    assert {"queued", "running", "failed_24h"} <= set(d["queues"])
    assert {"pending", "failed"} <= set(d["mail"])
    assert d["disk"]["status"] in ("ok", "warn", "down") and d["disk"]["total_bytes"] > 0
    assert "_body" not in json.dumps(d)


async def test_requests_chart_falls_back_to_process_ring(client):
    admin = await login(client)
    for _ in range(3):
        await client.get("/api/v1/terms", headers=admin)
    d = (await client.get("/api/v1/ops/requests?minutes=10", headers=admin)).json()
    assert d["source"] == "process" and len(d["points"]) == 10
    assert sum(p["requests"] for p in d["points"]) >= 3


async def test_logs_without_loki_and_service_whitelist(client):
    admin = await login(client)
    d = (await client.get("/api/v1/ops/logs?service=backend", headers=admin)).json()
    assert d["available"] is False and d["message_tr"]
    assert (await client.get("/api/v1/ops/logs?service=etc-passwd", headers=admin)).status_code == 422


async def test_logs_from_loki_are_redacted(client, monkeypatch):
    import httpx
    from app.api.v1 import ops

    admin = await login(client)
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.params["query"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "result": [
                        {
                            "stream": {"service": "backend"},
                            "values": [
                                ["1760000000000000000", "GET /x Authorization: Bearer abc.def.ghi"],
                                ["1760000001000000000", "request failed request_id=req-9 route=/api/v1/runs"],
                            ],
                        }
                    ]
                }
            },
        )

    real = httpx.AsyncClient
    monkeypatch.setattr(ops.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("OPS_LOKI_URL", "http://loki:3100")
    d = (await client.get('/api/v1/ops/logs?service=backend&q=req"9', headers=admin)).json()
    assert d["available"] is True and len(d["lines"]) == 2
    assert d["lines"][0]["line"].startswith("request failed")  # newest first
    assert "abc.def" not in json.dumps(d)
    assert seen["query"] == '{service="backend"} |= "req\\"9"'


async def test_dashboards_list_links_same_origin(client):
    admin = await login(client)
    d = (await client.get("/api/v1/ops/dashboards", headers=admin)).json()
    uids = {x["uid"] for x in d["dashboards"]}
    assert uids == {
        "smartsched-health",
        "smartsched-api",
        "smartsched-jobs",
        "smartsched-bookings",
        "smartsched-ai",
        "smartsched-errors",
    }
    for x in d["dashboards"]:
        assert x["url"].startswith("/grafana/d/") and x["title_tr"]
        assert all(p["embed"].startswith("/grafana/d-solo/") for p in x["panels"])
    assert d["grafana"]["status"] == "off"


def test_dashboard_files_match_the_api_list():
    from pathlib import Path

    from app.api.v1.ops import DASHBOARDS

    root = Path(__file__).resolve().parents[2] / "deploy/observability/grafana/dashboards"
    files = {json.loads(p.read_text())["uid"]: json.loads(p.read_text()) for p in root.glob("*.json")}
    for d in DASHBOARDS:
        assert d["uid"] in files, d["uid"]
        panel_ids = {p["id"] for p in files[d["uid"]]["panels"]}
        assert {p["id"] for p in d["panels"]} <= panel_ids, d["uid"]
        assert files[d["uid"]]["title"].startswith(d["title_tr"]), d["uid"]
