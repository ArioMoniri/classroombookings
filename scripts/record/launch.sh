#!/usr/bin/env bash
# SmartSched launch video: record lossless takes from a running stack, render the 60 fps cuts offline, encode the
# deliverables, publish the README copies. docs/launch/README.md explains the pipeline; docs/launch/RESEARCH.md why.
#
#   scripts/record/launch.sh record  OUT   record every take of story.mjs TAKES (record.mjs --engine frames)
#   scripts/record/launch.sh render  OUT   render landscape (1920x1080) + vertical (1080x1920) masters at 60 fps
#   scripts/record/launch.sh encode  OUT   MP4 (H.264 High, faststart), AV1 WebM, attach MP4, README loop, posters, VTT
#   scripts/record/launch.sh check   OUT   quality gate (launch/quality.py): judder, freezes, PSNR/VMAF against the master
#   scripts/record/launch.sh publish OUT   copy the deliverables into docs/launch/media and docs/images/recordings
#   scripts/record/launch.sh clips   OUT   README feature clips (story.mjs CLIPS): record, render 1600x960 (phone 720x1280)
#                                          60 fps, encode <id>.webp (1280 px / 30 fps, <= 4 MB), <id>.gif (fallback, <= 9 MB),
#                                          <take>.mp4 (H.264) + <take>-poster.png into OUT/clips; `publish` copies them
#   scripts/record/launch.sh hero    OUT   README hero loop (story.mjs buildHero: desktop moments of the launch and clip
#                                          takes): 1920x1080 60 fps master -> smartsched-hero.webp (1280x720, 30 fps, <= 3 MB)
#   scripts/record/launch.sh all     OUT   record, render, encode, check, clips, hero, publish (only when the gate passes)
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
    local dsf=${LAUNCH_DSF:-1.5} vp=1440x810
    [[ "$device" == phone ]] && dsf=${LAUNCH_PHONE_DSF:-2} vp=390x844
    log "take $journey ($device, ${vp} @${dsf}x, UI $UI_LANG, captions en)"
    REC_DEVICE="$device" REC_DSF="$dsf" REC_VIEWPORT="$vp" REC_CAPTION_LANG=en \
      $N node "$HERE/record.mjs" --journey "$journey" --lang "$UI_LANG" --engine frames --out "$TAKES" </dev/null || log "take $journey FAILED (see $TAKES/*.failure.png); the other takes go on"
  done <<<"$list"
}

do_render() {
  for fmt in landscape vertical; do
    log "render $fmt master (60 fps, lossless)"
    $N node "$HERE/launch/render.mjs" --takes "$TAKES" --format "$fmt" --out "$MASTER/launch-$fmt.mkv"
  done
}

# H.264 under a byte budget: the lowest CRF of the ladder that fits. The masters are 60 fps Matroska with millisecond
# timestamps (16, 33, 50 ms ...): setpts=N/60/TB puts every frame back on the exact 1/60 s grid first, so -r 60 keeps
# each frame once (without it, -r resampled the rounded times and could repeat or drop one) and -r 30 takes every other. UI text is flat colour with hard edges: -tune
# animation (more reference frames, deblocking off a little) and a low CRF keep it sharp; 1080p60 at crf 15 is about
# 6-10 Mbit/s for this cut. The ladder only climbs when a budget is hit.
h264() { # in out maxbytes vf fps "crf ladder"
  local in="$1" out="$2" max="$3" vf="$4" fps="$5" ladder="${6:-15 16 17 18 20}" crf last
  for crf in $ladder; do
    last=$crf
    $N ffmpeg -nostdin -hide_banner -loglevel error -y -i "$in" -vf "setpts=N/60/TB,$vf:out_color_matrix=bt709:out_range=tv,format=yuv420p" -r "$fps" -c:v libx264 -profile:v high -preset slow -tune animation -crf "$crf" \
      -x264-params "keyint=$((fps * 4)):min-keyint=$fps" -color_primaries bt709 -color_trc bt709 -colorspace bt709 -movflags +faststart -an "$out"
    [[ $(size "$out") -le $max ]] && { log "$(basename "$out"): crf $crf, $(mb "$out")"; return 0; }
  done
  log "WARNING $(basename "$out") is over budget at crf $last: $(mb "$out")"
}

