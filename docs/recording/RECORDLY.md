# Demo recordings with Recordly

How to make the SmartSched "how to use" recordings: by hand with **Recordly** on a Mac (best
quality), or automatically with the pipeline in `scripts/record/`, which drives the real app with
Playwright and adds Recordly-style polish. The pipeline can also hand its result to Recordly, either
to render on Linux or to fine-tune in the Recordly editor.

> **Status (2026-10-15).** Five journeys are recorded on the real backend and published in the README
> (`docs/images/recordings/`, 1280×848 MP4 + animated WebP + poster, light theme, English captions):
> `import-generate`, `calendar-move`, `studio-rule-fix`, `room-booking` and `admin-user`. All five were
> verified on 2026-10-08 against the Liquid Glass v2 UI. They were made with the **Playwright video →
> ffmpeg** route (§2 b), not with Recordly's renderer: in this container Recordly renders with software
> WebGL at about 45 s per second of video, which was too slow for five takes. Every take still writes a
> `.recordly` project, so a take can be opened and re-exported in Recordly on a Mac. See [Journeys](#journeys).

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

Each journey is a module in `scripts/record/journeys/`. Its captions are the step texts below (English;
`--lang tr` uses the Turkish texts in the same file). To record one by hand with Recordly, follow the same
steps and pause about 1 s after each step, so auto-zoom has something to frame. `scripts/record/record-all.sh`
records the five README journeys in this order: `calendar-move`, `studio-rule-fix`, `room-booking`,
`admin-user`, `import-generate`.

| Journey (`--journey`) | DB | Captions (= steps) | Published | Verified |
|---|---|---|---|---|
| `import-generate` | **fresh** (`stack.sh up --fresh`: admin + an empty 2026-BAHAR term) | Import the weekly room grid workbook → Then the planning list with every section → The import report: rows read, rows skipped and why → Generator Studio: plan week 3 of the term → The pre-check warns before solving: some classes cannot fit → Generate anyway to get the full diagnosis (solving time skipped) → The run report: every placed class keeps every hard rule → What could not be placed is listed with the reason and fixes. The waits for the import jobs and the solver are cut from the video. | `import-generate.{mp4,webp}`, 67 s; README hero | 2026-10-08 |
| `calendar-move` | seeded + `stack.sh runs` (published full-term COURSE run of 2026-GUZ; `REC_CAL_TERM`) | One room's week, from the published timetable → Click a class: the inspector shows when, where and why → Move it: only rooms that are free and fit are offered → The server re-checks every rule before it saves → Changed your mind? Undo puts it back | `calendar-move.{mp4,webp}`, 34 s | 2026-10-08 |
| `studio-rule-fix` | seeded | Rules are sentences: start from a template → Fill in the blanks; the preview counts the classes it affects → The pre-check tests the plan against the data before solving → Each problem names the classes involved and offers fixes. Uses the template path: plain-language rules need an Anthropic key, which the recording stack does not have. | `studio-rule-fix.{mp4,webp}`, 34 s | 2026-10-08 |
| `room-booking` | seeded (booking setup by `setup_api.py bookings`: Güz 2026-27 open) | Rooms by period for one day; classes from the timetable are already there → Pick a free period in a room that fits → Add a note and book it → It is listed under My bookings, with a calendar feed and CSV export. Booked as the seeded administrator in `REC_BOOK_ROOM` (A203) on the next teaching day. | `room-booking.{mp4,webp}`, 28 s | 2026-10-08 |
| `admin-user` | seeded | Setup → Users lists every account with its role → Add an account for the planning office → Pick the role; roles with rights you lack are greyed out → Save: the account can sign in straight away. The account is a functional one (`planlama`), not an invented person; the setup step deletes it from an earlier take. | `admin-user.{mp4,webp}`, 31 s | 2026-10-08 |

Older modules that are **not** part of the README set and were not re-verified on the v2 UI:
`login-dashboard` (the original sample journey), `run-report-fix` (covered by the last two captions of
`import-generate`) and `chat-edit` (needs an AI key; the model's answer varies between takes).

## 5. Automated pipeline

Requirements: the dev setup from `smartsched/README.md` (Python deps, `npm ci` in
`smartsched/frontend`), Playwright's Chromium (`PLAYWRIGHT_BROWSERS_PATH`, default
`/opt/pw-browsers`), `ffmpeg`/`ffprobe` ≥ 6, ImageMagick (`convert`), Node ≥ 22. Optional:
`xvfb-run` plus the extracted AppImage for `--engine recordly`.

```bash
# 1. isolated stack: SQLite + the real workbooks on :8610, production frontend build on :3610
#    (REC_API_PORT / REC_WEB_PORT to change them)
#    (everything under $REC_WORKDIR, default /tmp/smartsched-rec; nothing is written to the repo)
scripts/record/stack.sh up && scripts/record/stack.sh runs   # or: up --fresh (empty term, for import-generate)

# 2. one journey
node scripts/record/record.mjs --list
node scripts/record/record.mjs --journey calendar-move --theme light --out recordings/calendar-move-light
node scripts/record/record.mjs --journey room-booking --theme dark --lang tr

# 3. the five README journeys (one seeded stack + snapshot; a fresh stack for import-generate),
#    then the README copies under stable names
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
`REC_CURSOR_SCALE`. The recorder can point at any running SmartSched, not only the local stack
(set `REC_BASE_URL` and the credentials).

Output per take (`<journey>-<theme>[-tr]`):

| File | What |
|---|---|
| `*.mp4` | H.264 yuv420p, 30 fps, 1600×1060, `+faststart`; zoom, cursor, ripple, captions, framed |
| `*.webp` | animated WebP, looped, under `REC_WEBP_MAX_BYTES` (4 MB); `publish.sh` re-encodes it for the README under 2.6 MB |
| `*.gif` | only with `REC_GIF=1`: palette GIF, looped, under 4 MB |
| `*.poster.png` | frame from the step marked `poster` (else 60 % in): the GIF/MP4 placeholder |
| `*.raw.mp4`, `*.raw.mp4.cursor.json`, `*.recordly` | the trimmed raw take and a Recordly project. Open it in Recordly on any OS and fine-tune; on another machine, re-link the video if Recordly asks |
| `*.timeline.json` | steps, targets (bounding boxes), pointer track and sync data on the video clock |
| `*.recordly.mp4` | Recordly's own render (`--engine recordly/both`) |
| `*.failure.png` | screenshot when a journey fails; the raw take is kept |

How it works:

1. **Record.** Playwright opens Chromium with `recordVideo` at the viewport size, the theme
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

`scripts/record/publish.sh RECORD_ALL_OUT_DIR light` writes the README copies under stable names into
`docs/images/recordings/`: `<journey>.mp4` (H.264, 1280 px wide, CRF 28), `<journey>.webp` (animated, the
first width/fps/quality rung under 2.6 MB) and `<journey>-poster.webp`. Build into a scratch DEST first and
copy once: every re-encode committed to `docs/images` stays in git history. Commit only these three files
per journey (the raw take, timeline and Recordly project are build artefacts).

The README shows the animated WebP and links it to the MP4:

```html
<a href="docs/images/recordings/calendar-move.mp4">
  <img alt="Screen recording: room A 204's week in the calendar; a class is opened in the inspector,
       moved to a free room that the server confirms fits, and the move is undone."
       src="docs/images/recordings/calendar-move.webp">
</a>
```

GitHub does not play a `<video>` whose src is a repository path; for an inline player, drag the MP4 into
the README in GitHub's web editor (it becomes a github.com/user-attachments URL on its own line). Write
`alt` text that describes the action, and keep the poster next to each video for readers with reduced
motion or a slow connection.

## 7. Known limitations

- The five README journeys run on the v2 UI (2026-10-08). A failing step writes `*.failure.png` and keeps
  the raw take; re-check the selectors after a UI change (they use `data-testid`s with role/label fallbacks).
- `chat-edit` needs an Anthropic key in the backend, and the model's answer varies between takes. Record it
  more than once and keep the best take.
- Size: long journeys fall back to smaller WebP rungs (`import-generate`, 67 s). Link the MP4 for detail.
- With `stack.sh`, the backend schema comes from `create_all` (the CLI), not from Alembic, so a
  recording never waits for a migration that in-flight backend work has not written yet.
- `--engine recordly` on Linux is CPU-bound (software WebGL). Use it for one-off renders, or open
  the generated `.recordly` on a Mac and export from there.
