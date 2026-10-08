# SmartSched deployment

One-click Docker Compose stack for SmartSched (FastAPI + CP-SAT backend, Next.js frontend, PostgreSQL,
nginx), with an optional legacy classroombookings (CRBS) profile and an optional Caddy HTTPS edge.

```bash
cd smartsched/deploy
./deploy.sh                 # creates .env with random secrets, builds, starts, waits for health
# -> SmartSched is up: http://localhost:8080   admin: ADMIN_EMAIL / ADMIN_PASSWORD from .env
```

Requirements: Docker Engine 24+ with the Compose v2 plugin (2.24+ for the `--tls` override; 2.17+
otherwise), 4 CPU / 8 GB RAM recommended (see [Sizing](#sizing)). Nothing else is needed on the host.
`make -C smartsched deploy` does the same thing.

| Command | What it does |
|---|---|
| `./deploy.sh` | create `.env` if missing (every `__GENERATE__` becomes a random secret), `docker compose build`, `up -d`, wait for `/api/v1/health` through nginx, print the URL and where the admin credentials are |
| `./deploy.sh --legacy` | also build and start the legacy CRBS app (`php:8.3-apache` + `mysql:8.4`) on `127.0.0.1:8081` |
| `./deploy.sh --tls` | add the Caddy edge (`docker-compose.caddy.yml`): automatic Let's Encrypt on :80/:443 for `TLS_DOMAIN` |
| `./deploy.sh --update` | `git pull --ff-only`, pull pinned base images, rebuild, restart; migrations run on start (`--no-pull` skips git) |
| `./deploy.sh --logs` / `--status` | follow logs / container status + health |
| `./deploy.sh --down` | stop everything (data volumes kept). `--down --volumes` deletes ALL data after a typed confirmation (`FORCE=1` skips it) |
| `./validate.sh` | static checks that need no Docker daemon (also run in CI) |

Combine flags as needed, e.g. `./deploy.sh --update --legacy --tls`.

## What runs

| Service | Image | Runs as | Listens | Persistent data |
|---|---|---|---|---|
| `db` | `postgres:16.15-alpine3.24` | `postgres` (entrypoint drops root) | 5432, internal only | volume `pgdata` |
| `backend` | built from `smartsched/backend/Dockerfile` (`python:3.12.15-slim-bookworm`) | uid 1000 `app` | 8000, internal only | volume `uploads` (`/data/uploads`) |
| `frontend` | built from `smartsched/frontend/Dockerfile` (`node:22.23.3-alpine3.24`, Next.js standalone) | uid 1000 `node` | 3000, internal only | none |
| `proxy` | `nginxinc/nginx-unprivileged:1.28.2-alpine` | uid 101 | host `PROXY_BIND:PROXY_PORT` -> 8080 | none (config bind-mounted read-only) |
| `crbs-db` (legacy) | `mysql:8.4.11` | `mysql` | internal only | volume `crbs-mysql` |
| `crbs` (legacy) | built from `legacy/Dockerfile` (`php:8.3.35-apache-bookworm`) | `www-data` | host `127.0.0.1:8081` -> 8080 | volumes `crbs-local`, `crbs-uploads` |
| `caddy` (`--tls`) | `caddy:2.11.7-alpine` | root (binds 80/443, the only root container) | host 80/443 | volumes `caddy-data`, `caddy-config` |

Every service has a healthcheck, `restart: unless-stopped`, json-file log rotation (5 x 20 MB),
example CPU/memory limits (variables in `.env`) and `no-new-privileges`.

Backend start sequence (`smartsched/backend/docker-entrypoint.sh`): wait for the DB, then
`alembic upgrade head` (skip with `RUN_MIGRATIONS=0`), then `python -m app.cli seed-admin`, which creates
`ADMIN_EMAIL`/`ADMIN_PASSWORD` only when the users table is empty (skip with `SEED_ADMIN=0`). Then
`uvicorn --workers $UVICORN_WORKERS`. With arguments the entrypoint runs those instead of uvicorn, after
the migrate and seed steps:

```bash
docker compose --env-file .env run --rm backend python -m app.cli import planning-list /data/uploads/x.xlsx --term 2026-BAHAR
```

### Routing (nginx/default.conf)

| Path | Goes to | Notes |
|---|---|---|
| `/` | frontend | Next.js pages; `/_next/static` cached 1 year (hashed names) |
| `/api/v1/*` | frontend route handler, then backend | the handler turns the httpOnly cookie into `Authorization: Bearer`; the browser never talks to FastAPI directly |
| `/api/v1/runs/{id}/events` | same | SSE: `proxy_buffering off`, no upstream gzip, 1 h read timeout |
| `/api/docs`, `/api/openapi.json` | backend | Swagger UI for operators |
| `/uploads/rooms/*` | backend StaticFiles | room photos |
| `/uploads/*` (anything else) | 404 | imported workbooks live in `/uploads/imports/` and FastAPI serves that mount without auth |
| `/healthz` | nginx | container healthcheck |

`client_max_body_size 50m` (workbooks, photos). Uploads are streamed (`proxy_request_buffering off`).

## Configuration

All settings live in `deploy/.env`, created from `.env.example` by `deploy.sh`. Every variable that
`docker-compose*.yml` uses is listed there, and `validate.sh` fails if one is missing. Rules:

- Put comments on their own line. Compose reads `KEY=   # comment` as the value `# comment`.
- `NEXT_PUBLIC_*` values are inlined at build time. After changing them, run `./deploy.sh --update`.
- `ADMIN_PASSWORD` only applies on the first start. Changing it later does nothing; change it in the UI.
- `POSTGRES_PASSWORD` is fixed when the `pgdata` volume is first created. To rotate it, run
  `ALTER USER` inside the DB, then update `.env`.
- `.env` is `chmod 600` and git-ignored. Back it up together with the database: `APP_SECRET` also
  encrypts the API keys stored in settings.

## The job queue (read before scaling)

Solver runs and imports execute inside the backend process, in an in-process asyncio queue
(`app/workers/queue.py`). No separate worker container exists and no worker command needs to be started.
Job status and progress are written to the `schedule_runs` / `import_jobs` rows, so any API process can
report them. Consequences:

- Each uvicorn worker process has its own queue (max 2 concurrent jobs per process). A job runs in the
  process that received `POST /runs`.
- Live SSE progress (`/runs/{id}/events`) only streams from the process running the job. Other
  processes send keep-alives and the final `done` event from the DB. The UI polls `GET /runs/{id}`, so
  it is unaffected.
- The CP-SAT call runs in a worker thread (`asyncio.to_thread`), so the API and `/health` stay
  responsive while a solve runs. CP-SAT still uses the process's CPU cores, so size `solver_workers`
  and `UVICORN_WORKERS` to the host.
- Restarting the backend kills running jobs. On startup, runs and import jobs left `QUEUED`/`RUNNING`
  by a dead process on this host are marked `FAILED` ("interrupted by restart"); re-run them from the UI.
  `docker compose stop` gives uvicorn 30 s to finish requests (`stop_grace_period: 40s`).

## Scaling

The backend keeps no session state: auth is a JWT, data is in Postgres, and uploads are in a volume.

1. **Vertical first.** One backend container with `UVICORN_WORKERS=2..4`, `SOLVER_WORKERS` = the cores
   you give a solve, and `BACKEND_CPUS` >= `UVICORN_WORKERS x SOLVER_WORKERS` if solves may run in
   parallel. This covers one faculty or university planning office.
2. **Several backend replicas** (`docker compose up -d --scale backend=3`). nginx resolves the
   `backend` name once at start, so `docker compose restart proxy` after scaling. Set
   `RUN_MIGRATIONS=0` on all but one replica, or run `docker compose run --rm backend true` once
   before scaling, so that migrations do not race. The `uploads` volume must be shared: on one host
   that is automatic, across hosts use NFS / a CSI RWX volume / object storage. Jobs stay in the
   replica that accepted them; the DB-backed status keeps the UI correct.
3. **Dedicated workers** (planned). Swap `JobQueue.enqueue` for RQ or Celery on Redis (the interface
   is `enqueue(key, fn, on_status)`), add a `worker` service with the same image
   (`python -m app.cli worker`), and give the API replicas `UVICORN_WORKERS=2` and few CPUs. This step
   also gives progress fan-out over Redis pub/sub and job recovery after restarts.
4. **Frontend** is stateless (`--scale frontend=N`, then restart the proxy). **Postgres**: use a
   managed instance or a primary with streaming replicas. Set `DATABASE_URL` in `.env` and delete the
   `db` service.

## Sizing

These are estimates for one university planning office with ~1 500 sections per term (~1 300
weekly events, ~60 rooms, 14 weeks). The solver benchmarks in `backend/app/solver/README.md` give
1 300 events / 60 rooms FEASIBLE within a ~100 s budget using 8 CP-SAT threads.

| Component | CPU | RAM | Disk |
|---|---|---|---|
| backend | 4 vCPU (`SOLVER_WORKERS=4..8`) | 2-4 GB (CP-SAT model ~0.5-1.5 GB per concurrent solve, rough estimate) | uploads: < 1 GB per year |
| frontend | 0.5-1 vCPU | 256-512 MB | - |
| db | 1-2 vCPU | 1-2 GB | < 2 GB per year (assignments x runs). Prune old runs |
| proxy | 0.25 vCPU | 64 MB | - |

Total: a 4-8 vCPU / 8 GB VM is enough. Raise `BACKEND_CPUS`/`SOLVER_WORKERS` before raising RAM.
Exam periods with room sharing are the largest models. Give them `SOLVER_DEFAULT_TIME_LIMIT=120+`.

## Backups

The database and the `uploads` volume are the state. Keep a copy of `.env` too, offline: `APP_SECRET`
decrypts the stored API keys.

```bash
# /etc/cron.d/smartsched-backup: nightly at 02:30, keep 14 days
30 2 * * * root cd /opt/classroombookings/smartsched/deploy && \
  docker compose --env-file .env exec -T db pg_dump -U smartsched -Fc smartsched \
    > /var/backups/smartsched/db-$(date +\%F).dump && \
  docker run --rm -v smartsched_uploads:/u:ro -v /var/backups/smartsched:/b alpine:3.24 \
    tar czf /b/uploads-$(date +\%F).tgz -C /u . && \
  find /var/backups/smartsched -type f -mtime +14 -delete
```

(`smartsched_uploads` is `<COMPOSE_PROJECT_NAME>_uploads`. Copy `/var/backups/smartsched` off the
host. Legacy MySQL: `docker compose exec -T crbs-db sh -c 'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"'`.)

### Restore

```bash
docker compose --env-file .env stop backend frontend
docker compose --env-file .env exec -T db pg_restore -U smartsched -d smartsched --clean --if-exists --no-owner < db-2026-10-08.dump
docker run --rm -v smartsched_uploads:/u -v "$PWD":/b alpine:3.24 sh -c 'rm -rf /u/* && tar xzf /b/uploads-2026-10-08.tgz -C /u'
docker compose --env-file .env up -d     # entrypoint re-applies any newer migrations
```

Restore into the same or a newer SmartSched version. Alembic only migrates forward.

## Upgrade and rollback

```bash
./deploy.sh --update            # git pull --ff-only, rebuild with pinned bases, restart, migrate on start
```

1. Take a backup first (the cron command above, run by hand).
2. Read `docs/PROGRESS.md` and the commit log for new `.env` keys. `validate.sh` lists keys that are
   in `.env.example` but missing from compose. Add new keys to your `.env` by hand; `deploy.sh` never
   overwrites an existing `.env`.
3. Rollback: `git checkout <previous tag>`, then `./deploy.sh --update --no-pull`. If the newer version
   ran a migration, restore the pre-upgrade dump (there are no down-migrations in production).

Pinned base images: bump the tags in the Dockerfiles / compose deliberately (Renovate or Dependabot
can open the PRs). For bit-for-bit pulls, append `@sha256:` digests.

## TLS

The production frontend build marks the session cookie `Secure`. Browsers accept that on
`http://localhost`. From any other host the login therefore only works over HTTPS: a plain-http login
from another machine fails silently and bounces back to `/login`. Pick one:

**A. Caddy in compose (simplest).** Set `TLS_DOMAIN`, `ACME_EMAIL`, `PUBLIC_URL=https://<domain>` and
`CORS_ORIGINS=["https://<domain>"]` in `.env`, point DNS at the host, open ports 80/443, then
`./deploy.sh --tls`. Caddy gets and renews certificates and forwards to nginx (nginx is then bound to
`127.0.0.1` only).

**B. Host Caddy.** `apt install caddy`, set `PROXY_BIND=127.0.0.1`, and use this `/etc/caddy/Caddyfile`:

```
smartsched.example.edu.tr {
	reverse_proxy 127.0.0.1:8080 {
		flush_interval -1
	}
}
```

**C. certbot + host nginx.** `certbot --nginx -d smartsched.example.edu.tr`, then
`location / { proxy_pass http://127.0.0.1:8080; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_buffering off; client_max_body_size 50m; proxy_read_timeout 3600s; }`.

The inner nginx keeps an incoming `X-Forwarded-Proto` and trusts `X-Forwarded-For` from private
ranges, so the backend sees the real scheme and client IP.

## Legacy CRBS profile

`./deploy.sh --legacy` builds the PHP app from the repository root. Only `index.php`, `assets/`,
`crbs-core/`, `local/` and `uploads/` enter the image (`legacy/Dockerfile.dockerignore`). It runs as
`www-data` on `127.0.0.1:8081`, with MySQL settings coming from the environment
(`legacy/config.php` -> `local/config.php`).

- First visit: the CRBS installer runs. Database host `crbs-db`, name/user/password from `.env`
  (`CRBS_DB_*`).
- Existing CRBS data: `docker compose --env-file .env exec -T crbs-db sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < crbs-dump.sql`,
  then `docker compose exec crbs sh -c 'date > local/installed'`.
- Import into SmartSched: rebuild the backend with `BACKEND_EXTRA_PIP=pymysql`, then
  `docker compose --env-file .env --profile legacy exec backend python -m app.cli import crbs --dsn mysql://crbs:<CRBS_DB_PASSWORD>@crbs-db:3306/crbs`.
  The alternative is to upload SQL dumps in the UI.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `deploy.sh`: "Docker daemon is not reachable" | start Docker (`systemctl start docker`) or add your user to the `docker` group and log in again |
| `required variable X is missing a value` | `.env` predates a new key. Copy it from `.env.example` (or delete `.env` on a fresh install) |
| health wait times out | `./deploy.sh --logs`. Backend stuck at "waiting for database": wrong `POSTGRES_PASSWORD` for an existing `pgdata` volume. Alembic error: restore the last backup and report the migration |
| login from another PC bounces back to `/login` | Secure cookie over plain http; use [TLS](#tls) |
| 413 on upload | file > 50 MB. Raise `client_max_body_size` in `nginx/default.conf` (and in Caddy) |
| run shows `FAILED` "interrupted by restart" | backend restarted mid-solve (in-process queue). Start the run again |
| API slow while a solve runs | CP-SAT is using all CPU cores. Lower `solver_workers` or solve time limits, or move to dedicated workers ([Scaling](#scaling)) |
| SSE progress not live | a different uvicorn process holds the job (see [the job queue](#the-job-queue-read-before-scaling)); the UI polling still shows progress |
| frontend shows "Backend unreachable" (502 from `/api/v1`) | the frontend reaches FastAPI at `NEXT_PUBLIC_API_URL` (default `http://backend:8000`, baked in at build time). Check `docker compose ps backend`, fix the URL in `.env`, then `./deploy.sh --update`. There is no mock mode |
| `port is already allocated` | change `PROXY_PORT` (or `CRBS_PORT`) in `.env` |
| legacy app "unable to write" | the `crbs-local` / `crbs-uploads` volumes were created by an older root-owned image: `docker compose exec -u 0 crbs chown -R www-data: local uploads` |

## Verification status

`validate.sh` runs on every CI build (YAML, env completeness, no committed secrets, no inline-comment
values, pinned images, non-root final stages, COPY sources, shellcheck, `nginx -t`,
`docker compose config` for the base stack and the Caddy override). The CI jobs `docker` (buildx
build of all three images) and `stack-smoke` (`deploy.sh`, login through nginx, non-root check,
`--down --volumes`) exercise the real containers.
