# syntax=docker/dockerfile:1.7
# SmartSched backend: FastAPI + SQLAlchemy 2 + OR-Tools CP-SAT.
# Build context: smartsched/backend (see smartsched/deploy/docker-compose.yml).

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ---------------------------------------------------------------------------
# Stage 1: install dependencies into a virtualenv (all deps ship manylinux wheels,
# so no compiler is needed; keep the final image slim).
# ---------------------------------------------------------------------------
FROM base AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml ./
# Install the dependency set first (layer cache), then the package itself.
RUN mkdir -p app && touch app/__init__.py && pip install . && rm -rf app
COPY app ./app
RUN pip install --no-deps .
# Optional extras, e.g. EXTRA_PIP="pymysql" for the live CRBS (MySQL) importer.
ARG EXTRA_PIP=""
RUN if [ -n "$EXTRA_PIP" ]; then pip install $EXTRA_PIP; fi

# ---------------------------------------------------------------------------
# Stage 2: runtime image (non-root, migrations + admin seed on start).
# ---------------------------------------------------------------------------
FROM base AS runtime
RUN groupadd --system --gid 1000 app \
 && useradd --system --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app \
 && mkdir -p /app /data/uploads \
 && chown -R app:app /app /data
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app

COPY --chmod=755 <<'SH' /usr/local/bin/entrypoint.sh
#!/bin/sh
# Wait for the database, apply migrations, seed the admin user, then exec the server.
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${UVICORN_WORKERS:=2}"
: "${UVICORN_PORT:=8000}"
: "${DB_WAIT_SECONDS:=60}"

python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text
url = os.environ["DATABASE_URL"]
# Use the sync driver for the readiness probe (postgresql+psycopg:// and sqlite:// both work).
sync_url = url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")
deadline = time.time() + float(os.environ.get("DB_WAIT_SECONDS", "60"))
while True:
    try:
        with create_engine(sync_url, pool_pre_ping=True).connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[entrypoint] database reachable", flush=True)
        break
    except Exception as exc:  # noqa: BLE001
        if time.time() > deadline:
            print(f"[entrypoint] database not reachable: {exc}", file=sys.stderr, flush=True)
            sys.exit(1)
        print("[entrypoint] waiting for database ...", flush=True)
        time.sleep(2)
PY

echo "[entrypoint] alembic upgrade head"
alembic upgrade head
echo "[entrypoint] seed admin (no-op when users exist)"
python -m app.cli seed-admin

if [ "$#" -gt 0 ]; then
  exec "$@"
fi
echo "[entrypoint] starting uvicorn (${UVICORN_WORKERS} workers)"
exec uvicorn app.main:app --host 0.0.0.0 --port "${UVICORN_PORT}" --workers "${UVICORN_WORKERS}" --proxy-headers --forwarded-allow-ips='*'
SH

ENV PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=prod \
    UPLOAD_DIR=/data/uploads \
    UVICORN_WORKERS=2 \
    UVICORN_PORT=8000
USER app
EXPOSE 8000
VOLUME ["/data/uploads"]
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import sys,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4); sys.exit(0 if r.status==200 else 1)"
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
