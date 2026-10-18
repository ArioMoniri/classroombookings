#!/usr/bin/env bash
# Start an isolated SmartSched stack for demo recordings: FastAPI on SQLite with the real fixture
# workbooks, and a production build of the frontend against the real backend.
#
#   scripts/record/stack.sh up [--fresh]   start backend + frontend in the background, wait until ready
#   scripts/record/stack.sh down           stop both
#   scripts/record/stack.sh status         print URLs, PIDs and the database in use
#
# --fresh   empty database (admin only) for the "import planning files" journey; the default imports
#           the real workbooks of all three terms (Bahar 2026, Güz 2026-27, Final 2026) and the room
#           master, like docs/testing/2026-10-08-real-data-feasibility.md "Setup" (REC_DATA=bahar: Bahar only).
#
#   scripts/record/stack.sh snapshot       save the database + uploads; `REC_SNAPSHOT=1 stack.sh up` restores them
#                                           (REC_SNAPSHOT_NAME names the file, default rec.snapshot: e.g. REC_SNAPSHOT_NAME=rec.board
#                                           keeps the board-only state before `runs` for F-05 S15, flows README §4.2)
#   scripts/record/stack.sh mask           KVKK: instructor names -> title + initials in the running stack's
#                                           database (kvkk_mask.py; `up` already does it after its imports and keeps
#                                           the name list in $REC_WORKDIR for the fresh-database journeys) and in its
#                                           stored uploads, then the README §7 check (kvkk_mask.py --verify, also over
#                                           import preview rows, audit rows and uploads): fails when a name is left.
#                                           Works on a live stack (the append-only audit rows go through the KVKK
#                                           anonymise window).
#   scripts/record/stack.sh fixtures       KVKK: masked copies of the seed workbooks in $REC_WORKDIR/fixtures (`up`
#                                           makes them too). They are the only workbooks the stack's /import and
#                                           council accept (KVKK_UPLOAD_GUARD, app/core/kvkk_guard.py): use
#                                           E2E_FIXTURES_DIR=$REC_WORKDIR/fixtures for specs and queue items.
#   scripts/record/stack.sh runs           real solver runs through POST /runs on the running stack
#                                           (REC_RUNS, default "2026-GUZ:WEEK:3:120 2026-GUZ:TERM:-:240"
#                                           = term:horizon:week:time-limit), waits until they finish
#
# Ports: REC_API_PORT / REC_WEB_PORT (defaults 8610 / 3610).
#
# Nothing is written inside the repository: the database, uploads, logs and a copy of the frontend
# (built with its own .next, so a build here never clobbers another agent's dev server) live under
# $REC_WORKDIR (default: ${TMPDIR:-/tmp}/smartsched-rec). node_modules is symlinked, not copied.
#
# Env: REC_WORKDIR, REC_API_PORT (8610), REC_WEB_PORT (3610), REC_EMAIL / REC_PASSWORD (seeded admin,
#      default admin@smartsched.local / Admin-2026!), REC_TERM_CODE (2026-BAHAR), PYTHON (python3),
#      REC_TEACHER=1 + REC_TEACHER_EMAIL / REC_TEACHER_PASSWORD (also create a teacher account; off by default:
#      the journeys book as the seeded administrator so no invented person appears in the media),
#      REC_LANG (en|tr: the admin's profile language, which the booking pages follow),
#      REC_SKIP_BUILD=1 (reuse the previous frontend build), REC_DATA (all|bahar), REC_RUNS (see runs).
#      REC_CAL_SIGNOFF=0 (leave calendar sync off with no KVKK sign-off record; default 1 signs it off for the
#      recordings; the flow tests use 0, docs/testing/flows/README.md §4.2).
#      REC_SNAPSHOT_NAME (rec.snapshot): the snapshot file `snapshot` writes and `REC_SNAPSHOT=1 up` restores.
#      Every process the stack starts runs without the caller's credentials (GH_TOKEN, AWS_*, API keys; see
#      SECRET_VARS); REC_KEEP_ENV="NAME ..." keeps the named ones.
#      REC_IGNORE_TS=1: build the copy with `typescript.ignoreBuildErrors` (a checkpoint commit whose in-flight lanes do
#      not type-check yet still runs; only the copy's next.config is patched).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/smartsched/backend"
FRONTEND="$ROOT/smartsched/frontend"
WORK="${REC_WORKDIR:-${TMPDIR:-/tmp}/smartsched-rec}"
API_PORT="${REC_API_PORT:-8610}"
WEB_PORT="${REC_WEB_PORT:-3610}"
EMAIL="${REC_EMAIL:-admin@smartsched.local}"
PASSWORD="${REC_PASSWORD:-Admin-2026!}"
TERM_CODE="${REC_TERM_CODE:-2026-BAHAR}"
SNAP_NAME="${REC_SNAPSHOT_NAME:-rec.snapshot}"
# the default keeps its historical folder name (uploads.snapshot), so snapshots taken before this option still restore
UPL_SNAP="uploads.snapshot"; [[ "$SNAP_NAME" != rec.snapshot ]] && UPL_SNAP="uploads.$SNAP_NAME"
PYTHON="${PYTHON:-python3}"
[[ -x "$BACKEND/.venv/bin/python" && "$PYTHON" == python3 ]] && PYTHON="$BACKEND/.venv/bin/python"

