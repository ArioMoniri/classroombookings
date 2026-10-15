#!/usr/bin/env bash
# Gate: build the three images exactly as compose does (backend, frontend, legacy CRBS); no push. The
# backend image must import the intake parsers. The per-run tags are removed afterwards; the BuildKit layer
# cache stays and speeds up the redeploy.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$WS/src"
tags=()
trap 'docker image rm "${tags[@]}" >/dev/null 2>&1 || true' EXIT
build() { local tag="$1"; shift; tags+=("$tag"); section "docker build $tag"; docker build --label "smartsched-ci.run=${RUN_TAG}" -t "$tag" "$@"; }
# the build args compose passes (digest-pinned base images, NEXT_PUBLIC_API_URL default; smartsched/deploy/pins.py)
args() {
  local out
  out="$(python3 smartsched/deploy/pins.py build-args "$1")" || { echo "pins.py build-args $1 failed"; exit 1; }
  _args=(); [[ -n "$out" ]] && mapfile -t _args <<< "$out"; return 0
}
args backend
build "smartsched-backend:ci-${RUN_TAG}" -f smartsched/backend/Dockerfile ${_args[@]+"${_args[@]}"} smartsched/backend
# the clean image (requirements.lock) must import every parser the intake uses (review P19-Q3)
section "backend image imports"
docker run --rm --network none --entrypoint python "smartsched-backend:ci-${RUN_TAG}" -c \
  "import xlrd, defusedxml, pdfplumber, pypdfium2, icalendar, docx, pypdf, openpyxl, ortools; print('imports ok')"
args frontend
build "smartsched-frontend:ci-${RUN_TAG}" -f smartsched/frontend/Dockerfile ${_args[@]+"${_args[@]}"} smartsched/frontend
args crbs
build "smartsched-crbs:ci-${RUN_TAG}" -f smartsched/deploy/legacy/Dockerfile ${_args[@]+"${_args[@]}"} .
