#!/usr/bin/env bash
# SmartSched one-click deployment.
#
#   ./deploy.sh            build + start the stack, wait for health, print URL + credentials location
#   ./deploy.sh --legacy   also start the legacy CRBS app (profile "legacy") for live imports
#   ./deploy.sh --tls      add the Caddy HTTPS edge (docker-compose.caddy.yml; TLS_DOMAIN + ACME_EMAIL in .env). On by
#                          itself once TLS_DOMAIN and ACME_EMAIL are set (--domain writes them); --no-tls skips it
#   ./deploy.sh --observability     also start Prometheus, Loki, Alloy and Grafana (profile "observability", /grafana/
#                          for admins, ~0.5 GB RSS, capped at 768 MiB; observability/README.md). OBSERVABILITY=1|0 in .env
#                          makes it the default (written on the first run: OBSERVABILITY from the environment, else 1
#                          when the host has >= 7 GiB of memory); --no-observability skips it for one run
#   ./deploy.sh --update   git pull (if a checkout), rebuild images, restart, migrations run on start
#   ./deploy.sh --logs     follow logs
#   ./deploy.sh --down     stop the stack (volumes are kept; add --volumes to delete data)
#   ./deploy.sh --status   show container status + health
#   ./deploy.sh --backups  also install the nightly backup (backup.sh, 02:30) as /etc/cron.d/smartsched-backup (root;
#                          otherwise the line to install is printed). The AWS pod has a systemd timer instead.
#   extra flags: --no-build (start existing images; with --update: skip the rebuild when every smartsched-* image is
#                present, e.g. retagged from the pod CI images gate), --no-pull (--update without git pull)
#   ./deploy.sh --prepare  build/pull the images only: no `up`, no traffic, nothing started (pod first boot)
#
# Deploy-time values (each flag also works as --flag=value; docs/deploy/ONE-CLICK.md):
#   --admin-email ADDR     the first administrator (env ADMIN_EMAIL; first start only, asked on a terminal if missing)
#   --domain HOST          public DNS name: writes TLS_DOMAIN, PUBLIC_URL, CORS_ORIGINS and ACME_EMAIL (default: the
#                          admin e-mail; --acme-email ADDR) into .env and turns the HTTPS edge on
#   --profile NAME         seed profile for this run: empty | institution (default: profile.env)
#   --observability        see above (env OBSERVABILITY=1 on the first run does the same, permanently)
# Settings written ONCE into the database through the admin panel's own validation (seed/bootstrap_settings.py);
# a later deploy never overwrites what an administrator changed in the panel (BOOTSTRAP_FORCE=1 does):
#   --org-name TEXT        institution name                        (env ORG_NAME)
#   --ai-provider ID       anthropic (default), openai, gemini, ... (env AI_PROVIDER; the key: env AI_API_KEY,
#                          a base URL for an OpenAI-compatible server: --ai-base-url / AI_BASE_URL)
#   --smtp-host HOST, --smtp-port N, --smtp-security starttls|ssl|none, --smtp-user NAME, --smtp-from ADDR
#                          outgoing mail (env SMTP_HOST, SMTP_PORT, SMTP_SECURITY, SMTP_USERNAME, SMTP_FROM,
#                          SMTP_FROM_NAME; the password: env SMTP_PASSWORD)
#   --security-contact ADDR  the security.txt contact            (env SECURITY_CONTACT)
#   calendar OAuth clients: env GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET, MICROSOFT_CLIENT_ID +
#                          MICROSOFT_CLIENT_SECRET (+ MICROSOFT_TENANT)
# Secrets (AI_API_KEY, SMTP_PASSWORD, *_CLIENT_SECRET) are taken from the environment only, never from a flag (no
# shell history, no process list), are passed to the container by name, stored encrypted and never written to .env.
#
# The backend runs migrations (alembic upgrade head) and seeds the admin user on every start; solver
# and import jobs run inside the backend process (no separate worker container).
#
# Seed profile (profile.env, SEED_PROFILE; missing = empty): after the stack is healthy, `institution` imports the
# owner's files once (seed/seed.py: workbooks + room master from smartsched/backend/tests/fixtures, mounted
# read-only; their preference rules; learning extraction). A settings row records the finished steps, so later
# deploys and --update skip them. `empty` loads nothing (setup wizard + /onboarding). SEED_PROFILE=... in the
# environment (or --profile) overrides the file for one run.
#
# Secrets: on first run .env is created from .env.example and every "__GENERATE__" placeholder is
# replaced with a random value (openssl, falling back to python). .env is git-ignored.
# ADMIN_EMAIL has no default: set it in .env or pass it on the first run (--admin-email you@uni.edu.tr).
# The admin must change the generated password at the first login (ENVIRONMENT=prod). On a terminal the first run
# prints it once (SHOW_ADMIN_PASSWORD=0 never, =1 always on the first run); it stays in .env as ADMIN_PASSWORD.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$HERE/.env}"
COMPOSE_FILE="$HERE/docker-compose.yml"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
PROFILE_FILE="${PROFILE_FILE:-$HERE/profile.env}"
SEED_FILES_DIR="${SEED_FILES_DIR:-$REPO_ROOT/smartsched/backend/tests/fixtures}"

