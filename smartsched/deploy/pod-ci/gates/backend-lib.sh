#!/usr/bin/env bash
# Shared by gates/backend.sh and gates/backend-unit.sh (sourced after lib.sh).
#
# start_postgres: a PostgreSQL service container (the image + digest pinned in smartsched/deploy/docker-compose.yml,
# data on tmpfs) on a private per-run network as `postgres`; TEST_POSTGRES_URL points the PostgreSQL tests
# (tests/pg_support.py: concurrency, locks) at it, so they run instead of skipping. Removed on exit.
# PG_NET / PG_ENV: the docker run arguments that put a python container on that network with both URLs.
COMPOSE_FILE="$WS/src/smartsched/deploy/docker-compose.yml"
# one postgres per gate: backend and the backend-unit-* shards may run at the same time (podci/runner.py)
PG_TAG="${RUN_TAG}-${GATE_NAME:-backend}"
PG_PASSWORD="ci-${RUN_TAG}"
net="smartsched-ci-pg-${PG_TAG}"
pg="smartsched-ci-pg-${PG_TAG}"
PG_NET=(--network "$net")
PG_ENV=(
  -e TEST_POSTGRES_URL="postgresql+psycopg://postgres:${PG_PASSWORD}@postgres:5432/postgres"
  -e PG_MIGRATE_URL="postgresql+psycopg://postgres:${PG_PASSWORD}@postgres:5432/ci_migrate"
)

start_postgres() {
  PG_IMAGE="$(grep -oE 'image:[[:space:]]*postgres:[^[:space:]]+' "$COMPOSE_FILE" | head -n 1 | sed 's/^image:[[:space:]]*//')"
  [[ -n "$PG_IMAGE" ]] || { echo "no postgres image in $COMPOSE_FILE"; exit 1; }
  trap 'docker rm -f "$pg" >/dev/null 2>&1 || true; docker network rm "$net" >/dev/null 2>&1 || true' EXIT
  section "postgres service ($PG_IMAGE)"
  docker network create --label "smartsched-ci.run=${RUN_TAG}" "$net" >/dev/null
  # the postgres entrypoint starts as root and drops to the postgres user itself, so no --user here
  docker run -d --rm --label "smartsched-ci.run=${RUN_TAG}" --name "$pg" --network "$net" --network-alias postgres \
    --cpus 1 --memory 1g --security-opt no-new-privileges:true --tmpfs /var/lib/postgresql/data:rw,size=1g \
    -e POSTGRES_PASSWORD="$PG_PASSWORD" -e POSTGRES_INITDB_ARGS="--encoding=UTF8" "$PG_IMAGE" >/dev/null
  local ready=0
  for _ in $(seq 1 "${PG_READY_TRIES:-60}"); do
    if docker exec "$pg" pg_isready -U postgres -h 127.0.0.1 >/dev/null 2>&1; then ready=1; break; fi
    sleep "${PG_READY_SLEEP:-1}"
  done
  if [[ $ready -ne 1 ]]; then
    echo "postgres did not become ready"; docker logs --tail 50 "$pg" 2>&1 || true; exit 1
  fi
  docker exec "$pg" createdb -U postgres ci_migrate
  echo "postgres ready"
}

# The backend venv in the run's workspace (/w/venv): built by the backend-deps gate (PY_VENV_INSTALL), then only
# activated (PY_VENV) by backend.sh and backend-unit.sh, which may run concurrently. /w/venv/.podci-installed marks a
# finished install.
# shellcheck disable=SC2016
PY_VENV_INSTALL='
rm -rf /w/venv
python -m venv /w/venv && . /w/venv/bin/activate
# no unhashed "pip install --upgrade pip": the bundled pip runs hash-checking mode
# SECURITY F13: hash-checking mode. requirements-dev.lock = the versions the image ships (requirements.lock) plus
# pytest / ruff / mypy; requirements-build.lock = setuptools, so the editable install needs no isolated build env
pip install -q --require-hashes -r smartsched/backend/requirements-dev.lock -r smartsched/backend/requirements-build.lock
pip install -q --no-deps --no-build-isolation -e "./smartsched/backend"
touch /w/venv/.podci-installed
'
# shellcheck disable=SC2016
PY_VENV='
[ -f /w/venv/.podci-installed ] || { echo "no backend venv in /w/venv: the backend-deps gate builds it"; exit 1; }
. /w/venv/bin/activate
# SAML 2.0 is built in (signxml from the lock): fail loudly rather than let tests/test_w3b_idp_saml.py skip
python -c "import signxml; from importlib.metadata import version; print(\"signxml\", version(\"signxml\"))"
cd smartsched/backend
'
