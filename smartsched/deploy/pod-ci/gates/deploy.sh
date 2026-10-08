#!/usr/bin/env bash
# Deploy step (deploy branch only, after every blocking gate passed). podci/runner.py has already checked
# out the commit in $DEPLOY_DIR and rendered the /ci/ location into nginx/default.conf.
#   DEPLOY_DIR    the pod's deploy checkout (/opt/smartsched/src)
#   DEPLOY_FLAGS  extra deploy.sh flags, space separated (default --tls)
set -euo pipefail
: "${DEPLOY_DIR:?}"
cd "$DEPLOY_DIR/smartsched/deploy"
read -r -a flags <<< "${DEPLOY_FLAGS:---tls}"
echo "==== deploy.sh --update --no-pull ${flags[*]}"
./deploy.sh --update --no-pull "${flags[@]}"
files=(-f docker-compose.yml)
for f in "${flags[@]}"; do [[ "$f" == "--tls" ]] && files+=(-f docker-compose.caddy.yml); done
echo "==== restart proxy (picks up the re-rendered nginx config)"
docker compose --env-file .env "${files[@]}" restart proxy
port="$(grep -E '^PROXY_PORT=' .env | cut -d= -f2)"; port="${port:-8080}"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${port}/api/v1/health" | grep -q '"db":true'; then echo "healthy"; exit 0; fi
  sleep 3
done
echo "not healthy after the deploy"; docker compose --env-file .env "${files[@]}" ps; exit 1
