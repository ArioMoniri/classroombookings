#!/bin/sh
# SmartSched backend container entrypoint (POSIX sh; the image is python:3.12-slim-bookworm).
#
#   1. wait for the database (DB_WAIT_SECONDS, default 60)
#   2. alembic upgrade head            (skip with RUN_MIGRATIONS=0, e.g. on extra replicas)
#   3. python -m app.cli seed-admin    (skip with SEED_ADMIN=0; no-op when any user exists)
#   4. exec uvicorn (or the command given as arguments, e.g. `python -m app.cli import ...`)
#
# Solver/import jobs run in the backend's in-process asyncio queue (app/workers/queue.py); there is no
# separate worker process to start. See smartsched/deploy/README.md "Scaling".
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${UVICORN_WORKERS:=2}"
: "${UVICORN_PORT:=8000}"
: "${DB_WAIT_SECONDS:=60}"
: "${RUN_MIGRATIONS:=1}"
: "${SEED_ADMIN:=1}"
export DB_WAIT_SECONDS

python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
# Readiness probe with a sync driver: postgresql+psycopg:// is sync-capable, sqlite drops +aiosqlite.
sync_url = url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")
deadline = time.time() + float(os.environ.get("DB_WAIT_SECONDS", "60"))
while True:
    try:
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        print("[entrypoint] database reachable", flush=True)
        break
    except Exception as exc:  # noqa: BLE001
        if time.time() > deadline:
            print(f"[entrypoint] database not reachable: {exc}", file=sys.stderr, flush=True)
            sys.exit(1)
        print("[entrypoint] waiting for database ...", flush=True)
        time.sleep(2)
PY

if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head
else
  echo "[entrypoint] RUN_MIGRATIONS=0: skipping alembic"
fi

if [ "$SEED_ADMIN" = "1" ]; then
  echo "[entrypoint] seed admin (no-op when users exist)"
  python -m app.cli seed-admin
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

echo "[entrypoint] starting uvicorn on :${UVICORN_PORT} (${UVICORN_WORKERS} workers)"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${UVICORN_PORT}" \
  --workers "${UVICORN_WORKERS}" \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --timeout-graceful-shutdown 30