# the stack never inherits an agent's or developer's credentials (FIX-J): every process starts under "${CLEAN_ENV[@]}" (env -u …)
SECRET_VARS=(GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_PAT AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
  AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_PROFILE GOOGLE_APPLICATION_CREDENTIALS CLOUDSDK_AUTH_ACCESS_TOKEN
  AZURE_CLIENT_SECRET ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN OPENAI_API_KEY NPM_TOKEN NODE_AUTH_TOKEN
  HF_TOKEN DEEPGRAM_API_KEY SSH_AUTH_SOCK)
CLEAN_ENV=(env)
for _v in "${SECRET_VARS[@]}"; do
  [[ " ${REC_KEEP_ENV:-} " == *" $_v "* ]] || CLEAN_ENV+=(-u "$_v")
done
unset _v

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
  # KVKK (FIX-J, round-4 E2EA-F01): /import and the council refuse raw seed workbooks and unmasked names
  export KVKK_UPLOAD_GUARD="${REC_KVKK_GUARD:-1}" KVKK_NAMES_FILE="$WORK/kvkk-names.json"
  export CORS_ORIGINS="[\"http://127.0.0.1:$WEB_PORT\",\"http://localhost:$WEB_PORT\"]"
}

# Through the public API: the term (fresh mode: the import journey picks it in the wizard), the one-time
# booking setup (setup_api.py bookings) and, with REC_TEACHER=1, a teacher account.
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
  if [[ "$1" == 0 && "${REC_DATA:-all}" == all ]]; then
    "${CLEAN_ENV[@]}" "$PYTHON" "$ROOT/scripts/record/setup_api.py" "$api" "$EMAIL" "$PASSWORD" bookings --language "${REC_LANG:-en}" \
      >>"$WORK/import.log" 2>&1 && log "booking setup done (Güz 2026-27 open, admin language ${REC_LANG:-en}, calendar sync $([[ "${REC_CAL_SIGNOFF:-1}" == 0 ]] && echo off || echo 'signed off'))" \
      || die "booking setup failed, see $WORK/import.log"
  fi
  [[ "${REC_TEACHER:-0}" == 1 ]] || return 0
  curl -fsS -o /dev/null -X POST "$api/users" -H "Authorization: Bearer $token" -H 'content-type: application/json' \
    -d "{\"email\":\"${REC_TEACHER_EMAIL:-ogretmen@smartsched.local}\",\"full_name\":\"Akademik Personel\",\"role\":\"TEACHER\",\"password\":\"${REC_TEACHER_PASSWORD:-Teacher-2026!}\"}" \
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
  # Fallback for a crashed previous run that left no PID file: only on request, because other agents' or
  # developers' servers may be listening on these ports (REC_FREE_PORTS=1 scripts/record/stack.sh down).
  if [[ "${REC_FREE_PORTS:-0}" == 1 ]]; then
    fuser -k -TERM "$API_PORT/tcp" "$WEB_PORT/tcp" >/dev/null 2>&1 || true
  elif fuser "$API_PORT/tcp" "$WEB_PORT/tcp" >/dev/null 2>&1; then
    log "port $API_PORT or $WEB_PORT is still in use by a process this script did not start; left running"
  fi
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
  # the WAL and shared-memory files belong to the old database: a restored snapshot must not inherit them
  rm -f "$WORK/rec.db" "$WORK/rec.db-wal" "$WORK/rec.db-shm"
  local restored=0
  if [[ $fresh -eq 0 && "${REC_SNAPSHOT:-0}" == 1 && -f "$WORK/$SNAP_NAME.db" ]]; then
    cp "$WORK/$SNAP_NAME.db" "$WORK/rec.db" && restored=1 && log "restored the snapshot $SNAP_NAME.db (imports, booking setup, solver runs)"
    rm -rf "$WORK/uploads" && cp -r "$WORK/$UPL_SNAP" "$WORK/uploads" 2>/dev/null || mkdir -p "$WORK/uploads"
  fi
  if [[ $fresh -eq 0 && $restored -eq 0 ]]; then
    log "importing Bahar weekly grid + planning list (≈30 s)"
    (cd "$BACKEND" && "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import weekly-grid --source seed tests/fixtures/bahar_derslikler_takvimi_2026.xlsx \
        --term "$TERM_CODE" --year 2026 && \
      "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import planning-list --source seed tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx \
        --term "$TERM_CODE") >"$WORK/import.log" 2>&1 || die "fixture import failed, see $WORK/import.log"
    if [[ "${REC_DATA:-all}" == all ]]; then
      log "importing Güz 2026-27 (grid + planning list), Final 2026 (grid + exam list) and the room master (≈40 s)"
      (cd "$BACKEND" && F=tests/fixtures && \
        "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import weekly-grid --source seed "$F/guz_derslikler_takvimi_2026_2027.xlsx" --term 2026-GUZ --year 2026 && \
        "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import planning-list --source seed "$F/guz_derslik_planlama_2026_2027_v2.xlsx" --term 2026-GUZ && \
        "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import weekly-grid --source seed "$F/final_derslikler_takvimi_2026_v2.xlsx" --term 2026-FINAL --year 2026 && \
        "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import exam-list --source seed "$F/final_planlama_listesi_2026_v2.xlsx" --term 2026-FINAL && \
        "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import room-master --source seed "$F/room_master.csv") >>"$WORK/import.log" 2>&1 \
        || die "fixture import failed, see $WORK/import.log"
    fi
  fi
  [[ $restored -eq 1 ]] || { (cd "$BACKEND" && "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli seed-admin >>"$WORK/import.log" 2>&1) || die "seed-admin failed"; }
  # KVKK: the workbooks name every instructor; the recordings show title + initials only (kvkk_mask.py)
  if [[ $fresh -eq 0 && $restored -eq 0 && "${REC_KVKK_MASK:-1}" == 1 ]]; then
    "$PYTHON" -I "$ROOT/scripts/record/kvkk_mask.py" "$WORK/rec.db" --save-names "$WORK/kvkk-names.json" >"$WORK/kvkk.log" 2>&1 \
      || die "kvkk mask failed, see $WORK/kvkk.log"
    log "instructor names masked to initials ($(grep -m1 '^masked' "$WORK/kvkk.log"))"
    # the KVKK check of docs/testing/flows/README.md §7 (title tokens and initials only), fail loudly
    "$PYTHON" -I "$ROOT/scripts/record/kvkk_mask.py" "$WORK/rec.db" --verify --names "$WORK/kvkk-names.json" --uploads "$WORK/uploads" >>"$WORK/kvkk.log" 2>&1 \
      || die "names left after masking: $(grep -m1 '^left' "$WORK/kvkk.log"), see $WORK/kvkk.log"
  fi
  [[ "${REC_KVKK_MASK:-1}" == 1 ]] && ensure_fixtures

  # ---- backend ----------------------------------------------------------------------------------
  # exec + setsid: the PID file names the server itself (a session leader, so `down` can stop its
  # whole process group) and no shell keeps the caller's stdout open
  (cd "$BACKEND" && exec "${CLEAN_ENV[@]}" setsid "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" \
      >"$WORK/backend.log" 2>&1 </dev/null) &
  echo $! >"$WORK/backend.pid"
  wait_http "http://127.0.0.1:$API_PORT/api/v1/health" 60 || die "backend did not start, see $WORK/backend.log"
  log "backend ready on :$API_PORT (db $WORK/rec.db)"
  [[ $restored -eq 1 ]] || seed_via_api "$fresh"

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
    if [[ "${REC_IGNORE_TS:-0}" == 1 ]] && ! grep -q 'REC_IGNORE_TS' "$cfg"; then
      sed -i 's|^export default nextConfig;|nextConfig.typescript = { ...(nextConfig.typescript ?? {}), ignoreBuildErrors: true }; // rec-stack: REC_IGNORE_TS\nexport default nextConfig;|' "$cfg"
    fi
    log "building frontend copy (real mode) in $web"
    (cd "$web" && NEXT_PUBLIC_API_URL="http://127.0.0.1:$API_PORT" \
        NEXT_TELEMETRY_DISABLED=1 "${CLEAN_ENV[@]}" npx next build >"$WORK/build.log" 2>&1) \
      || die "next build failed, see $WORK/build.log"
  fi
  (cd "$web" && NEXT_PUBLIC_API_URL="http://127.0.0.1:$API_PORT" \
      NEXT_TELEMETRY_DISABLED=1 exec "${CLEAN_ENV[@]}" setsid npx next start -p "$WEB_PORT" -H 127.0.0.1 \
      >"$WORK/frontend.log" 2>&1 </dev/null) &
  echo $! >"$WORK/frontend.pid"
  wait_http "http://127.0.0.1:$WEB_PORT/login" 120 || die "frontend did not start, see $WORK/frontend.log"
  log "frontend ready: http://127.0.0.1:$WEB_PORT  (login $EMAIL)"
  [[ -d "$WORK/fixtures" ]] && log "KVKK: upload only the masked workbooks: E2E_FIXTURES_DIR=$WORK/fixtures"
  return 0
}

# KVKK: masked copies of the seed workbooks (title + initials) in $WORK/fixtures. The name list comes from the
# seeded database; a --fresh stack without one builds it once from a throwaway import (≈70 s), never in the repo.
ensure_fixtures() {
  local names="$WORK/kvkk-names.json" F="$BACKEND/tests/fixtures"
  if [[ ! -s "$names" ]]; then
    log "KVKK: building the name list for the masked workbooks (throwaway import, ≈70 s)"
    local tmpdb="$WORK/kvkk-names-build.db"
    rm -f "$tmpdb"
    (cd "$BACKEND" && export DATABASE_URL="sqlite+aiosqlite:///$tmpdb" && \
      "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import planning-list "$F/bahar_derslik_planlama_listesi_v5.xlsx" --term 2026-BAHAR && \
      "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import planning-list "$F/guz_derslik_planlama_2026_2027_v2.xlsx" --term 2026-GUZ && \
      "${CLEAN_ENV[@]}" "$PYTHON" -m app.cli import exam-list "$F/final_planlama_listesi_2026_v2.xlsx" --term 2026-FINAL) \
      >>"$WORK/kvkk.log" 2>&1 || die "KVKK name list build failed, see $WORK/kvkk.log"
    "$PYTHON" -I "$ROOT/scripts/record/kvkk_mask.py" "$tmpdb" --save-names "$names" >>"$WORK/kvkk.log" 2>&1 \
      || die "KVKK name list build failed, see $WORK/kvkk.log"
    rm -f "$tmpdb" "$tmpdb-wal" "$tmpdb-shm"
  fi
  "$PYTHON" -I "$ROOT/scripts/record/kvkk_mask.py" --workbooks "$F" "$WORK/fixtures" --names "$names" >>"$WORK/kvkk.log" 2>&1 \
    || die "masked workbook copies failed, see $WORK/kvkk.log"
  log "KVKK: masked workbooks in $WORK/fixtures (the only ones this stack accepts)"
}

# Real solver runs through the public API (the same POST /runs the Generate button sends), one after
# the other (scripts/record/setup_api.py runs).
cmd_runs() {
  # shellcheck disable=SC2086
  "${CLEAN_ENV[@]}" "$PYTHON" "$ROOT/scripts/record/setup_api.py" "http://127.0.0.1:$API_PORT/api/v1" "$EMAIL" "$PASSWORD" \
    runs ${REC_RUNS:-2026-GUZ:WEEK:3:120 2026-GUZ:TERM:-:240} || die "solver runs failed"
}

# Snapshot of the running stack's database (SQLite online backup) and uploads; `up` with REC_SNAPSHOT=1
# restores it instead of importing again, so every take starts from the same data in seconds.
cmd_snapshot() {
  # a single-file copy (journal_mode=delete): `up` restores it with cp, which would miss a WAL file
  rm -f "$WORK/$SNAP_NAME.db" "$WORK/$SNAP_NAME.db-wal" "$WORK/$SNAP_NAME.db-shm"
  "$PYTHON" -c 'import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.execute("pragma journal_mode=delete"); d.close()' \
    "$WORK/rec.db" "$WORK/$SNAP_NAME.db" || die "snapshot failed"
  rm -rf "$WORK/$UPL_SNAP" && cp -r "$WORK/uploads" "$WORK/$UPL_SNAP"
  log "snapshot saved: $WORK/$SNAP_NAME.db"
}

# KVKK mask on the running stack's database (after the fresh-database journeys imported their workbooks)
cmd_mask() {
  # safe on a live stack: SQLite waits for the API's writers (timeout 60 s); audit rows go through the KVKK window
  "$PYTHON" -I "$ROOT/scripts/record/kvkk_mask.py" "$WORK/rec.db" --names "$WORK/kvkk-names.json" | tee -a "$WORK/kvkk.log" | grep -m1 '^masked' \
    || die "kvkk mask failed"
  # the stored uploads (preview files included, E2EA2-F02)
  "$PYTHON" -I "$ROOT/scripts/record/kvkk_mask.py" --files "$WORK/uploads" --names "$WORK/kvkk-names.json" | tee -a "$WORK/kvkk.log" \
    || die "kvkk mask of the uploads failed"
  # README §7 check on the result: prints "left 0", or the shapes of the names left and fails
  "$PYTHON" -I "$ROOT/scripts/record/kvkk_mask.py" "$WORK/rec.db" --verify --names "$WORK/kvkk-names.json" --uploads "$WORK/uploads" | tee -a "$WORK/kvkk.log" \
    || die "names left after masking (README §7): run the README §4.4 masking block and report the count"
}

case "${1:-}" in
  snapshot) cmd_snapshot ;;
  mask) cmd_mask ;;
  fixtures) backend_env; ensure_fixtures ;;
  up) shift; cmd_up "$@" ;;
  runs) cmd_runs ;;
  down) cmd_down ;;
  status) cmd_status ;;
  *) sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
