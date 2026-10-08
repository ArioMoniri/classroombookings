#!/usr/bin/env bash
# Shared helpers for the pod CI gates (sourced). podci/runner.py exports:
#   WS          per-run workspace on the host (source tree in $WS/src, exported with git archive)
#   CACHE_DIR   persistent pip/npm caches (owned by the smartsched-ci user)
#   RUN_TAG     unique per run (container labels, image tags, network names)
#   CI_UID/CI_GID, GATE_CPUS, GATE_MEMORY, PY_IMAGE (pod CI python image), PW_IMAGE (Playwright image
#   matching package-lock.json), GATES_DIR (this directory, mounted read-only at /ci)
# Gates run one at a time; containers are non-root, resource-limited and removed afterwards.
set -euo pipefail
: "${WS:?}" "${CACHE_DIR:?}" "${RUN_TAG:?}" "${CI_UID:?}" "${CI_GID:?}" "${GATES_DIR:?}"
GATE_CPUS="${GATE_CPUS:-2}"
GATE_MEMORY="${GATE_MEMORY:-3g}"
mkdir -p "$WS/home" "$CACHE_DIR/pip" "$CACHE_DIR/npm"

docker_common=(
  --rm --init
  --label "smartsched-ci.run=${RUN_TAG}"
  --cpus "$GATE_CPUS" --memory "$GATE_MEMORY" --memory-swap "$GATE_MEMORY"
  --security-opt no-new-privileges:true
  --user "${CI_UID}:${CI_GID}"
  -e HOME=/w/home -e CI=1 -e PIP_CACHE_DIR=/cache/pip -e npm_config_cache=/cache/npm
  -v "$WS:/w" -v "$CACHE_DIR:/cache" -v "$GATES_DIR:/ci:ro"
)

# in_python [docker run args...] -- 'script'
in_python() {
  local extra=()
  while [[ $# -gt 1 && "$1" != "--" ]]; do extra+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] && shift
  : "${PY_IMAGE:?}"
  docker run "${docker_common[@]}" ${extra[@]+"${extra[@]}"} -w /w/src "$PY_IMAGE" bash -euo pipefail -c "$1"
}

# in_playwright [docker run args...] -- 'script'   (cwd: smartsched/frontend)
in_playwright() {
  local extra=()
  while [[ $# -gt 1 && "$1" != "--" ]]; do extra+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] && shift
  : "${PW_IMAGE:?}"
  docker run "${docker_common[@]}" ${extra[@]+"${extra[@]}"} --ipc=host -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    -w /w/src/smartsched/frontend "$PW_IMAGE" bash -euo pipefail -c "$1"
}

section() { printf '\n==== %s (%s)\n' "$*" "$(date -u +%H:%M:%S)"; }
