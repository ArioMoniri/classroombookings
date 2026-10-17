#!/usr/bin/env bash
# Refresh every README medium in one command, from the checkout this script is in (run it at the release commit):
#
#   scripts/record/refresh.sh [SCRATCH_DIR]        (default ${TMPDIR:-/tmp}/smartsched-media)
#
#   1. record-all.sh: the seeded journeys on one real-data stack (imports, KVKK mask, solver runs; the stack stays up)
#   2. screens.mjs:   the screenshots on that same stack, so they show what the journeys made (light + dark)
#   3. record-all.sh: the fresh-database journeys (import-generate, onboarding-intake), then the stack stops
#   4. publish.sh:    the README GIF clips, MP4s and posters under stable names
#   5. copy into docs/images/{recordings,screens} once (REC_COPY=0 to only build in SCRATCH_DIR), check_readme.py
#
# Everything is built under SCRATCH_DIR first: the repository only ever gets the final files.
# Env: REC_WORKDIR, REC_API_PORT, REC_WEB_PORT (stack.sh), REC_THEMES, REC_TR_JOURNEYS, REC_PUBLISH_CLIPS, ...
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${1:-${TMPDIR:-/tmp}/smartsched-media}"
export REC_BASE_URL="${REC_BASE_URL:-http://127.0.0.1:${REC_WEB_PORT:-3610}}"
SEEDED=(reserve-panel find-room approval-flow audit-undo calendar-move studio-rule-fix room-booking admin-user
  login-dashboard run-report-fix)
FRESH=(import-generate onboarding-intake)
mkdir -p "$OUT"

REC_KEEP_UP=1 "$HERE/record-all.sh" "$OUT/takes" "${SEEDED[@]}" | tee "$OUT/record-seeded.log"
node "$HERE/screens.mjs" --out "$OUT/screens" | tee "$OUT/screens.log" || echo "screens: some shots failed, see $OUT/screens.log"
"$HERE/record-all.sh" "$OUT/takes" "${FRESH[@]}" | tee "$OUT/record-fresh.log"
"$HERE/publish.sh" "$OUT/takes" light "$OUT/recordings" | tee "$OUT/publish.log"

if [[ "${REC_COPY:-1}" == 1 ]]; then
  find "$ROOT/docs/images/recordings" -maxdepth 1 -type f \( -name '*.gif' -o -name '*.mp4' -o -name '*.png' -o -name '*.webp' \) -delete
  cp "$OUT"/recordings/* "$ROOT/docs/images/recordings/"
  find "$ROOT/docs/images/screens" -maxdepth 1 -type f \( -name '*.webp' -o -name '*.png' \) -delete
  cp "$OUT"/screens/*.webp "$ROOT/docs/images/screens/"
fi
python3 "$HERE/check_readme.py"
grep -h "FAILED\|stack failed" "$OUT"/record-*.log && exit 2 || true
