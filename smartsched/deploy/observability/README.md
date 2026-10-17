# Observability profile (wave 3, W3-OPS)

Metrics, logs, dashboards and alerts for one SmartSched pod, plus the admin panel `/admin/ops` and grouped error
tracking in the backend. Everything here is optional: the core stack runs without it, and the panel then shows
Grafana / Prometheus / Loki as "Ulaşılamıyor" and falls back to the API process's own numbers.

```
./deploy.sh --observability          # this run (and: OBSERVABILITY=1 in .env makes it the default)
./deploy.sh --no-observability       # skip it for one run
docker compose --profile observability up -d      # without deploy.sh
```

On the first run `deploy.sh` writes `OBSERVABILITY=1` into `.env` when the host has at least 7 GiB of memory (the
8 GB t4g.large pod: on), else `0`. It also generates `GRAFANA_ADMIN_PASSWORD` when an older `.env` lacks it, and
exports `RELEASE_SHA` (git HEAD) and `DEPLOYED_AT` for the panel's "last deploy" card.

## What runs

| Service | Image (pinned by digest, arm64 + amd64) | Role | Memory cap | Measured RSS* |
|---|---|---|---|---|
| prometheus | prom/prometheus v3.15.0 | scrapes the backend (`/metrics`, every replica via DNS), Loki, Grafana, Alloy; receives Alloy's remote write; alert rules (`prometheus/alerts.yml`); 15 d / 1 GB retention | 160 MiB | 49–67 MiB |
| loki | grafana/loki 3.7.8 + static busybox (for the healthcheck; `loki/Dockerfile`) | logs, filesystem storage, 7 d retention (`loki/loki.yaml`) | 128 MiB | 35–71 MiB |
| alloy | grafana/alloy v1.20.1 | container logs → Loki (redacted), host metrics (embedded node exporter), PostgreSQL metrics (embedded postgres exporter), HTTP probes of frontend / proxy / backend `/readyz` (embedded blackbox) → Prometheus | 96 MiB | 44–58 MiB |
| grafana | grafana/grafana 13.2.4 | provisioned datasources + 6 dashboards, Turkish UI, served at `/grafana/` | 384 MiB | 230–296 MiB |

\* `docker stats` on 2026-10-17 (x86_64 dev host, cgroup v1), idle and after opening the dashboards. Together
≈ 0.37 GB idle, ≈ 0.49 GB after use; the caps total **768 MiB**. Grafana 13 was OOM-killed at a 192 MiB cap
(≈ 240 MiB at start), hence 384 MiB. Promtail (end of life 2026-03-02), node-exporter, postgres-exporter and
cAdvisor are replaced by Alloy's embedded components; there are no per-container memory metrics (no cAdvisor,
no Docker socket): the "Bellek" panel shows each service's own process memory and the host's used memory.

**Memory budget on the 8 GB pod.** The core caps are db 2g + backend 4g + frontend 1g + proxy 256m + caddy 256m
= 7.5 GB of *limits* (caps, not reservations; the stack normally uses far less). When `deploy.sh` turns the profile
on for a `.env` (first run on a host with >= 7 GiB) it also lowers the stock `BACKEND_MEMORY=4g` to `3500m`, so the
limits total **7.75 GB** with the profile: db 2048 + backend 3500 + frontend 1024 + proxy 256 + caddy 256 +
observability 768 MiB = 7852 MiB. Any other `BACKEND_MEMORY` value is kept; set it back to `4g` to override
(limits 8.25 GB).

## Access and security

* Nothing in the profile publishes a port. Prometheus, Loki and Alloy are reachable only on the compose network.
* Grafana is reached through the nginx proxy at `/grafana/` (`nginx/grafana.locations`, pasted into the proxy's
  server block in `nginx/default.conf` before `location / {`): nginx `auth_request` asks `GET /api/v1/ops/grafana-auth` through the Next.js handler (session
  cookie → bearer token). 204 (role holds `setup.settings` or `planning.admin`) → proxied with
  `X-WEBAUTH-USER: smartsched-admin` (Grafana `auth.proxy`, Editor role); 401 → `/login?next=/grafana/...`;
  403 → 403. The client's own `X-WEBAUTH-USER` is always overwritten. Grafana's login form, basic auth, sign-up and
  anonymous access are off (`validate.sh` checks the four settings). Embedding: `allow_embedding` + W3-SEC's
  `frame-ancestors 'self'` / `X-Frame-Options SAMEORIGIN` for `/grafana/` only; the panel embeds same-origin
  panels only.
