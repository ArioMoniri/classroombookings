#!/usr/bin/env bash
# Gate: every Playwright spec (smoke, real-backend, bookings, calendar, motion-audit, ...) against the REAL
# FastAPI backend loaded with the real Bahar fixture workbooks (docs/testing/2026-10-08-real-backend-e2e.md), on
# a private per-run docker network. The backend (e2e-backend-entry.sh) also solves the full term and pins the
# booking clock inside Bahar 2026. There is no mock API. Afterwards the production build Playwright served
# (.next/standalone) is checked for mock/demo code.
#
# Containers on the network (aliases), all removed afterwards:
#   backend        seeded backend (Bahar fixtures, admin, full-term run, booking clock 2026-02-16 08:00)
#   smtp           SMTP sink (smtp-sink.py): SMTP 1025, JSON API 8025; nothing is delivered (S-23, X-02)
#   backend-empty  second backend on an EMPTY database (no users): the first-run installer (B-SETUP-02);
#                  started once `backend` is healthy because it reuses its venv (/w/venv)
# Playwright gets E2E_SMTP_HOST/E2E_SMTP_PORT/E2E_SMTP_API and E2E_EMPTY_API_URL for the specs that use them.
# Before the specs, contract-record.py records the contract-test payloads from the seeded backend and reports
# their schema drift against src/lib/api/__fixtures__/real (/w/contract/contract-drift.json; never fails).
# The booking clock is checked before any spec runs: a clock outside Bahar 2026 fails the gate (the booking
# specs would otherwise skip and the gate would look green).
#   E2E_HEALTH_TRIES / E2E_HEALTH_SLEEP   backend health wait (default 300 x 2 s)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
net="podci-${RUN_TAG}"
backend="podci-${RUN_TAG}-backend"
smtp="podci-${RUN_TAG}-smtp"
empty="podci-${RUN_TAG}-backend-empty"
tries="${E2E_HEALTH_TRIES:-300}"
pause="${E2E_HEALTH_SLEEP:-2}"
clock="2026-02-16T08:00"
cleanup() {
  for c in "$backend" "$empty" "$smtp"; do
    echo "==== ${c##*-${RUN_TAG}-} log (tail)"; docker logs --tail 200 "$c" 2>&1 || true
  done
  docker rm -f "$backend" "$empty" "$smtp" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
}
trap cleanup EXIT
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
docker run -d "${docker_common[@]}" --name "$backend" --network "$net" --network-alias backend \
  -e E2E_BOOKING_CLOCK="$clock" \
  -w /w/src/smartsched/backend "$PY_IMAGE" bash /ci/e2e-backend-entry.sh >/dev/null
section "smtp sink"
docker run -d "${docker_common[@]}" --name "$smtp" --network "$net" --network-alias smtp \
  "$PY_IMAGE" python /ci/smtp-sink.py --host 0.0.0.0 --smtp-port 1025 --api-port 8025 >/dev/null
section "wait for the seeded backend (imports + full-term solve)"
ok=0
for _ in $(seq 1 "$tries"); do
  if healthy "$backend"; then ok=1; break; fi
  sleep "$pause"
done
if [ "$ok" != 1 ]; then echo "backend not healthy after $((tries * pause)) s"; exit 1; fi
section "contract fixtures: record + shape diff (report only; copy /w/contract/*.json to re-record)"
docker exec "$backend" python /ci/contract-record.py --api http://127.0.0.1:8000 --out /w/contract \
  --compare /w/src/smartsched/frontend/src/lib/api/__fixtures__/real || echo "contract recording failed (report only)"
section "empty backend (installer)"
docker run -d "${docker_common[@]}" --name "$empty" --network "$net" --network-alias backend-empty \
  -e E2E_EMPTY=1 -e E2E_VENV=/w/venv -e E2E_WORKDIR=/w/e2e-empty -e E2E_BOOKING_CLOCK="$clock" \
  -w /w/src/smartsched/backend "$PY_IMAGE" bash /ci/e2e-backend-entry.sh >/dev/null
section "playwright (E2E_REAL=1, all specs)"
# list for the log; json for the parity gate (gates/parity.sh maps UI rows to these test results)
in_playwright --network "$net" -e E2E_REAL=1 -e NEXT_PUBLIC_API_URL=http://backend:8000 \
  -e E2E_SMTP_HOST=smtp -e E2E_SMTP_PORT=1025 -e E2E_SMTP_API=http://smtp:8025 \
  -e E2E_EMPTY_API_URL=http://backend-empty:8000 \
  -e PLAYWRIGHT_JSON_OUTPUT_NAME=/w/playwright-report.json -- '
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
npx playwright test --reporter=list,json
echo "==== no mock/demo code in the production build"
bash ../deploy/validate.sh --no-mock-build .next/standalone
'
