"""Observability: Prometheus metrics, grouped error events, optional Sentry (W3-OPS, docs/OPERATIONS.md §Observability).

What lives here
* **Metrics** (``prometheus_client``) served as text on ``GET /metrics`` at the app root. The path is internal: nginx
  routes ``/`` to the frontend and only ``/api/v1/calendar|ics`` and ``/uploads/rooms`` to the backend, so the
  public edge never reaches it; Prometheus scrapes ``backend:8000/metrics`` on the compose network. Access: a
  ``METRICS_TOKEN`` bearer when one is configured, otherwise private / loopback client addresses only.
  - request count / latency by **route template** and status, requests in flight, DB pool use;
  - login failures and domain events (bookings created / cancelled, approvals decided, runs requested), derived
    from the route template of successful writes, so no other module has to call in;
  - AI calls: :func:`record_ai_call` (W3-AI's gateway imports it; counters by provider / model / feature /
    outcome, tokens, latency);
  - at scrape time, from the database: solver runs / council jobs / invigilation plans by status, solver
    durations of the last 24 h, mail outbox and delivery queue depth, bookings and approvals, error groups.
  With ``UVICORN_WORKERS`` > 1 the counters are shared through ``PROMETHEUS_MULTIPROC_DIR`` (set here before
  ``prometheus_client`` is imported, one directory per uvicorn master), so any worker answers the whole picture.
* **Error events**: unhandled exceptions and 5xx answers (middleware), ``ERROR`` log records with a traceback from
  the app's own loggers (job queue, workers) and browser reports (``POST /api/v1/ops/errors``) become grouped,
  PII-scrubbed rows of ``error_events`` (:func:`ingest`).
* **Sentry** (optional): ``SENTRY_DSN`` in the environment and the ``sentry-sdk`` package installed
  (``BACKEND_EXTRA_PIP=sentry-sdk``) forward the same events; nothing is sent otherwise.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import ipaddress
import logging
import os
import re
import tempfile
import threading
import time
import traceback
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _multiprocess_dir() -> None:
    """One shared metrics directory per uvicorn master (``--workers N`` spawns N processes with the same parent)."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        Path(os.environ["PROMETHEUS_MULTIPROC_DIR"]).mkdir(parents=True, exist_ok=True)
        return
    try:
        workers = int(os.environ.get("UVICORN_WORKERS", "1") or 1)
    except ValueError:
        workers = 1
    if workers > 1 and os.environ.get("ENVIRONMENT", "") != "test":
        d = Path(tempfile.gettempdir()) / f"smartsched-metrics-{os.getppid()}"
        d.mkdir(parents=True, exist_ok=True)
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(d)


_multiprocess_dir()

from prometheus_client import (  # noqa: E402  (after PROMETHEUS_MULTIPROC_DIR is decided)
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    disable_created_metrics,  # noqa: E402
    generate_latest,
)
from prometheus_client import REGISTRY as DEFAULT_REGISTRY  # noqa: E402

disable_created_metrics()  # type: ignore[no-untyped-call]  # no *_created series: half the series count (R-OPS: < 10k series)

log = logging.getLogger("smartsched.observability")
MULTIPROCESS = bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))
STARTED_AT = time.time()

# --------------------------------------------------------------------------------------------------------------------
# metric families
# --------------------------------------------------------------------------------------------------------------------

LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 120.0)

HTTP_REQUESTS = Counter(
    "smartsched_http_requests", "HTTP requests by route template and status", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "smartsched_http_request_duration_seconds",
    "HTTP request latency by route template",
    ["method", "route"],
    buckets=LATENCY_BUCKETS,
)
HTTP_IN_FLIGHT = Gauge("smartsched_http_requests_in_flight", "requests being served", multiprocess_mode="livesum")
DB_POOL = Gauge(
    "smartsched_db_pool_connections", "SQLAlchemy pool connections by state", ["state"], multiprocess_mode="livesum"
)
LOGIN_FAILURES = Counter("smartsched_login_failures", "failed sign-ins (401 / 429 on POST /auth/login)", ["reason"])
DOMAIN_EVENTS = Counter("smartsched_domain_events", "successful writes by kind", ["event"])
ERRORS = Counter("smartsched_errors", "error occurrences stored as error events", ["source", "kind"])
AI_CALLS = Counter("smartsched_ai_calls", "AI provider calls", ["provider", "model", "feature", "outcome"])
AI_TOKENS = Counter("smartsched_ai_tokens", "AI tokens", ["provider", "model", "direction"])
AI_LATENCY = Histogram(
    "smartsched_ai_call_duration_seconds",
    "AI call latency",
    ["provider", "feature"],
    buckets=(0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)
AI_COST = Counter("smartsched_ai_cost_usd", "estimated AI cost (USD) as reported by the gateway", ["provider", "model"])

AI_BUDGET = Gauge(
    "smartsched_ai_budget_used_ratio",
    "share of an AI budget used (W3-AI sets it; alerts at 0.8 and 1.0)",
    ["scope"],
    multiprocess_mode="mostrecent",
)
PROCESS_RSS = Gauge(
    "smartsched_process_resident_memory_bytes", "resident memory of the backend workers", multiprocess_mode="livesum"
)
GUARD_REFUSALS = Counter(
    "smartsched_guard_refusals", "integrity / AI guard refusals (publish, pin, move, AI scope)", ["guard"]
)

#: route templates whose 2xx answer is a domain event (method, template) -> event
DOMAIN_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/bookings"): "booking_created",
    ("POST", "/api/v1/bookings/recurring"): "booking_created",
    ("POST", "/api/v1/bookings/multi"): "booking_created",
    ("POST", "/api/v1/bookings/{booking_id}/cancel"): "booking_cancelled",
    ("POST", "/api/v1/bookings/cancel-multi"): "booking_cancelled",
    ("POST", "/api/v1/approvals/{request_id}/decide"): "approval_decided",
    ("POST", "/api/v1/approvals/groups/{group_id}/decide"): "approval_decided",
    ("POST", "/api/v1/runs"): "solver_run_requested",
    ("POST", "/api/v1/council/jobs"): "council_job_requested",
}
LOGIN_ROUTE = "/api/v1/auth/login"


