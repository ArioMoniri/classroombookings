"""CI results page served at /ci/ behind the app's nginx (proxy_pass to 172.17.0.1:8095).

Auth (either):
  1. the app's session cookie (smartsched_token): forwarded to the app's own /api/v1/auth/me through nginx
     on the host loopback; the user must be an admin (role ADMIN or permission planning.admin);
  2. HTTP basic auth with the credentials in SSM /smartsched/ci/basic_auth ("user:password", generated on
     the pod; cached in /var/lib/smartsched-ci/basic_auth, mode 600).

Pages: /ci/ (last runs), /ci/runs/<id> (steps, durations, statuses), /ci/runs/<id>/<step>.log (raw log).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from podci.config import Config
from podci.state import Store

COOKIE = "smartsched_token"
LOG_TAIL_BYTES = 512 * 1024
STATE_ICON = {"success": "&#10003;", "failure": "&#10007;", "error": "!", "running": "&#9654;", "queued": "&#8230;",
              "pending": "&#8230;", "skipped": "&#8211;", "superseded": "&#8631;", "cancelled": "&#8211;"}

MeFetcher = Callable[[str], dict[str, Any] | None]


def fetch_me(me_url: str) -> MeFetcher:
    def fetch(token: str) -> dict[str, Any] | None:
        req = urllib.request.Request(me_url, headers={  # noqa: S310 - fixed loopback URL from config
            "Cookie": f"{COOKIE}={token}", "Accept": "application/json", "X-Forwarded-Proto": "https"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                return dict(json.loads(resp.read().decode()))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None
    return fetch


def is_admin(me: dict[str, Any] | None) -> bool:
    if not me or not me.get("is_active", True):
        return False
    return str(me.get("role", "")).upper() == "ADMIN" or "planning.admin" in (me.get("permissions") or [])


class Auth:
    def __init__(self, basic: str | None, me: MeFetcher, ttl: float = 60, clock: Callable[[], float] = time.time):
        self.basic = basic or ""
        self.me = me
        self.ttl = ttl
        self.clock = clock
        self._cache: dict[str, tuple[float, bool]] = {}

    def check(self, headers: Any) -> bool:
        auth = headers.get("Authorization", "")
        if auth.startswith("Basic ") and self.basic:
            try:
                given = base64.b64decode(auth[6:], validate=True).decode()
            except (ValueError, UnicodeDecodeError):
                return False
            return hmac.compare_digest(given.encode(), self.basic.encode())
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001 - malformed cookie header = not logged in
            return False
        if COOKIE not in cookie:
            return False
        token = cookie[COOKIE].value
        key = hashlib.sha256(token.encode()).hexdigest()
        hit = self._cache.get(key)
        now = self.clock()
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        ok = is_admin(self.me(token))
        self._cache[key] = (now, ok)
        if len(self._cache) > 1000:
            self._cache.clear()
        return ok


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    s = int(seconds)
    return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"


def fmt_ts(ts: float | None) -> str:
    return "" if ts is None else time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>{title}</title>{refresh}<style>
body{{font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;color:#1d1d1f;background:#fafafa}}
table{{border-collapse:collapse;width:100%;background:#fff}}th,td{{padding:6px 10px;border-bottom:1px solid #eee;
text-align:left}}th{{font-weight:600;color:#555}}code,pre{{font:12px ui-monospace,Menlo,monospace}}
pre{{background:#111;color:#ddd;padding:12px;overflow:auto;white-space:pre-wrap}}a{{color:#0a58ca}}
.success{{color:#137333}}.failure,.error{{color:#c5221f}}.running,.queued,.pending{{color:#b06000}}
.skipped,.superseded,.cancelled{{color:#777}}</style></head><body><h1>{title}</h1>{body}</body></html>"""


def render_index(cfg: Config, store: Store) -> str:
    rows = []
    for r in store.recent(cfg.keep_runs):
        commit = f"https://github.com/{cfg.repo}/commit/{r.sha}"
        rows.append(
            f"<tr><td><a href='/ci/runs/{r.id}'>#{r.id}</a></td><td class='{r.state}'>{STATE_ICON.get(r.state, '')} "
            f"{r.state}</td><td>{html.escape(r.branch)}</td><td><a href='{commit}'><code>{r.short}</code></a></td>"
            f"<td>{'deploy' if r.deploy else ''}</td><td>{fmt_ts(r.started_at or r.created_at)}</td>"
            f"<td>{fmt_duration(r.duration)}</td><td>{html.escape(r.summary)}</td></tr>")
    body = ("<p>Pod CI for <code>" + html.escape(cfg.repo) + "</code>: branches " +
            ", ".join(f"<code>{html.escape(b)}</code>" for b in cfg.branches) +
            f"; deploys <code>{html.escape(cfg.deploy_branch)}</code>. One job at a time; polled every 2 min.</p>"
            "<table><tr><th>run</th><th>state</th><th>branch</th><th>commit</th><th></th><th>started</th>"
            "<th>duration</th><th>summary</th></tr>" + "".join(rows) + "</table>")
    refresh = "<meta http-equiv='refresh' content='20'>" if store.active() else ""
    return PAGE.format(title="SmartSched pod CI", refresh=refresh, body=body)


