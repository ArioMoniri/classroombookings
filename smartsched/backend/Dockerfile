# syntax=docker/dockerfile:1.7
# SmartSched backend: FastAPI + SQLAlchemy 2 + OR-Tools CP-SAT.
# Build context: smartsched/backend (see smartsched/deploy/docker-compose.yml).
#
# Reproducibility: the base image is pinned to a patch release + Debian codename. Python dependencies
# come from pyproject.toml; when a `requirements.lock` (pip freeze / pip-compile output) is present in
# the build context it is used as a constraints file so every build resolves the same versions.

ARG PYTHON_IMAGE=python:3.12.15-slim-bookworm

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ---------------------------------------------------------------------------
# Stage 1: install dependencies into a virtualenv. All deps ship manylinux wheels (ortools, psycopg[binary],
# argon2-cffi, cryptography, uvloop), so no compiler is needed and the runtime image stays slim.
# ---------------------------------------------------------------------------
FROM base AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# `requirements.lock*` is optional (glob matches nothing when the file is absent).
COPY pyproject.toml requirements.lock* ./
# Dependency layer first (cached until pyproject/lock change), then the package itself.
RUN mkdir -p app && touch app/__init__.py \
 && if [ -f requirements.lock ]; then pip install -c requirements.lock . ; else pip install . ; fi \
 && rm -rf app build ./*.egg-info
COPY app ./app
RUN pip install --no-deps .
# Optional extras, e.g. EXTRA_PIP="pymysql" for the live CRBS (MySQL) importer.
ARG EXTRA_PIP=""
RUN if [ -n "$EXTRA_PIP" ]; then pip install $EXTRA_PIP; fi

# ---------------------------------------------------------------------------
# Stage 2: runtime image (non-root uid 1000; migrations + admin seed on start).
# ---------------------------------------------------------------------------
FROM base AS runtime
LABEL org.opencontainers.image.title="smartsched-backend" \
      org.opencontainers.image.description="SmartSched API (FastAPI, CP-SAT solver, in-process job queue)" \
      org.opencontainers.image.source="https://github.com/classroombookings/classroombookings"
RUN groupadd --system --gid 1000 app \
 && useradd --system --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app \
 && mkdir -p /app /data/uploads \
 && chown -R app:app /app /data
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

ENV PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=prod \
    UPLOAD_DIR=/data/uploads \
    UVICORN_WORKERS=2 \
    UVICORN_PORT=8000 \
    RUN_MIGRATIONS=1 \
    SEED_ADMIN=1
USER app
EXPOSE 8000
VOLUME ["/data/uploads"]
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import sys,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4); sys.exit(0 if r.status==200 else 1)"
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
