#!/usr/bin/env bash
# Deploy step (deploy branch only, after every blocking gate passed). podci/runner.py has already checked
# out the commit in $DEPLOY_DIR and rendered the /ci/ location into nginx/default.conf.
#   DEPLOY_DIR    the pod's deploy checkout (/opt/smartsched/src)
#   DEPLOY_FLAGS  extra deploy.sh flags, space separated (default --tls)
#   DEPLOY_SHA    the commit being deployed (full sha). When the images gate kept this commit's images
#                 (smartsched-{backend,frontend,crbs}:ci-<DEPLOY_SHA>, images.sh) they are retagged to the compose tag
#                 and deploy.sh runs with --no-build (it still builds when any smartsched-* image is missing).
#   PUBLIC_HOST   the public host name (TLS_DOMAIN of .env when unset): https://<host>/api/v1/health is checked after
#                 the local check, report only (DNS / ACME / the edge are outside this commit)
set -euo pipefail
: "${DEPLOY_DIR:?}"
cd "$DEPLOY_DIR/smartsched/deploy"
read -r -a flags <<< "${DEPLOY_FLAGS:---tls}"
env_val() { grep -E "^$1=" .env 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '"'"'" || true; }
extra=()
sha="${DEPLOY_SHA:-}"
tag="$(env_val SMARTSCHED_TAG)"; tag="${tag:-0.1.0}"
api_url="$(env_val NEXT_PUBLIC_API_URL)"
reuse=0
if [[ "$sha" =~ ^[0-9a-f]{40}$ ]] && [[ -z "$(env_val BACKEND_EXTRA_PIP)" ]] \
   && [[ -z "$api_url" || "$api_url" == "http://backend:8000" ]]; then
  # the images gate builds with compose's default build args: reuse only when .env does not change them
  reuse=1
  for svc in backend frontend crbs; do
    docker image inspect "smartsched-${svc}:ci-${sha}" >/dev/null 2>&1 || reuse=0
    # an image built before the label fix carries smartsched-ci.run (its containers would look like CI containers)
    run_label="$(docker image inspect --format '{{index .Config.Labels "smartsched-ci.run"}}' \
      "smartsched-${svc}:ci-${sha}" 2>/dev/null || true)"
    [[ -z "$run_label" || "$run_label" == "<no value>" ]] || reuse=0
  done
fi
if [[ "$reuse" == 1 ]]; then
  echo "==== reusing the images gate's images for ${sha:0:12} (smartsched-*:ci-<sha> -> :${tag})"
  for svc in backend frontend crbs; do docker tag "smartsched-${svc}:ci-${sha}" "smartsched-${svc}:${tag}"; done
  extra+=(--no-build)
fi
echo "==== deploy.sh --update --no-pull ${extra[*]} ${flags[*]}"
./deploy.sh --update --no-pull ${extra[@]+"${extra[@]}"} "${flags[@]}"
files=(-f docker-compose.yml)
for f in "${flags[@]}"; do [[ "$f" == "--tls" ]] && files+=(-f docker-compose.caddy.yml); done
echo "==== restart proxy (picks up the re-rendered nginx config)"
docker compose --env-file .env "${files[@]}" restart proxy
port="$(env_val PROXY_PORT)"; port="${port:-8080}"
public_check() {
  local host="${PUBLIC_HOST:-$(env_val TLS_DOMAIN)}"
  [[ -n "$host" ]] || { echo "public check: no TLS_DOMAIN / PUBLIC_HOST; skipped"; return 0; }
  if curl -fsS --max-time 20 "https://${host}/api/v1/health" 2>&1 | grep -q '"db":true'; then
    echo "public check: https://${host}/api/v1/health healthy"
  else
    echo "public check: https://${host}/api/v1/health NOT healthy (report only; the local check passed)"
    proxy_logs
  fi
}
proxy_logs() {
  echo "==== proxy / caddy log (tail)"
  docker compose --env-file .env "${files[@]}" logs --no-color --tail 40 proxy 2>&1 || true
  [[ " ${files[*]} " == *caddy* ]] && { docker compose --env-file .env "${files[@]}" logs --no-color --tail 40 caddy 2>&1 || true; }
  return 0
}
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${port}/api/v1/health" | grep -q '"db":true'; then
    echo "healthy"
    public_check
    exit 0
  fi
  sleep 3
done
echo "not healthy after the deploy"; docker compose --env-file .env "${files[@]}" ps; proxy_logs; exit 1