def _label(value: object, limit: int = 64) -> str:
    s = str(value or "unknown").strip() or "unknown"
    return re.sub(r"[^\w.:/-]", "_", s)[:limit]


def record_ai_call(
    *,
    provider: str,
    model: str,
    feature: str = "other",
    outcome: str = "ok",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_s: float | None = None,
    cost_usd: float | None = None,
) -> None:
    """Count one AI call (W3-AI's gateway calls this after every provider call, blocked or not).

    ``outcome``: ``ok`` | ``error`` | ``blocked`` (guardrail) | ``limited`` (usage limit) | ``timeout``.
    Never raises."""
    try:
        p, m, f, o = _label(provider), _label(model), _label(feature), _label(outcome, 16)
        AI_CALLS.labels(p, m, f, o).inc()
        if input_tokens > 0:
            AI_TOKENS.labels(p, m, "input").inc(input_tokens)
        if output_tokens > 0:
            AI_TOKENS.labels(p, m, "output").inc(output_tokens)
        if latency_s is not None and latency_s >= 0:
            AI_LATENCY.labels(p, f).observe(latency_s)
        if cost_usd:
            AI_COST.labels(p, m).inc(max(0.0, float(cost_usd)))
    except Exception:  # noqa: BLE001 - metrics must never break a call
        log.debug("record_ai_call failed", exc_info=True)


def set_ai_budget_ratio(scope: str, ratio: float) -> None:
    """Publish how much of an AI budget is used (``scope``: ``global``, ``provider:<name>``, ``role:<code>``; never a
    user id or e-mail, R-OPS-04). 0.8 and 1.0 fire the ``SmartSchedAiBudget*`` alerts. Never raises."""
    try:
        AI_BUDGET.labels(_label(scope, 48)).set(max(0.0, float(ratio)))
    except Exception:  # noqa: BLE001
        log.debug("set_ai_budget_ratio failed", exc_info=True)


def record_guard_refusal(guard: str) -> None:
    """Count one refusal of an integrity or AI guard (``publish``, ``pin``, ``move``, ``ai_scope``, ...).
    Never raises."""
    try:
        GUARD_REFUSALS.labels(_label(guard, 32)).inc()
    except Exception:  # noqa: BLE001
        log.debug("record_guard_refusal failed", exc_info=True)


# --------------------------------------------------------------------------------------------------------------------
# per-minute ring buffer (the panel's mini chart when Prometheus is not running)
# --------------------------------------------------------------------------------------------------------------------


@dataclass
class _Minute:
    requests: int = 0
    errors: int = 0
    latencies: list[float] = field(default_factory=list)


_ring_lock = threading.Lock()
_ring: dict[int, _Minute] = {}
RING_MINUTES = 180
RING_SAMPLES = 400


def _ring_add(duration_s: float, status: int, now: float | None = None) -> None:
    minute = int((now if now is not None else time.time()) // 60)
    with _ring_lock:
        m = _ring.get(minute)
        if m is None:
            m = _ring[minute] = _Minute()
            for old in [k for k in _ring if k < minute - RING_MINUTES]:
                del _ring[old]
        m.requests += 1
        if status >= 500:
            m.errors += 1
        if len(m.latencies) < RING_SAMPLES:
            m.latencies.append(duration_s)


def recent_minutes(minutes: int = 60, now: float | None = None) -> list[dict[str, Any]]:
    """This process's per-minute requests / 5xx / p95 latency (ms), oldest first, empty minutes included."""
    end = int((now if now is not None else time.time()) // 60)
    out: list[dict[str, Any]] = []
    with _ring_lock:
        for minute in range(end - max(1, min(minutes, RING_MINUTES)) + 1, end + 1):
            m = _ring.get(minute)
            lat = sorted(m.latencies) if m else []
            p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))] * 1000 if lat else None
            out.append(
                {
                    "t": minute * 60,
                    "requests": m.requests if m else 0,
                    "errors": m.errors if m else 0,
                    "p95_ms": round(p95, 1) if p95 is not None else None,
                }
            )
    return out


