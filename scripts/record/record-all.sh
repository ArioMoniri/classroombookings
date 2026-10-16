#!/usr/bin/env bash
# Record the README journeys against the isolated real-data stack (scripts/record/stack.sh).
#
#   scripts/record/record-all.sh [OUT_DIR] [journey ...]
#
# Default OUT_DIR: ./recordings. Seeded journeys share one stack: the first run imports the real workbooks,
# masks instructor names (KVKK, kvkk_mask.py), makes the solver runs and saves a snapshot (stack.sh snapshot);
# later runs restore that snapshot (REC_SNAPSHOT=1), so every take starts from the same data. The seeded
# journeys are idempotent and run one after another on the same database (REC_RESTORE_EACH=1 restores the
# snapshot before each one instead). Journeys with db=fresh (import-generate, onboarding-intake) get an empty
# database (stack.sh up --fresh) and run last: they mask with the name list the seeded stack saved.
#
# README settings (each can be overridden): lossless screencast capture, 20 fps, a 1280x800 viewport, GIF clips
# (one per `clip` id of a journey, < 9 MB), a quicker camera. Themes: REC_THEMES (default "light").
# REC_TR_JOURNEYS (default "reserve-panel approval-flow"): also recorded with the Turkish interface.
# chat-edit is left out unless named: it needs an Anthropic key in the backend, which the stack does not have.
# A failing journey is reported and skipped. REC_KEEP_UP=1 leaves the stack running afterwards (e.g. for
# screens.mjs, which then shows the bookings, the approval rule and the account the journeys made).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$PWD/recordings}"
shift || true
JOURNEYS=("$@")
[[ ${#JOURNEYS[@]} -eq 0 ]] && JOURNEYS=(reserve-panel find-room approval-flow audit-undo calendar-move studio-rule-fix
  room-booking admin-user login-dashboard run-report-fix import-generate onboarding-intake)
read -r -a THEMES <<<"${REC_THEMES:-light}"
read -r -a TR_JOURNEYS <<<"${REC_TR_JOURNEYS-reserve-panel approval-flow}"
export REC_CAPTURE="${REC_CAPTURE:-screencast}" REC_FPS="${REC_FPS:-20}" REC_VIEWPORT="${REC_VIEWPORT:-1280x800}"
# a GIF pays for every camera move with whole new frames: fewer (bridged into one pan, none while the action is
# already in view), quicker, and a mild zoom (x1.2-1.35) whose wider view keeps a whole action in one frame
export REC_PAD="${REC_PAD:-56}" REC_GIF="${REC_GIF:-1}" REC_CAMERA_STIFFNESS="${REC_CAMERA_STIFFNESS:-220}"
export REC_CAMERA_BRIDGE_MS="${REC_CAMERA_BRIDGE_MS:-4000}" REC_CAMERA_MIN_ZOOM="${REC_CAMERA_MIN_ZOOM:-1.2}"
export REC_CAMERA_MAX_ZOOM="${REC_CAMERA_MAX_ZOOM:-1.35}"
export REC_GIF_WIDTHS="${REC_GIF_WIDTHS:-1120,1040,1000}"
# the README GIF set (publish.sh publishes the same list); the other journeys are published as MP4 + poster
export REC_GIF_CLIPS="${REC_GIF_CLIPS:-reserve-slot reserve-drag find-room approval-request approval-approve audit-undo calendar-move precheck-fix generate-report onboarding}"
export REC_BASE_URL="${REC_BASE_URL:-http://127.0.0.1:${REC_WEB_PORT:-3610}}"
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

take() { # journey theme lang
  local j="$1" theme="$2" lang="$3" dir="$OUT/$1-$2"
  [[ "$lang" == en ]] || dir="$dir-$lang"
  # the Turkish takes are published as MP4 only: no GIF clips to encode
  if REC_GIF="$([[ "$lang" == en ]] && echo "${REC_GIF}" || echo 0)" node "$HERE/record.mjs" --journey "$j" --theme "$theme" --lang "$lang" --out "$dir"; then
    SUMMARY+=("$j/$theme/$lang: ok")
  else
    SUMMARY+=("$j/$theme/$lang: FAILED (see $dir/*.failure.png)")
  fi
}

for j in "${JOURNEYS[@]}"; do
  mode=$(node -e "import('$HERE/journeys/$j.mjs').then(m=>console.log(m.default.db))")
  for theme in "${THEMES[@]}"; do
    langs=(en)
    [[ " ${TR_JOURNEYS[*]} " == *" $j "* ]] && langs+=(tr)
    for lang in "${langs[@]}"; do
      if [[ "$mode" == fresh ]]; then
        "$HERE/stack.sh" up --fresh || { SUMMARY+=("$j/$theme/$lang: stack failed"); continue; }
        stack_mode=fresh
      elif [[ "$stack_mode" != seeded || "${REC_RESTORE_EACH:-0}" == 1 ]]; then
        seeded_stack || { SUMMARY+=("$j/$theme/$lang: stack failed"); continue; }
        stack_mode=seeded
      fi
      export REC_SKIP_BUILD=1
      take "$j" "$theme" "$lang"
      # a fresh-db journey leaves its own data behind: the next journey gets a new stack
      [[ "$mode" == fresh ]] && stack_mode=""
    done
  done
done
[[ "${REC_KEEP_UP:-0}" == 1 ]] || "$HERE/stack.sh" down
printf '%s\n' "${SUMMARY[@]}"
