#!/usr/bin/env bash
# Static validation of the deployment files (no Docker daemon needed).
#   - YAML syntax of docker-compose.yml and the CI workflow (python + PyYAML)
#   - every ${VAR} referenced by docker-compose.yml is declared in .env.example; no secrets committed;
#     no inline comments after empty values (compose would read the comment as the value)
#   - every build context / dockerfile / bind-mount source referenced by compose exists
#   - every image is pinned to a patch release (no :latest, no bare major tags)
#   - Dockerfiles: pinned FROM (ARG defaults resolved), non-root USER in the final stage, COPY sources
#     exist in the build context
#   - bash -n / sh -n on every shell script (+ shellcheck when installed), nginx config sanity
#     (+ nginx -t when nginx is installed), `docker compose config` when the CLI plugin is installed
#   - no mock API / demo login anywhere in the shipped frontend: sources, image and compose config, and
#     the production build (.next/standalone) when one exists
# Exit code 1 on any failure. Usage: smartsched/deploy/validate.sh
#   smartsched/deploy/validate.sh --no-mock-build DIR   only the build check, on DIR (e.g. .next/standalone);
#                                                       bash + grep only (used by the pod CI e2e-real gate)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAIL=0
ok()   { printf '  \033[32mok\033[0m   %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; FAIL=1; }
note() { printf '  note %s\n' "$*"; }

# A production build must not contain the MSW mock API, its handlers or the demo-login copy.
NO_MOCK_PATTERNS=('node_modules/msw' 'mocks/handlers' 'mockServiceWorker' 'NEXT_PUBLIC_API_MOCK' 'password admin' 'password \\?"admin\\?"' 'Demo mode' 'Demo modu')
check_no_mock_build() {
  local dir="$1" pat hits
  if [[ ! -d "$dir" ]]; then fail "no build at $dir"; return; fi
  for pat in "${NO_MOCK_PATTERNS[@]}"; do
    hits=$(grep -rlE --exclude-dir=.cache -- "$pat" "$dir" 2>/dev/null | head -5)
    if [[ -n "$hits" ]]; then fail "build $dir contains '$pat': $(echo "$hits" | tr '\n' ' ')"; else ok "build has no '$pat'"; fi
  done
  # an msw package or a mocks/ chunk directory in the traced output
  hits=$(find "$dir" \( -path '*/node_modules/msw' -o -path '*/node_modules/@mswjs' -o -name 'handlers*.js' -path '*mocks*' \) -print 2>/dev/null | head -5)
  if [[ -n "$hits" ]]; then fail "build $dir ships mock files: $(echo "$hits" | tr '\n' ' ')"; else ok "build ships no msw package or mocks/ files"; fi
}
if [[ "${1:-}" == "--no-mock-build" ]]; then
  echo "== production build: no mock / demo code"
  check_no_mock_build "${2:?usage: validate.sh --no-mock-build DIR}"
  exit $FAIL
fi

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import yaml' 2>/dev/null; then
  echo "validate.sh needs PyYAML: pip install pyyaml" >&2
  exit 2
fi
SHELL_SCRIPTS=("$HERE"/*.sh "$ROOT"/scripts/*.sh)
POSIX_SCRIPTS=("$ROOT/smartsched/backend/docker-entrypoint.sh")

echo "== YAML syntax"
for f in "$HERE/docker-compose.yml" "$HERE/docker-compose.caddy.yml" "$ROOT/.github/workflows/smartsched.yml"; do
  [[ -f "$f" ]] || { fail "missing $f"; continue; }
  # compose's !override / !reset tags are accepted (constructed as plain values)
  if "$PY" -c "
import sys, yaml
class L(yaml.SafeLoader): pass
L.add_multi_constructor('!', lambda loader, suffix, node: loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode) else (loader.construct_mapping(node) if isinstance(node, yaml.MappingNode) else loader.construct_scalar(node)))
yaml.load(open(sys.argv[1]), Loader=L)
" "$f" 2>"$TMP/yaml.err"; then ok "${f#"$ROOT"/}"; else fail "$f: $(cat "$TMP/yaml.err")"; fi
done

echo "== .env.example vs docker-compose*.yml"
"$PY" - "$HERE" <<'PY' || FAIL=1
import re, sys
from pathlib import Path
here = Path(sys.argv[1])
compose = "\n".join(f.read_text() for f in sorted(here.glob("docker-compose*.yml")))
env_text = (here / ".env.example").read_text()
declared = {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", env_text, re.M)}
# ${VAR}, ${VAR:-default}, ${VAR:?msg}; skip $${...} (literal for the container shell)
used = set(re.findall(r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)", compose))
missing = sorted(used - declared)
rc = 0
for v in missing:
    print(f"  FAIL ${v} used in docker-compose*.yml but not declared in .env.example"); rc = 1
for v in sorted(declared - used):
    print(f"  note ${v} declared in .env.example but unused by compose (read by deploy.sh)")
print(f"  ok   {len(used)} variables used, {len(declared)} declared, {len(missing)} missing")
secret_keys = ("APP_SECRET", "JWT_SECRET", "AUTH_SECRET", "POSTGRES_PASSWORD", "ADMIN_PASSWORD",
               "CRBS_DB_PASSWORD", "CRBS_DB_ROOT_PASSWORD", "ANTHROPIC_API_KEY")
leaked = [k for k, v in re.findall(r"^([A-Z_]+)=(\S*)", env_text, re.M) if k in secret_keys and v not in ("", "__GENERATE__")]
if leaked:
    print(f"  FAIL .env.example contains concrete secret values for {leaked}"); rc = 1
else:
    print("  ok   no secrets committed in .env.example")
inline = [ln for ln in env_text.splitlines() if re.match(r"^[A-Z_]+=", ln) and re.search(r"\s#", ln)]
if inline:
    for ln in inline:
        print(f"  FAIL inline comment (compose keeps it as the value when the value is empty): {ln}")
    rc = 1
else:
    print("  ok   no inline comments after values")
sys.exit(rc)
PY

echo "== compose: paths and image pins"
"$PY" - "$HERE" <<'PY' || FAIL=1
import re, sys, yaml
from pathlib import Path
here = Path(sys.argv[1])
root = here.parent.parent
doc = yaml.safe_load((here / "docker-compose.yml").read_text())
rc = 0
PIN = re.compile(r"^[\w./-]+:\d+\.\d+(\.\d+)?[\w.-]*$")
def check(p: Path, what: str) -> None:
    global rc
    if p.exists():
        print(f"  ok   {what}: {p.relative_to(root)}")
    else:
        print(f"  FAIL {what} missing: {p}"); rc = 1
for name, svc in doc["services"].items():
    build = svc.get("build")
    image = svc.get("image", "")
    if isinstance(build, dict):
        ctx = (here / build.get("context", ".")).resolve()
        check(ctx, f"{name} build context")
        df = (ctx / build.get("dockerfile", "Dockerfile")).resolve()
        check(df, f"{name} dockerfile")
        if not (ctx / ".dockerignore").exists() and not Path(str(df) + ".dockerignore").exists():
            print(f"  FAIL {name}: no .dockerignore for context {ctx}"); rc = 1
    elif not PIN.match(image):
        print(f"  FAIL {name}: image '{image}' is not pinned to a version"); rc = 1
    else:
        print(f"  ok   {name}: image {image}")
    if "restart" not in svc:
        print(f"  FAIL {name}: no restart policy"); rc = 1
    if "healthcheck" not in svc:
        print(f"  FAIL {name}: no healthcheck"); rc = 1
    for vol in svc.get("volumes", []):
        src = vol.split(":")[0] if isinstance(vol, str) else vol.get("source", "")
        if src.startswith(("./", "../", "/")):
            check((here / src).resolve(), f"{name} bind mount")
        elif src not in (doc.get("volumes") or {}):
            print(f"  FAIL {name}: named volume {src} not declared"); rc = 1
print(f"  ok   named volumes: {', '.join(doc.get('volumes') or {})}")
sys.exit(rc)
PY

echo "== Dockerfiles (pinned FROM, non-root USER, COPY sources)"
"$PY" - "$ROOT" <<'PY' || FAIL=1
import re, sys
from pathlib import Path
root = Path(sys.argv[1])
targets = [
    (root / "smartsched/backend/Dockerfile", root / "smartsched/backend"),
    (root / "smartsched/frontend/Dockerfile", root / "smartsched/frontend"),
    (root / "smartsched/deploy/legacy/Dockerfile", root),
]
PIN = re.compile(r"^[\w./-]+:\d+\.\d+(\.\d+)?[\w.-]*$")
rc = 0
for df, ctx in targets:
    rel = df.relative_to(root)
    if not df.exists():
        print(f"  FAIL missing {rel}"); rc = 1; continue
    text = re.sub(r"\\\n", " ", df.read_text())
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    args: dict[str, str] = {}
    stages: set[str] = set()
    final_user = None
    for ln in lines:
        m = re.match(r"ARG\s+(\w+)=(\S+)", ln)
        if m:
            args.setdefault(m.group(1), m.group(2))
        m = re.match(r"FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", ln, re.I)
        if m:
            ref = re.sub(r"\$\{?(\w+)\}?", lambda x: args.get(x.group(1), x.group(0)), m.group(1))
            final_user = None
            if ref in stages:
                pass
            elif not PIN.match(ref):
                print(f"  FAIL {rel}: FROM {m.group(1)} -> '{ref}' is not pinned to a version"); rc = 1
            else:
                print(f"  ok   {rel}: FROM {ref}")
            if m.group(2):
                stages.add(m.group(2))
        m = re.match(r"USER\s+(\S+)", ln)
        if m:
            final_user = m.group(1)
        m = re.match(r"COPY\s+(.*)", ln)
        if m and "--from=" not in m.group(1) and "<<" not in m.group(1):
            parts = [p for p in m.group(1).split() if not p.startswith("--")]
            for src in parts[:-1]:
                if src.endswith("*"):
                    continue  # optional glob (e.g. requirements.lock*)
                if not (ctx / src).exists():
                    print(f"  FAIL {rel}: COPY source {src} not in build context {ctx.relative_to(root) or '.'}"); rc = 1
    if final_user in (None, "root", "0"):
        print(f"  FAIL {rel}: final stage runs as root (add USER)"); rc = 1
    else:
        print(f"  ok   {rel}: final stage USER {final_user}")
fe = (root / "smartsched/frontend/next.config.ts").read_text()
if re.search(r"output:\s*[\"']standalone[\"']", fe):
    print("  ok   next.config.ts output: standalone")
else:
    print("  FAIL next.config.ts lacks output: 'standalone'"); rc = 1
sys.exit(rc)
PY

echo "== shell scripts"
for s in "${SHELL_SCRIPTS[@]}"; do
  [[ -f "$s" ]] || continue
  if bash -n "$s"; then ok "bash -n ${s#"$ROOT"/}"; else fail "bash -n $s"; fi
  [[ -x "$s" ]] || fail "$s is not executable"
done
for s in "${POSIX_SCRIPTS[@]}"; do
  [[ -f "$s" ]] || { fail "missing $s"; continue; }
  if sh -n "$s"; then ok "sh -n ${s#"$ROOT"/}"; else fail "sh -n $s"; fi
  [[ -x "$s" ]] || fail "$s is not executable"
done
if command -v shellcheck >/dev/null 2>&1; then
  if shellcheck -S warning "${SHELL_SCRIPTS[@]}" && shellcheck -S warning -s sh "${POSIX_SCRIPTS[@]}"; then ok "shellcheck"; else fail "shellcheck"; fi
else
  note "shellcheck not installed; skipped"
fi

echo "== nginx config"
NG="$HERE/nginx/default.conf"
if [[ -f "$NG" ]]; then
  o=$(grep -o '{' "$NG" | wc -l); c=$(grep -o '}' "$NG" | wc -l)
  [[ "$o" -eq "$c" ]] && ok "braces balanced ($o)" || fail "braces unbalanced ($o vs $c)"
  grep -q 'client_max_body_size 50m' "$NG" && ok "client_max_body_size 50m" || fail "client_max_body_size missing"
  grep -q 'proxy_buffering off' "$NG" && ok "SSE proxy_buffering off" || fail "proxy_buffering off missing"
  grep -q 'listen 8080' "$NG" && ok "listens on 8080 (unprivileged image)" || fail "nginx must listen on 8080"
  for up in frontend:3000 backend:8000; do grep -q "server $up" "$NG" && ok "upstream $up" || fail "upstream $up missing"; done
  if command -v nginx >/dev/null 2>&1; then
    mkdir -p "$TMP/nginx/conf.d"
    # service names only resolve inside compose: map them to localhost for the syntax check
    sed 's/server frontend:3000/server 127.0.0.1:3000/; s/server backend:8000/server 127.0.0.1:8000/' "$NG" > "$TMP/nginx/conf.d/default.conf"
    printf 'pid %s/nginx.pid; error_log stderr; events {} http { access_log off; client_body_temp_path %s/cbt; proxy_temp_path %s/pt; fastcgi_temp_path %s/ft; uwsgi_temp_path %s/ut; scgi_temp_path %s/st; include %s/conf.d/*.conf; }\n' "$TMP" "$TMP" "$TMP" "$TMP" "$TMP" "$TMP" "$TMP/nginx" > "$TMP/nginx/nginx.conf"
    # -p/-e keep nginx away from /var/log/nginx and the compiled-in prefix, so the check runs as a normal user
    if nginx -t -q -p "$TMP" -e stderr -c "$TMP/nginx/nginx.conf" 2>"$TMP/nginx.err"; then ok "nginx -t"; else fail "nginx -t: $(cat "$TMP/nginx.err")"; fi
  else
    note "nginx not installed; nginx -t skipped"
  fi
else
  fail "missing $NG"
fi

echo "== frontend: no mock API or demo login"
FE="$ROOT/smartsched/frontend"
[[ -e "$FE/src/mocks" ]] && fail "smartsched/frontend/src/mocks exists (mock handlers must not live in app code)" || ok "no src/mocks"
# app code = everything under src/ except tests and the test fixtures in src/test/
hits=$(grep -rlE --include='*.ts' --include='*.tsx' -e 'from "msw' -e '@/mocks' -e 'NEXT_PUBLIC_API_MOCK' -e 'isMockMode' "$FE/src" 2>/dev/null)
[[ -n "$hits" ]] && fail "mock references in frontend sources: $hits" || ok "frontend sources: no msw / @/mocks / NEXT_PUBLIC_API_MOCK"
hits=$(grep -rlE --include='*.ts' --include='*.tsx' -e 'from "@/test/' "$FE/src" 2>/dev/null | grep -vE '\.test\.tsx?$|/src/test/' || true)
[[ -n "$hits" ]] && fail "app code imports test fixtures: $hits" || ok "app code does not import src/test/"
if "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(1 if "msw" in d.get("dependencies",{}) or "msw" in d.get("devDependencies",{}) else 0)' "$FE/package.json"; then
  ok "package.json does not depend on msw"
else
  fail "package.json depends on msw"
fi
hits=$(grep -lE 'NEXT_PUBLIC_API_MOCK|demoHint' "$FE/Dockerfile" "$FE/.env.example" "$HERE/docker-compose.yml" "$HERE/.env.example" "$FE/messages/en.json" "$FE/messages/tr.json" 2>/dev/null)
[[ -n "$hits" ]] && fail "mock switch / demo hint in: $hits" || ok "Dockerfile, compose, .env examples and messages: no mock switch or demo hint"
if [[ -d "$FE/.next/standalone" ]]; then
  check_no_mock_build "$FE/.next/standalone"
else
  note "no frontend build at smartsched/frontend/.next/standalone; build check skipped (pod CI e2e-real runs it)"
fi

echo "== docker compose config (CLI only, no daemon needed)"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  if docker compose --env-file "$HERE/.env.example" --profile legacy -f "$HERE/docker-compose.yml" config -q 2>"$TMP/compose.err"; then
    ok "docker compose config ($(docker compose version --short 2>/dev/null))"
  else
    fail "docker compose config: $(cat "$TMP/compose.err")"
  fi
  if TLS_DOMAIN=smartsched.example.org ACME_EMAIL=ops@example.org docker compose --env-file "$HERE/.env.example" \
       -f "$HERE/docker-compose.yml" -f "$HERE/docker-compose.caddy.yml" config -q 2>"$TMP/compose.err"; then
    ok "docker compose config with the Caddy TLS override"
  else
    fail "docker compose config (caddy override): $(cat "$TMP/compose.err")"
  fi
else
  note "docker compose plugin not installed; skipped"
fi

echo
if [[ $FAIL -eq 0 ]]; then echo "validate.sh: all checks passed"; else echo "validate.sh: FAILURES above"; fi
exit $FAIL
