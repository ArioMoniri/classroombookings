#!/usr/bin/env bash
# Gate: backend make check (ruff + mypy + pytest, real fixture workbooks) + solver/AI gates + migrations.
#
# A PostgreSQL service container (the image + digest pinned in smartsched/deploy/docker-compose.yml, data on
# tmpfs) runs on a private per-run network as `postgres`; TEST_POSTGRES_URL points the PostgreSQL tests
# (tests/pg_support.py: concurrency, locks) at it, so they run instead of skipping. Migrations: exactly one
# Alembic head (never a pinned revision), then a fresh `alembic upgrade head` on SQLite and on PostgreSQL.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

COMPOSE_FILE="$WS/src/smartsched/deploy/docker-compose.yml"
PG_IMAGE="$(grep -oE 'image:[[:space:]]*postgres:[^[:space:]]+' "$COMPOSE_FILE" | head -n 1 | sed 's/^image:[[:space:]]*//')"
[[ -n "$PG_IMAGE" ]] || { echo "no postgres image in $COMPOSE_FILE"; exit 1; }
PG_PASSWORD="ci-${RUN_TAG}"
net="smartsched-ci-pg-${RUN_TAG}"
pg="smartsched-ci-pg-${RUN_TAG}"
cleanup() {
  docker rm -f "$pg" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
}
trap cleanup EXIT

section "postgres service ($PG_IMAGE)"
docker network create --label "smartsched-ci.run=${RUN_TAG}" "$net" >/dev/null
# the postgres entrypoint starts as root and drops to the postgres user itself, so no --user here
docker run -d --rm --label "smartsched-ci.run=${RUN_TAG}" --name "$pg" --network "$net" --network-alias postgres \
  --cpus 1 --memory 1g --security-opt no-new-privileges:true --tmpfs /var/lib/postgresql/data:rw,size=1g \
  -e POSTGRES_PASSWORD="$PG_PASSWORD" -e POSTGRES_INITDB_ARGS="--encoding=UTF8" "$PG_IMAGE" >/dev/null
ready=0
for _ in $(seq 1 "${PG_READY_TRIES:-60}"); do
  if docker exec "$pg" pg_isready -U postgres -h 127.0.0.1 >/dev/null 2>&1; then ready=1; break; fi
  sleep "${PG_READY_SLEEP:-1}"
done
if [[ $ready -ne 1 ]]; then
  echo "postgres did not become ready"; docker logs --tail 50 "$pg" 2>&1 || true; exit 1
fi
docker exec "$pg" createdb -U postgres ci_migrate
echo "postgres ready"

in_python --network "$net" \
  -e TEST_POSTGRES_URL="postgresql+psycopg://postgres:${PG_PASSWORD}@postgres:5432/postgres" \
  -e PG_MIGRATE_URL="postgresql+psycopg://postgres:${PG_PASSWORD}@postgres:5432/ci_migrate" -- '
python -m venv /w/venv && . /w/venv/bin/activate
pip install -q --upgrade pip
# the versions the image ships (smartsched/backend/requirements.lock, as constraints like the Dockerfile)
lock=(); [ -f smartsched/backend/requirements.lock ] && lock=(-c smartsched/backend/requirements.lock)
pip install -q "${lock[@]}" -e "./smartsched/backend[dev]"
cd smartsched/backend
echo "==== make check (PostgreSQL tests on the postgres service)"; make check
echo "==== solver gate"; ruff check app/solver && python -m mypy app/solver && python -m pytest tests/solver -q
echo "==== ai gate"
if [ -d app/ai ]; then ruff check app/ai; fi
if grep -q -- "--ignore=tests/ai" Makefile && [ -d tests/ai ]; then python -m pytest tests/ai -q; fi
echo "==== migrations: one head, fresh upgrade on SQLite and PostgreSQL"
heads="$(DATABASE_URL=sqlite+aiosqlite:////w/ci-heads.db alembic heads)"
echo "$heads"
n="$(grep -c "(head)" <<< "$heads" || true)"
if [ "$n" != 1 ]; then echo "expected exactly one Alembic head, found $n"; exit 1; fi
DATABASE_URL=sqlite+aiosqlite:////w/ci-migrate.db alembic upgrade head
DATABASE_URL="$PG_MIGRATE_URL" alembic upgrade head
DATABASE_URL="$PG_MIGRATE_URL" alembic current
'
