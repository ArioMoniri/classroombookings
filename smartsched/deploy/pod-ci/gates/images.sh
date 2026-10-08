#!/usr/bin/env bash
# Gate: build the three images exactly as compose does (backend, frontend, legacy CRBS); no push. The
# per-run tags are removed afterwards; the BuildKit layer cache stays and speeds up the redeploy.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$WS/src"
tags=()
trap 'docker image rm "${tags[@]}" >/dev/null 2>&1 || true' EXIT
build() { local tag="$1"; shift; tags+=("$tag"); section "docker build $tag"; docker build --label "smartsched-ci.run=${RUN_TAG}" -t "$tag" "$@"; }
build "smartsched-backend:ci-${RUN_TAG}" -f smartsched/backend/Dockerfile smartsched/backend
build "smartsched-frontend:ci-${RUN_TAG}" -f smartsched/frontend/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://backend:8000 --build-arg NEXT_PUBLIC_API_MOCK=0 smartsched/frontend
build "smartsched-crbs:ci-${RUN_TAG}" -f smartsched/deploy/legacy/Dockerfile .
