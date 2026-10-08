#!/usr/bin/env bash
# Make the README copies of finished recordings under stable names:
#   <journey>.mp4 (H.264, 1280 px wide, CRF 28), <journey>.webp (animated, under REC_WEBP_PUBLISH_MAX bytes,
#   default 2.6 MB) and <journey>-poster.webp
#
#   scripts/record/publish.sh RECORD_ALL_OUT_DIR [theme] [DEST]
#
# theme default light; DEST default docs/images/recordings. Build into a scratch DEST first, check the
# result, then copy it into the repository once: every re-encode committed to docs/images stays in git history.
set -euo pipefail
SRC="${1:?usage: publish.sh RECORD_ALL_OUT_DIR [theme] [DEST]}"
THEME="${2:-light}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${3:-$ROOT/docs/images/recordings}"
MAX="${REC_WEBP_PUBLISH_MAX:-2600000}"
mkdir -p "$DEST"
for dir in "$SRC"/*-"$THEME"; do
  [[ -d "$dir" ]] || continue
  name="$(basename "$dir")"
  id="${name%-"$THEME"}"
  [[ -f "$dir/$name.mp4" ]] || { echo "skip $id (no mp4)"; continue; }
  ffmpeg -hide_banner -loglevel error -y -i "$dir/$name.mp4" -vf "scale=1280:-2:flags=lanczos" -c:v libx264 \
    -preset slow -crf "${REC_PUBLISH_CRF:-28}" -pix_fmt yuv420p -movflags +faststart -an "$DEST/$id.mp4"
  # animated WebP: the first rung (width, fps, quality) under the budget
  for rung in "1000 12 55" "920 12 50" "880 10 50" "800 10 46" "720 10 42" "680 8 40"; do
    read -r w fps q <<<"$rung"
    ffmpeg -hide_banner -loglevel error -y -i "$dir/$name.mp4" -vf "fps=$fps,scale=$w:-2:flags=lanczos" \
      -c:v libwebp_anim -lossless 0 -quality "$q" -compression_level 6 -preset picture -loop 0 -an "$DEST/$id.webp"
    (( $(stat -c %s "$DEST/$id.webp") <= MAX )) && break
  done
  convert "$dir/$name.poster.png" -resize 1200x -quality 78 -define webp:method=6 "$DEST/$id-poster.webp"
  printf '%-18s mp4 %4.1f MB  webp %4.1f MB (%s px, %s fps)  %s s\n' "$id" \
    "$(echo "$(stat -c %s "$DEST/$id.mp4") / 1000000" | bc -l)" \
    "$(echo "$(stat -c %s "$DEST/$id.webp") / 1000000" | bc -l)" "$w" "$fps" \
    "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$DEST/$id.mp4" | cut -d. -f1)"
done
