#!/usr/bin/env bash
# Gate: one shard of the Playwright specs (`e2e-real.sh 1/3`: `npx playwright test --shard=1/3`) against the REAL
# FastAPI backend loaded with the real Bahar fixture workbooks (docs/testing/2026-10-08-real-backend-e2e.md), on a
# private per-shard docker network. The backend (e2e-backend-entry.sh) also solves the full term and pins the booking
# clock inside Bahar 2026. There is no mock API. Playwright shards are contiguous slices of the ordered test files, so
# the last shard ends with the `integrity` and `intake` projects, as the unsharded run did. The production build is
# the one the e2e-build gate made (and checked for mock/demo code); this gate only `next start`s a private copy.
#
# Every shard has its own stack (container names podci-<run>-e2e<i>-*, network podci-<run>-e2e<i>, files under
# /w/e2e-shard-<i>), so the shards run at the same time without sharing state. Containers (aliases), all removed:
#   backend        seeded backend (Bahar fixtures, admin, full-term run, booking clock 2026-02-16 08:00);
#                  DB /w/e2e-shard-<i>/e2e.db, uploads beside it, the backend venv /w/venv (backend-deps gate)
#   smtp           SMTP sink (smtp-sink.py): SMTP 1025, JSON API 8025; nothing is delivered (S-23, X-02)
#   backend-empty  second backend on an EMPTY database (no users): the first-run installer (B-SETUP-02);
#                  started once `backend` is healthy (/w/e2e-shard-<i>/empty)
#   idp            mock OpenID Connect issuer in the backend's network namespace (w3-idp.spec.ts)
# Playwright joins the backend's namespace and gets E2E_SMTP_HOST/E2E_SMTP_PORT/E2E_SMTP_API, E2E_EMPTY_API_URL and
# E2E_DB (this shard's SQLite file: consent.spec.ts 4 seeds an unreadable grant there with python3 -I + sqlite3).
# Its .next and test-results are per-shard bind mounts (/w/e2e-shard-<i>/next, /w/e2e-shard-<i>/test-results) over the
# shared source tree; its JSON report is /w/playwright-report-<i>.json (the parity gate merges all shards).
# Shard 1 also records the contract-test payloads before its specs (contract-record.py: /w/contract/contract-drift.json;
# report only). The booking clock is checked before any spec runs: a clock outside Bahar 2026 fails the shard (the
# booking specs would otherwise skip and the gate would look green).
# Memory: one slot (lib.sh defaults, 8 GB pod) keeps the caps that ran there: the seeded backend GATE_MEMORY,
# Playwright NODE_MEMORY. A multi-slot share (runner.py Slots.env, two slots: NODE_MEMORY >= 8 GiB) is split so the
# shard's caps add up to it: 1.5 GiB side containers (empty 1g, smtp 256m, issuer 256m), of the rest 2/5 (at least
# 3 GiB) for the seeded backend and the remainder for Playwright (next start + Chromium + runner, heap 3/4 of it).
#   E2E_HEALTH_TRIES / E2E_HEALTH_SLEEP   backend health wait (default 450 x 2 s: imports, full-term solve, analytics seed)
#   E2E_BACKEND_MEMORY / E2E_PLAYWRIGHT_MEMORY   override the split (docker sizes, e.g. 3g / 4096m)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SHARD="${1:?usage: e2e-real.sh <index>/<count>}"
[[ "$SHARD" =~ ^([1-9][0-9]*)/([1-9][0-9]*)$ ]] && (( BASH_REMATCH[1] <= BASH_REMATCH[2] )) \
  || { echo "bad shard $SHARD"; exit 2; }