PROFILE_ARGS=()
OBS_FLAG=""
TLS_FLAG=""
FILE_ARGS=(-f "$COMPOSE_FILE")
ACTION="up"
REMOVE_VOLUMES=0
NO_BUILD=0
NO_PULL=0
DOMAIN=""
ENV_CREATED=0
BACKUPS=0
# every variable seed/bootstrap_settings.py reads (pod-ci/tests/test_deploy_oneclick.py keeps the lists equal)
SETTINGS_KEYS=(ORG_NAME AI_PROVIDER AI_API_KEY AI_BASE_URL SMTP_HOST SMTP_PORT SMTP_SECURITY SMTP_USERNAME SMTP_PASSWORD SMTP_FROM SMTP_FROM_NAME SECURITY_CONTACT GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET MICROSOFT_CLIENT_ID MICROSOFT_CLIENT_SECRET MICROSOFT_TENANT)

# true when an image the stack builds itself (smartsched-*) is not present locally (`config --images`: every service
# of the active files and profiles)
missing_local_images() {
  local img out=1
  while IFS= read -r img; do
    [[ "$img" == smartsched-* ]] || continue
    docker image inspect "$img" >/dev/null 2>&1 || { echo "missing image $img" >&2; out=0; }
  done < <("${COMPOSE[@]}" config --images 2>/dev/null)
  return $out
}