def render_run(cfg: Config, store: Store, run_id: int) -> str | None:
    r = store.get(run_id)
    if r is None:
        return None
    rows = []
    for s in store.steps(run_id):
        log = f"<a href='/ci/runs/{run_id}/{s.name}.log'>log</a>" if s.log_path else ""
        rows.append(f"<tr><td>{html.escape(s.name)}</td><td class='{s.state}'>{STATE_ICON.get(s.state, '')} "
                    f"{s.state}</td><td>{'' if s.blocking else 'non-blocking'}</td>"
                    f"<td>{'' if s.exit_code is None else s.exit_code}</td><td>{fmt_duration(s.duration)}</td>"
                    f"<td>{log}</td></tr>")
    commit = f"https://github.com/{cfg.repo}/commit/{r.sha}"
    body = (f"<p><a href='/ci/'>&larr; all runs</a></p><p class='{r.state}'><b>{r.state}</b> &middot; "
            f"{html.escape(r.branch)} @ <a href='{commit}'><code>{r.sha}</code></a> &middot; attempt {r.attempts}"
            f" &middot; {fmt_duration(r.duration)} &middot; {html.escape(r.summary)}</p>"
            "<table><tr><th>step</th><th>state</th><th></th><th>exit</th><th>duration</th><th></th></tr>"
            + "".join(rows) + "</table>")
    refresh = "<meta http-equiv='refresh' content='10'>" if r.state in ("queued", "running") else ""
    return PAGE.format(title=f"Run #{r.id}", refresh=refresh, body=body)


def read_log(cfg: Config, store: Store, run_id: int, step: str) -> bytes | None:
    s = store.step(run_id, step)
    if s is None or not s.log_path:
        return None
    path = Path(s.log_path).resolve()
    if cfg.logs_dir.resolve() not in path.parents or not path.exists():
        return None
    size = path.stat().st_size
    with open(path, "rb") as fh:
        if size > LOG_TAIL_BYTES:
            fh.seek(size - LOG_TAIL_BYTES)
            return f"[pod-ci] showing the last {LOG_TAIL_BYTES // 1024} KB of {size // 1024} KB\n".encode() + fh.read()
        return fh.read()


RUN_RE = re.compile(r"^/ci/runs/(\d+)/?$")
LOG_RE = re.compile(r"^/ci/runs/(\d+)/([a-z0-9-]+)\.log$")


def make_handler(cfg: Config, store_factory: Callable[[], Store], auth: Auth) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "smartsched-pod-ci"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:  # quieter: path + status only
            pass

        def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8",
                  extra: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/ci/healthz":
                self._send(200, b"ok\n", "text/plain")
                return
            if not auth.check(self.headers):
                body = ("<p>Admins only. <a href='/login?next=/ci/'>Log in to SmartSched</a> as an admin, or use "
                        "the basic-auth credentials from SSM <code>/smartsched/ci/basic_auth</code>.</p>")
                self._send(401, PAGE.format(title="SmartSched pod CI", refresh="", body=body).encode(),
                           extra={"WWW-Authenticate": 'Basic realm="smartsched-ci", charset="UTF-8"'})
                return
            store = store_factory()
            if path in ("/ci", "/ci/"):
                self._send(200, render_index(cfg, store).encode())
                return
            if m := RUN_RE.match(path):
                page = render_run(cfg, store, int(m.group(1)))
                if page is not None:
                    self._send(200, page.encode())
                    return
            if m := LOG_RE.match(path):
                data = read_log(cfg, store, int(m.group(1)), m.group(2))
                if data is not None:
                    self._send(200, data, "text/plain; charset=utf-8")
                    return
            self._send(404, b"not found\n", "text/plain")

    return Handler


def serve(cfg: Config, basic: str | None) -> None:  # pragma: no cover - exercised on the pod
    auth = Auth(basic, fetch_me(cfg.me_url))
    httpd = ThreadingHTTPServer((cfg.web_bind, cfg.web_port), make_handler(cfg, lambda: Store(cfg.db_path), auth))
    print(f"pod CI web on http://{cfg.web_bind}:{cfg.web_port}/ci/")
    httpd.serve_forever()
