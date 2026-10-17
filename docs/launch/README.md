# SmartSched launch video

The launch video and the README media are built from the real application on the real 2026 workbooks (instructor
names reduced to initials, RECORDLY.md "KVKK"), recorded losslessly and rendered offline at 60 fps. Why this route
and not Remotion, Recordly or a screen recorder: [RESEARCH.md](RESEARCH.md).

## 1. Deliverables

<!-- launch:deliverables (rewritten by hand from dist/REPORT.txt after each render) -->

| File (`docs/launch/media/`) | What | Format |
|---|---|---|
| `smartsched-launch.mp4` | the hero cut, landscape | 1920x1080, 60 fps, H.264 High, yuv420p, `+faststart`, ≤ 25 MB |
| `smartsched-launch-av1.webm` | the same cut, AV1 | 1920x1080, 60 fps, SVT-AV1 10-bit in WebM |
| `smartsched-launch-vertical.mp4` | phones and social | 1080x1920, 60 fps, H.264 High, ≤ 25 MB |
| `smartsched-launch.en.vtt` | English captions (they are also burned in) | WebVTT |
| `smartsched-loop.webp` | the README loop (the phone booking scene) | animated WebP, 1280 px, 30 fps, ≤ 5 MB |
| `smartsched-loop-poster.png`, `smartsched-launch-poster.png`, `smartsched-launch-vertical-poster.png` | stills | PNG |

Not committed (build folder `OUT/dist`): `smartsched-launch-attach.mp4` (≤ 9.8 MB, 1080p 30 fps, for a GitHub
user-attachments upload on a free plan, §4) and `smartsched-loop.avif` (RESEARCH.md §1).

The per-feature README clips keep their names (`docs/images/recordings/clips.json`): `<id>.gif`, `<take>.mp4`,
`<take>-poster.png`, now rendered by the same pipeline (1600x960, 60 fps master; GIF fallback at 25 fps), plus
`<id>.webp` (1280 px, 30 fps) in `docs/launch/media/clips/` until the README generator can show WebP (§4).

## 2. The story (scripts/record/launch/story.mjs)

| # | Scene | Source |
|---|---|---|
| 0 | Intro: the SmartSched lockup, the `hero-solver` Lottie (vector, drawn at 1056 px), the tagline | Lottie |
| 1 | "Start from the planning office's own workbooks" (`file-to-rules` Lottie) → the import page: the workbook kinds, then an edited room master whose two changes are listed before anything is saved | `launch-import` |
| 2 | Solve: a real full-term solver run of Güz 2026-27; the verdict says every hard rule was kept | `launch-run` steps 0-1 |
| 3 | "Nothing is dropped silently" (`precheck-fix` Lottie) → the run report: each unplaced class, why, and what would fix it | `launch-run` steps 2-3 |
| 4 | Publish, with the dialog that names what is left out | `launch-run` steps 4-5 |
| 5 | A member of staff books a room on a phone with quick reserve (`/reserve`), touch taps shown as finger dots | `launch-reserve` (390x844, `isMobile`, `hasTouch`) |
| 6 | The approver opens the request and approves it | `approval-flow` steps 2-4 |
| 7 | The admin views of wave 3: AI console (providers/models, usage, limits, guardrails) and the operations panel | `launch-admin` |
| 8 | Outro: lockup, licence, repository, feature pills | — |

The vertical cut uses the same scenes: desktop scenes become a 1000x800 window that follows the camera, the phone fills
the frame, titles sit above.

## 3. How it is made

```
stack.sh up (+ runs)          real backend + production frontend on the real workbooks, names masked
        │
record.mjs --engine frames    Playwright drives each journey; Chrome's screencast keeps every painted frame as a
        │                     lossless PNG (desktop 1440x810 CSS px at 1.5x, phone 390x844 at 2x) with its paint time;
        │                     the Recorder logs steps, camera targets, pointer track, taps and typed keys
render.mjs (story.mjs)        per output frame (60 fps): which take frame, spring camera (lib/camera.mjs), cursor and
        │                     ripples, finger taps, keystroke chips, caption pill, chapter chip, Lottie frame →
        │                     compositor.html in headless Chromium → PNG → ffmpeg (H.264 RGB lossless master)
launch.sh encode              MP4 / AV1 / vertical / attach / WebP loop / AVIF / posters / VTT, each under its budget
launch.sh clips               the README feature clips from the same pipeline
```

Why it is smooth: the screen video is never the clock. The UI frames are shown as they were painted (a still screen is
one PNG), and everything that moves on top of it (camera, cursor, captions, transitions, Lottie) is computed for each
of the 60 frames per second. A busy host makes the render slower, not the video choppier. Two limits remain: UI
animations inside the app (a sheet sliding in) are as smooth as Chrome could paint them during the take (on a host
with a load of 30+ that is 3-10 paints per second), and still stretches longer than 2 s (`LAUNCH_MAX_IDLE_MS`) are
shortened to 2 s, so a slow server answer reads as a cut, not as waiting.

### Reproduce

```bash
export REC_WORKDIR=/tmp/launch-stack REC_API_PORT=19610 REC_WEB_PORT=19611 REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0
export REC_BASE_URL=http://127.0.0.1:19611
scripts/record/stack.sh up && scripts/record/stack.sh runs        # REC_IGNORE_TS=1 for a checkpoint that does not type-check
scripts/record/launch.sh all /tmp/launch-out                       # record, render, encode, clips, publish
scripts/record/stack.sh down
```

Steps one by one: `launch.sh record|render|encode|clips|publish OUT`. Preview a scene without rendering everything:
`node scripts/record/launch/render.mjs --takes OUT/takes --scenes reserve --out /tmp/p.mkv --still 3=/tmp/p.png`.
A single README clip: `node scripts/record/launch/render.mjs --takes OUT/clip-takes --story clip --format clip --take find-room-light --clip find-room --out /tmp/c.mkv`.
Dependencies: what the repository already has (Playwright + Chromium and `lottie-web` from the frontend's
lockfile, ffmpeg ≥ 6 with libx264, libsvtav1, libwebp; ImageMagick only for contact sheets). No music: the video is
silent by design (captions carry it), so there is no licence to track for audio.

## 4. README use

The top of the README (asked of the README owner; `scripts/docs/sync_docs.py` is not in this lane):

```html
<a href="docs/launch/media/smartsched-launch.mp4">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="docs/launch/media/smartsched-loop-poster.png">
    <img alt="SmartSched in 10 seconds: a member of staff books a free room on a phone in a few taps" src="docs/launch/media/smartsched-loop.webp" width="100%">
  </picture>
</a>
<sub>▶ <a href="docs/launch/media/smartsched-launch.mp4">Launch video (1080p60, MP4)</a> ·
<a href="docs/launch/media/smartsched-launch-av1.webm">AV1</a> ·
<a href="docs/launch/media/smartsched-launch-vertical.mp4">vertical, for phones</a></sub>
```

For an inline player: open README.md on github.com → edit → drag `smartsched-launch-attach.mp4` into the editor →
keep the `https://github.com/user-attachments/assets/…` line GitHub inserts (on its own line) → commit. That URL
cannot be produced from a script.

Check after a commit that GitHub kept the reduced-motion `<source>`:

```bash
curl -sS -H "Accept: application/vnd.github.html+json" \
  "https://api.github.com/repos/ArioMoniri/classroombookings/contents/README.md?ref=<branch>" | grep -o '<source[^>]*>'
```

## 5. Media weight

<!-- launch:weight (filled from dist/REPORT.txt) -->
See §1 and `docs/recording/RECORDLY.md` §8 for the measured sizes of this render.
