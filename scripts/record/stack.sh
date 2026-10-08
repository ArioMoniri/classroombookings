#!/usr/bin/env bash
# Start an isolated SmartSched stack for demo recordings: FastAPI on SQLite with the real fixture
# workbooks, and a production build of the frontend in real mode (NEXT_PUBLIC_API_MOCK=0).
#
#   scripts/record/stack.sh up [--fresh]   start backend + frontend in the background, wait until ready
#   scripts/record/stack.sh down           stop both
#   scripts/record/stack.sh status         print URLs, PIDs and the database in use
#
# --fresh   empty database (admin only) for the "import planning files" journey; the default imports
#           the Bahar weekly grid + planning list exactly like docs/testing/2026-10-08-real-backend-e2e.md.
#
# Nothing is written inside the repository: the database, uploads, logs and a copy of the frontend
# (built with its own .next, so a build here never clobbers another agent's dev server) live under
# $REC_WORKDIR (default: ${TMPDIR:-/tmp}/smartsched-rec). node_modules is symlinked, not copied.
#
# Env: REC_WORKDIR, REC_API_PORT (8200), REC_WEB_PORT (3500), REC_EMAIL / REC_PASSWORD (seeded admin,
#      default admin@smartsched.local / Admin-2026!), REC_TERM_CODE (2026-BAHAR), PYTHON (python3),
#      REC_TEACHER_EMAIL / REC_TEACHER_PASSWORD (teacher created for the booking journey),
#      REC_SKIP_BUILD=1 (reuse the previous frontend build).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/smartsched/backend"
FRONTEND="$ROOT/smartsched/frontend"
WORK="${REC_WORKDIR:-${TMPDIR:-/tmp}/smartsched-rec}"
API_PORT="${REC_API_PORT:-8200}"
WEB_PORT="${REC_WEB_PORT:-3500}"
EMAIL="${REC_EMAIL:-admin@smartsched.local}"
PASSWORD="${REC_PASSWORD:-Admin-2026!}"
TERM_CODE="${REC_TERM_CODE:-2026-BAHAR}"
PYTHON="${PYTHON:-python3}"
[[ -x "$BACKEND/.venv/bin/python" && "$PYTHON" == python3 ]] && PYTHON="$BACKEND/.venv/bin/python"

log() { printf '\033[1;36m[rec-stack]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[rec-stack] error:\033[0m %s\n' "$*" >&2; exit 1; }

wait_http() { # url, seconds
  local url="$1" n="${2:-120}"
  for _ in $(seq "$n"); do curl -fsS -o /dev/null "$url" 2>/dev/null && return 0; sleep 1; done
  return 1
}

backend_env() {
  export ENVIRONMENT=dev
  export DATABASE_URL="sqlite+aiosqlite:///$WORK/rec.db"
  export ADMIN_EMAIL="$EMAIL" ADMIN_PASSWORD="$PASSWORD"
  export APP_SECRET="${REC_APP_SECRET:-recording-only-secret-recording-only-secret}"
  export UPLOAD_DIR="$WORK/uploads"
  export CORS_ORIGINS="[\"http://127.0.0.1:$WEB_PORT\",\"http://localhost:$WEB_PORT\"]"
}

# Through the public API: the term (fresh mode: the import journey picks it in the wizard) and a
# teacher account for the booking journey (REC_TEACHER_EMAIL / REC_TEACHER_PASSWORD).
seed_via_api() {
  local api="http://127.0.0.1:$API_PORT/api/v1" token
  token="$(curl -fsS -X POST "$api/auth/login" -H 'content-type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')" \
    || die "admin login failed"
  if [[ "$1" == 1 ]]; then
    curl -fsS -o /dev/null -X POST "$api/terms" -H "Authorization: Bearer $token" -H 'content-type: application/json' \
      -d "{\"code\":\"$TERM_CODE\",\"name\":\"2026 Bahar\",\"is_active\":true,\"week_count\":19}" \
      && log "created empty term $TERM_CODE" || log "term $TERM_CODE not created (exists?)"
  fi
  curl -fsS -o /dev/null -X POST "$api/users" -H "Authorization: Bearer $token" -H 'content-type: application/json' \
    -d "{\"email\":\"${REC_TEACHER_EMAIL:-ogretmen@smartsched.local}\",\"full_name\":\"Ayşe Öğretmen\",\"role\":\"TEACHER\",\"password\":\"${REC_TEACHER_PASSWORD:-Teacher-2026!}\"}" \
    && log "teacher ${REC_TEACHER_EMAIL:-ogretmen@smartsched.local} ready" || log "teacher not created (exists, or the TEACHER role is not available yet)"
}

