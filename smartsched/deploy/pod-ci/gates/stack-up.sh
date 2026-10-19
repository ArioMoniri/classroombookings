#!/usr/bin/env bash
# Boot: bring the last good app stack back up (smartsched-stack.service, after docker.service). The compose services
# already use `restart: unless-stopped`, so dockerd restarts them on its own; this covers containers that were
# stopped (`docker stop`, a manual `deploy.sh --down`) or never started after the pod came back. It never builds,
# pulls, checks out or stops anything: `docker compose up -d --no-build` on the deploy checkout, which pod CI only
# leaves on a commit whose deploy passed its health check (podci/runner.py rolls a failed deploy back). Before the first
# deploy (no deployed-sha) it starts nothing: "first deploy pending", exit 0.
#   PODCI_DEPLOY_DIR    deploy checkout (default /opt/smartsched/src)
#   PODCI_DEPLOY_FLAGS  deploy.sh flags, comma separated (unset: --tls, adds docker-compose.caddy.yml; empty: none)
#   PODCI_STATE_DIR     pod CI state (default /var/lib/smartsched-ci; deployed-sha = the last good deploy)
set -euo pipefail
DEPLOY_DIR="${PODCI_DEPLOY_DIR:-/opt/smartsched/src}"
STATE_DIR="${PODCI_STATE_DIR:-/var/lib/smartsched-ci}"
cd "$DEPLOY_DIR/smartsched/deploy" 2>/dev/null || { echo "no deploy checkout in $DEPLOY_DIR: nothing to start"; exit 0; }
[[ -f .env ]] || { echo "no $PWD/.env (first deploy never ran): nothing to start"; exit 0; }
good="$(cat "$STATE_DIR/deployed-sha" 2>/dev/null || true)"
head="$(git -C "$DEPLOY_DIR" rev-parse HEAD 2>/dev/null || echo '?')"
if [[ -z "$good" ]]; then
  # pod-bootstrap.sh only prepares images; nothing ungated is ever started. Pod CI's first green run deploys
  echo "first deploy pending (no deployed-sha yet; checkout at ${head:0:7}): nothing to start"
  exit 0
elif [[ "$good" != "$head" ]]; then
  echo "warning: checkout at ${head:0:7}, last good deploy ${good:0:7} (an interrupted deploy?); starting existing images"
fi
files=(-f docker-compose.yml)
IFS=',' read -r -a flags <<< "${PODCI_DEPLOY_FLAGS---tls}"
for f in "${flags[@]}"; do [[ "${f// /}" == "--tls" ]] && files+=(-f docker-compose.caddy.yml); done
echo "==== docker compose ${files[*]} up -d --no-build"
docker compose --env-file .env "${files[@]}" up -d --no-build
docker compose --env-file .env "${files[@]}" ps
