#!/usr/bin/env bash
# Gate: backend make check (ruff + mypy + pytest, real fixture workbooks) + solver/AI gates + SQLite migrations.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_python -- '
python -m venv /w/venv && . /w/venv/bin/activate
pip install -q --upgrade pip
# the versions the image ships (smartsched/backend/requirements.lock, as constraints like the Dockerfile)
lock=(); [ -f smartsched/backend/requirements.lock ] && lock=(-c smartsched/backend/requirements.lock)
pip install -q "${lock[@]}" -e "./smartsched/backend[dev]"
cd smartsched/backend
echo "==== make check"; make check
echo "==== solver gate"; ruff check app/solver && python -m mypy app/solver && python -m pytest tests/solver -q
echo "==== ai gate"
if [ -d app/ai ]; then ruff check app/ai; fi
if grep -q -- "--ignore=tests/ai" Makefile && [ -d tests/ai ]; then python -m pytest tests/ai -q; fi
echo "==== migrations on a fresh SQLite database"
DATABASE_URL=sqlite+aiosqlite:////w/ci-migrate.db alembic upgrade head
'
