#!/usr/bin/env bash
# Gate: the production `next build` the e2e-real shards serve, once per run, in this run's source tree
# (smartsched/frontend/.next), then the standalone output is checked for mock/demo code (validate.sh --no-mock-build).
# NEXT_PUBLIC_API_URL is http://backend:8000: every shard's seeded backend has that alias on its own network, so one
# build serves all shards (src/ reads no other build-time env). The shards copy .next (without cache/ and standalone/)
# into their own directory and only `next start` it (E2E_PREBUILT=1 in playwright.config.ts), so three servers never
# write into one .next. Runs after the vitest shards: nothing else writes the frontend tree then (the images gate
# builds from a context that excludes .next). Memory: NODE_MEMORY / NODE_HEAP_MB (lib.sh; two slots in gates.py).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_playwright -e NEXT_PUBLIC_API_URL=http://backend:8000 -e NEXT_TELEMETRY_DISABLED=1 -- '
[ -x node_modules/.bin/next ] || { echo "node_modules missing: the frontend gate installs them"; exit 1; }
echo "==== next build (NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}; NODE_OPTIONS=${NODE_OPTIONS:-})"
start=$SECONDS
npx next build >/w/next-build.log 2>&1 || { tail -n 60 /w/next-build.log; exit 1; }
echo "next build: $((SECONDS - start)) s"
[ -f .next/BUILD_ID ] || { echo "next build left no .next/BUILD_ID"; exit 1; }
echo "==== no mock/demo code in the production build"
bash ../deploy/validate.sh --no-mock-build .next/standalone
'