idx="${SHARD%/*}"
tag="podci-${RUN_TAG}-e2e${idx}"
net="$tag"
backend="${tag}-backend"
smtp="${tag}-smtp"
empty="${tag}-backend-empty"
idp="${tag}-idp"
sdir="e2e-shard-${idx}"            # under /w (host: $WS)
fe="$WS/src/smartsched/frontend"
tries="${E2E_HEALTH_TRIES:-450}"
pause="${E2E_HEALTH_SLEEP:-2}"
clock="2026-02-16T08:00"
mib() {  # docker memory size (512m, 3g, bytes) -> MiB
  local v="${1,,}"
  case "$v" in *g) echo $(( ${v%g} * 1024 )) ;; *m) echo "${v%m}" ;; *k) echo $(( ${v%k} / 1024 )) ;; *) echo $(( v / 1048576 )) ;; esac
}
share=$(mib "$NODE_MEMORY")
if (( share >= 8192 )); then
  rest=$(( share - 1536 ))
  be=$(( rest * 2 / 5 )); (( be >= 3072 )) || be=3072
  pw=$(( rest - be ))
  BACKEND_MEMORY="${be}m"; PW_MEMORY="${pw}m"
else
  BACKEND_MEMORY="$GATE_MEMORY"; PW_MEMORY="$NODE_MEMORY"
fi
BACKEND_MEMORY="${E2E_BACKEND_MEMORY:-$BACKEND_MEMORY}"
PW_MEMORY="${E2E_PLAYWRIGHT_MEMORY:-$PW_MEMORY}"
if [ "$PW_MEMORY" != "$NODE_MEMORY" ]; then NODE_HEAP_MB=$(( $(mib "$PW_MEMORY") * 3 / 4 )); fi
NODE_MEMORY="$PW_MEMORY"            # in_playwright (lib.sh) caps the Playwright container with these
echo "shard ${SHARD}: seeded backend --memory ${BACKEND_MEMORY}, playwright --memory ${NODE_MEMORY} (heap ${NODE_HEAP_MB} MB), --cpus ${GATE_CPUS} each"
[ -f "$fe/.next/BUILD_ID" ] || { echo "no next build in $fe/.next: the e2e-build gate builds it"; exit 1; }
# Playwright's error-context.md files (the failure, the page's aria snapshot) outlive the workspace: copied into
# ARTIFACT_DIR (runner.py: logs/<run>/artifacts, kept for the last 3 runs by podci/disk.py), at most
# ARTIFACT_MAX_BYTES (20 MB) per run across all shards. Only those files: no traces, videos or screenshots.
keep_failure_context() {
  local src="$WS/$sdir/test-results" dest cap used size f rel
  [[ -n "${ARTIFACT_DIR:-}" && -d "$src" ]] || return 0
  dest="$ARTIFACT_DIR/e2e-shard-${idx}"
  cap="${ARTIFACT_MAX_BYTES:-20971520}"
  while IFS= read -r -d '' f; do
    mkdir -p "$dest" || return 0
    used="$(du -sb "$ARTIFACT_DIR" 2>/dev/null | cut -f1)"; used="${used:-0}"
    size="$(stat -c %s "$f" 2>/dev/null || echo 0)"
    if (( used + size > cap )); then echo "failure context: ${cap} bytes per run reached; the rest is not kept"; break; fi
    rel="${f#"$src"/}"
    mkdir -p "$dest/$(dirname "$rel")" && cp "$f" "$dest/$rel" || true
  done < <(find "$src" -type f -name error-context.md -print0 2>/dev/null)
  [[ -d "$dest" ]] && echo "failure context: $(find "$dest" -type f | wc -l) error-context.md kept in $dest"
  return 0
}
# A failed shard also keeps its seeded backend's side of the failure: lines with " 500 ", Traceback, Error, locked or
# Exception (+ the 8 lines after each Traceback), at most 200 KB, as ARTIFACT_DIR/backend-errors-<shard>.log. E-mail
# addresses and credential-looking values are masked here; `smartsched_aws.py logs` redacts again when it prints.
backend_errors() {  # stdin: the backend's log, stdout: the filtered, masked lines
  awk '/Traceback/ { print; n = 8; next } n > 0 { print; n--; next } / 500 |Error|locked|Exception/ { print }' \
    | sed -E -e 's/[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}/[email]/g' \
      -e 's/(password|passwd|secret|token|api[_-]?key|authorization|cookie)([^[:space:]]*[[:space:]]*[:=][[:space:]]*|[[:space:]]+)[^[:space:]]+/\1 [redacted]/Ig' \
    | head -c "${BACKEND_ERRORS_MAX_BYTES:-204800}"
}
keep_backend_errors() {
  [[ -n "${ARTIFACT_DIR:-}" ]] || return 0
  mkdir -p "$ARTIFACT_DIR" || return 0
  docker logs "$backend" 2>&1 | backend_errors > "$ARTIFACT_DIR/backend-errors-${idx}.log" || true
  echo "backend errors: $(wc -l < "$ARTIFACT_DIR/backend-errors-${idx}.log") line(s) kept in $ARTIFACT_DIR/backend-errors-${idx}.log"
}
cleanup() {
  local rc=$?
  keep_failure_context || true
  if [[ "$rc" != 0 ]]; then keep_backend_errors || true; fi
  for c in "$backend" "$empty" "$smtp" "$idp"; do
    echo "==== ${c##*-${RUN_TAG}-} log (tail)"; docker logs --tail 200 "$c" 2>&1 || true
  done
  docker rm -f "$idp" "$backend" "$empty" "$smtp" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
  rm -rf "${WS:?}/$sdir/next"  # the build copy; test-results (traces, screenshots) stay with the workspace
}
trap cleanup EXIT
trap 'exit 143' TERM INT  # a timeout or a cancel (SIGTERM) still runs cleanup (bash skips EXIT traps on signals)
section "shard ${SHARD}: private copy of the e2e-build gate's .next (no cache/, no standalone/)"
rm -rf "${WS:?}/$sdir"
mkdir -p "$WS/$sdir/next" "$WS/$sdir/test-results" "$WS/$sdir/empty" "$fe/test-results"
tar -C "$fe/.next" --exclude=./cache --exclude=./standalone -cf - . | tar -C "$WS/$sdir/next" -xf -
# health of a backend container, from inside it (no published ports on the pod)
healthy() {
  docker exec "$1" python -c 'import sys, urllib.request
try:
    sys.exit(0 if urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=5).status == 200 else 1)