* The backend's `/metrics`, `/healthz`, `/readyz` live at the app root, which nginx never routes to the backend
  (only `/api/v1/calendar|ics` and `/uploads/rooms` go there directly). `/metrics` answers private / loopback
  addresses only, or a `METRICS_TOKEN` bearer when one is set (then add `authorization: {credentials: ...}` to the
  backend job in `prometheus/prometheus.yml`).
* Alloy runs as root inside its container (the json-file logs are root-only) with every capability dropped except
  `DAC_OVERRIDE`, a read-only root filesystem and read-only host mounts. It never touches the Docker socket: the
  compose service/project names come from the json-file `attrs` (`labels` log option in `docker-compose.yml`).
* Redaction before shipping (Alloy `stage.replace`): Authorization / Cookie values, bearer / basic credentials,
  JWTs, `password=` / `token=` / `api_key=` values, e-mail addresses, Turkish mobile numbers, 11-digit ids and
  query strings. The panel's log tail scrubs again (`app.core.observability.scrub`). Client IPs stay in the proxy
  access lines (abuse handling); note them in the KVKK inventory with the 7-day log retention.

## Retention (KVKK inventory)

| Data | Where | Kept |
|---|---|---|
| metrics (no user ids or e-mails as labels: routes by template, AI usage by provider/model/feature) | Prometheus volume `prometheus-data` | 15 days or 1 GB |
| container logs (redacted) | Loki volume `loki-data` | 7 days |
| error groups (scrubbed message/stack, role code, release, last request id; no user id) | `error_events` table | 90 days after last seen |

## Dashboards (as code)

`grafana/build_dashboards.py` writes `grafana/dashboards/*.json` (Turkish title first); `validate.sh` fails when the
JSON is stale. Service health · API · Çözücü ve işler · Rezervasyonlar ve onaylar · Yapay zekâ kullanımı ·
Hatalar ve günlükler (Loki). The uids and the panels `/admin/ops` embeds are listed in
`smartsched/backend/app/api/v1/ops.py` `DASHBOARDS` (a backend test keeps both in step).

## Alerts

`prometheus/alerts.yml`: backend down, a failing HTTP probe, 5xx > 2 %, p95 > 2 s, disk > 80 %, host memory
< 10 %, DB connections > 80 %, database down, ≥ 3 solver failures in an hour, mail backlog, a new error group,
AI budget 80 % / 100 % (`smartsched_ai_budget_used_ratio`, set by W3-AI through
`observability.set_ai_budget_ratio`), last backup > 26 h, TLS certificate < 14 days.

Delivery without an Alertmanager: the backend's **alert relay** (`app/services/ops_alerts.py`) polls Prometheus
`/api/v1/alerts` every 60 s and sends each new firing alert, a reminder every 6 h while it keeps firing, and one
"resolved" notice to every admin (`setup.settings` / `planning.admin`) as notification event `ops.alert`: the bell,
the themed e-mail and any channel the admin connected, switchable in the notification preferences. Delivery is
idempotent per admin and channel (the dispatcher's ledger), so several workers or replicas never double-send; the
firing set is kept in the settings row `ops.alert_relay`, so a restart still resolves what was firing. Firing
alerts are also listed on `/admin/ops` and in Grafana.

## Backups

`deploy/backup.sh` (nightly cron line in `deploy/README.md` "Backups") dumps the database, archives the uploads
volume, keeps 14 days and, after a successful run, writes
`smartsched_backup_last_success_timestamp_seconds` into `/var/lib/smartsched/textfile/backup.prom` (atomic rename).
Alloy reads that directory; `SmartSchedBackupStale` fires when the last success is older than 26 h.

## Horizontal scaling

* Inside one backend container the uvicorn workers share counters through `PROMETHEUS_MULTIPROC_DIR`
  (`/tmp/smartsched-metrics-<master pid>`, set by `app/core/observability.py`), so a scrape of any worker returns
  the container's totals.
* `docker compose up --scale backend=N`: Prometheus discovers every replica (`dns_sd_configs` on `backend`). The
  database gauges (queues, outbox, bookings, error groups) are the same on every replica: aggregate them with
  `max`, not `sum`. Request counters and latency histograms sum across replicas.
* Error groups are rows in the shared database (unique fingerprint; a concurrent first insert falls back to an
  update), so replicas never split a group. The browser-report rate limit is per process.
* Loki, Prometheus and Grafana stay single instances on one pod; for several hosts, point Alloy's `loki.write` /
  `prometheus.remote_write` at a central instance instead of running the profile on each host.

## Sentry (optional)

Set `SENTRY_DSN` (and `BACKEND_EXTRA_PIP=sentry-sdk`): every stored error event is also sent to Sentry with the
same fingerprint, no PII and no tracing. Self-hosted Sentry is not an option on this pod (16 GB RAM).