def reset_ring() -> None:
    with _ring_lock:
        _ring.clear()


# --------------------------------------------------------------------------------------------------------------------
# PII scrubbing + fingerprints
# --------------------------------------------------------------------------------------------------------------------

_SCRUBBERS: tuple[tuple[re.Pattern[str], str], ...] = (
    # JWTs and bearer / basic credentials
    (re.compile(r"eyJ[\w-]{6,}\.[\w-]{6,}\.[\w-]{6,}"), "[token]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[\w.~+/=-]{8,}"), r"\1 [token]"),
    # key=value / "key": "value" secrets
    (
        re.compile(
            r"(?i)([\"']?(?:password|passwd|parola|şifre|sifre|secret|token|api[_-]?key|authorization|cookie|"
            r"session|access_token|refresh_token|dsn)[\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&}]+)"
        ),
        r"\1[redacted]",
    ),
    (re.compile(r"(?i)\b(sk-ant-|sk-|xox[abp]-|ghp_|AKIA)[\w-]{8,}"), "[secret]"),
    # e-mail addresses
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    # query strings of URLs (they carry search terms, names, tokens)
    (re.compile(r"(https?://[^\s?#\"']+|/[\w./%-]*)\?[^\s\"')]*"), r"\1?[query]"),
    # Turkish mobile numbers, TC kimlik (11 digits), other long digit runs (card / phone / IBAN parts)
    (re.compile(r"(?<![\w.])(?:\+?90[\s-]?)?0?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?![\w])"), "[phone]"),
    (re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b"), "[iban]"),
    (re.compile(r"(?<![\w.:])\d{10,}(?![\w])"), "[number]"),
    # IPv4 addresses
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[ip]"),
)


def scrub(text: str | None, limit: int | None = None) -> str:
    """Remove personal data and credentials from free text (messages, stacks, URLs, log lines)."""
    if not text:
        return ""
    out = str(text)
    for rx, repl in _SCRUBBERS:
        out = rx.sub(repl, out)
    if limit is not None and len(out) > limit:
        out = out[: limit - 1] + "…"
    return out


_NORMALISE = (
    (re.compile(r"\[(?:token|email|query|phone|iban|number|ip|redacted|secret)\]"), "?"),
    (re.compile(r"0x[0-9a-fA-F]+|\b[0-9a-f]{8,}\b"), "H"),
    (re.compile(r"\d+"), "N"),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "S"),
    (re.compile(r"\s+"), " "),
)


def normalise_message(message: str) -> str:
    out = scrub(message)
    for rx, repl in _NORMALISE:
        out = rx.sub(repl, out)
    return out.strip()[:300]


_JS_FRAME = (
    re.compile(r"^\s*at\s+(?:(?P<fn>[^\s(]+)\s+\()?(?P<file>[^\s()]+?):\d+:\d+\)?\s*$"),  # V8
    re.compile(r"^\s*(?P<fn>[^@\s]*)@(?P<file>\S+?):\d+:\d+\s*$"),  # Firefox / Safari
)
_CHUNK_HASH = re.compile(r"[-.][0-9a-f]{6,}(?=\.m?js$)")


def js_frames(stack: str, limit: int = 5) -> list[str]:
    """``fn@file`` of the top browser stack frames, without line/column, query or build hash (stable per release)."""
    frames: list[str] = []
    for line in (stack or "").splitlines():
        for rx in _JS_FRAME:
            m = rx.match(line)
            if m:
                file = m.group("file").split("?")[0].split("#")[0].rsplit("/", 1)[-1]
                frames.append(f"{m.group('fn') or '?'}@{_CHUNK_HASH.sub('', file)}")
                break
        if len(frames) >= limit:
            break
    return frames


def py_frames(exc: BaseException, limit: int = 5) -> list[str]:
    """``module:function`` of the innermost in-app frames (``app/...``), innermost first."""
    out: list[str] = []
    for fs in reversed(traceback.extract_tb(exc.__traceback__)):
        path = fs.filename.replace("\\", "/")
        if "/site-packages/" in path or "/app/" not in path:
            continue
        mod = path.rsplit("/app/", 1)[-1].removesuffix(".py").replace("/", ".")
        out.append(f"app.{mod}:{fs.name}")
        if len(out) >= limit:
            break
    return out


