#!/usr/bin/env bash
# Shared helpers for the pod CI gates (sourced). podci/runner.py exports:
#   WS          per-run workspace on the host (source tree in $WS/src, exported with git archive)
#   CACHE_DIR   persistent pip/npm caches (owned by the smartsched-ci user)
#   RUN_TAG     unique per run (container labels, image tags, network names)
#   CI_UID/CI_GID, GATE_CPUS, GATE_MEMORY, PY_IMAGE (pod CI python image), PW_IMAGE (Playwright image
#   matching package-lock.json), GATES_DIR (this directory, mounted read-only at /ci)
#   GATE_NAME (this gate), and with PODCI_PARALLEL slots > 1 also GATE_CPUS / GATE_MEMORY / NODE_MEMORY / NODE_HEAP_MB
#   (one slot's share: gates may run at the same time, podci/runner.py). Never share a container or network name
#   or a /w path between gates that can overlap. Containers are non-root, resource-limited and removed afterwards.
set -euo pipefail
: "${WS:?}" "${CACHE_DIR:?}" "${RUN_TAG:?}" "${CI_UID:?}" "${CI_GID:?}" "${GATES_DIR:?}"
GATE_CPUS="${GATE_CPUS:-2}"
GATE_MEMORY="${GATE_MEMORY:-3g}"
# Node gates (frontend, e2e-real's Playwright container): the pod is a 2 vCPU / 8 GB arm64 t4g.large that also
# runs the app stack (~2 GB). V8 sizes its default heap from the cgroup limit, which ran out in tsc/next build
# ("Ineffective mark-compacts near heap limit", run #51), so node containers get NODE_MEMORY and an explicit heap
# of NODE_HEAP_MB below it. vitest.config.mts caps its own forks (2 workers, 1536 MB each) under CI=1.
NODE_MEMORY="${NODE_MEMORY:-4g}"
NODE_HEAP_MB="${NODE_HEAP_MB:-3072}"
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
  # the later --memory/--memory-swap win over docker_common's GATE_MEMORY
  docker run "${docker_common[@]}" --memory "$NODE_MEMORY" --memory-swap "$NODE_MEMORY" \
    -e NODE_OPTIONS="--max-old-space-size=${NODE_HEAP_MB}" ${extra[@]+"${extra[@]}"} \
    --ipc=host -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    -w /w/src/smartsched/frontend "$PW_IMAGE" bash -euo pipefail -c "$1"
}

section() { printf '\n==== %s (%s)\n' "$*" "$(date -u +%H:%M:%S)"; }
