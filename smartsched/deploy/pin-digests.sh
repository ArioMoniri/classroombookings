#!/usr/bin/env bash
# Refresh the base image digest pins (pins.py): resolves the current multi-arch index digest of every pinned
# tag (docker buildx imagetools inspect; needs registry access, no pulls) and rewrites docker-compose.yml,
# docker-compose.caddy.yml and the pod CI python image in one go, then checks them. Review the diff, run the
# pod CI (the images gate rebuilds with the new bases) and commit. Bumping a *tag* is a deliberate edit:
# change compose and the Dockerfile ARG default together (pins.py check fails when they differ).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$HERE/pins.py" refresh
python3 "$HERE/pins.py" check