log()  { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[deploy] warning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[deploy] error:\033[0m %s\n' "$*" >&2; exit 1; }

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; }

# flags with a value: --flag value or --flag=value
VALUE_FLAGS=" --domain --acme-email --admin-email --profile --org-name --ai-provider --ai-base-url --smtp-host --smtp-port --smtp-security --smtp-user --smtp-from --smtp-from-name --security-contact "
while [[ $# -gt 0 ]]; do
  arg="$1"; shift
  value=""
  if [[ "$arg" == --*=* ]]; then
    value="${arg#*=}"; arg="${arg%%=*}"
    [[ "$VALUE_FLAGS" == *" $arg "* ]] || die "$arg takes no value (see --help)"
  elif [[ "$VALUE_FLAGS" == *" $arg "* ]]; then
    [[ $# -gt 0 ]] || die "$arg needs a value (see --help)"
    value="$1"; shift
  fi
  case "$arg" in
    --legacy)   PROFILE_ARGS+=(--profile legacy) ;;
    --observability)    OBS_FLAG=1 ;;
    --no-observability) OBS_FLAG=0 ;;
    --tls)      TLS_FLAG=1 ;;
    --no-tls)   TLS_FLAG=0 ;;
    --down)     ACTION="down" ;;
    --logs)     ACTION="logs" ;;
    --update)   ACTION="update" ;;
    --prepare)  ACTION="prepare" ;;
    --status)   ACTION="status" ;;
    --volumes)  REMOVE_VOLUMES=1 ;;
    --no-build) NO_BUILD=1 ;;
    --no-pull)  NO_PULL=1 ;;
    --backups)  BACKUPS=1 ;;
    --domain)   DOMAIN="$value" ;;
    --acme-email)  export ACME_EMAIL_FLAG="$value" ;;
    --admin-email) export ADMIN_EMAIL="$value" ;;
    --profile)  export SEED_PROFILE="$value" ;;
    --org-name) export ORG_NAME="$value" ;;
    --ai-provider) export AI_PROVIDER="$value" ;;
    --ai-base-url) export AI_BASE_URL="$value" ;;
    --smtp-host) export SMTP_HOST="$value" ;;
    --smtp-port) export SMTP_PORT="$value" ;;
    --smtp-security) export SMTP_SECURITY="$value" ;;
    --smtp-user) export SMTP_USERNAME="$value" ;;
    --smtp-from) export SMTP_FROM="$value" ;;
    --smtp-from-name) export SMTP_FROM_NAME="$value" ;;
    --security-contact) export SECURITY_CONTACT="$value" ;;
    --ai-key|--ai-api-key|--smtp-password|--*-client-secret)
      die "$arg: secrets are read from the environment only (AI_API_KEY=... / SMTP_PASSWORD=... ./deploy.sh), never from a flag" ;;
    -h|--help)  usage; exit 0 ;;
    *) die "unknown flag: $arg (see --help)" ;;
  esac
