#!/usr/bin/env bash
# Gate: planner-level validation on the real workbooks (tools/validate_planner.py). Imports the Bahar, Güz and
# Final 2026 fixtures with the importers, solves Bahar week 3, Güz week 3, the Final exams and the full Bahar
# term exactly like POST /runs, and checks every stored run against the raw request rows
# (app/services/planner_check.py). Fails on any planner-level violation (an unwaived finding, or an accepted
# exception the run does not report). JSON lines go to the run workspace ($WS/validate-planner.json).
#   PLANNER_TIME_LIMIT   solver time limit per run in seconds (default 120)
#   PLANNER_INSTANCES    space-separated instances (default: bahar_w3 guz_w3 final bahar_term)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_python -e "PLANNER_TIME_LIMIT=${PLANNER_TIME_LIMIT:-120}" \
  -e "PLANNER_INSTANCES=${PLANNER_INSTANCES:-bahar_w3 guz_w3 final bahar_term}" -e "GATE_CPUS=${GATE_CPUS}" -- '
if [ -x /w/venv/bin/python ]; then
  . /w/venv/bin/activate              # the backend gate already installed the backend here
else
  python -m venv /w/venv-planner && . /w/venv-planner/bin/activate
  pip install -q --upgrade pip
  pip install -q -e "./smartsched/backend[dev]"
fi
cd smartsched/backend
rm -rf /w/validate-planner.json /w/validate-planner-cache  # a fresh import of this commit
echo "==== validate_planner ${PLANNER_INSTANCES} (time limit ${PLANNER_TIME_LIMIT}s, ${GATE_CPUS} workers)"
start=$(date +%s)
status=0
# shellcheck disable=SC2086
python -m tools.validate_planner --instances ${PLANNER_INSTANCES} --time-limit "${PLANNER_TIME_LIMIT}" \
  --workers "${GATE_CPUS%.*}" --cache-dir /w/validate-planner-cache --out /w/validate-planner.json || status=$?
echo "==== summary ($(( $(date +%s) - start ))s)"
python - <<"PY" || true
import json
for line in open("/w/validate-planner.json", encoding="utf-8"):
    r = json.loads(line)
    args = (r["instance"], r["status"], r["events_placed"], r["events_total"], r["wall_s"], r["planner"].get("violations"))
    print("%-12s %-17s placed %s/%s wall %ss violations %s" % args)
PY
exit "$status"
'
