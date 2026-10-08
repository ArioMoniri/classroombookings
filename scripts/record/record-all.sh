#!/usr/bin/env bash
# Record every journey in light and dark against a fresh isolated stack.
#
#   scripts/record/record-all.sh [OUT_DIR] [journey ...]
#
# Default OUT_DIR: ./recordings. The import journey needs an empty database, so the stack is
# restarted with --fresh for it and then re-seeded for the rest. Extra env is passed through to
# record.mjs (REC_ENGINE, REC_LANG, RECORDLY_BIN, ...). A failing journey is reported and skipped.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$PWD/recordings}"
shift || true
JOURNEYS=("$@")
[[ ${#JOURNEYS[@]} -eq 0 ]] && JOURNEYS=(import-planning login-dashboard generator-studio run-report-fix calendar-drag chat-edit teacher-booking)
THEMES=(${REC_THEMES:-light dark})
mkdir -p "$OUT"
declare -a SUMMARY=()

for j in "${JOURNEYS[@]}"; do
  mode=$(node -e "import('$HERE/journeys/$j.mjs').then(m=>console.log(m.default.db))")
  for theme in "${THEMES[@]}"; do
    # every recording starts from the same data: re-create the stack (REC_SKIP_BUILD reuses the build)
    if [[ "$mode" == fresh ]]; then "$HERE/stack.sh" up --fresh; else REC_SKIP_BUILD=1 "$HERE/stack.sh" up; fi \
      || { SUMMARY+=("$j/$theme: stack failed"); continue; }
    export REC_SKIP_BUILD=1
    if node "$HERE/record.mjs" --journey "$j" --theme "$theme" --out "$OUT/$j-$theme"; then
      SUMMARY+=("$j/$theme: ok")
    else
      SUMMARY+=("$j/$theme: FAILED (see $OUT/$j-$theme/*.failure.png)")
    fi
  done
done
"$HERE/stack.sh" down
printf '%s\n' "${SUMMARY[@]}"