except Exception:
    sys.exit(1)' >/dev/null 2>&1
}
docker network create --label "smartsched-ci.run=${RUN_TAG}" "$net" >/dev/null
section "backend with the Bahar fixtures"
docker run -d "${docker_common[@]}" --memory "$BACKEND_MEMORY" --memory-swap "$BACKEND_MEMORY" \
  --name "$backend" --network "$net" --network-alias backend \
  -e E2E_WORKDIR="/w/$sdir" -e E2E_VENV=/w/venv -e E2E_BOOKING_CLOCK="$clock" \
  -w /w/src/smartsched/backend "$PY_IMAGE" bash /ci/e2e-backend-entry.sh >/dev/null
section "smtp sink"
docker run -d "${docker_common[@]}" --memory 256m --memory-swap 256m --name "$smtp" --network "$net" --network-alias smtp \
  "$PY_IMAGE" python /ci/smtp-sink.py --host 0.0.0.0 --smtp-port 1025 --api-port 8025 >/dev/null
section "wait for the seeded backend (imports + full-term solve)"
ok=0
for _ in $(seq 1 "$tries"); do
  if healthy "$backend"; then ok=1; break; fi
  sleep "$pause"
done
if [ "$ok" != 1 ]; then echo "backend not healthy after $((tries * pause)) s"; exit 1; fi
if [ "$idx" = 1 ]; then  # one recording per run (every shard's backend is seeded alike); /w/contract is shared
  section "contract fixtures: record + shape diff (report only; copy /w/contract/*.json to re-record)"
  docker exec "$backend" python /ci/contract-record.py --api http://127.0.0.1:8000 --out /w/contract \
    --compare /w/src/smartsched/frontend/src/lib/api/__fixtures__/real || echo "contract recording failed (report only)"
fi
section "empty backend (installer)"
# migrations only, no imports or solves: 1 GB is plenty (part of the shard's 1.5 GiB side-container budget)
docker run -d "${docker_common[@]}" --memory 1g --memory-swap 1g --name "$empty" --network "$net" \
  --network-alias backend-empty \
  -e E2E_EMPTY=1 -e E2E_VENV=/w/venv -e E2E_WORKDIR="/w/$sdir/empty" -e E2E_BOOKING_CLOCK="$clock" \
  -w /w/src/smartsched/backend "$PY_IMAGE" bash /ci/e2e-backend-entry.sh >/dev/null
