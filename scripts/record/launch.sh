#!/usr/bin/env bash
# SmartSched launch video: record lossless takes from a running stack, render the 60 fps cuts offline, encode the
# deliverables, publish the README copies. docs/launch/README.md explains the pipeline; docs/launch/RESEARCH.md why.
#
#   scripts/record/launch.sh record  OUT   record every take of story.mjs TAKES (record.mjs --engine frames)
#   scripts/record/launch.sh render  OUT   render landscape (1920x1080) + vertical (1080x1920) masters at 60 fps
#   scripts/record/launch.sh encode  OUT   MP4 (H.264 High, faststart), AV1 WebM, attach MP4, README loop, posters, VTT
#   scripts/record/launch.sh publish OUT   copy the deliverables into docs/launch/media and docs/images/recordings
#   scripts/record/launch.sh all     OUT   all four
#
# Needs a stack (scripts/record/stack.sh up, then `stack.sh runs` for the published-run scenes) at REC_BASE_URL.
# Env: REC_BASE_URL, LAUNCH_UI_LANG (en|tr, default en; captions are always English), LAUNCH_WORKERS (render pages,
# default 2), LAUNCH_ONLY (record: space-separated take journeys), LAUNCH_LOOP (README loop window "FROM-TO" seconds
# on the landscape master; default: the "reserve" scene), NICE (default 10).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CMD="${1:?usage: launch.sh record|render|encode|publish|all OUT}"
OUT="$(mkdir -p "${2:?OUT dir}" && cd "$2" && pwd)"
TAKES="$OUT/takes"; MASTER="$OUT/master"; DIST="$OUT/dist"
mkdir -p "$TAKES" "$MASTER" "$DIST"
N="nice -n ${NICE:-10}"
UI_LANG="${LAUNCH_UI_LANG:-en}"
log() { printf '\033[1;35m[launch]\033[0m %s\n' "$*"; }
size() { stat -c%s "$1"; }
mb() { awk -v b="$(size "$1")" 'BEGIN{printf "%.2f MB", b/1e6}'; }

do_record() {
  local list
  list="$(node --input-type=module -e "import { TAKES } from '$HERE/launch/story.mjs'; for (const t of TAKES) console.log(t.journey + ' ' + t.device)")"
  while read -r journey device; do
    [[ -n "${LAUNCH_ONLY:-}" && " $LAUNCH_ONLY " != *" $journey "* ]] && continue
    local dsf=2 vp=1440x810
    [[ "$device" == phone ]] && dsf=3 vp=390x844
    log "take $journey ($device, ${vp} @${dsf}x, UI $UI_LANG, captions en)"
    REC_DEVICE="$device" REC_DSF="$dsf" REC_VIEWPORT="$vp" REC_CAPTION_LANG=en \
      $N node "$HERE/record.mjs" --journey "$journey" --lang "$UI_LANG" --engine frames --out "$TAKES"
  done <<<"$list"
}

do_render() {
  for fmt in landscape vertical; do
    log "render $fmt master (60 fps, lossless)"
    $N node "$HERE/launch/render.mjs" --takes "$TAKES" --format "$fmt" --out "$MASTER/launch-$fmt.mkv"
  done
}

# H.264 under a byte budget: the lowest CRF of the ladder that fits
h264() { # in out maxbytes vf fps
  local in="$1" out="$2" max="$3" vf="$4" fps="$5" crf
  for crf in 18 20 22 24 26 28; do
    $N ffmpeg -hide_banner -loglevel error -y -i "$in" -vf "$vf,format=yuv420p" -r "$fps" -c:v libx264 -profile:v high -preset slow -crf "$crf" \
      -x264-params "keyint=$((fps * 4)):min-keyint=$fps" -movflags +faststart -an "$out"
    [[ $(size "$out") -le $max ]] && { log "$(basename "$out"): crf $crf, $(mb "$out")"; return 0; }
  done
  log "WARNING $(basename "$out") is over budget at crf 28: $(mb "$out")"
}

do_encode() {
  local L="$MASTER/launch-landscape.mkv" V="$MASTER/launch-vertical.mkv"
  # 1. the launch video: 1920x1080 60 fps H.264 High (plays everywhere), <= 25 MB
  h264 "$L" "$DIST/smartsched-launch.mp4" 25000000 "scale=1920:1080:flags=lanczos" 60
  # 2. AV1 in WebM (SVT-AV1, 10-bit): the same picture at a fraction of the bytes, for browsers that play AV1
  $N ffmpeg -hide_banner -loglevel error -y -i "$L" -vf "format=yuv420p10le" -c:v libsvtav1 -preset 5 -crf 34 -g 240 \
    -svtav1-params "tune=0" -an "$DIST/smartsched-launch-av1.webm"
  log "smartsched-launch-av1.webm: $(mb "$DIST/smartsched-launch-av1.webm")"
  # 3. a copy for a GitHub user-attachments upload on a free plan (10 MB limit): 1920x1080 at 30 fps
  h264 "$L" "$DIST/smartsched-launch-attach.mp4" 9800000 "scale=1920:1080:flags=lanczos" 30
  # 4. the vertical cut for phones and social, <= 25 MB
  [[ -f "$V" ]] && h264 "$V" "$DIST/smartsched-launch-vertical.mp4" 25000000 "scale=1080:1920:flags=lanczos" 60
  # 5. captions sidecar (WebVTT) from the render plan
  python3 -I - "$MASTER/launch-landscape.plan.json" "$DIST/smartsched-launch.en.vtt" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1]))
