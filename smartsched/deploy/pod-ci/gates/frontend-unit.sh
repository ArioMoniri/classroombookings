#!/usr/bin/env bash
# Gate: one vitest shard (`frontend-unit.sh 1/2`), on the node_modules the frontend gate installed in this run's
# workspace. Every test file belongs to exactly one shard (vitest --shard); the shards together are the
# `vitest run` of package.json "check". CI=1: vitest.config.mts uses 2 forks with a capped heap and a 30 s test
# timeout. Nothing is skipped.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SHARD="${1:?usage: frontend-unit.sh <index>/<count>}"
[[ "$SHARD" =~ ^[1-9][0-9]*/[1-9][0-9]*$ ]] || { echo "bad shard $SHARD"; exit 2; }
in_playwright -e VITEST_SHARD="$SHARD" -- '
[ -x node_modules/.bin/vitest ] || { echo "node_modules missing: the frontend gate installs them"; exit 1; }
echo "==== vitest run --shard=${VITEST_SHARD}"; node_modules/.bin/vitest run --shard="${VITEST_SHARD}"
'
