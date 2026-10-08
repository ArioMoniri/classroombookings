#!/usr/bin/env bash
# Runs INSIDE the python CI container for e2e-real.sh: import the real fixtures, seed the admin, serve.
set -euo pipefail
if [ ! -x /w/venv/bin/python ]; then
  python -m venv /w/venv && /w/venv/bin/pip install -q -e "/w/src/smartsched/backend[dev]"
fi
. /w/venv/bin/activate
export ENVIRONMENT=dev DATABASE_URL=sqlite+aiosqlite:////w/e2e.db UPLOAD_DIR=/w/e2e-uploads \
       ADMIN_EMAIL=admin@smartsched.local ADMIN_PASSWORD='Admin-2026!' \
       APP_SECRET=pod-ci-e2e-secret-0123456789abcdef0123456789 JWT_SECRET=pod-ci-e2e-jwt-0123456789abcdef0123456789ab
rm -f /w/e2e.db
alembic upgrade head
python -m app.cli import weekly-grid tests/fixtures/bahar_derslikler_takvimi_2026.xlsx --term 2026-BAHAR --year 2026
python -m app.cli import planning-list tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx --term 2026-BAHAR
python -m app.cli seed-admin
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
