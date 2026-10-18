#!/usr/bin/env bash
# Gate: backend static checks (ruff + format + mypy: `make lint type`) + solver/AI gates + migrations. pytest of
# `make test` runs in the backend-unit-* gates (gates/backend-unit.sh): one gate for all of `make check` ran past
# 2400 s on the 2-CPU pod (runs #81, #82: pytest alone took ~90 min at 2 CPUs).
#
# PostgreSQL service: gates/backend-lib.sh. Migrations: exactly one Alembic head (never a pinned revision), then a
# fresh `alembic upgrade head` on SQLite and on PostgreSQL.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/backend-lib.sh"
start_postgres

in_python "${PG_NET[@]}" "${PG_ENV[@]}" -- "$PY_VENV"'
echo "==== make lint type (ruff, ruff format, mypy)"; make lint type
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
