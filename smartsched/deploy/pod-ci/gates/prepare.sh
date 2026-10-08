#!/usr/bin/env bash
# Build the pod CI python image (once per Dockerfile hash) and pull the pinned Playwright image.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
section "python CI image ${PY_IMAGE}"
if ! docker image inspect "$PY_IMAGE" >/dev/null 2>&1; then
  docker build --pull -t "$PY_IMAGE" --build-arg "PYTHON_IMAGE=${PY_BASE_IMAGE:?}" -f "$GATES_DIR/python-ci.Dockerfile" "$GATES_DIR"
fi
section "playwright image ${PW_IMAGE}"
docker image inspect "$PW_IMAGE" >/dev/null 2>&1 || docker pull "$PW_IMAGE"
docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep -E 'podci|playwright' || true
