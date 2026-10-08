#!/usr/bin/env bash
# Bootstrap a SmartSched development machine and (optionally) run both dev servers.
#
#   scripts/dev.sh            bootstrap only: python venv + pip install -e ".[dev]", npm ci, .env files,
#                             SQLite migrations, seeded admin
#   scripts/dev.sh --run      bootstrap (idempotent) then run backend :8000 + frontend :3000 together
#   scripts/dev.sh --mock     like --run but the frontend serves MSW mock data (no backend needed)
#
# Requirements: python3 >= 3.12, node >= 22 + npm. No Docker needed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/smartsched/backend"
FRONTEND="$ROOT/smartsched/frontend"
VENV="$BACKEND/.venv"
RUN=0
MOCK=0
for arg in "$@"; do
  case "$arg" in
    --run) RUN=1 ;;
    --mock) RUN=1; MOCK=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done

log() { printf '\033[1;32m[dev]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[dev] error:\033[0m %s\n' "$*" >&2; exit 1; }

# ---- toolchain checks ------------------------------------------------------------------------
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || die "python3 not found"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || die "python >= 3.12 required (found $("$PYTHON" --version))"
command -v node >/dev/null 2>&1 || die "node not found (need >= 22)"
node -e 'process.exit(parseInt(process.versions.node) >= 22 ? 0 : 1)' || die "node >= 22 required (found $(node --version))"
command -v npm >/dev/null 2>&1 || die "npm not found"

# ---- backend ----------------------------------------------------------------------------------
if [[ ! -x "$VENV/bin/python" ]]; then
  log "creating venv at $VENV"
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
log "installing backend (pip install -e .[dev])"
pip install --quiet --upgrade pip
pip install --quiet -e "${BACKEND}[dev]"

if [[ ! -f "$BACKEND/.env" ]]; then
  log "creating backend/.env (SQLite, dev admin)"
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  secret="$(python -c 'import secrets; print(secrets.token_hex(32))')"
  sed -i.bak "s|^APP_SECRET=.*|APP_SECRET=$secret|; s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=admin|; s|^ADMIN_EMAIL=.*|ADMIN_EMAIL=admin@example.com|" "$BACKEND/.env"
  rm -f "$BACKEND/.env.bak"
fi
# A SQLite file created by tests / `create_all` (ENVIRONMENT=dev) has tables but no alembic_version:
# stamp it instead of failing with "table already exists".
(cd "$BACKEND" && python - <<'PY'
import asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings

async def main() -> None:
    url = get_settings().database_url
    if not url.startswith("sqlite"):
        return
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    await engine.dispose()
    if names and "alembic_version" not in names:
        print("STAMP")

asyncio.run(main())
PY
) > "$BACKEND/.dev-stamp" || true
if grep -q STAMP "$BACKEND/.dev-stamp" 2>/dev/null; then
  log "existing SQLite schema without alembic_version: alembic stamp head"
  (cd "$BACKEND" && alembic stamp head)
fi
rm -f "$BACKEND/.dev-stamp"
log "alembic upgrade head"
(cd "$BACKEND" && alembic upgrade head)
log "seeding admin (no-op if users exist)"
(cd "$BACKEND" && python -m app.cli seed-admin)

# ---- frontend ---------------------------------------------------------------------------------
if [[ ! -d "$FRONTEND/node_modules" ]] || [[ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]]; then
  log "npm ci (frontend)"
  (cd "$FRONTEND" && npm ci --no-audit --no-fund)
fi
if [[ ! -f "$FRONTEND/.env.local" ]]; then
  log "creating frontend/.env.local (real backend on :8000; set NEXT_PUBLIC_API_MOCK=1 for mock data)"
  {
    echo "NEXT_PUBLIC_API_URL=http://localhost:8000"
    echo "NEXT_PUBLIC_API_MOCK=0"
    echo "AUTH_SECRET=$(python -c 'import secrets; print(secrets.token_hex(16))')"
  } > "$FRONTEND/.env.local"
fi

env_val() { grep -E "^$1=" "$BACKEND/.env" | head -1 | cut -d= -f2-; }
log "bootstrap complete. Admin: $(env_val ADMIN_EMAIL) / $(env_val ADMIN_PASSWORD) (from backend/.env; seeded only into an empty users table)"
if grep -q '^NEXT_PUBLIC_API_MOCK=1' "$FRONTEND/.env.local" 2>/dev/null; then
  log "note: frontend/.env.local has NEXT_PUBLIC_API_MOCK=1 (mock data); set 0 to use the backend"
fi
[[ $RUN -eq 1 ]] || { log "run both servers with: scripts/dev.sh --run   (or: make -C smartsched dev)"; exit 0; }

# ---- run both servers -------------------------------------------------------------------------
PIDS=()
cleanup() {
  log "stopping"
  local p
  for p in "${PIDS[@]:-}"; do
    [[ -n "$p" ]] || continue
    pkill -TERM -P "$p" 2>/dev/null || true   # npm -> next, uvicorn --reload -> worker
    kill "$p" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ $MOCK -eq 0 ]]; then
  log "backend  → http://localhost:8000  (docs: /api/docs)"
  (cd "$BACKEND" && exec python -m uvicorn app.main:app --reload --port 8000) &
  PIDS+=($!)
fi
log "frontend → http://localhost:3000"
if [[ $MOCK -eq 1 ]]; then
  (cd "$FRONTEND" && NEXT_PUBLIC_API_MOCK=1 exec npm run dev) &
else
  (cd "$FRONTEND" && exec npm run dev) &
fi
PIDS+=($!)
wait -n