def ts(ms):
    ms = int(ms); return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}.{ms%1000:03d}"
with open(sys.argv[2], "w") as f:
    f.write("WEBVTT\n\n")
    for i, c in enumerate(plan["captions"], 1):
        f.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n")
PY
  # 6. README loop: animated WebP (GitHub serves repo .webp as image/webp; see RESEARCH.md), <= 5 MB, >= 1280 px
  local win="${LAUNCH_LOOP:-}"
  if [[ -z "$win" ]]; then
    win="$(python3 -I -c 'import json,sys; p=json.load(open(sys.argv[1])); s=[x for x in p["scenes"] if x["id"]=="reserve"][0]; a=s["start"]/1000+0.5; print(f"{a:.2f}-{min(a+10, s["end"]/1000-0.3):.2f}")' "$MASTER/launch-landscape.plan.json")"
  fi
  local from="${win%-*}" to="${win#*-}" q w fps
  for spec in "1280 30 80" "1280 30 70" "1280 30 60" "1280 24 60" "1280 24 50"; do
    read -r w fps q <<<"$spec"
    $N ffmpeg -hide_banner -loglevel error -y -ss "$from" -to "$to" -i "$L" -vf "fps=$fps,scale=$w:-2:flags=lanczos" -c:v libwebp_anim \
      -lossless 0 -quality "$q" -compression_level 6 -preset picture -loop 0 -an "$DIST/smartsched-loop.webp"
    [[ $(size "$DIST/smartsched-loop.webp") -le 5000000 ]] && break
  done
  log "smartsched-loop.webp: ${w}px ${fps} fps q$q, $(mb "$DIST/smartsched-loop.webp") (window $from-$to s)"
  # animated AVIF of the same loop (smaller; not used in the README until GitHub's raw host is checked for .avif)
  $N ffmpeg -hide_banner -loglevel error -y -ss "$from" -to "$to" -i "$L" -vf "fps=30,scale=1280:-2:flags=lanczos,format=yuv420p" -c:v libsvtav1 -preset 6 -crf 36 \
    -an -f avif "$DIST/smartsched-loop.avif" 2>/dev/null && log "smartsched-loop.avif: $(mb "$DIST/smartsched-loop.avif")" || log "animated AVIF not written (ffmpeg without the avif muxer)"
  # 7. posters (the loop's first frame, the launch video's title frame) as PNG at full size
  $N ffmpeg -hide_banner -loglevel error -y -ss "$from" -i "$L" -frames:v 1 -vf "scale=1280:-2:flags=lanczos" "$DIST/smartsched-loop-poster.png"
  $N ffmpeg -hide_banner -loglevel error -y -ss 3.4 -i "$L" -frames:v 1 "$DIST/smartsched-launch-poster.png"
  [[ -f "$V" ]] && $N ffmpeg -hide_banner -loglevel error -y -ss 3.4 -i "$V" -frames:v 1 -vf "scale=540:-2:flags=lanczos" "$DIST/smartsched-launch-vertical-poster.png"
  # report
  for f in "$DIST"/*; do
    printf '%-40s %10s  %s\n' "$(basename "$f")" "$(mb "$f")" "$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,width,height,avg_frame_rate,bit_rate -show_entries format=duration -of compact=p=0:nk=1 "$f" 2>/dev/null | tr '\n' ' ')"
  done | tee "$DIST/REPORT.txt"
}

do_publish() {
  local media="$ROOT/docs/launch/media"
  mkdir -p "$media"
  cp "$DIST"/smartsched-launch.mp4 "$DIST"/smartsched-launch-av1.webm "$DIST"/smartsched-launch-vertical.mp4 "$DIST"/smartsched-launch.en.vtt \
     "$DIST"/smartsched-launch-poster.png "$DIST"/smartsched-launch-vertical-poster.png "$DIST"/smartsched-loop.webp "$DIST"/smartsched-loop-poster.png "$media/"
  log "published to docs/launch/media (attach copy and AVIF stay in $DIST)"
}

case "$CMD" in
  record) do_record ;;
  render) do_render ;;
  encode) do_encode ;;
  publish) do_publish ;;
  all) do_record; do_render; do_encode; do_publish ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