cmd_down() {
  for name in backend frontend; do
    if [[ -f "$WORK/$name.pid" ]]; then
      local pid; pid="$(cat "$WORK/$name.pid")"
      kill -TERM -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
      rm -f "$WORK/$name.pid"
      log "stopped $name"
    fi
  done
  # fallback: anything still listening on our ports (e.g. a crashed previous run)
  fuser -k -TERM "$API_PORT/tcp" "$WEB_PORT/tcp" >/dev/null 2>&1 || true
}

cmd_status() {
  for name in backend frontend; do
    local pid="-"; [[ -f "$WORK/$name.pid" ]] && pid="$(cat "$WORK/$name.pid")"
    echo "$name pid=$pid"
  done
  echo "api=http://127.0.0.1:$API_PORT web=http://127.0.0.1:$WEB_PORT db=$WORK/rec.db"
}

cmd_up() {
  local fresh=0
  [[ "${1:-}" == "--fresh" ]] && fresh=1
  mkdir -p "$WORK/uploads"
  cmd_down >/dev/null
  backend_env

  # ---- database ---------------------------------------------------------------------------------
  # The CLI builds the schema with create_all from the current models, so a recording never waits
  # for a migration that an in-flight backend change has not written yet (uvicorn then starts in
  # its "legacy create_all database" mode and only logs drift).
  rm -f "$WORK/rec.db"
  if [[ $fresh -eq 0 ]]; then
    log "importing Bahar weekly grid + planning list (≈30 s)"
    (cd "$BACKEND" && "$PYTHON" -m app.cli import weekly-grid tests/fixtures/bahar_derslikler_takvimi_2026.xlsx \
        --term "$TERM_CODE" --year 2026 && \
      "$PYTHON" -m app.cli import planning-list tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx \
        --term "$TERM_CODE") >"$WORK/import.log" 2>&1 || die "fixture import failed, see $WORK/import.log"
  fi
  (cd "$BACKEND" && "$PYTHON" -m app.cli seed-admin >>"$WORK/import.log" 2>&1) || die "seed-admin failed"

  # ---- backend ----------------------------------------------------------------------------------
  (cd "$BACKEND" && setsid nohup "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" \
      >"$WORK/backend.log" 2>&1 & echo $! >"$WORK/backend.pid")
  wait_http "http://127.0.0.1:$API_PORT/api/v1/health" 60 || die "backend did not start, see $WORK/backend.log"
  log "backend ready on :$API_PORT (db $WORK/rec.db)"
  seed_via_api "$fresh"

  # ---- frontend (isolated copy, real mode) -------------------------------------------------------
  local web="$WORK/frontend"
  if [[ "${REC_SKIP_BUILD:-0}" != 1 || ! -d "$web/.next" ]]; then
    mkdir -p "$web"
    # copy sources only; node_modules is shared through a symlink
    tar -C "$FRONTEND" --exclude=./node_modules --exclude=./.next --exclude=./test-results \
        --exclude=./playwright-report -cf - . | tar -C "$web" -xf -
    ln -sfn "$FRONTEND/node_modules" "$web/node_modules"
    # Turbopack refuses a node_modules symlink that leaves the project root: widen the root of the
    # copy (only the copy's next.config is patched, never the repository's).
    local cfg; cfg="$(ls "$web"/next.config.* | head -1)"
    grep -q 'rec-stack' "$cfg" || sed -i 's|^export default nextConfig;|// rec-stack: shared node_modules symlink\nnextConfig.turbopack = { ...(nextConfig.turbopack ?? {}), root: "/" };\nnextConfig.outputFileTracingRoot = "/";\nexport default nextConfig;|' "$cfg"
    log "building frontend copy (real mode) in $web"
    (cd "$web" && NEXT_PUBLIC_API_MOCK=0 NEXT_PUBLIC_API_URL="http://127.0.0.1:$API_PORT" \
        NEXT_TELEMETRY_DISABLED=1 npx next build >"$WORK/build.log" 2>&1) \
      || die "next build failed, see $WORK/build.log"
  fi
  (cd "$web" && NEXT_PUBLIC_API_MOCK=0 NEXT_PUBLIC_API_URL="http://127.0.0.1:$API_PORT" AUTH_SECRET=rec \
      NEXT_TELEMETRY_DISABLED=1 setsid nohup npx next start -p "$WEB_PORT" -H 127.0.0.1 \
      >"$WORK/frontend.log" 2>&1 & echo $! >"$WORK/frontend.pid")
  wait_http "http://127.0.0.1:$WEB_PORT/login" 120 || die "frontend did not start, see $WORK/frontend.log"
  log "frontend ready: http://127.0.0.1:$WEB_PORT  (login $EMAIL)"
}

case "${1:-}" in
  up) shift; cmd_up "$@" ;;
  down) cmd_down ;;
  status) cmd_status ;;
  *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