done
if [[ -n "$DOMAIN" ]]; then
  [[ "$DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ && "$DOMAIN" == *.* ]] \
    || die "--domain '$DOMAIN' is not a host name (e.g. smartsched.university.edu.tr, no https://)"
  [[ -n "$TLS_FLAG" ]] || TLS_FLAG=1
fi

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
COMPOSE_BASE=("${COMPOSE[@]}")
OBS_ON=0
TLS_ON=0
# the compose command: base files, the Caddy edge when TLS is on, the profiles
build_compose() {
  FILE_ARGS=(-f "$COMPOSE_FILE")
  [[ $TLS_ON == 1 ]] && FILE_ARGS+=(-f "$HERE/docker-compose.caddy.yml")
  COMPOSE=("${COMPOSE_BASE[@]}" --env-file "$ENV_FILE" "${FILE_ARGS[@]}" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"})
  [[ $OBS_ON == 1 ]] && COMPOSE+=(--profile observability)
  return 0
}
build_compose

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
  # 20 chars, URL/shell safe (no quotes, no $), readable enough to type once. 48 random bytes give 64
  # base64 characters, so 20 alphanumerics remain after dropping + / = (the backend needs >= 12 in prod).
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 20; echo
  else
    python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("".join(secrets.choice(a) for _ in range(20)))'
  fi
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    log "creating $ENV_FILE from .env.example"
    cp "$HERE/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ENV_CREATED=1
  fi
  local created=0 key value
  # One pass over KEY=__GENERATE__ lines only (comments may mention the placeholder too).
  for key in $(grep -oE '^[A-Z][A-Z0-9_]*=__GENERATE__[[:space:]]*$' "$ENV_FILE" | cut -d= -f1); do
    case "$key" in
      ADMIN_PASSWORD|*_DB_PASSWORD|POSTGRES_PASSWORD|CRBS_DB_ROOT_PASSWORD|GRAFANA_ADMIN_PASSWORD) value="$(random_password)" ;;
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
  # keys added after this .env was created (observability profile, W3-OPS)
  if ! grep -Eq '^GRAFANA_ADMIN_PASSWORD=' "$ENV_FILE"; then
    printf 'GRAFANA_ADMIN_PASSWORD=%s\n' "$(random_password)" >> "$ENV_FILE"
    log "GRAFANA_ADMIN_PASSWORD generated in $ENV_FILE"
  fi
  if ! grep -Eq '^OBSERVABILITY=' "$ENV_FILE"; then
    local mem_kb=0
    [[ -r /proc/meminfo ]] && mem_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    local obs_default=0
    (( mem_kb >= 7 * 1024 * 1024 )) && obs_default=1
    case "${OBSERVABILITY:-}" in 0|1) obs_default="$OBSERVABILITY" ;; "") ;; *) die "OBSERVABILITY=$OBSERVABILITY: expected 0 or 1" ;; esac
    printf '# observability profile by default (deploy.sh --observability / --no-observability override one run)\nOBSERVABILITY=%s\n' "$obs_default" >> "$ENV_FILE"
    log "OBSERVABILITY=$obs_default written to $ENV_FILE (host memory $((mem_kb / 1024)) MiB)"
    # with the profile on, the stock backend cap (4g) gives way to the profile's 768 MiB: limits stay <= 7.75 GB on
    # an 8 GB host (observability/README.md "Memory budget"). Only the stock value is changed, once; edit it back
    # in .env to override.
    if [[ $obs_default == 1 && "$(env_get BACKEND_MEMORY)" == 4g ]]; then
      sed -i.bak "s|^BACKEND_MEMORY=4g[[:space:]]*$|BACKEND_MEMORY=3500m|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
      log "BACKEND_MEMORY=3500m written to $ENV_FILE (observability profile on; set it back to 4g to override)"
    fi
  fi
  # ADMIN_EMAIL has no default (no-placeholder audit m1): take it from the environment / --admin-email on the first
  # run, or ask once on a terminal.
  if [[ -z "$(env_get ADMIN_EMAIL)" && -z "${ADMIN_EMAIL:-}" && -t 0 && -t 1 ]]; then
    read -r -p "Administrator e-mail (the first login): " ADMIN_EMAIL || true
  fi
  if [[ -n "$(env_get ADMIN_EMAIL)" && -n "${ADMIN_EMAIL:-}" && "$(env_get ADMIN_EMAIL)" != "$ADMIN_EMAIL" ]]; then
    warn "ADMIN_EMAIL is used on the first start only; keeping $(env_get ADMIN_EMAIL). Add or rename administrators in Kurulum > Kullanıcılar (/admin/users)"
  fi
  if [[ -z "$(env_get ADMIN_EMAIL)" && -n "${ADMIN_EMAIL:-}" ]]; then
    [[ "$ADMIN_EMAIL" =~ ^[^[:space:]\|\\\&]+@[^[:space:]\|\\\&]+$ ]] || die "ADMIN_EMAIL='$ADMIN_EMAIL' is not an e-mail address"
    if grep -Eq '^ADMIN_EMAIL=' "$ENV_FILE"; then
      sed -i.bak "s|^ADMIN_EMAIL=.*$|ADMIN_EMAIL=${ADMIN_EMAIL}|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    else
      printf 'ADMIN_EMAIL=%s\n' "$ADMIN_EMAIL" >> "$ENV_FILE"
    fi
    log "ADMIN_EMAIL=$ADMIN_EMAIL written to $ENV_FILE"
  fi
  # Required keys must be present and non-empty.
  local k hint
  for k in APP_SECRET JWT_SECRET POSTGRES_PASSWORD ADMIN_EMAIL ADMIN_PASSWORD; do
    hint=""
    [[ $k == ADMIN_EMAIL ]] && hint=" (set the real administrator address, or run ADMIN_EMAIL=you@university.edu.tr ./deploy.sh)"
    [[ -n "$(env_get "$k")" ]] || die "$k is empty in $ENV_FILE$hint"
  done
  local email
  email="$(env_get ADMIN_EMAIL)"
  if [[ "$(printf '%s' "$email" | tr '[:upper:]' '[:lower:]')" == *example.* ]]; then
    die "ADMIN_EMAIL=$email is an example address; set the real administrator address in $ENV_FILE"
  fi
  # --domain: the public name, written into .env (infrastructure, not a database setting: later runs keep it)
  if [[ -n "$DOMAIN" ]]; then
    local acme="${ACME_EMAIL_FLAG:-$(env_get ACME_EMAIL)}"
    acme="${acme:-$email}"
    [[ "$acme" =~ ^[^[:space:]\|\\\&]+@[^[:space:]\|\\\&]+$ ]] || die "--acme-email '$acme' is not an e-mail address"
    env_set TLS_DOMAIN "$DOMAIN"
    env_set PUBLIC_URL "https://$DOMAIN"
    env_set CORS_ORIGINS "[\"https://$DOMAIN\"]"
    env_set ACME_EMAIL "$acme"
    log "domain $DOMAIN written to $ENV_FILE (TLS_DOMAIN, PUBLIC_URL, CORS_ORIGINS, ACME_EMAIL=$acme)"
  fi
}

