#!/usr/bin/env bash
# Gate: CRBS superset (docs/ROADMAP.md Phase 18). scripts/parity_check.py runs every API acceptance test of the
# parity inventory (smartsched/backend/tests/parity/inventory.py) on the real Bahar 2026 fixtures, maps the UI
# rows to the Playwright titles of e2e/bookings.spec.ts + calendar.spec.ts, prints one line per row and fails
# on any failing or uncovered row. The report goes to the run workspace ($WS/crbs-parity-report.md, /w inside
# the container), not into the source tree. The UI column ALWAYS comes from the Playwright JSON reports the
# e2e-real-<i> shard gates leave at $WS/playwright-report-<i>.json, merged (`parity.sh <shard count>`, gates.py): a
# mapped spec that was skipped, failed or not run fails its row, and a missing shard report (that shard skipped or
# killed) fails the gate. API rows still run and are reported either way.
#   PARITY_STRICT=1   declared gaps fail the gate too
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SHARDS="${1:-3}"
[[ "$SHARDS" =~ ^[1-9][0-9]*$ ]] || { echo "bad shard count $SHARDS"; exit 2; }
# RUN_TAG is <run id>-<short sha>: the report names the tested commit (the workspace has no .git)
in_python -e "PARITY_STRICT=${PARITY_STRICT:-0}" -e PARITY_COMMIT="${RUN_TAG#*-}" -e E2E_SHARDS="$SHARDS" -- '
if [ -x /w/venv/bin/python ]; then
  . /w/venv/bin/activate              # the backend gate already installed the backend here
else
  python -m venv /w/venv-parity && . /w/venv-parity/bin/activate
  pip install -q --upgrade pip
  pip install -q -e "./smartsched/backend[dev]"
fi
args=(--report /w/crbs-parity-report.md --json /w/crbs-parity.json)
for i in $(seq 1 "${E2E_SHARDS}"); do args+=(--playwright-json "/w/playwright-report-${i}.json"); done
[ "${PARITY_STRICT}" = "1" ] && args+=(--strict)
echo "==== parity_check.py ${args[*]}"
status=0
python scripts/parity_check.py "${args[@]}" || status=$?
echo "==== report (/w/crbs-parity-report.md, first lines)"
head -n 12 /w/crbs-parity-report.md 2>/dev/null || true
exit "$status"
'
