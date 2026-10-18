# Demo recordings with Recordly

> **2026-10-17: the launch video and the README media move to an offline 60 fps renderer.** `scripts/record/launch.sh`
> records each journey as lossless Chrome screencast frames (`record.mjs --engine frames`, 1.5x desktop / 2x phone,
> touch taps on a 390x844 `isMobile` + `hasTouch` context) and `scripts/record/launch/render.mjs` composites every
> output frame in headless Chromium (spring camera, cursor, ripples, finger taps, keystroke chips, captions, the
> Lottie intro/outro), so motion is 60 fps whatever the host load was during the take. The per-feature README clips
> keep their names and are rendered the same way (`launch.sh clips`). See [§8](#8-launch-video-and-60-fps-clips-2026-10-17),
> [docs/launch/README.md](../launch/README.md) and the research behind it, [docs/launch/RESEARCH.md](../launch/RESEARCH.md).
> The ffmpeg-expression compositor below (§5) still works and stays the route for quick GIF takes. Current README media:
> rendered 2026-10-18 from snapshot `a39559b` (sizes in docs/launch/README.md §1 and §5).

How to make the SmartSched "how to use" recordings: by hand with **Recordly** on a Mac (best
quality), or automatically with the pipeline in `scripts/record/`, which drives the real app with
Playwright and adds Recordly-style polish. The pipeline can also hand its result to Recordly, either
to render on Linux or to fine-tune in the Recordly editor.

> **Status (2026-10-16, snapshot `1210795`, the redesigned UI).** The README shows 7 GIF clips and 9 full takes (MP4), all
> recorded on the real backend with the **screencast → ffmpeg** route (§2 b′; the two upload journeys use Playwright's
> video, see Known limitations), light theme, English captions, plus Turkish takes of `reserve-panel`:
> `reserve-slot` 8.08 MB (10.2 s, 1040 px), `reserve-drag` 1.93 MB (8.7 s), `find-room` 0.95 MB (7.8 s), `audit-undo`
> 2.86 MB (9.9 s), `calendar-move` 8.33 MB (7.2 s), `precheck-fix` 2.46 MB (11.3 s), `onboarding` 5.97 MB (14.6 s);
> all at 20 fps (every frame delay a multiple of 5/100 s), 1120 px unless noted. Not recorded this time: `approval-flow`
> and `login-dashboard` (the sign-in page and the approval screens are being rebuilt), `chat-edit` (needs an AI key),
> and `import-generate` (see Known limitations). Every take still writes a `.recordly` project for hand editing on a Mac.
>
> **KVKK.** The real workbooks name every instructor. Before any take, `scripts/record/kvkk_mask.py` rewrites each
> instructor's name in the throwaway recording database (never in product data or code) to title + initials
> ("Dr. Öğr. Üyesi A. K."), derived from the real name, so nothing is invented and two instructors with the same
> initials stay two rows. The same rule covers the imported source rows, exam requests, grid labels and run results;
> the journeys that import during the take hold the page's answer until the database is masked. Every recording and
> screenshot therefore shows **initials only**. The accounts the journeys use are roles, not people (the seeded
> administrator, "Akademik Personel", the planning office's "Planlama Ofisi"); private calendar-feed links are blurred.

## 1. Recordly facts (checked on 2026-10-08)

| | |
|---|---|
| Official repository | **[github.com/webadderallorg/Recordly](https://github.com/webadderallorg/Recordly)**. `package.json` (`homepage`, `repository`, `bugs`) and the README's download link all point to `webadderallorg`. `github.com/webadderall/Recordly` is the author's personal account (`webadderall` is the copyright holder in LICENSE.md) and redirects to the org repository. `lsj5031/Recordly` is not referenced anywhere in the official repository, so treat it as a fork. |
| Licence | **AGPL-3.0**: `LICENSE.md`, plus the author's summary on top. The summary adds two terms: you may not use the "Recordly" name or branding for your own project, and code derived from Recordly must credit Recordly. The "MIT" seen on third-party pages belongs to the upstream fork parent **OpenScreen** (siddharthvaddem/openscreen). We only *use* Recordly as a tool, so the AGPL puts no obligations on SmartSched or on the videos. `scripts/record` contains no Recordly code: it writes Recordly's documented JSON project format. |
| Latest release | **v1.4.0** (2026-09-08). Assets: `Recordly-arm64.dmg` / `.zip` (macOS Apple silicon), `Recordly-windows-x64.exe`, `Recordly-linux-x64.AppImage` (204 317 716 bytes; its sha512 matched `latest-linux.yml`). Linux ships only as an AppImage (no .deb); on Arch use the AUR package `recordly-bin`. |
| Platforms | macOS 14+ (ScreenCaptureKit; the real cursor is hidden cleanly). Windows 10 build 19041+ (WGC helper). Linux: any modern distro, captured through Electron. On Linux the real cursor **cannot be hidden**, so the styled overlay and the real cursor can both appear, and system audio needs PipeWire. Building from source on Linux needs `build-essential cmake libx11-dev libxtst-dev libxrandr-dev libxt-dev`. |
| Features | Auto-zoom suggestions and manual zoom regions; a cursor overlay (style, size, smoothing, motion blur, click bounce, sway, click effects `ripple`/`spotlight`/`echo`); wallpapers, gradients, padding, rounded corners, shadow; trims, speed regions, annotations, webcam overlay, Whisper auto-captions. |
| Export | **MP4** and **GIF**: quality, frame rate, GIF loop, GIF size presets, aspect ratio and output size. |
| Project file | `*.recordly` is **JSON**: `{version: 2, projectId?, videoPath, editor: {...}}`. The `editor` fields are listed in `src/components/video-editor/projectPersistence.ts` (`ProjectEditorState`). Zoom regions are `{id, startMs, endMs, depth 1-6, focus {cx, cy} normalised 0-1, mode}`; depth N zooms ×1.25, 1.5, 1.8, 2.2, 3.5 or 5.0. Captions are `autoCaptions: [{id, startMs, endMs, text}]`. Cursor telemetry is a sidecar file next to the video: `<video>.cursor.json` = `{version: 2, samples: [{timeMs, cx, cy, interactionType: move/click/mouseup/…, cursorType}]}`. |
| CLI / automation | **No documented CLI.** The packaged build does contain an undocumented headless **smoke-export mode**, which Recordly uses for its own tests. Set the environment variables `RECORDLY_SMOKE_EXPORT=1`, `RECORDLY_SMOKE_EXPORT_PROJECT=<file.recordly>` (or `_INPUT=<video>`), `RECORDLY_SMOKE_EXPORT_OUTPUT=<out.mp4>` and optionally `_QUALITY`, `_FPS`, `_PIPELINE`, `_RENDER_BACKEND`. Recordly then opens the project, exports an MP4 and writes `<out>.mp4.report.json`. Because the project is plain JSON, **a recording plus its zoom and cursor timeline can be produced programmatically.** Recordly's own capture can also be driven, through Playwright's `_electron` (see §2). |
| Agent skills | [openskillindex: tdimino/claude-code-minoan "recordly"](https://openskillindex.com/skills/tdimino-claude-code-minoan-recordly) (MIT skill; source `skills/design-media/recordly/SKILL.md`). Its `install_recordly.sh` clones and builds Recordly into `~/tools/recordly`, and `launch_recordly.sh [file]` opens a video or `.recordly` file. **All editing is manual.** The skill also bundles "Slant", a Three.js 3D-tilt renderer. Its intended use is polishing `feature-video` captures for PR descriptions. No Recordly skill was found on skills.sh. Neither uses the project format or smoke export: `scripts/record` goes further than either. |

## 2. What works in a headless Linux container (evidence)

This container: Ubuntu 24.04, no GPU, `Xvfb`/`xvfb-run` already installed, `/dev/fuse` present.
The AppImage was unpacked with `--appimage-extract`, so it runs without FUSE.

| Route | Result |
|---|---|
| **(b′) Chrome screencast → ffmpeg polish** (`REC_CAPTURE=screencast`, the README default since 2026-10-15) | **Works; used for the README GIFs.** CDP `Page.startScreencast` sends a lossless PNG frame whenever the page paints; the frames are laid out on their real timestamps as a lossless 20 fps video. A still screen is then the same frame bit for bit, which is what makes a sharp, smooth GIF affordable: with Playwright's VP8 every frame differed by ±2-7 levels, and an error-diffusion palette turned that into a new dither pattern per frame (a 16 s clip at 1040 px came to 29 MB). The camera spring is integrated in 2 ms substeps (one explicit step per frame jitters at 20 fps) and snaps onto its target once it is within half a pixel, for the same reason. |
| **(b) Playwright video → ffmpeg polish** | **Works; this is the default.** `login-dashboard` (light and dark, 16-18 s) produced MP4 1600×1060 H.264, a GIF under 8 MB and a PNG poster. Final run (light, 17.9 s): MP4 3.1 MB (H.264 High, yuv420p, 30 fps, 538 frames); GIF 7.03 MB at 800 px / 12 fps (the 1000 px / 15 fps rung was over 8 MB); dark: GIF 6.8 MB. A whole take (record + post) takes 2 min 34 s; compositing alone takes 2 min for 18 s of video on 8 vCPU. |
| **Recordly as renderer** (generated `.recordly` → smoke export) | **Works, but slowly.** It runs under `xvfb-run` with `--ozone-platform=x11 --use-angle=swiftshader --enable-unsafe-swiftshader`, `XDG_SESSION_TYPE=wayland` and `RECORDLY_SMOKE_EXPORT_PIPELINE=legacy`. Recordly loaded the generated project, kept all 4 zoom regions, the 4 captions and the preset, and re-saved the project. It rendered 525/525 frames to H.264 at 1080×674 (quality `good`) in **780 s for 17.5 s of video** (software WebGL). Two settings are required, and the reasons are in the code comments. Without the session override, Recordly forces `--use-gl=egl`, which Xvfb lacks: "No supported Pixi modern renderer". The `modern` pipeline fails on WebGPU (`_resourceType`). On a 4 s test clip, the legacy pipeline at `source` quality took 184 s. Only one Recordly instance can run at a time (single-instance lock). |
| **(a) Recordly capturing a Playwright window under Xvfb** | **Possible, but not useful here.** Playwright's `_electron.launch()` drives the packaged HUD. `electronAPI.getSources()` lists the Xvfb screen, `selectSource()` accepts it, and clicking record → *Stop* produced `recording-*.webm` (VP9 1920×1080, 8.4 s) plus a `.cursor.json`, and opened the editor. However, the recording shows the HUD bar, the browser chrome and the X cursor. Playwright's mouse sends CDP events and never moves the X pointer, so Recordly's telemetry recorded 250 samples, all at (0.5, 0.5) with no clicks, and auto-zoom and cursor effects have nothing to work from. Route (b) logs exact pointer positions, then writes them in Recordly's own telemetry format, which is better. |
| Recordly on macOS (manual) | Not testable here. This is the route for highest-fidelity recordings (§4). |

## 3. Install Recordly (official links only)

- Releases: <https://github.com/webadderallorg/Recordly/releases> (v1.4.0 or later).
- **macOS 14+ (Apple silicon):** download `Recordly-arm64.dmg` and drag Recordly to Applications.
  On first record, allow *Screen Recording*, and *Accessibility* if you want cursor telemetry
  (System Settings → Privacy & Security). If you build it yourself and macOS refuses to open it:
  `xattr -rd com.apple.quarantine /Applications/Recordly.app`.
- **Windows 10 19041+:** `Recordly-windows-x64.exe`.
- **Linux x64:** `Recordly-linux-x64.AppImage` (`chmod +x`, then run; or `--appimage-extract` on
  machines without FUSE). Arch: `yay -S recordly-bin`.
- From source: `git clone https://github.com/webadderallorg/Recordly.git && cd Recordly && npm install && npm run dev`.

For the automated Recordly renderer on Linux:

```bash
mkdir -p ~/tools/recordly && cd ~/tools/recordly
curl -fLO https://github.com/webadderallorg/Recordly/releases/download/v1.4.0/Recordly-linux-x64.AppImage
chmod +x Recordly-linux-x64.AppImage && ./Recordly-linux-x64.AppImage --appimage-extract >/dev/null
export RECORDLY_BIN=~/tools/recordly/squashfs-root/recordly
```

## 4. Recommended settings for SmartSched demos

These values live in [`recordly-preset.json`](recordly-preset.json), which the pipeline merges into
every generated project. Set the same values by hand in the editor.

| Setting | Value | Why |
|---|---|---|
| Browser window | 1440×900 content area, 100 % zoom, one tab, bookmarks bar hidden | matches the pipeline's viewport; text stays readable after zoom |
| Record | *Window* (the browser window), not the whole screen; microphone off; countdown 3 s | no desktop clutter; demos are silent and use captions |
| Aspect ratio | 16:10 | the app's natural shape; README GIFs then need no letterboxing |
| Background | wallpaper `tahoe-light` (light theme) / `tahoe-dark` (dark theme); blur 0 | quiet, close to the app's palette |
| Padding / corners / shadow | 12 (linked) / 8 % / 0.6 (dark 0.8) | the "floating window" look |
| Cursor | style *Tahoe*, size 2.5, smoothing 0.67, click bounce 2 (350 ms), sway 0 | enlarged, calm |
| Click effect | *Ripple*, `#2563EB` (dark `#60A5FA`), 600 ms, opacity 0.9 | matches the app's primary blue |
| Zoom | auto-zoom on; easing *Recordly*; connect zooms on; depth 3 (×1.8) for buttons and inputs, depth 2 (×1.5) for cards and tables, none for full-page views; motion blur 0.35 | the same rules the pipeline uses (`scripts/record/lib/camera.mjs`) |
| Captions | one caption per step (texts in [Journeys](#journeys)), font size 30, fade, background opacity 0.86, one row | silent demos |
| Export MP4 | quality *High*, 30 fps | docs and PRs |
| Export GIF | 15 fps, loop on, size *Medium*. **Keep it under 8 MB**: lower the size preset, then the fps | README |

Before each take: run `scripts/record/stack.sh up` (or `up --fresh` for journey 1) so the data is
always the same. Choose the theme in the app (sun/moon button) and the language with TR/EN. Close
toasts and devtools.

## Journeys

Each journey is a module in `scripts/record/journeys/`. Its captions are the step texts (English; `--lang tr` uses the
Turkish texts in the same file), and a step's `clip` id puts it into a README GIF: consecutive steps with the same id
form one short clip (6-12 s, one action). To record one by hand with Recordly, follow the same steps and pause about
1 s after each, so auto-zoom has something to frame.

The README section "See it work" is generated: `scripts/docs/sync_docs.py` (block `recordings`) reads
`docs/images/recordings/clips.json` (featured clips with their captions, every full take with its title) and the files
next to it, and fails `--check` when a referenced file is missing. Edit captions in `clips.json`; `refresh.sh` rebuilds
the files under the same names, then `python3 -I scripts/docs/sync_docs.py` rewrites the README block.

| Journey (`--journey`) | DB | What it shows | README GIF clip(s) | Full take |
|---|---|---|---|---|
| `reserve-panel` | seeded | A free period offers Reserve on hover; one more click books it; a drag across three periods; room details with other free rooms | `reserve-slot` (8.08 MB), `reserve-drag` (1.93 MB) | `reserve-panel.mp4`, `reserve-panel-tr.mp4` |
| `find-room` | seeded | Head count and the computer-lab feature (adopted from the room master's PC tag); ranked results with reasons; reserve from the list | `find-room` (0.95 MB) | `find-room.mp4` |
| `approval-flow` (not recorded on `1210795`: approval screens being rebuilt) | seeded | The academic staff account asks for a room with an approval rule (set up through the API); the request is held as pending; the administrator approves it in `/approvals`; the requester sees it confirmed | `approval-request`, `approval-approve` (8.1 / 8.7 MB on `52f96d4`) | — |
| `audit-undo` | seeded | A booking move in the audit log with its before/after values; Undo after a confirm | `audit-undo` (2.86 MB) | `audit-undo.mp4` |
| `calendar-move` | seeded | The inspector; Move offers only rooms that are free and fit; the server's check; confirm; undo | `calendar-move` (8.33 MB, the move) | `calendar-move.mp4` |
| `studio-rule-fix` | seeded | A rule from a template; the pre-check against the data; one of its fixes applied | `precheck-fix` (2.46 MB) | `studio-rule-fix.mp4` |
| `import-generate` (not published on `1210795`, see Known limitations) | fresh | `generate-report` (not published) | — |
| `onboarding-intake` | fresh | The Final 2026 exam planning list dropped on `/onboarding` with AI off; classified; the review (instructor names held until masked); commit into 2026-FINAL | `onboarding` (5.97 MB) | `onboarding-intake.mp4` |
| `room-booking` | seeded | A free period booked with a note; My bookings | — | `room-booking.mp4` |
| `admin-user` | seeded | Setup → Users: an account for the planning office ("Planlama Ofisi") with the Planner role | — | `admin-user.mp4` |
| `login-dashboard` (not recorded on `1210795`: sign-in page being rebuilt) | seeded | Sign in; the dashboard | — | — |
| `run-report-fix` | seeded | The run report of Güz week 3 and one suggested fix applied | — | `run-report-fix.mp4` |

`chat-edit` (edit the timetable by chat) is not recorded: it needs an Anthropic key in the backend, and the recording
stack has none. A take with a key would show a real model answer; the pipeline does not fake one.

## 5. Automated pipeline

Requirements: the dev setup from `smartsched/README.md` (Python deps, `npm ci` in
`smartsched/frontend`), Playwright's Chromium (`PLAYWRIGHT_BROWSERS_PATH`, default
`/opt/pw-browsers`), `ffmpeg`/`ffprobe` ≥ 6, ImageMagick (`convert`), Node ≥ 22. Optional:
`xvfb-run` plus the extracted AppImage for `--engine recordly`.

```bash
# everything at once (what the README uses): seeded journeys, screenshots, fresh-database journeys, publish,
# copy into docs/images, check the README; built under SCRATCH_DIR first
REC_WORKDIR=/tmp/smartsched-rec scripts/record/refresh.sh /tmp/smartsched-media

# or step by step
# 1. isolated stack: SQLite + the real workbooks (instructor names masked to initials) on :8610, a production
#    frontend build on :3610 (REC_API_PORT / REC_WEB_PORT); everything under $REC_WORKDIR, nothing in the repo
scripts/record/stack.sh up && scripts/record/stack.sh runs   # or: up --fresh (empty instance, for import-generate)

# 2. one journey
node scripts/record/record.mjs --list
REC_CAPTURE=screencast REC_FPS=20 REC_GIF=1 node scripts/record/record.mjs --journey calendar-move --out recordings/calendar-move-light
node scripts/record/record.mjs --journey reserve-panel --theme dark --lang tr

# 3. every journey with the README settings, then the README copies under stable names
scripts/record/record-all.sh recordings
scripts/record/publish.sh recordings light

# 4. optional: let Recordly render the same take (Linux: Xvfb + SwiftShader, ~45 s per video second)
RECORDLY_BIN=~/tools/recordly/squashfs-root/recordly \
  node scripts/record/record.mjs --journey calendar-move --engine both

scripts/record/stack.sh down
```

Parameters: `REC_BASE_URL` (default `http://127.0.0.1:3610`), `REC_EMAIL`/`REC_PASSWORD`
(admin; default `admin@smartsched.local` / `Admin-2026!`), `REC_TEACHER_EMAIL`/`REC_TEACHER_PASSWORD`,
`REC_TERM_CODE` (2026-BAHAR), `--theme light|dark`, `--lang en|tr`, `--speed 1.3` (slower, more
deliberate), `--engine ffmpeg|recordly|both|raw`, `REC_VIEWPORT=1440x900`, `REC_CRF`,
`REC_CURSOR_SCALE`, `REC_CAPTURE=video|screencast`, `REC_FPS`, `REC_GIF=1`, `REC_GIF_MAX_BYTES` (9 MB),
`REC_GIF_WIDTHS` (1120,1040,1000), `REC_GIF_CLIPS`, `REC_PAD`, `REC_CAMERA_STIFFNESS`, `REC_CAMERA_BRIDGE_MS`,
`REC_CAMERA_MIN_ZOOM`. `record-all.sh` sets the README values: screencast capture, 20 fps, a 1280×800 viewport,
padding 56, a quicker camera (stiffness 220, shots up to 4 s apart joined into one pan) with a mild zoom (×1.2 to
×1.35), and the camera stays put while the next target is already in view: at ×1.3 the view is 985×615 px of the
1280×800 page, enough to keep a whole action (a cell, the sheet that opens, its button) in one frame. Every camera
move costs a GIF about 2 MB at 1040 px, so this is what keeps a clip under 9 MB without dropping frames.
`node scripts/record/record.mjs --journey J --out DIR --repolish` re-composites a finished take (its lossless raw and
timeline) with the current settings, without recording again. The recorder can point at any running SmartSched, not only the local stack
(set `REC_BASE_URL` and the credentials).

Output per take (`<journey>-<theme>[-tr]`):

| File | What |
|---|---|
| `*.mp4` | H.264 yuv420p, 30 fps, 1600×1060, `+faststart`; zoom, cursor, ripple, captions, framed |
| `*.<clip>.gif` | with `REC_GIF=1`: one README clip per `clip` id, cut from a lossless master: `fps=20`, `mpdecimate`, Lanczos scale, `palettegen=stats_mode=diff` + `paletteuse=dither=sierra2_4a:diff_mode=rectangle`, looped. A still stretch
(waiting for the server) is capped at 1.5 s (`REC_GIF_MAX_HOLD`): a jump cut of a screen where nothing moves. Widths 1120 → 1040 → 1000 until it is under 9 MB; never fewer frames per second (a clip that does not fit is shortened in its journey). 20 fps because a GIF frame delay is a whole number of 1/100 s: 5/100 s is exact, 24 fps would alternate 4 and 5 and stutter |
| `*.webp` | only with `REC_WEBP=1`: animated WebP, under `REC_WEBP_MAX_BYTES` (4 MB) |
| `*.poster.png` | frame from the step marked `poster` (else 60 % in): the GIF/MP4 placeholder |
| `*.raw.mp4`, `*.raw.mp4.cursor.json`, `*.recordly` | the trimmed raw take and a Recordly project. Open it in Recordly on any OS and fine-tune; on another machine, re-link the video if Recordly asks |
| `*.timeline.json` | steps, targets (bounding boxes), pointer track and sync data on the video clock |
| `*.recordly.mp4` | Recordly's own render (`--engine recordly/both`) |
| `*.failure.png` | screenshot when a journey fails; the raw take is kept |

How it works:

1. **Record.** Playwright opens Chromium (with `REC_CAPTURE=video`, `recordVideo` at the viewport size; with
   `screencast`, a CDP screencast of lossless PNG frames, `lib/screencast.mjs`), the theme
   (`colorScheme` + next-themes `localStorage.theme`) and the locale (`NEXT_LOCALE` cookie). Hidden
   setup steps (logging in, opening the start page) happen before the take. The `Recorder`
   (`lib/recorder.mjs`) moves the mouse along eased paths and logs every pointer sample, click and
   target bounding box.
2. **Sync.** A 350 ms magenta frame is painted at a logged instant. `lib/video.mjs` finds it in the
   video (to ±1 frame; measured offsets 16-38 ms), maps the timeline onto the video clock and cuts
   the setup and the flash away.
3. **Camera.** `lib/camera.mjs`: each target gets a shot with zoom = min(50 % of the frame /
   target size, ×1.8). The shot starts 550 ms before the action and lasts until 900 ms after it; shots
   less than 1.4 s apart are joined into one pan. A critically damped spring smooths zoom (in log
   space) and centre, the same idea as Recordly's camera springs.
4. **Composite.** `lib/polish.mjs` / `lib/assets.mjs`. Pass 1 applies the camera as a sub-pixel
   `perspective` crop (separate pass: inside a larger graph, ffmpeg 6.1's frame counter drifts).
   Pass 2 adds the rounded mask, shadow and gradient background (ImageMagick), the enlarged cursor
   moved along the camera-transformed pointer track, a ripple per click and a fading caption pill
   per step. Both tracks are piecewise-linear ffmpeg expressions simplified with RDP.

## 6. Embedding in the README

`scripts/record/publish.sh RECORD_ALL_OUT_DIR light DEST` writes the README copies under stable names:
`<clip>.gif` (the README set in `REC_GIF_CLIPS`), `<journey>.mp4` (H.264, 1280 px wide, CRF 26),
`<journey>-poster.png` (1200 px, 256 colours) and `<journey>-tr.mp4` for the Turkish takes, and prints each GIF's size,
pixels and frame delays. Build into a scratch DEST and copy once (`refresh.sh` does both): every re-encode
committed to `docs/images` stays in git history. Commit only these files (the raw take, timeline and Recordly
project are build artefacts).

The README shows each GIF and links it to the journey's MP4; GitHub does not play an MP4 inline:

```html
<a href="docs/images/recordings/calendar-move.mp4">
  <img alt="Screen recording: a class is moved to a free room that the server confirms, then the move is undone"
       src="docs/images/recordings/calendar-move.gif" width="100%">
</a>
```

Write `alt` text that describes the action. The poster of every journey links its MP4 too, for readers with a slow
connection. `scripts/record/check_readme.py` checks that every referenced file exists, that no file in
`docs/images/recordings`, `docs/images/screens` or `docs/media` is orphaned, and that no README GIF is over 9 MB.

## 7. Known limitations

- The journeys run on the UI of `52f96d4` (2026-10-15); a UI redesign needs `refresh.sh` again. A failing step writes `*.failure.png` and keeps
  the raw take; re-check the selectors after a UI change (they use `data-testid`s with role/label fallbacks).
- `chat-edit` needs an Anthropic key in the backend, and the model's answer varies between takes. Record it
  more than once and keep the best take.
- Size: a GIF pays for every camera move with whole new frames (about 2.5 MB per second of zoom or pan at 1040 px),
  while still stretches cost almost nothing. Keep clips to one action, few targets per clip, and let the MP4 carry
  the rest.
- `import-generate` and `onboarding-intake` upload workbooks during the take. Chrome's screencast stalls while a large
  file is uploaded and imported (no frames for half a minute, then a burst), so these two use Playwright's video
  (`capture: "video"` in the journey). Under the load of this container (load average 15-30 on 4 cores) the video of
  `import-generate` still drifts by up to 8 s against the recorder clock during its three long waits, so its captions
  land on the wrong screens; it was recorded but not published on `1210795`. A take on a quieter machine, or a cut
  mapping anchored on frame timestamps instead of marker flashes, should fix it.
- `onboarding-intake` drops the Final 2026 exam planning list: on this build onboarding refuses the Bahar and Güz
  planning lists ("16376 columns, limit 1024", their sheets declare a full-width range).
- With `stack.sh`, the backend schema comes from `create_all` (the CLI), not from Alembic, so a
  recording never waits for a migration that in-flight backend work has not written yet.
- `--engine recordly` on Linux is CPU-bound (software WebGL). Use it for one-off renders, or open
  the generated `.recordly` on a Mac and export from there.

## 8. Launch video and 60 fps clips (2026-10-17)

What changed against §5, and why:

| | §5 route (until 2026-10-16) | Launch route (`launch.sh`) |
|---|---|---|
| Capture | screencast PNG at 1x, laid out as a 20 fps lossless video | screencast PNG at 1.5x (desktop) / 2x (phone), **kept as frames** with Chrome's paint time (`metadata.timestamp` + the smallest arrival lag as clock offset); a frame identical to the one before is not stored |
| Pointer | Playwright mouse moved along the path (each `mouse.move` a CDP round trip: under a load of 30 a 0.6 s move took seconds) | `virtualPointer`: the eased path is logged on its planned schedule, the real mouse jumps once; the renderer draws the cursor |
| Phone | not recorded | `REC_DEVICE=phone`: 390x844, `isMobile`, `hasTouch`, taps (`page.touchscreen.tap`), finger dots instead of a cursor |
| Keys | not shown | `Recorder.type/press` log `{t, text}` / `{t, key}`; keystroke chips in the corner of the card |
| Compositing | ffmpeg expressions (piecewise-linear camera, overlay graph), 20-30 fps | a page per output frame (`compositor.html`), 60 fps, sub-pixel CSS transforms; Lottie through `lottie-web` (vector, any size, fractional frames) |
| Dead air | `REC_GIF_MAX_HOLD` (GIF only) | still stretches > 2 s (`LAUNCH_MAX_IDLE_MS`) are cut to 2 s in every output |
| Outputs | MP4 1280-1600 px 30 fps, GIF 1040-1120 px 20 fps ≤ 9 MB | launch MP4 1920x1080 60 fps + AV1 WebM + vertical 1080x1920 + attach MP4 ≤ 9.8 MB + WebP loop ≤ 5 MB; clips: MP4 1600x960 60 fps, WebP 1280 px 30 fps ≤ 4 MB, GIF fallback 25 fps ≤ 9 MB |

`stack.sh` learned `REC_IGNORE_TS=1` (build the copy with `typescript.ignoreBuildErrors`): checkpoint commits of
in-flight lanes did not type-check on 2026-10-17 (`86370b3`), and a recording should not wait for that.

Measured numbers of each render (sizes, durations, bitrates) are in docs/launch/README.md §1/§5 and in the hand-off
of the render's ledger row in docs/PROGRESS.md.