# KEY=value into .env (replace the first KEY= line or append); values are checked by the callers (no | & \\)
env_set() {
  if grep -Eq "^$1=" "$ENV_FILE"; then
    sed -i.bak "s|^$1=.*$|$1=$2|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
  fi
}

# the Caddy HTTPS edge: --tls / --no-tls, else on when .env names a domain and an ACME e-mail
apply_tls() {
  local want="$TLS_FLAG"
  if [[ -z "$want" && -n "$(env_get TLS_DOMAIN)" && -n "$(env_get ACME_EMAIL)" ]]; then want=1; fi
  if [[ "$want" == 1 ]]; then
    [[ -n "$(env_get TLS_DOMAIN)" && -n "$(env_get ACME_EMAIL)" ]] || die "--tls needs TLS_DOMAIN and ACME_EMAIL in $ENV_FILE (or --domain)"
    TLS_ON=1
  fi
  build_compose
}

# profile "observability": --observability / --no-observability, else OBSERVABILITY in .env
apply_observability() {
  local want="${OBS_FLAG:-$(env_get OBSERVABILITY)}"
  if [[ "$want" == 1 ]]; then
    OBS_ON=1
    build_compose
    log "observability profile on (Prometheus, Loki, Alloy, Grafana at /grafana/)"
  fi
  # the deployed commit for the operations panel (/admin/ops) and the error events' release
  if [[ -z "${RELEASE_SHA:-}" ]] && command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse HEAD >/dev/null 2>&1; then
    RELEASE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  fi
  export RELEASE_SHA="${RELEASE_SHA:-}"
  DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  export DEPLOYED_AT
  # Alloy mounts the backup textfile directory (observability/README.md "Backups"); create it when we can
  [[ ${OBS_ON:-0} == 1 ]] && { mkdir -p /var/lib/smartsched/textfile 2>/dev/null || true; }
  return 0
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

# ---- seed profile ----------------------------------------------------------------------------
seed_profile() {
  local v=""
  [[ -f "$PROFILE_FILE" ]] && v="$(grep -E '^[[:space:]]*(export[[:space:]]+)?SEED_PROFILE=' "$PROFILE_FILE" | tail -n 1 \
    | cut -d= -f2- | sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//' | tr -d "\"'")"
  v="${SEED_PROFILE:-${v:-empty}}"
  case "$v" in empty|institution) printf '%s\n' "$v" ;; *) die "SEED_PROFILE=$v in $PROFILE_FILE: expected empty or institution" ;; esac
}

run_seed() {
  local profile
  profile="$(seed_profile)"
  if [[ "$profile" == empty ]]; then
    log "seed profile: empty (nothing loaded; the administrator starts at /admin/welcome and /onboarding)"
    return 0
  fi
  [[ -d "$SEED_FILES_DIR" ]] || die "seed profile $profile needs the seed files in $SEED_FILES_DIR"
  log "seed profile: $profile (owner files, once; finished steps are recorded in the database)"
  # same image + DATABASE_URL as the running backend; the entrypoint skips migrations/admin (already done)
  "${COMPOSE[@]}" run --rm --no-deps -T -e RUN_MIGRATIONS=0 -e SEED_ADMIN=0 -e SEED_PROFILE="$profile" \
    -e SEED_FORCE="${SEED_FORCE:-0}" -v "$SEED_FILES_DIR:/seed/files:ro" -v "$HERE/seed:/seed/tool:ro" \
    backend python /seed/tool/seed.py run \
    || die "seeding ($profile) failed; finished steps are kept, rerun ./deploy.sh --no-build to resume"
}

