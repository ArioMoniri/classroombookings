#!/usr/bin/env bash
# Render every docs/lottie/*-{light,dark}.json to GIF + MP4 + poster PNG in docs/images/lottie/.
# Requires: node >= 20, ffmpeg, a Chromium binary, and a scratch npm project with lottie-web + playwright-core:
#   export LOTTIE_BUILD_DEPS=/tmp/lottie-build CHROMIUM=/path/to/chrome-or-headless_shell
#   docs/lottie/build/render.sh            # all animations
#   docs/lottie/build/render.sh hero-solver # one animation, both themes
# Optional: GIF_FPS (default 30), FRAMES_DIR (default $LOTTIE_BUILD_DEPS/frames).
# Licence: same as the repository (AGPL-3.0).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="$ROOT/docs/lottie"
OUT="$ROOT/docs/images/lottie"
: "${LOTTIE_BUILD_DEPS:?set LOTTIE_BUILD_DEPS (see header)}"
FRAMES_DIR="${FRAMES_DIR:-$LOTTIE_BUILD_DEPS/frames}"
GIF_FPS="${GIF_FPS:-30}"
mkdir -p "$OUT"

# poster frame = the most informative moment of each loop
declare -A POSTER=([hero-solver]=140 [nl-to-rules]=125 [file-to-rules]=128 [precheck-fix]=96)
NAMES=("${@:-hero-solver nl-to-rules file-to-rules precheck-fix}")
NAMES=(${NAMES[@]})

for name in "${NAMES[@]}"; do
  for theme in light dark; do
    id="$name-$theme"; json="$SRC/$id.json"; fr="$FRAMES_DIR/$id"
    rm -rf "$fr" "$fr@2x"
    node "$SRC/build/render.mjs" "$json" "$fr"
    # GIF: two-pass palette (diff stats keep flat UI colours exact), infinite loop
    ffmpeg -v error -y -framerate 30 -i "$fr/f%04d.png" \
      -vf "fps=$GIF_FPS,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff:reserve_transparent=0[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" \
      -loop 0 "$OUT/$id.gif"
    # MP4: H.264, yuv420p, faststart (yuv420p needs even sizes: 720x405 is cropped to 720x404, the last row is background)
    ffmpeg -v error -y -framerate 30 -i "$fr/f%04d.png" -vf "crop=trunc(iw/2)*2:trunc(ih/2)*2:0:0" -c:v libx264 -pix_fmt yuv420p -preset slow -crf 20 \
      -movflags +faststart "$OUT/$id.mp4"
    # Poster: 2x for crisp README / reduced-motion fallback
    node "$SRC/build/render.mjs" "$json" "$fr@2x" --scale 2 --frames "${POSTER[$name]}" >/dev/null
    cp "$fr@2x/f$(printf %04d "${POSTER[$name]}").png" "$OUT/$id-poster.png"
    printf '%-26s gif %6s KB  mp4 %5s KB  poster %5s KB\n' "$id" \
      $(( $(stat -c%s "$OUT/$id.gif") / 1024 )) $(( $(stat -c%s "$OUT/$id.mp4") / 1024 )) $(( $(stat -c%s "$OUT/$id-poster.png") / 1024 ))
  done
done
