#!/usr/bin/env bash
# SmartSched one-click deployment.
#
#   ./deploy.sh            build + start the stack, wait for health, print URL + credentials location
#   ./deploy.sh --legacy   also start the legacy CRBS app (profile "legacy") for live imports
#   ./deploy.sh --tls      add the Caddy HTTPS edge (docker-compose.caddy.yml; TLS_DOMAIN + ACME_EMAIL in .env)
#   ./deploy.sh --update   git pull (if a checkout), rebuild images, restart, migrations run on start
#   ./deploy.sh --logs     follow logs
#   ./deploy.sh --down     stop the stack (volumes are kept; add --volumes to delete data)
#   ./deploy.sh --status   show container status + health
#   extra flags: --no-build (start existing images), --no-pull (--update without git pull)
#
# The backend runs migrations (alembic upgrade head) and seeds the admin user on every start; solver
# and import jobs run inside the backend process (no separate worker container).
#
# Secrets: on first run .env is created from .env.example and every "__GENERATE__" placeholder is
# replaced with a random value (openssl, falling back to python). .env is git-ignored.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$HERE/.env}"
COMPOSE_FILE="$HERE/docker-compose.yml"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

PROFILE_ARGS=()
FILE_ARGS=(-f "$COMPOSE_FILE")
ACTION="up"
REMOVE_VOLUMES=0
NO_BUILD=0
NO_PULL=0

log()  { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[deploy] warning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[deploy] error:\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; }

for arg in "$@"; do
  case "$arg" in
    --legacy)   PROFILE_ARGS=(--profile legacy) ;;
    --tls)      FILE_ARGS+=(-f "$HERE/docker-compose.caddy.yml") ;;
    --down)     ACTION="down" ;;
    --logs)     ACTION="logs" ;;
    --update)   ACTION="update" ;;
    --status)   ACTION="status" ;;
    --volumes)  REMOVE_VOLUMES=1 ;;
    --no-build) NO_BUILD=1 ;;
    --no-pull)  NO_PULL=1 ;;
    -h|--help)  usage; exit 0 ;;
    *) die "unknown flag: $arg (see --help)" ;;
  esac
done

# ---- prerequisites --------------------------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "docker is not installed (https://docs.docker.com/engine/install/)"
docker info >/dev/null 2>&1 || die "the Docker daemon is not reachable (is it running? are you in the docker group?)"
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  die "docker compose v2 is required (https://docs.docker.com/compose/install/)"
fi
COMPOSE_VERSION="$("${COMPOSE[@]}" version --short 2>/dev/null || echo 0)"
case "${COMPOSE_VERSION#v}" in
  1.*|2.[0-9].*|2.1[0-6].*) warn "docker compose $COMPOSE_VERSION is old; >= 2.17 is recommended" ;;
esac
# ${arr[@]+...} keeps `set -u` happy with an empty array on bash 3.2 (macOS).
COMPOSE+=(--env-file "$ENV_FILE" "${FILE_ARGS[@]}" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"})

# ---- .env with generated secrets ------------------------------------------------------------
random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    die "need openssl or python3 to generate secrets"
  fi
}

random_password() {
  # 20 chars, URL/shell safe (no quotes, no $), readable enough to type once.
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 30 | tr -dc 'A-Za-z0-9' | head -c 20; echo
  else
    python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("".join(secrets.choice(a) for _ in range(20)))'
  fi
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    log "creating $ENV_FILE from .env.example"
    cp "$HERE/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi
  local created=0 key value
  # One pass over KEY=__GENERATE__ lines only (comments may mention the placeholder too).
  for key in $(grep -oE '^[A-Z][A-Z0-9_]*=__GENERATE__[[:space:]]*$' "$ENV_FILE" | cut -d= -f1); do
    case "$key" in
      ADMIN_PASSWORD|*_DB_PASSWORD|POSTGRES_PASSWORD|CRBS_DB_ROOT_PASSWORD) value="$(random_password)" ;;
      *) value="$(random_secret)" ;;
    esac
    [[ -n "$value" ]] || die "could not generate a value for $key"
    sed -i.bak "s|^${key}=__GENERATE__[[:space:]]*$|${key}=${value}|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    created=1
  done
  if grep -Eq '^[A-Z][A-Z0-9_]*=.*__GENERATE__' "$ENV_FILE"; then
    die "unreplaced __GENERATE__ placeholder in $ENV_FILE: $(grep -E '^[A-Z][A-Z0-9_]*=.*__GENERATE__' "$ENV_FILE" | cut -d= -f1 | tr '\n' ' ')"
  fi
  if [[ $created -eq 1 ]]; then log "generated secrets written to $ENV_FILE (keep it safe; it is git-ignored)"; fi
  # Required keys must be present and non-empty.
  local k
  for k in APP_SECRET JWT_SECRET AUTH_SECRET POSTGRES_PASSWORD ADMIN_EMAIL ADMIN_PASSWORD; do
    grep -Eq "^${k}=.+" "$ENV_FILE" || die "$k is empty in $ENV_FILE"
  done
}

