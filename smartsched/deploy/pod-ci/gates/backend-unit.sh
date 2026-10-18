#!/usr/bin/env bash
# Gate: one shard of the backend `make test` (`backend-unit.sh 1/3`): pytest with make test's options on a
# deterministic share of the test files (tests/**/test_*.py outside tests/solver, sorted, every <count>th starting
# at <index>), against the PostgreSQL service (gates/backend-lib.sh). The shards together run every file of
# `make test`; nothing is skipped (pytest-xdist is not in the lock, so the shards are separate gates).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/backend-lib.sh"
SHARD="${1:?usage: backend-unit.sh <index>/<count>}"
[[ "$SHARD" =~ ^([1-9][0-9]*)/([1-9][0-9]*)$ ]] && (( BASH_REMATCH[1] <= BASH_REMATCH[2] )) \
  || { echo "bad shard $SHARD"; exit 2; }
start_postgres

in_python "${PG_NET[@]}" "${PG_ENV[@]}" -e SHARD_INDEX="${SHARD%/*}" -e SHARD_COUNT="${SHARD#*/}" -- "$PY_VENV"'
# `make test` = pytest -q --ignore=tests/solver -m "not slow" over testpaths=tests
mapfile -t files < <(find tests -path tests/solver -prune -o -type f \( -name "test_*.py" -o -name "*_test.py" \) -print \
  | LC_ALL=C sort | awk -v i="$SHARD_INDEX" -v n="$SHARD_COUNT" "(NR - 1) % n == i - 1")
echo "==== pytest shard ${SHARD_INDEX}/${SHARD_COUNT}: ${#files[@]} test files (PostgreSQL tests on the postgres service)"
[ "${#files[@]}" -gt 0 ] || { echo "no test files in this shard"; exit 1; }
python -m pytest -q --ignore=tests/solver -m "not slow" --durations=15 "${files[@]}"
'
