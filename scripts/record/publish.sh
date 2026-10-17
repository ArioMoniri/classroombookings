#!/usr/bin/env bash
# Make the README copies of finished recordings under stable names in DEST (default docs/images/recordings):
#   <clip>.gif         the README GIF clips (6-12 s, >= 1000 px, 20 fps, < 9 MB; made by polish.mjs from the
#                      lossless master), only the clips listed in REC_PUBLISH_CLIPS (default: the README set below)
#   <journey>.mp4      the whole take, H.264 1280 px wide, CRF 26 (GitHub does not play an MP4 inline; each GIF links to it)
#   <journey>-poster.png  a still from the step marked `poster`, 1200 px, 256 colours
# Takes in Turkish (record-all.sh REC_TR_JOURNEYS) are published as <journey>-tr.mp4 (no GIF).
#
#   scripts/record/publish.sh RECORD_ALL_OUT_DIR [theme] [DEST]
#
# Build into a scratch DEST first, check the result, then copy it into the repository once: every re-encode
# committed to docs/images stays in git history.
set -euo pipefail
SRC="${1:?usage: publish.sh RECORD_ALL_OUT_DIR [theme] [DEST]}"
THEME="${2:-light}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${3:-$ROOT/docs/images/recordings}"
# the README set: fewer, better clips (the other journeys are published as MP4 + poster)
read -r -a CLIPS <<<"${REC_PUBLISH_CLIPS:-${REC_GIF_CLIPS:-reserve-slot reserve-drag find-room approval-request approval-approve audit-undo calendar-move precheck-fix generate-report onboarding}}"
mkdir -p "$DEST"
mb() { awk -v b="$1" 'BEGIN { printf "%.2f", b / 1000000 }'; }
for dir in "$SRC"/*-"$THEME" "$SRC"/*-"$THEME"-tr; do
  [[ -d "$dir" ]] || continue
  name="$(basename "$dir")"
  suffix=""; [[ "$name" == *-tr ]] && suffix="-tr"
  id="${name%-"$THEME$suffix"}"
  [[ -f "$dir/$name.mp4" ]] || { echo "skip $name (no mp4)"; continue; }
  ffmpeg -hide_banner -loglevel error -y -i "$dir/$name.mp4" -vf "scale=1280:-2:flags=lanczos" -c:v libx264 \
    -preset slow -crf "${REC_PUBLISH_CRF:-26}" -pix_fmt yuv420p -movflags +faststart -an "$DEST/$id$suffix.mp4"
  [[ -z "$suffix" ]] && convert "$dir/$name.poster.png" -resize 1200x -colors 256 "PNG8:$DEST/$id-poster.png"
  printf '%-34s %6s MB  %5s s\n' "$id$suffix.mp4" "$(mb "$(stat -c %s "$DEST/$id$suffix.mp4")")" \
    "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$DEST/$id$suffix.mp4" | cut -d. -f1)"
  for gif in "$dir/$name".*.gif; do
    [[ -f "$gif" ]] || continue
    clip="${gif##*/"$name".}"; clip="${clip%.gif}"
    [[ " ${CLIPS[*]} " == *" $clip "* ]] || continue
    cp "$gif" "$DEST/$clip$suffix.gif"
    # frame delays in 1/100 s: 20 fps = 5 each (longer ones are held, unchanged frames)
    wh="$(ffprobe -v error -select_streams v -show_entries stream=width,height -of csv=p=0:s=x "$gif")"
    delays="$(ffprobe -v error -select_streams v -show_entries packet=duration -of csv=p=0 "$gif" | sort -n | uniq -c | awk '{printf "%sx%s ", $1, $2}')"
    printf '%-34s %6s MB  %s  delays(count x 1/100 s): %s\n' "$clip$suffix.gif" "$(mb "$(stat -c %s "$gif")")" "$wh" "$delays"
  done
done
