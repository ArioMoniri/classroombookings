#!/usr/bin/env bash
# Gate: smartsched/deploy/validate.sh on the host (python3-yaml, docker compose config, nginx -t if present).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
section "deploy/validate.sh"
cd "$WS/src"
bash smartsched/deploy/validate.sh
