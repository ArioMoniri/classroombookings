#!/usr/bin/env bash
# Gate: build the three images exactly as compose does (backend, frontend, legacy CRBS); no push. The
# backend image must import the intake parsers. The per-run tags are removed afterwards; the BuildKit layer
# cache stays and speeds up the redeploy. A deploy-branch run (RUN_DEPLOY=1) keeps its images as
# smartsched-{backend,frontend,crbs}:ci-<full RUN_SHA> for gates/deploy.sh (retag + deploy.sh --no-build); the
# ci-<sha> tags of every other commit are removed, so only the newest deploy-branch run's images stay.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$WS/src"
tags=()
# per-run tags and this run's dangling images go; the BuildKit cache stays (podci/disk.py trims it)
trap 'docker image rm "${tags[@]}" >/dev/null 2>&1 || true
docker image prune -f --filter "label=smartsched-ci.image=${RUN_TAG}" >/dev/null 2>&1 || true' EXIT
section "disk before the builds"; df -h / | tail -n 1
# The image label is smartsched-ci.image, NEVER smartsched-ci.run: containers inherit their image's labels, and these
# images can become the live app's (gates/deploy.sh retags them); a run label on them made the worker's leftover
# cleanup remove the live backend and frontend (gracious run #150, 2026-10-20)
build() { local tag="$1"; shift; tags+=("$tag"); section "docker build $tag"; docker build --label "smartsched-ci.image=${RUN_TAG}" -t "$tag" "$@"; }
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
if [[ "${RUN_DEPLOY:-0}" == 1 && "${RUN_SHA:-}" =~ ^[0-9a-f]{40}$ ]]; then
  section "keep this commit's images for the deploy step (ci-${RUN_SHA:0:12})"
  for svc in backend frontend crbs; do
    docker tag "smartsched-${svc}:ci-${RUN_TAG}" "smartsched-${svc}:ci-${RUN_SHA}"
    docker image ls --format '{{.Repository}}:{{.Tag}}' "smartsched-${svc}" | while IFS= read -r ref; do
      case "${ref##*:}" in
        "ci-${RUN_SHA}") ;;
        ci-????????????????????????????????????????) docker image rm "$ref" >/dev/null 2>&1 || true ;;
      esac
    done
  done
fi