env_get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//'; }

# ---- health wait -----------------------------------------------------------------------------
http_ok() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then curl -fsS --max-time 5 -o /dev/null "$url"
  elif command -v wget >/dev/null 2>&1; then wget -q -O /dev/null --timeout=5 "$url"
  else python3 -c "import sys,urllib.request; urllib.request.urlopen('$url', timeout=5)" 2>/dev/null
  fi
}

wait_healthy() {
  local url="$1" timeout="${2:-300}" start now
  start=$(date +%s)
  log "waiting for $url (timeout ${timeout}s) ..."
  while true; do
    if http_ok "$url"; then log "healthy: $url"; return 0; fi
    now=$(date +%s)
    if (( now - start > timeout )); then
      warn "not healthy after ${timeout}s; last container status:"
      "${COMPOSE[@]}" ps
      return 1
    fi
    sleep 3
  done
}

print_summary() {
  local port url
  port="$(env_get PROXY_PORT)"; port="${port:-8080}"
  url="$(env_get PUBLIC_URL)"
  if [[ -z "$url" && ${#FILE_ARGS[@]} -gt 2 ]]; then url="https://$(env_get TLS_DOMAIN)"; fi
  url="${url:-http://localhost:$port}"
  echo
  log "SmartSched is up:  $url"
  log "API docs:          $url/api/docs"
  log "Admin login:       $(env_get ADMIN_EMAIL)  (password: ADMIN_PASSWORD in $ENV_FILE)"
  log "                   seeded on the first start only; later changes to .env do not reset it"
  if [[ ${#PROFILE_ARGS[@]} -gt 0 ]]; then
    log "Legacy CRBS:       http://localhost:$(env_get CRBS_PORT)  (first visit runs the CRBS installer; DB host crbs-db)"
    log "CRBS import DSN:   mysql://$(env_get CRBS_DB_USER):<CRBS_DB_PASSWORD>@crbs-db:3306/$(env_get CRBS_DB_NAME)  (needs BACKEND_EXTRA_PIP=pymysql)"
  fi
  log "Logs: ./deploy.sh --logs   Stop: ./deploy.sh --down   Update: ./deploy.sh --update"
}

# ---- actions ---------------------------------------------------------------------------------
case "$ACTION" in
  down)
    [[ -f "$ENV_FILE" ]] || die "no $ENV_FILE; nothing to stop"
    if [[ $REMOVE_VOLUMES -eq 1 ]]; then
      warn "removing volumes: ALL DATA (Postgres, uploads, legacy MySQL) will be deleted"
      if [[ "${FORCE:-0}" != "1" ]]; then
        read -r -p "type 'delete' to confirm (or run with FORCE=1): " answer
        [[ "$answer" == "delete" ]] || die "aborted"
      fi
      "${COMPOSE[@]}" --profile legacy down --volumes --remove-orphans
    else
      "${COMPOSE[@]}" --profile legacy down --remove-orphans
    fi
    ;;
  logs)
    exec "${COMPOSE[@]}" logs -f --tail=200
    ;;
  status)
    "${COMPOSE[@]}" ps
    ;;
  update)
    ensure_env
    if [[ -d "$REPO_ROOT/.git" ]] && command -v git >/dev/null 2>&1 && [[ $NO_PULL -eq 0 ]]; then
      log "git pull --ff-only"
      git -C "$REPO_ROOT" pull --ff-only || warn "git pull failed; continuing with the current checkout"
    fi
    log "pulling base images"
    "${COMPOSE[@]}" pull --ignore-buildable || true
    log "rebuilding images"
    "${COMPOSE[@]}" build --pull
    log "restarting (migrations run in the backend entrypoint)"
    "${COMPOSE[@]}" up -d --remove-orphans
    wait_healthy "http://localhost:$(env_get PROXY_PORT)/api/v1/health"
    docker image prune -f >/dev/null 2>&1 || true
    print_summary
    ;;
  up)
    ensure_env
    if [[ ${#FILE_ARGS[@]} -gt 2 ]]; then
      [[ -n "$(env_get TLS_DOMAIN)" && -n "$(env_get ACME_EMAIL)" ]] || die "--tls needs TLS_DOMAIN and ACME_EMAIL in $ENV_FILE"
    fi
    if [[ $NO_BUILD -eq 0 ]]; then
      log "building images (first build takes a few minutes)"
      "${COMPOSE[@]}" build
    fi
    log "starting"
    "${COMPOSE[@]}" up -d --remove-orphans
    wait_healthy "http://localhost:$(env_get PROXY_PORT)/api/v1/health"
    print_summary
    ;;
esac