do_encode() {
  local L="$MASTER/launch-landscape.mkv" V="$MASTER/launch-vertical.mkv"
  # 1. the launch video: 1920x1080 60 fps H.264 High (plays everywhere), crf 15, <= 60 MB
  h264 "$L" "$DIST/smartsched-launch.mp4" 60000000 "scale=1920:1080:flags=lanczos" 60 "15 16 17 18"
  # 2. AV1 in WebM (SVT-AV1, 10-bit): the same picture at a fraction of the bytes, for browsers that play AV1
  #    (preset 5, crf 28; lp=2 keeps SVT-AV1's memory in bounds on a shared host)
  $N ffmpeg -nostdin -hide_banner -loglevel error -y -i "$L" -vf "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p10le" -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:v libsvtav1 -preset "${LAUNCH_AV1_PRESET:-5}" -crf "${LAUNCH_AV1_CRF:-28}" -g 240 \
    -svtav1-params "tune=0:lp=2" -an "$DIST/smartsched-launch-av1.webm"
  log "smartsched-launch-av1.webm: $(mb "$DIST/smartsched-launch-av1.webm")"
  # 3. a copy for a GitHub user-attachments upload on a free plan (10 MB limit): 1920x1080 at 30 fps (every other
  #    frame of the 60 fps master, all of them real frames since the capture is deterministic)
  h264 "$L" "$DIST/smartsched-launch-attach.mp4" 9800000 "scale=1920:1080:flags=lanczos" 30 "20 21 22 23 24 25 26 28 30"
  # 4. the vertical cut for phones and social, <= 50 MB
  [[ -f "$V" ]] && h264 "$V" "$DIST/smartsched-launch-vertical.mp4" 50000000 "scale=1080:1920:flags=lanczos" 60 "15 16 17 18 20"
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
    $N ffmpeg -nostdin -hide_banner -loglevel error -y -ss "$from" -to "$to" -i "$L" -vf "setpts=N/60/TB,fps=$fps,scale=$w:-2:flags=lanczos" -c:v libwebp_anim \
      -lossless 0 -quality "$q" -compression_level 6 -preset picture -loop 0 -an "$DIST/smartsched-loop.webp"
    [[ $(size "$DIST/smartsched-loop.webp") -le 5000000 ]] && break
  done
  log "smartsched-loop.webp: ${w}px ${fps} fps q$q, $(mb "$DIST/smartsched-loop.webp") (window $from-$to s)"
  # animated AVIF of the same loop (smaller; not used in the README until GitHub's raw host is checked for .avif)
  $N ffmpeg -nostdin -hide_banner -loglevel error -y -ss "$from" -to "$to" -i "$L" -vf "setpts=N/60/TB,fps=30,scale=1280:-2:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv420p" -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:v libsvtav1 -preset 6 -crf 36 \
    -an -f avif "$DIST/smartsched-loop.avif" 2>/dev/null && log "smartsched-loop.avif: $(mb "$DIST/smartsched-loop.avif")" || log "animated AVIF not written (ffmpeg without the avif muxer)"
  # 7. posters (the loop's first frame, the launch video's title frame) as PNG at full size
  $N ffmpeg -nostdin -hide_banner -loglevel error -y -ss "$from" -i "$L" -frames:v 1 -vf "scale=1280:-2:flags=lanczos" "$DIST/smartsched-loop-poster.png"
  $N ffmpeg -nostdin -hide_banner -loglevel error -y -ss 3.4 -i "$L" -frames:v 1 "$DIST/smartsched-launch-poster.png"
  [[ -f "$V" ]] && $N ffmpeg -nostdin -hide_banner -loglevel error -y -ss 3.4 -i "$V" -frames:v 1 -vf "scale=540:-2:flags=lanczos" "$DIST/smartsched-launch-vertical-poster.png"
  # report
  for f in "$DIST"/*; do
    printf '%-40s %10s  %s\n' "$(basename "$f")" "$(mb "$f")" "$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,width,height,avg_frame_rate,bit_rate -show_entries format=duration -of compact=p=0:nk=1 "$f" 2>/dev/null | tr '\n' ' ')"
  done | tee "$DIST/REPORT.txt"
}

do_clips() {
  local CL="$OUT/clips" CT="$OUT/clip-takes" list
  mkdir -p "$CL" "$CT"
  list="$(node --input-type=module -e "import { CLIPS } from '$HERE/launch/story.mjs'; for (const c of CLIPS) console.log([c.id, c.journey, c.clip ?? '-', c.device].join(' '))")"
  # 1. one take per journey (LAUNCH_CLIPS_STAGE=render skips to step 2)
  [[ "${LAUNCH_CLIPS_STAGE:-all}" == render ]] || while read -r id journey clip device; do
    local name="$journey-light"; [[ "$UI_LANG" != en ]] && name="$name-$UI_LANG"; [[ "$device" == phone ]] && name="$name-phone"
    [[ -n "${LAUNCH_ONLY:-}" && " $LAUNCH_ONLY " != *" $journey "* ]] && continue
    if [[ ! -f "$CT/$name.take.json" ]]; then
      local dsf=${LAUNCH_DSF:-1.5} vp=1440x810; [[ "$device" == phone ]] && dsf=${LAUNCH_PHONE_DSF:-2} vp=390x844
      log "clip take $journey ($device)"
      REC_DEVICE="$device" REC_DSF="$dsf" REC_VIEWPORT="$vp" REC_CAPTION_LANG=en \
        $N node "$HERE/record.mjs" --journey "$journey" --lang "$UI_LANG" --engine frames --out "$CT" </dev/null || { log "take $journey failed"; continue; }
    fi
  done <<<"$list"
  [[ "${LAUNCH_CLIPS_STAGE:-all}" == record ]] && return 0
  # 2. renders + encodes (LAUNCH_CLIPS_STAGE=record stops before this, so the stack can go down first)
  while read -r id journey clip device; do
    local name="$journey-light"; [[ "$UI_LANG" != en ]] && name="$name-$UI_LANG"; [[ "$device" == phone ]] && name="$name-phone"
    [[ -f "$CT/$name.take.json" ]] || continue
    local fmt=clip take="$journey"; [[ "$device" == phone ]] && fmt=phone-clip take="$journey-phone"
    if [[ ! -f "$CL/$take.mp4" ]]; then
      [[ -f "$CT/$take.full.mkv" ]] || $N node "$HERE/launch/render.mjs" --takes "$CT" --story clip --format "$fmt" --take "$name" --out "$CT/$take.full.mkv" </dev/null || { log "render of $take failed"; continue; }
      local vf="scale=1600:960:flags=lanczos"; [[ "$device" == phone ]] && vf="scale=720:1280:flags=lanczos"
      h264 "$CT/$take.full.mkv" "$CL/$take.mp4" 12000000 "$vf" 60 "16 18 20 22 24 26"
      $N ffmpeg -nostdin -hide_banner -loglevel error -y -sseof -2.5 -i "$CT/$take.full.mkv" -frames:v 1 -vf "scale=1200:-2:flags=lanczos" "$CL/$take-poster.png"
    fi
    local src="$CT/$take.full.mkv"
    if [[ "$clip" != - ]]; then
      src="$CT/$id.clip.mkv"
      [[ -f "$src" ]] || $N node "$HERE/launch/render.mjs" --takes "$CT" --story clip --format "$fmt" --take "$name" --clip "$clip" --out "$src" </dev/null || { log "render of clip $id failed"; continue; }
    fi
    local w=1280 q fps=30; [[ "$device" == phone ]] && w=540
    for q in 82 74 66 58 50; do
      $N ffmpeg -nostdin -hide_banner -loglevel error -y -i "$src" -vf "setpts=N/60/TB,fps=$fps,scale=$w:-2:flags=lanczos" -c:v libwebp_anim -lossless 0 -quality "$q" \
        -compression_level 6 -preset picture -loop 0 -an "$CL/$id.webp"
      [[ $(size "$CL/$id.webp") -le 4000000 ]] && break
    done
    # GIF fallback: 25 fps (an exact 4/100 s delay) or 20 fps (5/100 s), diff palette, a width ladder until <= 9 MB
    local gw gfps spec
    for spec in "1120 25" "1040 25" "960 25" "880 25" "800 25" "960 20" "880 20" "800 20" "720 20"; do
      read -r gw gfps <<<"$spec"
      [[ "$device" == phone ]] && gw=$((gw * 45 / 100))
      $N ffmpeg -nostdin -hide_banner -loglevel error -y -i "$src" -vf "setpts=N/60/TB,fps=$gfps,scale=$gw:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=256:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle" \
        -loop 0 "$CL/$id.gif"
      [[ $(size "$CL/$id.gif") -le 9000000 ]] && break
    done
    log "clip $id: webp ${w}px/${fps}fps q$q $(mb "$CL/$id.webp"), gif ${gw}px/${gfps}fps $(mb "$CL/$id.gif"), take $(mb "$CL/$take.mp4")"
  done <<<"$list"
}

do_hero() {
  local H="$MASTER/hero.mkv" q fps w spec
  [[ -f "$H" ]] || $N node "$HERE/launch/render.mjs" --takes "$TAKES:$OUT/clip-takes" --story hero --format hero --out "$H" </dev/null
  for spec in "1280 30 78" "1280 30 70" "1280 30 62" "1280 30 54" "1280 24 54" "1280 24 46"; do
    read -r w fps q <<<"$spec"
    $N ffmpeg -nostdin -hide_banner -loglevel error -y -i "$H" -vf "setpts=N/60/TB,fps=$fps,scale=$w:-2:flags=lanczos" -c:v libwebp_anim -lossless 0 -quality "$q" \
      -compression_level 6 -preset picture -loop 0 -an "$DIST/smartsched-hero.webp"
    [[ $(size "$DIST/smartsched-hero.webp") -le 3000000 ]] && break
  done
  $N ffmpeg -nostdin -hide_banner -loglevel error -y -ss 2.0 -i "$H" -frames:v 1 -vf "scale=1280:-2:flags=lanczos" "$DIST/smartsched-hero-poster.png"
  log "smartsched-hero.webp: ${w}px ${fps} fps q$q, $(mb "$DIST/smartsched-hero.webp")"
  python3 -I "$HERE/launch/quality.py" "$H" --exact --plan "$MASTER/hero.plan.json" --json "$DIST/q-hero-master.json" || log "hero master: gate not met (dist/q-hero-master.json)"
}

# Quality gate (launch/quality.py): judder and freezes on the lossless masters and the deliverables, PSNR and (with
# LAUNCH_VMAF_FFMPEG, an ffmpeg built with libvmaf) VMAF of the H.264 against the master. Writes dist/QUALITY.json.
do_check() {
  local Q="$HERE/launch/quality.py" vm=() rc=0
  [[ -n "${LAUNCH_VMAF_FFMPEG:-}" ]] && vm=(--ffmpeg-vmaf "$LAUNCH_VMAF_FFMPEG")
  python3 -I "$Q" "$MASTER/launch-landscape.mkv" --exact --plan "$MASTER/launch-landscape.plan.json" --json "$DIST/q-master.json" || rc=1
  python3 -I "$Q" "$DIST/smartsched-launch.mp4" --ref "$MASTER/launch-landscape.mkv" "${vm[@]}" --json "$DIST/q-mp4.json" || rc=1
  [[ -f "$MASTER/launch-vertical.mkv" ]] && { python3 -I "$Q" "$DIST/smartsched-launch-vertical.mp4" --ref "$MASTER/launch-vertical.mkv" --json "$DIST/q-vertical.json" || rc=1; }
  python3 -I "$Q" "$DIST/smartsched-launch-attach.mp4" --ref "$MASTER/launch-landscape.mkv" --json "$DIST/q-attach.json" || rc=1
  python3 -I - "$DIST" <<'PY'
import glob, json, os, sys
out = {os.path.basename(f)[2:-5]: json.load(open(f)) for f in sorted(glob.glob(os.path.join(sys.argv[1], "q-*.json")))}
json.dump(out, open(os.path.join(sys.argv[1], "QUALITY.json"), "w"), indent=2)
for k, r in out.items():
    print(f"{k:9} unique {r['unique_pct']}%  motion-unique {r['motion_unique_pct']}%  freezes {r['freezes']} (holds {r['holds']}, judder {r['judder_freezes']})"
          + f"  repeats: isolated {r['isolated_repeats']} (ease-out tails), mid-motion {r['midmotion_repeats']}" + (f" (+{r['midmotion_lottie']} Lottie hold keyframes)" if "midmotion_lottie" in r else "")
          + (f"  PSNR-Y {r['psnr_y']}" if "psnr_y" in r else "") + (f"  VMAF {r['vmaf_mean']} (p1 {r['vmaf_p1']})" if "vmaf_mean" in r else "")
          + f"  {r['mbit_s']} Mbit/s  gate {'PASS' if all(r['gate'].values()) else 'FAIL ' + str(r['gate'])}")
PY
  return $rc
}

do_publish() {
  local media="$ROOT/docs/launch/media"
  mkdir -p "$media"
  cp "$DIST"/smartsched-launch.mp4 "$DIST"/smartsched-launch-av1.webm "$DIST"/smartsched-launch-vertical.mp4 "$DIST"/smartsched-launch.en.vtt \
     "$DIST"/smartsched-launch-poster.png "$DIST"/smartsched-launch-vertical-poster.png "$DIST"/smartsched-loop.webp "$DIST"/smartsched-loop-poster.png \
     "$DIST"/smartsched-launch-attach.mp4 "$DIST"/smartsched-loop.avif "$media/"
  [[ -f "$DIST/smartsched-hero.webp" ]] && cp "$DIST"/smartsched-hero.webp "$DIST"/smartsched-hero-poster.png "$media/"
  log "published to docs/launch/media"
  if [[ -d "$OUT/clips" ]]; then
    mkdir -p "$media/clips"
    # GIF + MP4 + poster under the names clips.json uses; the WebP clips next to the launch media until the README
    # generator shows WebP (check_readme.py fails on a file in docs/images/recordings that no README references)
    # GIF fallbacks only for the clips the README features (clips.json "featured"); the others are WebP only, and a
    # GIF nobody links any more is removed (check_readme.py fails on orphans)
    local featured
    featured=" $(python3 -I -c 'import json,sys; print(" ".join(c["id"] for c in json.load(open(sys.argv[1]))["featured"]))' "$ROOT/docs/images/recordings/clips.json") "
    find "$OUT/clips" -maxdepth 1 -type f ! -name '*.webp' ! -name '*.gif' -exec cp {} "$ROOT/docs/images/recordings/" \;
    for g in "$OUT"/clips/*.gif; do
      local id; id="$(basename "$g" .gif)"
      if [[ "$featured" == *" $id "* ]]; then cp "$g" "$ROOT/docs/images/recordings/"
      elif [[ -f "$ROOT/docs/launch/media/clips/$id.webp" || -f "$OUT/clips/$id.webp" ]]; then rm -f "$ROOT/docs/images/recordings/$id.gif"; fi
    done
    find "$OUT/clips" -maxdepth 1 -type f -name '*.webp' -exec cp {} "$media/clips/" \;
    log "README clips copied: $(find "$OUT/clips" -maxdepth 1 -type f ! -name '*.webp' | wc -l) files to docs/images/recordings, $(find "$OUT/clips" -maxdepth 1 -name '*.webp' | wc -l) WebP to docs/launch/media/clips"
  fi
}

case "$CMD" in
  record) do_record ;;
  render) do_render ;;
  encode) do_encode ;;
  publish) do_publish ;;
  clips) do_clips ;;
  check) do_check ;;
  hero) do_hero ;;
  all) do_record; do_render; do_encode; do_check || log "quality gate FAILED (dist/QUALITY.json): not publishing"; do_clips; do_hero; do_check && do_publish ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