section "mock OpenID Connect issuer (w3-idp.spec.ts) inside the backend's network namespace"
# The issuer URL is http://localhost:19712: the backend (discovery, JWKS, token) and the browser (authorize) must both
# reach it, and the panel's public URL (127.0.0.1:3100) must be the browser's too. So the issuer runs next to the
# backend and Playwright joins the backend's namespace: localhost is the same for all three. It needs the backend venv
# (joserfc), which the Playwright image does not have.
docker run -d "${docker_common[@]}" --memory 256m --memory-swap 256m --name "$idp" --network "container:$backend" \
  "$PY_IMAGE" /w/venv/bin/python -I /w/src/smartsched/frontend/e2e/w3-idp-mock-issuer.py 19712 >/dev/null
section "playwright (E2E_REAL=1, shard ${SHARD})"
# list for the log; json for the parity gate (gates/parity.sh merges every shard's report and maps UI rows to it).
# .next and test-results are this shard's own directories mounted over the shared source tree
rm -f "$WS/playwright-report-${idx}.json"
in_playwright --network "container:$backend" -e W3_IDP_EXTERNAL=1 -e E2E_REAL=1 -e NEXT_PUBLIC_API_URL=http://backend:8000 \
  -v "$WS/$sdir/next:/w/src/smartsched/frontend/.next" \
  -v "$WS/$sdir/test-results:/w/src/smartsched/frontend/test-results" \
  -e NEXT_TELEMETRY_DISABLED=1 -e E2E_SHARD="$SHARD" \
  -e E2E_SMTP_HOST=smtp -e E2E_SMTP_PORT=1025 -e E2E_SMTP_API=http://smtp:8025 \
  -e E2E_EMPTY_API_URL=http://backend-empty:8000 \
  -e E2E_DB="/w/$sdir/e2e.db" \
  -e PLAYWRIGHT_JSON_OUTPUT_NAME="/w/playwright-report-${idx}.json" -- '
up() { node -e "fetch(process.argv[1]).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" "$1"; }
for url in http://backend:8000/api/v1/health http://backend-empty:8000/api/v1/health http://smtp:8025/health; do
  for i in $(seq 1 150); do
    if up "$url"; then break; fi
    [ "$i" = 150 ] && { echo "$url not healthy after 5 min"; exit 1; }
    sleep 2
  done
done
echo "==== booking clock inside Bahar 2026 (bookings.spec.ts would skip otherwise)"
node -e "
const api = \"http://backend:8000/api/v1\";
(async () => {
  const login = await fetch(api + \"/auth/login\", { method: \"POST\", headers: { \"content-type\": \"application/json\" },
    body: JSON.stringify({ email: process.env.E2E_ADMIN_EMAIL || \"admin@smartsched.local\", password: process.env.E2E_ADMIN_PASSWORD || \"Admin-2026!\" }) });
  if (!login.ok) { console.log(\"admin login failed: \" + login.status); process.exit(1); }
  const { access_token } = await login.json();
  const r = await fetch(api + \"/bookings/dates\", { headers: { authorization: \"Bearer \" + access_token } });
  const today = r.ok ? (await r.json()).today : \"?\";
  console.log(\"backend booking today: \" + today);
  process.exit(today >= \"2026-02-02\" && today <= \"2026-06-28\" ? 0 : 1);
})().catch((e) => { console.log(String(e)); process.exit(1); });
"
[ -f .next/BUILD_ID ] || { echo "no .next/BUILD_ID: the e2e-build gate builds it"; exit 1; }
# the e2e-build gate built and checked .next; the webServer only starts it (E2E_PREBUILT=1). One worker (also
# playwright.config.ts): the specs of a shard share its one seeded backend
E2E_PREBUILT=1 npx playwright test --shard="${E2E_SHARD}" --workers=1 --reporter=list,json
'
