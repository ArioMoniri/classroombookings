#!/usr/bin/env python3
"""Dashboards as code (W3-OPS): writes dashboards/*.json for Grafana's file provisioning.

    python3 smartsched/deploy/observability/grafana/build_dashboards.py          # rewrite the JSON files
    python3 smartsched/deploy/observability/grafana/build_dashboards.py --check  # exit 1 when they are stale

Titles are Turkish first ("Servis sağlığı / Service health"). The uids and the panel ids that /admin/ops embeds
are listed in smartsched/backend/app/api/v1/ops.py ``DASHBOARDS`` (tests/test_w3_ops_observability.py keeps both in
step). Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OUT = HERE / "dashboards"
PROM = {"type": "prometheus", "uid": "smartsched-prometheus"}
LOKI = {"type": "loki", "uid": "smartsched-loki"}


def ts(pid: int, title: str, exprs: list[tuple[str, str]], x: int, y: int, w: int = 12, h: int = 8,
       unit: str = "short", stack: bool = False) -> dict[str, Any]:
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "datasource": PROM,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {
            "defaults": {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 10,
                                                   "stacking": {"mode": "normal" if stack else "none"}}},
            "overrides": [],
        },
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
        "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": lg, "datasource": PROM}
                    for i, (e, lg) in enumerate(exprs)],
    }


def stat(pid: int, title: str, expr: str, x: int, y: int, w: int = 6, h: int = 4, unit: str = "short",
         legend: str = "", thresholds: list[tuple[float | None, str]] | None = None,
         mappings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    steps = [{"value": v, "color": c} for v, c in (thresholds or [(None, "green")])]
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "datasource": PROM,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps},
                                     "mappings": mappings or []}, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "reduceOptions": {"calcs": ["lastNotNull"]},
                    "textMode": "value_and_name"},
        "targets": [{"refId": "A", "expr": expr, "legendFormat": legend, "datasource": PROM}],
    }


def logs(pid: int, title: str, expr: str, x: int, y: int, w: int = 24, h: int = 12) -> dict[str, Any]:
    return {
        "id": pid,
        "type": "logs",
        "title": title,
        "datasource": LOKI,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True},
        "targets": [{"refId": "A", "expr": expr, "datasource": LOKI}],
    }


UP = [{"type": "value", "options": {"0": {"text": "KAPALI / DOWN", "color": "red"},
                                    "1": {"text": "AÇIK / UP", "color": "green"}}}]
RED_GREEN = [(None, "red"), (1, "green")]


def dashboard(uid: str, title: str, panels: list[dict[str, Any]], tags: list[str],
              variables: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "uid": uid,
        "title": title,
        "tags": ["smartsched", *tags],
        "timezone": "browser",
        "refresh": "30s",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "graphTooltip": 1,
        "time": {"from": "now-6h", "to": "now"},
        "templating": {"list": variables or []},
        "annotations": {"list": []},
        "links": [{"title": "Operasyon / Operations", "type": "link", "url": "/admin/ops", "targetBlank": False}],
        "panels": panels,
    }


RATE = "sum(rate(smartsched_http_requests_total[5m]))"
ERR5 = 'sum(rate(smartsched_http_requests_total{status=~"5.."}[5m]))'

DASHBOARDS: list[dict[str, Any]] = [
    dashboard("smartsched-health", "Servis sağlığı / Service health", [
        stat(1, "Servisler ayakta / Services up", 'up', 0, 0, w=12, h=5, legend="{{job}}", thresholds=RED_GREEN,
             mappings=UP),
        stat(2, "HTTP denetimleri / HTTP probes", "probe_success", 12, 0, w=6, h=5, legend="{{job}}",
             thresholds=RED_GREEN, mappings=UP),
        stat(3, "Veritabanı / Database", "smartsched_db_up", 18, 0, w=6, h=5, thresholds=RED_GREEN, mappings=UP),
        ts(4, "Bellek (servisler) / Memory (services)", [
            ('process_resident_memory_bytes{job!="backend"}', "{{job}}"),
            ("max(smartsched_process_resident_memory_bytes)", "backend"),
            ("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "sunucu kullanılan / host used"),
        ], 0, 5, unit="bytes"),
        ts(5, "CPU (sunucu) / CPU (host)", [
            ('1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', "kullanım / used"),
            ("node_load1", "load 1m"),
        ], 12, 5, unit="percentunit"),
        ts(6, "Disk doluluğu / Disk used", [
            ('1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}',
             "{{mountpoint}}"),
        ], 0, 13, unit="percentunit"),
        ts(7, "Veritabanı bağlantıları / DB connections", [
            ("sum(pg_stat_database_numbackends)", "bağlantı / connections"),
            ("max(pg_settings_max_connections)", "üst sınır / max"),
            ('sum(smartsched_db_pool_connections{state="checked_out"})', "havuz kullanımda / pool checked out"),
        ], 12, 13),
        stat(8, "Sertifika (gün) / Certificate (days)", "smartsched_tls_cert_expiry_seconds / 86400", 0, 21,
             unit="none", thresholds=[(None, "red"), (14, "orange"), (30, "green")]),
        stat(9, "Son yedek (saat önce) / Last backup (hours ago)",
             "(time() - smartsched_backup_last_success_timestamp_seconds) / 3600", 6, 21, unit="none",
             thresholds=[(None, "green"), (26, "red")]),
        stat(10, "Sürüm / Release", "smartsched_build_info", 12, 21, w=12, legend="{{version}} {{release}}"),
    ], ["health"]),
    dashboard("smartsched-api", "API / API", [
        ts(1, "İstek/sn / Requests/s", [(f"sum by (status) (rate(smartsched_http_requests_total[5m]))", "{{status}}")],
           0, 0, unit="reqps", stack=True),
        ts(2, "p95 gecikme / p95 latency", [
            ("histogram_quantile(0.95, sum by (le) (rate(smartsched_http_request_duration_seconds_bucket[5m])))", "p95"),
            ("histogram_quantile(0.5, sum by (le) (rate(smartsched_http_request_duration_seconds_bucket[5m])))", "p50"),
        ], 12, 0, unit="s"),
        ts(3, "En yavaş rotalar (p95) / Slowest routes (p95)", [
            ("topk(8, histogram_quantile(0.95, sum by (le, route) "
             "(rate(smartsched_http_request_duration_seconds_bucket[15m]))))", "{{route}}"),
        ], 0, 8, unit="s"),
        ts(4, "En çok çağrılan rotalar / Busiest routes", [
            ("topk(8, sum by (route) (rate(smartsched_http_requests_total[15m])))", "{{route}}"),
        ], 12, 8, unit="reqps"),
        ts(5, "Başarısız girişler / Failed sign-ins", [
            ("sum by (reason) (increase(smartsched_login_failures_total[5m]))", "{{reason}}"),
        ], 0, 16),
        ts(6, "Eşzamanlı istekler / In flight", [("sum(smartsched_http_requests_in_flight)", "in flight")], 12, 16),
    ], ["api"]),
    dashboard("smartsched-jobs", "Çözücü ve işler / Solver & jobs", [
        ts(1, "Kuyruk / Queue", [
            ('sum(smartsched_solver_runs{status=~"QUEUED|RUNNING"}) by (status)', "çözücü / solver {{status}}"),
            ('sum(smartsched_council_jobs{status=~"QUEUED|RUNNING"}) by (status)', "konsey / council {{status}}"),
            ('sum(smartsched_invigilation_plans{status=~"QUEUED|RUNNING"}) by (status)', "gözetmen / invigilation {{status}}"),
        ], 0, 0),
        ts(2, "Son 24 saatte biten çalışmalar / Runs finished (24 h)", [
            ("smartsched_solver_runs_finished_24h", "{{status}}")], 12, 0),
        ts(3, "Çözüm süresi (24 sa) / Solve time (24 h)", [
            ("smartsched_solver_run_duration_seconds_24h", "q{{quantile}}")], 0, 8, unit="s"),
        ts(4, "E-posta kuyruğu / Mail outbox", [("smartsched_mail_outbox", "{{status}}")], 12, 8),
        ts(5, "Teslim kuyrukları / Delivery queues", [
            ('smartsched_delivery_queue{status=~"PENDING|RUNNING|FAILED"}', "{{queue}} {{status}}")], 0, 16),
        ts(6, "İstenen işler / Jobs requested", [
            ('sum by (event) (increase(smartsched_domain_events_total{event=~"solver_run_requested|council_job_requested"}[1h]))',
             "{{event}}")], 12, 16),
    ], ["jobs"]),
    dashboard("smartsched-bookings", "Rezervasyonlar ve onaylar / Bookings & approvals", [
        ts(1, "Rezervasyonlar / Bookings", [
            ('sum by (event) (increase(smartsched_domain_events_total{event=~"booking_.*"}[1h]))', "{{event}} / sa"),
        ], 0, 0),
        stat(2, "Son 24 saatte oluşturulan / Created in 24 h", "smartsched_bookings_created_24h", 12, 0),
        stat(3, "Bekleyen onaylar / Pending approvals", 'sum(smartsched_approval_requests{status="PENDING"})', 18, 0,
             thresholds=[(None, "green"), (20, "orange"), (100, "red")]),
        ts(4, "Onay talepleri / Approval requests", [("smartsched_approval_requests", "{{status}}")], 12, 4, h=4),
        ts(5, "Onay kararları / Approval decisions", [
            ('sum(increase(smartsched_domain_events_total{event="approval_decided"}[1h]))', "karar / decisions per h"),
        ], 0, 8),
        ts(6, "Rezervasyon durumları / Booking states", [("smartsched_bookings", "{{status}}")], 12, 8),
    ], ["bookings"]),
    dashboard("smartsched-ai", "Yapay zekâ kullanımı / AI usage", [
        ts(1, "Çağrılar / Calls", [
            ("sum by (provider, outcome) (increase(smartsched_ai_calls_total[1h]))", "{{provider}} {{outcome}}"),
        ], 0, 0),
        ts(2, "Belirteçler / Tokens", [
            ("sum by (provider, direction) (increase(smartsched_ai_tokens_total[1h]))", "{{provider}} {{direction}}"),
        ], 12, 0),
        ts(3, "Gecikme p95 / Latency p95", [
            ("histogram_quantile(0.95, sum by (le, provider) (rate(smartsched_ai_call_duration_seconds_bucket[15m])))",
             "{{provider}}")], 0, 8, unit="s"),
        ts(4, "Bütçe kullanımı / Budget used", [("smartsched_ai_budget_used_ratio", "{{scope}}")], 12, 8,
           unit="percentunit"),
        ts(5, "Koruma reddi / Guard refusals", [
            ("sum by (guard) (increase(smartsched_guard_refusals_total[1h]))", "{{guard}}"),
            ('sum by (feature) (increase(smartsched_ai_calls_total{outcome=~"blocked|limited"}[1h]))',
             "AI {{feature}}"),
        ], 0, 16),
        ts(6, "Tahmini maliyet (USD) / Estimated cost (USD)", [
            ("sum by (provider) (increase(smartsched_ai_cost_usd_total[24h]))", "{{provider}}")], 12, 16, unit="currencyUSD"),
    ], ["ai"]),
    dashboard("smartsched-errors", "Hatalar ve günlükler / Errors & logs", [
        ts(1, "5xx oranı / 5xx rate", [(f"{ERR5} / clamp_min({RATE}, 0.001)", "5xx / all")], 0, 0,
           unit="percentunit"),
        ts(2, "Hata olayları / Error events", [
            ("sum by (source, kind) (increase(smartsched_errors_total[15m]))", "{{source}} {{kind}}")], 12, 0),
        stat(3, "Açık hata grupları / Open error groups", 'sum(smartsched_error_groups{status="open"})', 0, 8,
             thresholds=[(None, "green"), (1, "orange"), (10, "red")]),
        stat(4, "Uyarılar / Alerts firing", 'count(ALERTS{alertstate="firing"}) or vector(0)', 6, 8,
             thresholds=[(None, "green"), (1, "red")]),
        logs(5, "Hata satırları / Error lines", '{service=~"$service"} |~ "(?i)(error|exception|traceback|failed)"',
             0, 12),
        logs(6, "Tüm günlükler / All logs", '{service=~"$service"}', 0, 24),
    ], ["errors", "logs"], variables=[{
        "name": "service", "label": "Servis / Service", "type": "custom", "multi": True, "includeAll": True,
        "query": "backend,frontend,proxy,db,caddy,grafana,prometheus,loki,alloy",
        "current": {"text": "All", "value": "$__all"}, "allValue": ".+",
        "options": [],
    }]),
]


def render() -> dict[str, str]:
    return {f"{d['uid']}.json": json.dumps(d, ensure_ascii=False, indent=2) + "\n" for d in DASHBOARDS}


def main(argv: list[str]) -> int:
    files = render()
    if "--check" in argv:
        stale = [n for n, text in files.items() if not (OUT / n).exists() or (OUT / n).read_text("utf-8") != text]
        extra = sorted(p.name for p in OUT.glob("*.json") if p.name not in files)
        for n in stale + extra:
            print(f"stale dashboard: {n} (run {Path(__file__).name})")
        return 1 if stale or extra else 0
    OUT.mkdir(exist_ok=True)
    for n, text in files.items():
        (OUT / n).write_text(text, encoding="utf-8")
    print(f"wrote {len(files)} dashboards to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