def fingerprint(source: str, kind: str, message: str, frames: list[str], route: str | None) -> str:
    """Stable group key: the in-app frames when there are any, else the normalised message."""
    basis = "|".join(
        [source, kind, ";".join(frames) if frames else normalise_message(message), _route_key(route or "")]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


_ID_SEGMENT = re.compile(r"/(?:\d+|[0-9a-f]{8,}|[0-9a-f-]{36})(?=/|$)")


def _route_key(route: str) -> str:
    """Browser paths carry ids (``/runs/42``): fold them so one page is one group."""
    return _ID_SEGMENT.sub("/:id", route.split("?")[0])


# --------------------------------------------------------------------------------------------------------------------
# error ingestion
# --------------------------------------------------------------------------------------------------------------------


def release_sha() -> str:
    from app.core.config import app_version

    return (os.environ.get("RELEASE_SHA") or "").strip()[:40] or app_version()


@dataclass
class ErrorReport:
    source: str  # backend | frontend
    kind: str
    message: str
    stack: str = ""
    route: str | None = None
    method: str | None = None
    status_code: int | None = None
    user_role: str | None = None
    release: str | None = None
    request_id: str | None = None
    frames: list[str] = field(default_factory=list)

    def cleaned(self) -> ErrorReport:
        route = scrub(self.route, 255) if self.route else None
        if route and self.source == "frontend":
            route = _route_key(route.split("?[query]")[0])
        return ErrorReport(
            source=self.source[:16],
            kind=scrub(self.kind, 128) or "Error",
            message=scrub(self.message, 1000),
            stack=scrub(self.stack, 16000),
            route=route,
            method=(self.method or None) and self.method[:8],
            status_code=self.status_code,
            user_role=(self.user_role or None) and self.user_role[:32],
            release=(self.release or release_sha())[:64],
            request_id=(self.request_id or None) and re.sub(r"[^\w.:-]", "", self.request_id)[:64],
            frames=self.frames,
        )


async def ingest(session: Any, report: ErrorReport) -> Any:
    """Fold one occurrence into its group (insert or count). Returns the ``ErrorEvent`` row (committed)."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models.base import utcnow
    from app.models.error_event import ACKNOWLEDGED, IGNORED, OPEN, RESOLVED, ErrorEvent

    r = report.cleaned()
    fp = fingerprint(r.source, r.kind, r.message, r.frames, r.route)
    now = utcnow()
    for _attempt in range(2):  # a concurrent first insert of the same group (other worker) -> update instead
        row = (await session.execute(select(ErrorEvent).where(ErrorEvent.fingerprint == fp))).scalar_one_or_none()
        if row is None:
            row = ErrorEvent(
                fingerprint=fp,
                source=r.source,
                kind=r.kind,
                message=r.message,
                route=r.route,
                method=r.method,
                status_code=r.status_code,
                user_role=r.user_role,
                release=r.release,
                sample_stack=r.stack or None,
                last_request_id=r.request_id,
                count=1,
                first_seen=now,
                last_seen=now,
                status=OPEN,
            )
            session.add(row)
        else:
            row.count = (row.count or 0) + 1
            row.last_seen = now
            row.release = r.release
            row.user_role = r.user_role or row.user_role
            row.status_code = r.status_code or row.status_code
            row.last_request_id = r.request_id or row.last_request_id
            if not row.sample_stack and r.stack:
                row.sample_stack = r.stack
            if row.status == RESOLVED:  # regression
                row.status = OPEN
                row.reopened = (row.reopened or 0) + 1
                row.resolved_at = None
                row.resolved_by = None
            elif row.status not in (OPEN, ACKNOWLEDGED, IGNORED):
                row.status = OPEN
        try:
            await session.commit()
            break
        except IntegrityError:
            await session.rollback()
    ERRORS.labels(_label(r.source, 16), _label(r.kind)).inc()
    _sentry_forward(r, fp)
    return row


_capturing: contextvars.ContextVar[bool] = contextvars.ContextVar("smartsched_capturing_error", default=False)


async def store_report(report: ErrorReport, timeout: float = 3.0) -> None:
    """``ingest`` in its own session; never raises (the database may be the thing that failed)."""
    if _capturing.get():
        return
    token = _capturing.set(True)
    try:
        from app.core.db import get_session_factory

        async def _go() -> None:
            async with get_session_factory()() as session:
                await ingest(session, report)

        await asyncio.wait_for(_go(), timeout)
    except Exception:  # noqa: BLE001
        log.warning("could not store an error event (%s: %s)", report.kind, report.message[:120], exc_info=True)
    finally:
        _capturing.reset(token)


def report_from_exception(
    exc: BaseException,
    *,
    route: str | None = None,
    method: str | None = None,
    status_code: int | None = 500,
    user_role: str | None = None,
    request_id: str | None = None,
) -> ErrorReport:
    report = ErrorReport(
        source="backend",
        kind=type(exc).__name__,
        message=str(exc) or type(exc).__name__,
        stack="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        route=route,
        method=method,
        status_code=status_code,
        user_role=user_role,
        request_id=request_id,
        frames=py_frames(exc),
    )
    _sentry_pending[id(report)] = exc
    return report


# --------------------------------------------------------------------------------------------------------------------
# rate limit for browser reports
# --------------------------------------------------------------------------------------------------------------------


class SlidingWindow:
    """At most ``per_key`` reports per key and ``total`` overall per ``window`` seconds (per process)."""

    def __init__(self, per_key: int = 20, total: int = 300, window: float = 60.0) -> None:
        self.per_key, self.total, self.window = per_key, total, window
        self._lock = threading.Lock()
        self._keys: dict[str, deque[float]] = defaultdict(deque)
        self._all: deque[float] = deque()

    def _prune(self, q: deque[float], now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def hit(self, key: str, now: float | None = None) -> int:
        """0 when allowed (and counted); otherwise the seconds to wait."""
        t = time.monotonic() if now is None else now
        with self._lock:
            q = self._keys[key]
            self._prune(q, t)
            self._prune(self._all, t)
            if len(q) >= self.per_key:
                return int(self.window - (t - q[0])) + 1
            if len(self._all) >= self.total:
                return int(self.window - (t - self._all[0])) + 1
            q.append(t)
            self._all.append(t)
            if len(self._keys) > 5000:
                for k in [k for k, v in self._keys.items() if not v]:
                    del self._keys[k]
            return 0

    def reset(self) -> None:
        with self._lock:
            self._keys.clear()
            self._all.clear()


report_limiter = SlidingWindow()


# --------------------------------------------------------------------------------------------------------------------
# optional Sentry
# --------------------------------------------------------------------------------------------------------------------

_sentry: Any = None
_sentry_pending: dict[int, BaseException] = {}


def init_sentry() -> bool:
    """Initialise Sentry when ``SENTRY_DSN`` is set and ``sentry_sdk`` is installed (no PII, no tracing)."""
    global _sentry
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        log.warning("SENTRY_DSN is set but sentry-sdk is not installed (BACKEND_EXTRA_PIP=sentry-sdk); skipped")
        return False
    sentry_sdk.init(
        dsn=dsn,
        release=release_sha(),
        environment=os.environ.get("SENTRY_ENVIRONMENT") or os.environ.get("ENVIRONMENT", "prod"),
        send_default_pii=False,
        traces_sample_rate=0.0,
        default_integrations=False,
    )
    _sentry = sentry_sdk
    return True


def _sentry_forward(report: ErrorReport, fp: str) -> None:
    exc = _sentry_pending.pop(id(report), None)
    if _sentry is None:
        return
    try:
        with _sentry.new_scope() as scope:
            scope.fingerprint = [fp]
            scope.set_tag("source", report.source)
            if report.route:
                scope.set_tag("route", report.route)
            if report.user_role:
                scope.set_tag("user_role", report.user_role)
            if exc is not None:
                _sentry.capture_exception(exc)
            else:
                _sentry.capture_message(f"{report.kind}: {report.message}", level="error")
    except Exception:  # noqa: BLE001
        log.debug("sentry forward failed", exc_info=True)


# --------------------------------------------------------------------------------------------------------------------
# ASGI middleware
# --------------------------------------------------------------------------------------------------------------------

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]


def route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        # nested routers keep the template relative to their prefix (``/terms``): put the prefix back from the
        # request path (path parameters span one segment each)
        req = [p for p in str(scope.get("path", "")).split("/") if p]
        tpl = [p for p in path.split("/") if p]
        if len(req) > len(tpl) and ":path}" not in path:
            return "/" + "/".join(req[: len(req) - len(tpl)] + tpl)
        return path
    if scope.get("endpoint") is not None and not scope.get("path_params"):
        return str(scope.get("path", "unmatched"))[:120]  # a plain Starlette route (/healthz, /readyz)
    return "unmatched"


def _sample_pool() -> None:
    try:
        from app.core.db import get_engine

        pool: Any = get_engine().sync_engine.pool
        checked_out = int(pool.checkedout()) if hasattr(pool, "checkedout") else 0
        idle = int(pool.checkedin()) if hasattr(pool, "checkedin") else 0
        overflow = max(0, int(pool.overflow())) if hasattr(pool, "overflow") else 0
        DB_POOL.labels("checked_out").set(checked_out)
        DB_POOL.labels("idle").set(idle)
        DB_POOL.labels("overflow").set(overflow)
        with open("/proc/self/statm", encoding="ascii") as fh:
            PROCESS_RSS.set(int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE"))
    except Exception:  # noqa: BLE001
        pass


def _header(scope: Scope, name: bytes) -> str:
    for k, v in scope.get("headers") or []:
        if k == name:
            return str(v.decode("latin-1"))
    return ""


async def _role_of(scope: Scope) -> str | None:
    """Role code of the bearer token's user (errors are rare: one indexed lookup)."""
    auth = ""
    for k, v in scope.get("headers") or []:
        if k == b"authorization":
            auth = v.decode("latin-1")
            break
    if not auth.lower().startswith("bearer "):
        return None
    try:
        from app.core.db import get_session_factory
        from app.core.security import decode_access_token
        from app.models import User

        uid = int(decode_access_token(auth[7:]).get("uid", 0))
        if not uid:
            return None
        async with get_session_factory()() as s:
            user = await s.get(User, uid)
            return user.role if user else None
    except Exception:  # noqa: BLE001
        return None


_relay_started = False


def _start_relay() -> None:
    """Start the Prometheus alert relay (app/services/ops_alerts.py) once per process, outside tests."""
    global _relay_started
    _relay_started = True
    try:
        from app.core.config import get_settings

        if get_settings().environment == "test":
            return
        from app.services import ops_alerts

        ops_alerts.start()
    except Exception:  # noqa: BLE001
        log.warning("alert relay not started", exc_info=True)


class ObservabilityMiddleware:
    """Times every HTTP request, counts it by route template, and stores unhandled exceptions / 5xx answers."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return
        if not _relay_started:
            _start_relay()
        start = time.perf_counter()
        status = [500]
        request_id = [""]

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status[0] = int(message.get("status", 500))
                for k, v in message.get("headers") or []:
                    if k.lower() == b"x-request-id":
                        request_id[0] = v.decode("latin-1")[:64]
            await send(message)

        HTTP_IN_FLIGHT.inc()
        failure: BaseException | None = None
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            failure = exc
            status[0] = 500
            raise
        finally:
            HTTP_IN_FLIGHT.dec()
            duration = time.perf_counter() - start
            method = str(scope.get("method", "GET"))
            route = route_template(scope)
            code = status[0]
            try:
                HTTP_REQUESTS.labels(method, route, str(code)).inc()
                HTTP_LATENCY.labels(method, route).observe(duration)
                _ring_add(duration, code)
                if route == LOGIN_ROUTE and method == "POST" and code in (401, 429):
                    LOGIN_FAILURES.labels("rate_limited" if code == 429 else "bad_credentials").inc()
                elif 200 <= code < 300 and (event := DOMAIN_ROUTES.get((method, route))):
                    DOMAIN_EVENTS.labels(event).inc()
                _sample_pool()
            except Exception:  # noqa: BLE001
                log.debug("metrics update failed", exc_info=True)
            if failure is not None or code >= 500:
                role = await _role_of(scope)
                rid = request_id[0] or _header(scope, b"x-request-id")[:64]
                # one greppable line per failure: the panel's log tail and Loki find it by request id
                log.error(
                    "request failed request_id=%s method=%s route=%s status=%s error=%s",
                    rid or "-",
                    method,
                    route,
                    code,
                    type(failure).__name__ if failure is not None else f"http_{code}",
                )
                if failure is not None:
                    report = report_from_exception(
                        failure, route=route, method=method, status_code=500, user_role=role, request_id=rid
                    )
                else:
                    report = ErrorReport(
                        source="backend",
                        kind=f"http_{code}",
                        message=f"{method} {route} answered {code}",
                        route=route,
                        method=method,
                        status_code=code,
                        user_role=role,
                        request_id=rid,
                    )
                await store_report(report)


class _LogCapture(logging.Handler):
    """``ERROR`` records with a traceback from the app's loggers (job queue, workers, services) -> error events.
    uvicorn's own "Exception in ASGI application" record is skipped (the middleware stored that one already)."""

    PREFIXES = ("smartsched", "app.")

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._tasks: set[asyncio.Task[None]] = set()

    def emit(self, record: logging.LogRecord) -> None:
        if not record.exc_info or not record.exc_info[1] or record.name == log.name or _capturing.get():
            return
        if not record.name.startswith(self.PREFIXES):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        exc = record.exc_info[1]
        report = report_from_exception(exc, route=f"logger:{record.name}", status_code=None)
        report.message = f"{record.getMessage()[:300]}: {report.message}"
        task = loop.create_task(store_report(report))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


_log_capture: _LogCapture | None = None


# --------------------------------------------------------------------------------------------------------------------
# /metrics
# --------------------------------------------------------------------------------------------------------------------


def _private(host: str | None) -> bool:
    if not host:
        return False
    if host in ("testclient", "test", "localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


async def _db_metrics(registry: CollectorRegistry) -> None:
    """Gauges computed from the database at scrape time (shared truth across workers and replicas)."""
    from sqlalchemy import func, select, text

    from app.core.db import get_session_factory
    from app.models import (
        ApprovalRequest,
        Booking,
        CouncilJob,
        InvigilationPlan,
        NotificationOutbox,
        ScheduleRun,
        WebhookDelivery,
    )
    from app.models.base import utcnow
    from app.models.channels import ChannelDelivery
    from app.models.error_event import ErrorEvent
    from app.models.integrations import CalendarSyncJob

    up = Gauge("smartsched_db_up", "database answered SELECT 1", registry=registry)
    ping = Gauge("smartsched_db_ping_seconds", "SELECT 1 round trip", registry=registry)
    t0 = time.perf_counter()
    try:
        async with get_session_factory()() as s:
            await s.execute(text("SELECT 1"))
            ping.set(time.perf_counter() - t0)
            up.set(1)

            async def by_status(model: Any, name: str, doc: str, label: str = "status") -> None:
                g = Gauge(name, doc, [label], registry=registry)
                for k, v in (await s.execute(select(model.status, func.count()).group_by(model.status))).all():
                    g.labels(str(k)).set(v)

            await by_status(ScheduleRun, "smartsched_solver_runs", "solver runs by status")
            await by_status(CouncilJob, "smartsched_council_jobs", "ingestion council jobs by status")
            await by_status(InvigilationPlan, "smartsched_invigilation_plans", "invigilation plans by status")
            await by_status(NotificationOutbox, "smartsched_mail_outbox", "e-mail outbox rows by status")
            await by_status(ApprovalRequest, "smartsched_approval_requests", "approval requests by status")
            await by_status(ErrorEvent, "smartsched_error_groups", "error groups by status")
            await by_status(Booking, "smartsched_bookings", "bookings by status")

            dq = Gauge(
                "smartsched_delivery_queue",
                "integration deliveries by queue and status",
                ["queue", "status"],
                registry=registry,
            )
            for qname, model in (
                ("channel", ChannelDelivery),
                ("webhook", WebhookDelivery),
                ("calendar", CalendarSyncJob),
            ):
                for k, v in (await s.execute(select(model.status, func.count()).group_by(model.status))).all():
                    dq.labels(qname, str(k)).set(v)

            since = utcnow() - timedelta(hours=24)
            rows = (
                await s.execute(
                    select(ScheduleRun.status, ScheduleRun.started_at, ScheduleRun.finished_at).where(
                        ScheduleRun.finished_at.is_not(None), ScheduleRun.finished_at >= since
                    )
                )
            ).all()
            fin = Gauge(
                "smartsched_solver_runs_finished_24h",
                "solver runs finished in the last 24 h by outcome",
                ["status"],
                registry=registry,
            )
            counts: dict[str, int] = defaultdict(int)
            durations: list[float] = []
            for st, started, finished in rows:
                counts[str(st)] += 1
                if started and finished:
                    durations.append(max(0.0, (finished - started).total_seconds()))
            for k, v in counts.items():
                fin.labels(k).set(v)
            dur = Gauge(
                "smartsched_solver_run_duration_seconds_24h",
                "solver run duration over the last 24 h",
                ["quantile"],
                registry=registry,
            )
            if durations:
                durations.sort()
                for q in (0.5, 0.95):
                    dur.labels(str(q)).set(durations[min(len(durations) - 1, int(q * len(durations)))])
                dur.labels("1").set(durations[-1])
            created = Gauge("smartsched_bookings_created_24h", "bookings created in the last 24 h", registry=registry)
            created.set(
                (
                    await s.execute(select(func.count()).select_from(Booking).where(Booking.created_at >= since))
                ).scalar_one()
            )
    except Exception:  # noqa: BLE001 - a broken database is itself a metric
        up.set(0)
        log.warning("database metrics failed", exc_info=True)


def _process_registry() -> CollectorRegistry:
    if MULTIPROCESS:
        from prometheus_client import multiprocess  # type: ignore[attr-defined,unused-ignore]

        reg = CollectorRegistry()
        multiprocess.MultiProcessCollector(reg)  # type: ignore[no-untyped-call]
        return reg
    return DEFAULT_REGISTRY


async def metrics_text() -> bytes:
    """The whole exposition: process-shared counters + scrape-time database gauges + build info."""
    db_reg = CollectorRegistry()
    info = Gauge("smartsched_build_info", "release of the running backend", ["version", "release"], registry=db_reg)
    from app.core.config import app_version

    info.labels(app_version(), release_sha()).set(1)
    Gauge("smartsched_process_start_time_seconds", "backend start (unix)", registry=db_reg).set(STARTED_AT)
    await _db_metrics(db_reg)
    host = public_tls_host()
    if host:
        left = await asyncio.to_thread(tls_expiry, host)
        if left is not None:
            Gauge(
                "smartsched_tls_cert_expiry_seconds",
                "seconds until the public TLS certificate expires",
                registry=db_reg,
            ).set(left)
    return generate_latest(_process_registry()) + generate_latest(db_reg)


def _metrics_allowed(request: Any) -> bool:
    import hmac

    from app.core.config import get_settings

    token = get_settings().metrics_token
    auth = request.headers.get("authorization", "")
    if token:
        return auth.lower().startswith("bearer ") and hmac.compare_digest(auth[7:].strip(), token)
    return _private(request.client.host if request.client else None)


ERROR_RETENTION_DAYS = 90
_last_purge = [0.0]


async def purge_old_errors(days: int = ERROR_RETENTION_DAYS, force: bool = False) -> int:
    """Delete error groups unseen for ``days`` days (at most once an hour unless ``force``). Returns rows deleted."""
    now = time.time()
    if not force and now - _last_purge[0] < 3600:
        return 0
    _last_purge[0] = now
    from sqlalchemy import delete

    from app.core.db import get_session_factory
    from app.models.base import utcnow
    from app.models.error_event import ErrorEvent

    try:
        async with get_session_factory()() as s:
            res: Any = await s.execute(delete(ErrorEvent).where(ErrorEvent.last_seen < utcnow() - timedelta(days=days)))
            await s.commit()
            return int(res.rowcount or 0)
    except Exception:  # noqa: BLE001
        log.warning("error retention purge failed", exc_info=True)
        return 0


# --------------------------------------------------------------------------------------------------------------------
# readiness: database, migrations at head, job queue alive; TLS certificate expiry
# --------------------------------------------------------------------------------------------------------------------

_alembic_head: list[str | None] = []


def alembic_head() -> str | None:
    """The newest revision of the shipped migration scripts (cached; ``None`` when the scripts are not present)."""
    if not _alembic_head:
        try:
            from alembic.config import Config
            from alembic.script import ScriptDirectory

            cfg = Config()
            cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
            heads = ScriptDirectory.from_config(cfg).get_heads()
            _alembic_head.append(heads[0] if len(heads) == 1 else ",".join(sorted(heads)) or None)
        except Exception:  # noqa: BLE001
            _alembic_head.append(None)
    return _alembic_head[0]


async def readiness() -> dict[str, Any]:
    """``/readyz``: ``ready`` only when the database answers, its schema is at the migration head (or the database
    was created without Alembic, dev/test) and no queued/running job of this deployment lost its heartbeat."""
    from sqlalchemy import or_, select, text

    from app.core.db import get_session_factory
    from app.models import ScheduleRun
    from app.models.base import utcnow

    out: dict[str, Any] = {"db": False, "migrations": "unknown", "workers": "unknown"}
    try:
        async with get_session_factory()() as s:
            await s.execute(text("SELECT 1"))
            out["db"] = True
            head = alembic_head()
            try:
                current = (await s.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            except Exception:  # noqa: BLE001 - created by create_all (dev / tests)
                await s.rollback()
                current = None
            if current is None:
                out["migrations"] = "unmanaged"
            else:
                out["migrations"] = "head" if head and head in current else "behind"
                out["migration_current"] = ",".join(current)
            out["migration_head"] = head
            stale = utcnow() - timedelta(minutes=5)
            stuck = (
                (
                    await s.execute(
                        select(ScheduleRun.id)
                        .where(ScheduleRun.status == "RUNNING")
                        .where(or_(ScheduleRun.heartbeat_at.is_(None), ScheduleRun.heartbeat_at < stale))
                        .where(ScheduleRun.started_at < stale)
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            out["workers"] = "stalled" if stuck else "ok"
            out["stalled_runs"] = list(stuck)
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__
    out["ready"] = bool(out["db"]) and out["migrations"] in ("head", "unmanaged") and out["workers"] == "ok"
    return out


_tls_cache: dict[str, tuple[float, float | None]] = {}


def tls_expiry(host: str, port: int = 443, timeout: float = 4.0) -> float | None:
    """Seconds until the certificate of ``host`` expires (cached one hour; ``None`` when it cannot be read)."""
    import socket
    import ssl

    hit = _tls_cache.get(host)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    value: float | None = None
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert() or {}
        not_after = cert.get("notAfter")
        if isinstance(not_after, str):
            value = ssl.cert_time_to_seconds(not_after) - time.time()
    except Exception:  # noqa: BLE001
        value = None
    _tls_cache[host] = (time.time(), value)
    return value


def public_tls_host() -> str | None:
    from urllib.parse import urlparse

    url = (os.environ.get("PUBLIC_URL") or "").strip()
    if not url.startswith("https://"):
        return None
    return urlparse(url).hostname


def install(app: Any) -> None:
    """Wire metrics, the error middleware, the log capture, ``/metrics``, ``/healthz``, ``/readyz`` and optional
    Sentry into the app (one call from ``app.main.create_app``)."""
    global _log_capture
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse, Response

    from app.core.config import get_settings

    async def metrics_endpoint(request: Request) -> Response:
        if not _metrics_allowed(request):
            return PlainTextResponse("forbidden\n", status_code=403)
        await purge_old_errors()
        return Response(await metrics_text(), media_type=CONTENT_TYPE_LATEST)

    async def healthz(_request: Request) -> Response:
        return PlainTextResponse("ok\n")

    async def readyz(_request: Request) -> Response:
        state = await readiness()
        return JSONResponse(state, status_code=200 if state["ready"] else 503)

    app.add_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
    app.add_route("/healthz", healthz, methods=["GET"], include_in_schema=False)
    app.add_route("/readyz", readyz, methods=["GET"], include_in_schema=False)
    app.add_middleware(ObservabilityMiddleware)
    if get_settings().environment != "test" and _log_capture is None:
        _log_capture = _LogCapture()
        logging.getLogger().addHandler(_log_capture)
    init_sentry()


def uptime_s() -> float:
    return time.time() - STARTED_AT


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
