#!/usr/bin/env bash
# Copy finished recordings into docs/images/recordings under stable names:
#   <journey>.mp4 (H.264), <journey>.webp (animated, < 4 MB), <journey>-poster.webp
#
#   scripts/record/publish.sh RECORD_ALL_OUT_DIR [theme]     (theme default: light)
set -euo pipefail
SRC="${1:?usage: publish.sh RECORD_ALL_OUT_DIR [theme]}"
THEME="${2:-light}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="$ROOT/docs/images/recordings"
mkdir -p "$DEST"
for dir in "$SRC"/*-"$THEME"; do
  [[ -d "$dir" ]] || continue
  name="$(basename "$dir")"
  id="${name%-"$THEME"}"
  [[ -f "$dir/$name.mp4" && -f "$dir/$name.webp" ]] || { echo "skip $id (no mp4/webp)"; continue; }
  cp "$dir/$name.mp4" "$DEST/$id.mp4"
  cp "$dir/$name.webp" "$DEST/$id.webp"
  convert "$dir/$name.poster.png" -resize 1200x -quality 80 -define webp:method=6 "$DEST/$id-poster.webp"
  printf '%-18s mp4 %5.1f MB  webp %4.1f MB  %s s\n' "$id" \
    "$(echo "$(stat -c %s "$DEST/$id.mp4") / 1000000" | bc -l)" \
    "$(echo "$(stat -c %s "$DEST/$id.webp") / 1000000" | bc -l)" \
    "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$DEST/$id.mp4" | cut -d. -f1)"
done
