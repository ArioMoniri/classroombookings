#!/usr/bin/env bash
# The REAL backend for the browser e2e stack: fresh SQLite, the real Bahar 2026 workbooks, the seeded
# admin, one full-term CP-SAT run, then serve with the booking clock inside the term (e2e-backend-serve.py).
#
# pod CI (e2e-real.sh): runs INSIDE the python CI container, cwd /w/src/smartsched/backend, gates at /ci.
# Locally (no Docker), from smartsched/backend with the backend deps installed:
#   E2E_WORKDIR=/tmp/e2e E2E_VENV=none E2E_PORT=8000 bash ../deploy/pod-ci/gates/e2e-backend-entry.sh
#
# Env: E2E_WORKDIR (default /w: DB, uploads, venv), E2E_VENV (default $E2E_WORKDIR/venv; "none" = the
# current python), E2E_HOST/E2E_PORT (0.0.0.0:8000), E2E_BOOKING_CLOCK (default 2026-02-16T08:00, empty =
# wall clock), E2E_SOLVE_TIME_LIMIT (seconds for the full-term run, default 120).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
W="${E2E_WORKDIR:-/w}"
VENV="${E2E_VENV:-$W/venv}"
mkdir -p "$W"
if [ "$VENV" != "none" ]; then
  if [ ! -x "$VENV/bin/python" ]; then
    python -m venv "$VENV" && "$VENV/bin/pip" install -q -e "$PWD[dev]"
  fi
  # shellcheck disable=SC1091
  . "$VENV/bin/activate"
fi
PY="$(command -v python || command -v python3)"
export ENVIRONMENT=dev DATABASE_URL="sqlite+aiosqlite:///$W/e2e.db" UPLOAD_DIR="$W/e2e-uploads" \
       ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-admin@smartsched.local}" ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-Admin-2026!}" \
       APP_SECRET=pod-ci-e2e-secret-0123456789abcdef0123456789 JWT_SECRET=pod-ci-e2e-jwt-0123456789abcdef0123456789ab
export E2E_BOOKING_CLOCK="${E2E_BOOKING_CLOCK-2026-02-16T08:00}"
rm -f "$W/e2e.db"
alembic upgrade head
"$PY" -m app.cli import weekly-grid tests/fixtures/bahar_derslikler_takvimi_2026.xlsx --term 2026-BAHAR --year 2026
"$PY" -m app.cli import planning-list tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx --term 2026-BAHAR
"$PY" -m app.cli seed-admin
# a solver run for the whole term (the calendar and motion specs need one besides the imported boards)
"$PY" -m app.cli solve --term 2026-BAHAR --kind COURSE --horizon TERM --solver cpsat \
  --time-limit "${E2E_SOLVE_TIME_LIMIT:-120}" --label "e2e: Bahar full term"
exec "$PY" "$HERE/e2e-backend-serve.py" --host "${E2E_HOST:-0.0.0.0}" --port "${E2E_PORT:-8000}"
