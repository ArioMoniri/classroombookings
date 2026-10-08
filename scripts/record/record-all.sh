#!/usr/bin/env bash
# Record the README journeys against the isolated real-data stack (scripts/record/stack.sh).
#
#   scripts/record/record-all.sh [OUT_DIR] [journey ...]
#
# Default OUT_DIR: ./recordings. Seeded journeys share one stack: the first run imports the real workbooks,
# makes the solver runs and saves a snapshot (stack.sh snapshot); later runs restore that snapshot
# (REC_SNAPSHOT=1), so every take starts from the same data. The seeded journeys are idempotent and run one
# after another on the same database (REC_RESTORE_EACH=1 restores the snapshot before each one instead).
# Journeys with db=fresh (import-generate) get an empty database (stack.sh up --fresh).
# Themes: REC_THEMES (default "light"). Extra env is passed to record.mjs (REC_ENGINE, REC_LANG, ...).
# A failing journey is reported and skipped. REC_KEEP_UP=1 leaves the stack running afterwards (e.g. for
# screens.mjs, which then shows the booking and the account the journeys made).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$PWD/recordings}"
shift || true
JOURNEYS=("$@")
[[ ${#JOURNEYS[@]} -eq 0 ]] && JOURNEYS=(calendar-move studio-rule-fix room-booking admin-user import-generate)
read -r -a THEMES <<<"${REC_THEMES:-light}"
WORK="${REC_WORKDIR:-${TMPDIR:-/tmp}/smartsched-rec}"
mkdir -p "$OUT"
declare -a SUMMARY=()
stack_mode=""

seeded_stack() {
  if [[ -f "$WORK/rec.snapshot.db" ]]; then
    REC_SKIP_BUILD="${REC_SKIP_BUILD:-1}" REC_SNAPSHOT=1 "$HERE/stack.sh" up
  else
    "$HERE/stack.sh" up && "$HERE/stack.sh" runs && "$HERE/stack.sh" snapshot
  fi
}

for j in "${JOURNEYS[@]}"; do
  mode=$(node -e "import('$HERE/journeys/$j.mjs').then(m=>console.log(m.default.db))")
  for theme in "${THEMES[@]}"; do
    if [[ "$mode" == fresh ]]; then
      "$HERE/stack.sh" up --fresh || { SUMMARY+=("$j/$theme: stack failed"); continue; }
      stack_mode=fresh
    elif [[ "$stack_mode" != seeded || "${REC_RESTORE_EACH:-0}" == 1 ]]; then
      seeded_stack || { SUMMARY+=("$j/$theme: stack failed"); continue; }
      stack_mode=seeded
    fi
    export REC_SKIP_BUILD=1
    if node "$HERE/record.mjs" --journey "$j" --theme "$theme" --out "$OUT/$j-$theme"; then
      SUMMARY+=("$j/$theme: ok")
    else
      SUMMARY+=("$j/$theme: FAILED (see $OUT/$j-$theme/*.failure.png)")
    fi
    # a fresh-db journey leaves its own data behind: the next seeded journey restores the snapshot
    [[ "$mode" == fresh ]] && stack_mode=""
  done
done
[[ "${REC_KEEP_UP:-0}" == 1 ]] || "$HERE/stack.sh" down
printf '%s\n' "${SUMMARY[@]}"
