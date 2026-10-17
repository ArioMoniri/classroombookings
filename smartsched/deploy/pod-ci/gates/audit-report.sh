#!/usr/bin/env bash
# Report step of the validate gate (security follow-up wave3-sec2, docs/SECURITY.md §6): known vulnerabilities in the
# pinned backend dependencies (pip-audit --no-deps on requirements.lock, python image) and in the frontend's runtime
# dependencies (npm audit --omit=dev on package-lock.json, Playwright image, lockfile only). REPORT ONLY: the
# findings are printed and never fail the gate; both need the advisory databases online (PyPI / OSV, npm registry).
# Roadmap F13: a hash-pinned lock (pip-compile --generate-hashes + pip install --require-hashes).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$WS/src"
set +e
section "dependency audit (report only): pip-audit"
pa=/w/home/pip-audit
in_python -- "python -m venv $pa >/dev/null && $pa/bin/pip install -q --disable-pip-version-check pip-audit && $pa/bin/pip-audit --no-deps -r smartsched/backend/requirements.lock"
rc=$?
[[ $rc -eq 0 ]] && echo "pip-audit: no known vulnerabilities (report only)" \
  || echo "pip-audit: findings or the audit did not complete (exit $rc); report only, the gate continues"
section "dependency audit (report only): npm audit"
in_playwright -- 'npm audit --omit=dev --package-lock-only --audit-level=high'
rc=$?
[[ $rc -eq 0 ]] && echo "npm audit --omit=dev: no high or critical advisories (report only)" \
  || echo "npm audit --omit=dev: findings or the audit did not complete (exit $rc); report only, the gate continues"
exit 0
