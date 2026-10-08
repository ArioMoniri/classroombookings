#!/usr/bin/env bash
# Gate: every Playwright spec (smoke, real-backend, bookings, calendar, motion-audit) against the REAL FastAPI
# backend loaded with the real Bahar fixture workbooks (docs/testing/2026-10-08-real-backend-e2e.md), on a
# private per-run docker network. The backend (e2e-backend-entry.sh) also solves the full term and pins the
# booking clock inside Bahar 2026. There is no mock API. Afterwards the production build Playwright served
# (.next/standalone) is checked for mock/demo code.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
net="podci-${RUN_TAG}"
backend="podci-${RUN_TAG}-backend"
cleanup() {
  echo "==== backend log (tail)"; docker logs --tail 200 "$backend" 2>&1 || true
  docker rm -f "$backend" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker network create --label "smartsched-ci.run=${RUN_TAG}" "$net" >/dev/null
section "backend with the Bahar fixtures"
docker run -d "${docker_common[@]}" --name "$backend" --network "$net" --network-alias backend \
  -e E2E_BOOKING_CLOCK=2026-02-16T08:00 \
  -w /w/src/smartsched/backend "$PY_IMAGE" bash /ci/e2e-backend-entry.sh >/dev/null
section "playwright (E2E_REAL=1, all specs)"
# list for the log; json for the parity gate (gates/parity.sh maps UI rows to these test results)
in_playwright --network "$net" -e E2E_REAL=1 -e NEXT_PUBLIC_API_URL=http://backend:8000 \
  -e PLAYWRIGHT_JSON_OUTPUT_NAME=/w/playwright-report.json -- '
for i in $(seq 1 300); do
  if node -e "fetch(\"http://backend:8000/api/v1/health\").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"; then break; fi
  [ "$i" = 300 ] && { echo "backend not healthy after 10 min"; exit 1; }
  sleep 2
done
npx playwright test --reporter=list,json
echo "==== no mock/demo code in the production build"
bash ../deploy/validate.sh --no-mock-build .next/standalone
'
