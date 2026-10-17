"""Operations panel API (W3-OPS, ``/admin/ops``; app/core/observability.py, docs/OPERATIONS.md §Observability).

Admin endpoints (``setup.settings`` or ``planning.admin``):
  GET  /ops/status                service cards: API, DB, job queues, mail, deliveries, disk, Grafana / Prometheus /
                                  Loki reachability, last deploy, pod CI
  GET  /ops/requests              requests / 5xx / p95 per minute (Prometheus when it runs, else this process)
  GET  /ops/errors                error groups (filter by status / source); GET /ops/errors/{id} with the stack
  POST /ops/errors/{id}/status    open | acknowledged | resolved | ignored
  GET  /ops/logs                  last N lines of one service from Loki (filter text)
  GET  /ops/dashboards            the provisioned Grafana dashboards (links / same-origin panels)
  GET  /ops/alerts                firing Prometheus alerts
  GET  /ops/grafana-auth          Caddy / nginx forward-auth for ``/grafana/``: 204 admin, 401 signed out, 403 other
Open endpoint (signed in or not, rate limited, PII-scrubbed, <= 8 KB):
  POST /ops/errors  (alias /ops/client-errors)   a browser error report
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DB, bearer, forbidden, get_current_user, require_permission
from app.core import observability as obs
from app.core.config import app_version, get_settings
from app.models import CouncilJob, NotificationOutbox, ScheduleRun, User, WebhookDelivery
from app.models.base import utcnow
from app.models.channels import ChannelDelivery
from app.models.error_event import STATUSES, ErrorEvent
from app.models.integrations import CalendarSyncJob
from app.services import audit
from app.services import ops_alerts as alert_relay
from app.services.bookings_perms import load_access

router = APIRouter(prefix="/ops", tags=["ops"])

OPS_PERMS = ("setup.settings", "planning.admin")
OpsAdmin = Annotated[User, Depends(require_permission(*OPS_PERMS))]
MAX_REPORT_BYTES = 8 * 1024
#: compose service names the log tail may ask Loki for
LOG_SERVICES = (
    "backend",
    "frontend",
    "proxy",
    "db",
    "caddy",
    "grafana",
    "prometheus",
    "loki",
    "alloy",
)


@dataclass(frozen=True)
class OpsConfig:
    """Internal URLs (compose defaults; empty = not configured). Read per request so tests and .env changes apply."""

    grafana: str
    prometheus: str
    loki: str
    podci: str
    grafana_public: str

    @classmethod
    def load(cls) -> OpsConfig:
        env = os.environ.get
        return cls(
            grafana=(env("OPS_GRAFANA_URL") or "").rstrip("/"),
            prometheus=(env("OPS_PROMETHEUS_URL") or "").rstrip("/"),
            loki=(env("OPS_LOKI_URL") or "").rstrip("/"),
            podci=(env("OPS_PODCI_URL") or "").strip(),
            grafana_public=(env("OPS_GRAFANA_PUBLIC_PATH") or "/grafana/").strip() or "/grafana/",
        )


def _msg(tr: str, en: str) -> dict[str, str]:
    return {"message_tr": tr, "message_en": en}


async def _probe(url: str, timeout: float = 2.0, headers: dict[str, str] | None = None) -> dict[str, Any]:
    if not url:
        return {"configured": False, "reachable": False, "status": "off"}
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as c:
            r = await c.get(url, headers=headers or {})
        ok = r.status_code < 400
        return {
            "configured": True,
            "reachable": ok,
            "http_status": r.status_code,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "status": "ok" if ok else "down",
            "_body": r.text[:200_000] if ok else "",
        }
    except (httpx.HTTPError, OSError) as exc:
        return {"configured": True, "reachable": False, "status": "down", "error": type(exc).__name__}


async def _counts(db: Any, model: Any) -> dict[str, int]:
    rows = (await db.execute(select(model.status, func.count()).group_by(model.status))).all()
    return {str(k): int(v) for k, v in rows}


_PODCI_ROW = re.compile(
    r"<td class='(?P<state>[a-z]+)'>[^<]*</td><td>(?P<branch>[^<]*)</td><td><a href='[^']*'><code>(?P<sha>\w+)</code>"
    r"</a></td><td>[^<]*</td><td>(?P<started>[^<]*)</td>"
)


def parse_podci(page: str) -> dict[str, Any] | None:
    """The newest run of the pod CI ``/ci/`` page (``podci/web.py`` ``render_index``)."""
    m = _PODCI_ROW.search(page or "")
    if not m:
        return None
    return {"state": m["state"], "branch": m["branch"], "sha": m["sha"], "started": m["started"]}


def _card(status_: str, **kw: Any) -> dict[str, Any]:
    return {"status": status_, **kw}


@router.get("/status")
async def ops_status(
    _admin: OpsAdmin, db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> dict[str, Any]:
    cfg = OpsConfig.load()
    t0 = time.perf_counter()
    ready = await obs.readiness()
    db_ms = round((time.perf_counter() - t0) * 1000, 1)
    since = utcnow() - timedelta(hours=24)

    runs = await _counts(db, ScheduleRun)
    council = await _counts(db, CouncilJob)
    outbox = await _counts(db, NotificationOutbox)
    failed_runs_24h = (
        await db.execute(
            select(func.count())
            .select_from(ScheduleRun)
            .where(ScheduleRun.status == "FAILED", ScheduleRun.finished_at >= since)
        )
    ).scalar_one()
    oldest_pending = (
        await db.execute(select(func.min(NotificationOutbox.created_at)).where(NotificationOutbox.status == "PENDING"))
    ).scalar_one()
    deliveries: dict[str, dict[str, int]] = {}
    for name, model in (("channel", ChannelDelivery), ("webhook", WebhookDelivery), ("calendar", CalendarSyncJob)):
        deliveries[name] = await _counts(db, model)
    errors_open = (
        await db.execute(select(func.count()).select_from(ErrorEvent).where(ErrorEvent.status == "open"))
    ).scalar_one()
    errors_24h = (
        await db.execute(select(func.count()).select_from(ErrorEvent).where(ErrorEvent.last_seen >= since))
    ).scalar_one()

    disk_path = Path(get_settings().upload_dir).resolve()
    while not disk_path.exists() and disk_path != disk_path.parent:
        disk_path = disk_path.parent
    try:
        du = shutil.disk_usage(disk_path)
        pct = round(du.used / du.total * 100, 1) if du.total else 0.0
        disk = _card(
            "down" if pct >= 90 else "warn" if pct >= 80 else "ok",
            total_bytes=du.total,
            used_bytes=du.used,
            free_bytes=du.free,
            used_pct=pct,
        )
    except OSError:
        disk = _card("unknown")

    podci_headers = {"Cookie": f"smartsched_token={creds.credentials}"} if creds else {}
    grafana, prom, loki, podci = await asyncio.gather(
        _probe(f"{cfg.grafana}/api/health" if cfg.grafana else ""),
        _probe(f"{cfg.prometheus}/-/ready" if cfg.prometheus else ""),
        _probe(f"{cfg.loki}/ready" if cfg.loki else ""),
        _probe(cfg.podci, timeout=3.0, headers=podci_headers),
    )
    podci_run = parse_podci(podci.pop("_body", "")) if podci.get("reachable") else None
    for p in (grafana, prom, loki):
        p.pop("_body", None)
    if podci_run:
        podci["last_run"] = podci_run
        if podci_run["state"] in ("failure", "error"):
            podci["status"] = "warn"

    queued = runs.get("QUEUED", 0) + council.get("QUEUED", 0)
    running = runs.get("RUNNING", 0) + council.get("RUNNING", 0)
    mail_failed = outbox.get("FAILED", 0)
    mail_pending = outbox.get("PENDING", 0) + outbox.get("RUNNING", 0)
    oldest_min = round((utcnow() - oldest_pending).total_seconds() / 60, 1) if oldest_pending else None
    deliveries_failed = sum(v.get("FAILED", 0) for v in deliveries.values())
    alerts = await _firing_alerts(cfg) if prom.get("reachable") else []

    return {
        "generated_at": obs.now_iso(),
        "release": {
            "version": app_version(),
            "sha": (os.environ.get("RELEASE_SHA") or "").strip() or None,
            "deployed_at": (os.environ.get("DEPLOYED_AT") or "").strip() or None,
            "environment": get_settings().environment,
        },
        "api": _card("ok", uptime_s=round(obs.uptime_s()), workers=int(os.environ.get("UVICORN_WORKERS", "1") or 1)),
        "db": _card(
            "ok"
            if ready["db"] and ready["migrations"] in ("head", "unmanaged")
            else "down"
            if not ready["db"]
            else "warn",
            latency_ms=db_ms,
            migrations=ready["migrations"],
            migration_head=ready.get("migration_head"),
            dialect=get_settings().database_url.split(":", 1)[0].split("+", 1)[0],
        ),
        "queues": _card(
            "warn" if ready["workers"] != "ok" or failed_runs_24h else "ok",
            queued=queued,
            running=running,
            failed_24h=int(failed_runs_24h),
            solver=runs,
            council=council,
            stalled_runs=ready.get("stalled_runs", []),
        ),
        "mail": _card(
            "warn" if mail_failed or (oldest_min or 0) > 30 else "ok",
            pending=mail_pending,
            failed=mail_failed,
            unsent=outbox.get("UNSENT", 0),
            sent=outbox.get("SENT", 0),
            oldest_pending_min=oldest_min,
        ),
        "deliveries": _card("warn" if deliveries_failed else "ok", failed=deliveries_failed, by_queue=deliveries),
        "disk": disk,
        "errors": _card("warn" if errors_open else "ok", open=int(errors_open), seen_24h=int(errors_24h)),
        "services": {"grafana": grafana, "prometheus": prom, "loki": loki},
        "grafana_path": cfg.grafana_public,
        "podci": podci,
        "alerts": alerts,
        # the alert relay (app/services/ops_alerts.py): admins get firing / resolved alerts as event ops.alert
        "alert_relay": dict(alert_relay.last_result) or None,
    }


async def _firing_alerts(cfg: OpsConfig) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"{cfg.prometheus}/api/v1/alerts")
        data = r.json().get("data", {}).get("alerts", []) if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError, OSError):
        return []
    out = []
    for a in data:
        if a.get("state") != "firing":
            continue
        labels, ann = a.get("labels") or {}, a.get("annotations") or {}
        out.append(
            {
                "name": labels.get("alertname"),
                "severity": labels.get("severity", "warning"),
                "summary_tr": ann.get("summary_tr") or ann.get("summary"),
                "summary_en": ann.get("summary_en") or ann.get("summary"),
                "since": a.get("activeAt"),
            }
        )
    return out


@router.get("/alerts")
async def ops_alerts(_admin: OpsAdmin) -> dict[str, Any]:
    cfg = OpsConfig.load()
    if not cfg.prometheus:
        return {
            "available": False,
            "alerts": [],
            **_msg("Prometheus yapılandırılmadı.", "Prometheus is not configured."),
        }
    return {"available": True, "alerts": await _firing_alerts(cfg)}


# ---- requests mini chart ---------------------------------------------------------------------------------------------


async def _prom_range(cfg: OpsConfig, query: str, start: float, end: float, step: int) -> dict[int, float]:
    async with httpx.AsyncClient(timeout=3.0) as c:
        r = await c.get(
            f"{cfg.prometheus}/api/v1/query_range", params={"query": query, "start": start, "end": end, "step": step}
        )
    r.raise_for_status()
    out: dict[int, float] = {}
    for series in r.json().get("data", {}).get("result", []):
        for t, v in series.get("values", []):
            try:
                val = float(v)
            except ValueError:
                continue
            if val == val:  # NaN when there was no traffic
                out[int(float(t))] = out.get(int(float(t)), 0.0) + val
    return out


@router.get("/requests")
async def ops_requests(_admin: OpsAdmin, minutes: Annotated[int, Query(ge=5, le=180)] = 60) -> dict[str, Any]:
    cfg = OpsConfig.load()
    if cfg.prometheus:
        end = time.time() // 60 * 60
        start = end - (minutes - 1) * 60
        try:
            req, err, p95 = await asyncio.gather(
                _prom_range(cfg, "sum(increase(smartsched_http_requests_total[2m])) / 2", start, end, 60),
                _prom_range(
                    cfg, 'sum(increase(smartsched_http_requests_total{status=~"5.."}[2m])) / 2', start, end, 60
                ),
                _prom_range(
                    cfg,
                    "histogram_quantile(0.95, sum by (le) (rate(smartsched_http_request_duration_seconds_bucket[5m])))",
                    start,
                    end,
                    60,
                ),
            )
            points = [
                {
                    "t": int(t),
                    "requests": round(req.get(int(t), 0.0)),
                    "errors": round(err.get(int(t), 0.0)),
                    "p95_ms": round(p95[int(t)] * 1000, 1) if int(t) in p95 else None,
                }
                for t in range(int(start), int(end) + 1, 60)
            ]
            return {"source": "prometheus", "points": points}
        except (httpx.HTTPError, ValueError, OSError):
            pass
    return {"source": "process", "points": obs.recent_minutes(minutes)}


# ---- error groups ----------------------------------------------------------------------------------------------------


def _error_out(e: ErrorEvent, full: bool = False) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": e.id,
        "fingerprint": e.fingerprint[:12],
        "source": e.source,
        "kind": e.kind,
        "message": e.message,
        "route": e.route,
        "method": e.method,
        "status_code": e.status_code,
        "user_role": e.user_role,
        "release": e.release,
        "count": e.count,
        "first_seen": e.first_seen.isoformat() if e.first_seen else None,
        "last_seen": e.last_seen.isoformat() if e.last_seen else None,
        "status": e.status,
        "reopened": e.reopened,
        "last_request_id": e.last_request_id,
    }
    if full:
        d["sample_stack"] = e.sample_stack
        d["resolved_at"] = e.resolved_at.isoformat() if e.resolved_at else None
    return d


@router.get("/errors")
async def list_errors(
    _admin: OpsAdmin,
    db: DB,
    status_: Annotated[str | None, Query(alias="status")] = None,
    source: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    q = select(ErrorEvent)
    if status_:
        wanted = [s for s in status_.split(",") if s in STATUSES]
        if wanted:
            q = q.where(ErrorEvent.status.in_(wanted))
    if source in ("backend", "frontend"):
        q = q.where(ErrorEvent.source == source)
    rows = (await db.execute(q.order_by(ErrorEvent.last_seen.desc()).limit(limit))).scalars().all()
    counts = {
        str(k): int(v)
        for k, v in (await db.execute(select(ErrorEvent.status, func.count()).group_by(ErrorEvent.status))).all()
    }
    return {"items": [_error_out(e) for e in rows], "counts": counts, "retention_days": obs.ERROR_RETENTION_DAYS}


@router.get("/errors/{error_id}")
async def get_error(error_id: int, _admin: OpsAdmin, db: DB) -> dict[str, Any]:
    e = await db.get(ErrorEvent, error_id)
    if e is None:
        raise HTTPException(404, {"code": "not_found", **_msg("Hata kaydı bulunamadı.", "Error group not found.")})
    return _error_out(e, full=True)


class StatusIn(BaseModel):
    status: str


@router.post("/errors/{error_id}/status")
async def set_error_status(error_id: int, body: StatusIn, admin: OpsAdmin, db: DB) -> dict[str, Any]:
    if body.status not in STATUSES:
        raise HTTPException(
            422,
            {
                "code": "invalid_status",
                "allowed": list(STATUSES),
                **_msg("Geçersiz durum.", "Invalid status."),
            },
        )
    e = await db.get(ErrorEvent, error_id)
    if e is None:
        raise HTTPException(404, {"code": "not_found", **_msg("Hata kaydı bulunamadı.", "Error group not found.")})
    before = e.status
    e.status = body.status
    if body.status == "resolved":
        e.resolved_at = utcnow()
        e.resolved_by = admin.id
    else:
        e.resolved_at = None
        e.resolved_by = None
    if before != body.status:  # triage is shared between admins: who changed it, from what, to what
        await audit.record(
            db,
            "ops.error.status",
            "error_event",
            e.id,
            before={"status": before},
            after={"status": body.status},
            actor=admin,
        )
    await db.commit()
    return _error_out(e)


class ClientErrorIn(BaseModel):
    message: str = Field(default="", max_length=4000)
    kind: str | None = Field(default=None, max_length=200)
    stack: str | None = Field(default=None, max_length=8000)
    component_stack: str | None = Field(default=None, max_length=4000)
    url: str | None = Field(default=None, max_length=1000)
    release: str | None = Field(default=None, max_length=64)
    #: window.onerror | unhandledrejection | boundary
    origin: str | None = Field(default=None, max_length=32)


async def _optional_user(request: Request, creds: HTTPAuthorizationCredentials | None, db: Any) -> User | None:
    if creds is None:
        return None
    try:
        return await get_current_user(request, creds, db)
    except HTTPException:
        return None


async def _client_error(
    request: Request,
    response: Response,
    db: DB,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_REPORT_BYTES:
        raise HTTPException(
            413, {"code": "too_large", **_msg("Hata raporu 8 KB'den büyük.", "Error report over 8 KB.")}
        )
    try:
        body = ClientErrorIn.model_validate_json(raw or b"{}")
    except ValueError as exc:
        raise HTTPException(
            422, {"code": "invalid_report", **_msg("Hata raporu okunamadı.", "Unreadable error report.")}
        ) from exc
    user = await _optional_user(request, creds, db)
    key = (
        f"u:{user.id}"
        if user
        else f"a:{request.headers.get('x-real-ip') or (request.client.host if request.client else '-')}"
    )
    wait = obs.report_limiter.hit(key)
    if wait:
        raise HTTPException(
            429,
            {"code": "rate_limited", **_msg("Çok fazla hata raporu; biraz sonra.", "Too many error reports; later.")},
            headers={"Retry-After": str(wait)},
        )
    role: str | None = None
    if user is not None:
        acc = await load_access(db, user)
        role = (acc.role.code if acc.role is not None else None) or user.role
    stack = body.stack or ""
    if body.component_stack:
        stack = f"{stack}\n--- component stack ---\n{body.component_stack}"
    path = None
    if body.url:
        path = re.sub(r"^https?://[^/]+", "", body.url) or "/"
    row = await obs.ingest(
        db,
        obs.ErrorReport(
            source="frontend",
            kind=(body.kind or "Error")[:128],
            message=body.message or (body.kind or "Error"),
            stack=stack,
            route=path,
            user_role=role,
            release=body.release,
            frames=obs.js_frames(body.stack or ""),
        ),
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return {"accepted": True, "group": row.fingerprint[:12]}


router.add_api_route("/errors", _client_error, methods=["POST"], status_code=202)
router.add_api_route("/client-errors", _client_error, methods=["POST"], status_code=202, include_in_schema=False)


# ---- logs (Loki) -----------------------------------------------------------------------------------------------------


@router.get("/logs")
async def ops_logs(
    _admin: OpsAdmin,
    service: Annotated[str, Query()] = "backend",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    q: Annotated[str | None, Query(max_length=200)] = None,
    minutes: Annotated[int, Query(ge=1, le=10080)] = 60,
) -> dict[str, Any]:
    if service not in LOG_SERVICES:
        raise HTTPException(
            422,
            {
                "code": "unknown_service",
                "allowed": list(LOG_SERVICES),
                **_msg("Bilinmeyen servis.", "Unknown service."),
            },
        )
    cfg = OpsConfig.load()
    base = {"service": service, "services": list(LOG_SERVICES)}
    if not cfg.loki:
        return {**base, "available": False, "lines": [], **_msg("Loki yapılandırılmadı.", "Loki is not configured.")}
    selector = f'{{service="{service}"}}'
    if q:
        needle = q.replace("\\", "\\\\").replace('"', '\\"')
        selector += f' |= "{needle}"'
    end_ns = int(time.time() * 1e9)
    params: dict[str, str | int] = {
        "query": selector,
        "limit": limit,
        "direction": "backward",
        "start": end_ns - minutes * 60 * 10**9,
        "end": end_ns,
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(f"{cfg.loki}/loki/api/v1/query_range", params=params)
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
    except (httpx.HTTPError, ValueError, OSError) as exc:
        return {
            **base,
            "available": False,
            "lines": [],
            "error": type(exc).__name__,
            **_msg("Loki'ye ulaşılamadı.", "Loki is unreachable."),
        }
    lines: list[dict[str, Any]] = []
    for stream in result:
        labels = stream.get("stream") or {}
        for ts, line in stream.get("values", []):
            lines.append(
                {
                    "ts": int(ts) // 1_000_000,
                    "service": labels.get("service", service),
                    "line": obs.scrub(line, 4000),
                }
            )
    lines.sort(key=lambda x: x["ts"], reverse=True)
    return {**base, "available": True, "lines": lines[:limit]}


# ---- Grafana ---------------------------------------------------------------------------------------------------------

#: provisioned in smartsched/deploy/observability/grafana/dashboards (uid -> titles, the panels the page may embed)
DASHBOARDS: tuple[dict[str, Any], ...] = (
    {
        "uid": "smartsched-health",
        "slug": "servis-sagligi",
        "title_tr": "Servis sağlığı",
        "title_en": "Service health",
        "panels": [
            {"id": 1, "title_tr": "Servisler ayakta", "title_en": "Services up"},
            {"id": 4, "title_tr": "Bellek (servisler)", "title_en": "Memory (services)"},
        ],
    },
    {
        "uid": "smartsched-api",
        "slug": "api",
        "title_tr": "API",
        "title_en": "API",
        "panels": [
            {"id": 1, "title_tr": "İstek/sn", "title_en": "Requests/s"},
            {"id": 2, "title_tr": "p95 gecikme", "title_en": "p95 latency"},
        ],
    },
    {
        "uid": "smartsched-jobs",
        "slug": "cozucu-ve-isler",
        "title_tr": "Çözücü ve işler",
        "title_en": "Solver & jobs",
        "panels": [{"id": 1, "title_tr": "Kuyruk", "title_en": "Queue"}],
    },
    {
        "uid": "smartsched-bookings",
        "slug": "rezervasyon-ve-onaylar",
        "title_tr": "Rezervasyonlar ve onaylar",
        "title_en": "Bookings & approvals",
        "panels": [{"id": 1, "title_tr": "Rezervasyonlar", "title_en": "Bookings"}],
    },
    {
        "uid": "smartsched-ai",
        "slug": "yapay-zeka-kullanimi",
        "title_tr": "Yapay zekâ kullanımı",
        "title_en": "AI usage",
        "panels": [{"id": 1, "title_tr": "Çağrılar", "title_en": "Calls"}],
    },
    {
        "uid": "smartsched-errors",
        "slug": "hatalar-ve-gunlukler",
        "title_tr": "Hatalar ve günlükler",
        "title_en": "Errors & logs",
        "panels": [{"id": 1, "title_tr": "5xx oranı", "title_en": "5xx rate"}],
    },
)


@router.get("/dashboards")
async def ops_dashboards(_admin: OpsAdmin) -> dict[str, Any]:
    cfg = OpsConfig.load()
    probe = await _probe(f"{cfg.grafana}/api/health" if cfg.grafana else "")
    probe.pop("_body", None)
    base = cfg.grafana_public.rstrip("/")
    return {
        "grafana": {**probe, "path": cfg.grafana_public},
        "dashboards": [
            {
                **d,
                "url": f"{base}/d/{d['uid']}/{d['slug']}?orgId=1",
                "panels": [
                    {**p, "embed": f"{base}/d-solo/{d['uid']}/{d['slug']}?orgId=1&panelId={p['id']}&from=now-6h&to=now"}
                    for p in d["panels"]
                ],
            }
            for d in DASHBOARDS
        ],
    }


@router.get("/grafana-auth", status_code=204, include_in_schema=False)
async def grafana_auth(
    request: Request, db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> Response:
    """Forward-auth target of the edge for ``/grafana/`` (Grafana trusts the edge's ``X-WEBAUTH-USER``)."""
    user = await get_current_user(request, creds, db)  # 401 when signed out / revoked
    access = await load_access(db, user)
    if not any(p in access.perms for p in OPS_PERMS):
        raise forbidden(*OPS_PERMS)
    return Response(status_code=204, headers={"Cache-Control": "no-store", "X-Ops-User": f"smartsched-{user.id}"})
