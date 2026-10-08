#!/usr/bin/env bash
# Static validation of the deployment files (no Docker daemon needed).
#   - YAML syntax of docker-compose.yml (python + PyYAML) and the CI workflow
#   - `docker compose config` when the compose CLI plugin is available (daemon not required)
#   - every ${VAR} referenced by docker-compose.yml is declared in .env.example
#   - every build context / dockerfile / bind-mount source referenced by compose exists
#   - Dockerfiles reference files that exist in their build context
#   - bash -n on every shell script, nginx config brace balance
# Exit code 1 on any failure.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
FAIL=0
ok()   { printf '  \033[32mok\033[0m   %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; FAIL=1; }

echo "== YAML syntax"
for f in "$HERE/docker-compose.yml" "$ROOT/.github/workflows/smartsched.yml"; do
  [[ -f "$f" ]] || { fail "missing $f"; continue; }
  if python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]))" "$f" 2>/tmp/validate_yaml.err; then ok "$f"; else fail "$f: $(cat /tmp/validate_yaml.err)"; fi
done

echo "== env completeness (.env.example vs docker-compose.yml)"
if python3 - "$HERE" <<'PY'; then :; else FAIL=1; fi
import re, sys
from pathlib import Path
here = Path(sys.argv[1])
compose = (here / "docker-compose.yml").read_text()
declared = {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", (here / ".env.example").read_text(), re.M)}
# ${VAR}, ${VAR:-default}, ${VAR:?msg}; skip $${…} (literal for the container shell)
used = set(re.findall(r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)", compose))
missing = sorted(used - declared)
unused = sorted(declared - used)
for v in missing:
    print(f"  FAIL ${v} used in docker-compose.yml but not declared in .env.example")
for v in unused:
    print(f"  note ${v} declared in .env.example but unused by compose (fine if read by deploy.sh)")
print(f"  ok   {len(used)} variables used, {len(declared)} declared, {len(missing)} missing")
secrets = re.findall(r"^(?:APP_SECRET|JWT_SECRET|AUTH_SECRET|POSTGRES_PASSWORD|ADMIN_PASSWORD|CRBS_DB_PASSWORD|CRBS_DB_ROOT_PASSWORD|ANTHROPIC_API_KEY)=(\S*)", (here / ".env.example").read_text(), re.M)
leaked = [s for s in secrets if s not in ("", "__GENERATE__")]
if leaked:
    print(f"  FAIL .env.example contains concrete secret values: {leaked}")
else:
    print("  ok   no secrets committed in .env.example")
sys.exit(1 if missing or leaked else 0)
PY

echo "== referenced paths exist"
if python3 - "$HERE" <<'PY'; then :; else FAIL=1; fi
import sys, yaml
from pathlib import Path
here = Path(sys.argv[1])
doc = yaml.safe_load((here / "docker-compose.yml").read_text())
rc = 0
def check(p: Path, what: str) -> None:
    global rc
    if p.exists():
        print(f"  ok   {what}: {p.relative_to(here.parent.parent)}")
    else:
        print(f"  FAIL {what} missing: {p}")
        rc = 1
for name, svc in doc["services"].items():
    build = svc.get("build")
    if isinstance(build, dict):
        ctx = (here / build.get("context", ".")).resolve()
        check(ctx, f"{name} build context")
        check((ctx / build.get("dockerfile", "Dockerfile")).resolve(), f"{name} dockerfile")
        for ign in (ctx / ".dockerignore",):
            if not ign.exists():
                print(f"  note {name}: no .dockerignore in {ctx}")
    for vol in svc.get("volumes", []):
        src = vol.split(":")[0] if isinstance(vol, str) else vol.get("source", "")
        if src.startswith("./") or src.startswith("../"):
            check((here / src).resolve(), f"{name} bind mount")
for name in doc.get("volumes", {}):
    print(f"  ok   named volume {name}")
sys.exit(rc)
PY

echo "== Dockerfile references"
for df in "$ROOT/smartsched/backend/Dockerfile" "$ROOT/smartsched/frontend/Dockerfile" "$HERE/legacy/Dockerfile"; do
  [[ -f "$df" ]] || { fail "missing $df"; continue; }
  grep -q '^USER ' "$df" || fail "$df: no USER instruction (must run non-root)"
  grep -Eq '^FROM [a-z0-9./-]+:[A-Za-z0-9._-]+' "$df" || fail "$df: unpinned FROM"
  grep -Eq '^FROM [a-z0-9./-]+(:latest)?( |$)' "$df" && fail "$df: FROM without a pinned tag"
  ok "$df: FROM pinned, USER $(grep -m1 '^USER ' "$df" | awk '{print $2}' 2>/dev/null || echo '-')"
done
# backend: files COPYed must exist in the context
for f in pyproject.toml alembic.ini alembic app; do
  [[ -e "$ROOT/smartsched/backend/$f" ]] && ok "backend context has $f" || fail "backend context missing $f"
done
for f in package.json package-lock.json public next.config.ts; do
  [[ -e "$ROOT/smartsched/frontend/$f" ]] && ok "frontend context has $f" || fail "frontend context missing $f"
done
grep -q 'output: "standalone"' "$ROOT/smartsched/frontend/next.config.ts" && ok "next.config.ts output=standalone" || fail "next.config.ts lacks output: \"standalone\""
[[ -f "$HERE/legacy/apache-crbs.conf" ]] && ok "legacy apache conf present" || fail "legacy/apache-crbs.conf missing"
[[ -f "$ROOT/index.php" ]] && ok "legacy app index.php at repo root" || fail "repo root index.php missing (legacy profile)"

echo "== shell scripts (bash -n)"
for s in "$HERE"/*.sh "$ROOT"/scripts/*.sh; do
  [[ -f "$s" ]] || continue
  if bash -n "$s"; then ok "$s"; else fail "$s"; fi
  [[ -x "$s" ]] || fail "$s is not executable"
done
# the entrypoint embedded in the backend Dockerfile (POSIX sh)
python3 - "$ROOT/smartsched/backend/Dockerfile" <<'PY' > /tmp/validate_entrypoint.sh
import re, sys
src = open(sys.argv[1]).read()
m = re.search(r"COPY --chmod=755 <<'SH' /usr/local/bin/entrypoint.sh\n(.*?)\nSH\n", src, re.S)
print(m.group(1) if m else "")
PY
if [[ -s /tmp/validate_entrypoint.sh ]] && sh -n /tmp/validate_entrypoint.sh; then ok "backend entrypoint (sh -n)"; else fail "backend entrypoint heredoc"; fi
if command -v shellcheck >/dev/null 2>&1; then shellcheck -S warning "$HERE"/*.sh "$ROOT"/scripts/*.sh && ok "shellcheck" || fail "shellcheck"; fi

echo "== nginx config"
NG="$HERE/nginx/default.conf"
if [[ -f "$NG" ]]; then
  o=$(grep -o '{' "$NG" | wc -l); c=$(grep -o '}' "$NG" | wc -l)
  [[ "$o" -eq "$c" ]] && ok "braces balanced ($o)" || fail "braces unbalanced ($o vs $c)"
  grep -q 'client_max_body_size 50m' "$NG" && ok "client_max_body_size 50m" || fail "client_max_body_size missing"
  grep -q 'proxy_buffering off' "$NG" && ok "SSE proxy_buffering off" || fail "proxy_buffering off missing"
  for up in frontend:3000 backend:8000; do grep -q "server $up" "$NG" && ok "upstream $up" || fail "upstream $up missing"; done
  if command -v nginx >/dev/null 2>&1; then
    tmp=$(mktemp -d); mkdir -p "$tmp/conf.d"; cp "$NG" "$tmp/conf.d/"
    printf 'events{} http{ include %s/conf.d/*.conf; }\n' "$tmp" > "$tmp/nginx.conf"
    nginx -t -c "$tmp/nginx.conf" >/dev/null 2>&1 && ok "nginx -t" || fail "nginx -t"
  fi
else
  fail "missing $NG"
fi

echo "== docker compose config (CLI only, no daemon needed)"
if docker compose version >/dev/null 2>&1; then
  if docker compose --env-file "$HERE/.env.example" --profile legacy -f "$HERE/docker-compose.yml" config -q 2>/tmp/validate_compose.err; then
    ok "docker compose config"
  else
    fail "docker compose config: $(cat /tmp/validate_compose.err)"
  fi
else
  echo "  skip docker compose plugin not installed"
fi

echo
if [[ $FAIL -eq 0 ]]; then echo "validate.sh: all checks passed"; else echo "validate.sh: FAILURES above"; fi
exit $FAIL