# ---- deploy-time settings (seed/bootstrap_settings.py) --------------------------------------------------------
settings_given() {
  local k
  for k in "${SETTINGS_KEYS[@]}"; do [[ -n "${!k:-}" ]] && return 0; done
  return 1
}

# before any build: refuse bad values early and show what will be written (secrets as <set>)
plan_settings() {
  settings_given || return 0
  local k
  for k in "${SETTINGS_KEYS[@]}"; do [[ -n "${!k:-}" ]] && export "${k?}"; done
  if command -v python3 >/dev/null 2>&1; then
    python3 "$HERE/seed/bootstrap_settings.py" plan || die "deploy-time settings refused (nothing was built or changed)"
  fi
}

run_settings() {
  settings_given || return 0
  local k args=()
  for k in "${SETTINGS_KEYS[@]}"; do
    # by name only: the value travels in the environment, never on a command line
    if [[ -n "${!k:-}" ]]; then export "${k?}"; args+=(-e "$k"); fi
  done
  log "deploy-time settings: written once into the database (the admin panel wins on later deploys)"
  local rc=0
  "${COMPOSE[@]}" run --rm --no-deps -T -e RUN_MIGRATIONS=0 -e SEED_ADMIN=0 -e BOOTSTRAP_FORCE="${BOOTSTRAP_FORCE:-0}" \
    "${args[@]}" -v "$HERE/seed:/seed/tool:ro" backend python /seed/tool/bootstrap_settings.py run || rc=$?
  case $rc in
    0) ;;
    3) warn "some deploy-time settings were refused (above); set them in the admin panel or fix them and redeploy" ;;
    *) warn "deploy-time settings were not written (exit $rc); set them in the admin panel or redeploy" ;;
  esac
  return 0
}

# ---- nightly backup (--backups) -------------------------------------------------------------------------------
install_backups() {
  [[ $BACKUPS == 1 ]] || return 0
  local file="${BACKUP_CRON_FILE:-/etc/cron.d/smartsched-backup}"
  local line="30 2 * * * root ENV_FILE=$ENV_FILE $HERE/backup.sh >> /var/log/smartsched-backup.log 2>&1"
  if { printf '# SmartSched nightly backup (deploy.sh --backups; backup.sh header)\n%s\n' "$line" > "$file"; } 2>/dev/null; then
    chmod 644 "$file" 2>/dev/null || true
    log "nightly backup installed: $file (02:30, ${BACKUP_DIR:-/var/backups/smartsched}, 14 days)"
  else
    warn "cannot write $file (not root); install the nightly backup with:"
    warn "  echo '$line' | sudo tee $file"
  fi
}

print_summary() {
  local port url
  port="$(env_get PROXY_PORT)"; port="${port:-8080}"
  url="$(env_get PUBLIC_URL)"
  if [[ -z "$url" && $TLS_ON == 1 ]]; then url="https://$(env_get TLS_DOMAIN)"; fi
  url="${url:-http://localhost:$port}"
  echo
  log "SmartSched is up:  $url"
  log "Admin login:       $(env_get ADMIN_EMAIL)  (password: ADMIN_PASSWORD in $ENV_FILE)"
  local show="${SHOW_ADMIN_PASSWORD:-}"
  if [[ -z "$show" && -t 1 ]]; then show=1; fi
  if [[ $ENV_CREATED == 1 && "$show" == 1 ]]; then
    log "Admin password:    $(env_get ADMIN_PASSWORD)  (shown once; you must change it at the first login)"
  fi
  log "                   seeded on the first start only (change it at the first login); later .env changes do not reset it"
  if [[ ${#PROFILE_ARGS[@]} -gt 0 ]]; then
    log "Legacy CRBS:       http://localhost:$(env_get CRBS_PORT)  (first visit runs the CRBS installer; DB host crbs-db)"
    log "CRBS import DSN:   mysql://$(env_get CRBS_DB_USER):<CRBS_DB_PASSWORD>@crbs-db:3306/$(env_get CRBS_DB_NAME)  (needs BACKEND_EXTRA_PIP=pymysql)"
  fi
  log "Seed profile:      $(seed_profile)  ($PROFILE_FILE)"
  if [[ ${OBS_ON:-0} == 1 ]]; then
    log "Observability:     ${url%/}/grafana/ (admins only)  ·  panel: ${url%/}/admin/ops"
  fi
  log "Logs: ./deploy.sh --logs   Stop: ./deploy.sh --down   Update: ./deploy.sh --update"
}

# ---- actions ---------------------------------------------------------------------------------
case "$ACTION" in
  down)
    [[ -f "$ENV_FILE" ]] || die "no $ENV_FILE; nothing to stop"
    apply_tls
    if [[ $REMOVE_VOLUMES -eq 1 ]]; then
      warn "removing volumes: ALL DATA (Postgres, uploads, legacy MySQL) will be deleted"
      if [[ "${FORCE:-0}" != "1" ]]; then
        read -r -p "type 'delete' to confirm (or run with FORCE=1): " answer
        [[ "$answer" == "delete" ]] || die "aborted"
      fi
      "${COMPOSE[@]}" --profile legacy --profile observability down --volumes --remove-orphans
    else
      "${COMPOSE[@]}" --profile legacy --profile observability down --remove-orphans
    fi
    ;;
  logs)
    [[ -f "$ENV_FILE" ]] && apply_tls
    exec "${COMPOSE[@]}" logs -f --tail=200
    ;;
  status)
    [[ -f "$ENV_FILE" ]] && apply_tls
    "${COMPOSE[@]}" ps
    ;;
  update)
    seed_profile >/dev/null
    plan_settings
    ensure_env
    apply_tls
    apply_observability
    if [[ -d "$REPO_ROOT/.git" ]] && command -v git >/dev/null 2>&1 && [[ $NO_PULL -eq 0 ]]; then
      log "git pull --ff-only"
      git -C "$REPO_ROOT" pull --ff-only || warn "git pull failed; continuing with the current checkout"
    fi
    log "pulling base images"
    "${COMPOSE[@]}" pull --ignore-buildable || true
    if [[ $NO_BUILD -eq 1 ]] && ! missing_local_images; then
      # pod CI: the images gate built this commit's images and gates/deploy.sh retagged them
      log "--no-build: every local image is present; not rebuilding"
    else
      [[ $NO_BUILD -eq 1 ]] && warn "--no-build: a local image is missing; building after all"
      log "rebuilding images"
      "${COMPOSE[@]}" build --pull
    fi
    log "restarting (migrations run in the backend entrypoint)"
    "${COMPOSE[@]}" up -d --remove-orphans
    wait_healthy "http://localhost:$(env_get PROXY_PORT)/api/v1/health"
    run_seed
    run_settings
    install_backups
    docker image prune -f >/dev/null 2>&1 || true
    print_summary
    ;;
  prepare)
    # first boot of the pod: images only. Nothing is started and nothing serves traffic: the first deploy is pod CI's
    # first green run (gates, then deploy.sh --update)
    ensure_env
    apply_tls
    apply_observability
    log "pulling base images"
    "${COMPOSE[@]}" pull --ignore-buildable || true
    log "building images (no containers are started)"
    "${COMPOSE[@]}" build
    ;;
  up)
    seed_profile >/dev/null
    plan_settings
    ensure_env
    apply_tls
    apply_observability
    if [[ $NO_BUILD -eq 0 ]]; then
      log "building images (first build takes a few minutes)"
      "${COMPOSE[@]}" build
    fi
    log "starting"
    "${COMPOSE[@]}" up -d --remove-orphans
    wait_healthy "http://localhost:$(env_get PROXY_PORT)/api/v1/health"
    run_seed
    run_settings
    install_backups
    print_summary
    ;;
esac
