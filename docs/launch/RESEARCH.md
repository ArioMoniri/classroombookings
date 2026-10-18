# Launch video: tools and delivery research (2026-10-17)

Owner request (2026-10-17 ~20:00 UTC): replace the small, low-quality, laggy README clips with a real launch video,
reuse the existing Lottie animations, add phone views. This file records what was checked, when, and what was decided.
Everything here was checked on **2026-10-17** unless a row says otherwise. "Checked" means fetched or run from this
container; "reported" means a third-party source that could not be confirmed.

## 1. Decision (BLUF)

| Question | Decision | Main evidence |
|---|---|---|
| How to render | **Offline, frame by frame, in headless Chromium** (`scripts/record/launch/`: our own compositor page + `lottie-web` already in the frontend lockfile), from **lossless captures** (Chrome screencast PNG frames at 1.5x on desktop, 2x on the phone) | No screen video in the chain, so the camera, cursor and captions are exactly 60 fps whatever the host load was during the take (the old clips were 20 fps GIFs; the host's load average is 25-37 on 4 cores). Remotion does the same job; its free licence applies (individual open-source project, owner-confirmed 2026-10-17), see §3 for why the first release keeps this renderer |
| Hero video | **MP4, H.264 High, 1920x1080, 60 fps, `+faststart`, crf 15 `-tune animation`, ≤ 60 MB** (2026-10-18: ≤ 25 MB at crf 18 was too soft for UI text); plus **AV1 in WebM** (SVT-AV1, 10-bit) for browsers that play AV1; plus a **1080x1920 vertical cut** | H.264 is the only codec GitHub's own docs recommend for attachments (§4.1); AV1 is smaller at equal quality but not universal on Apple devices |
| README top | **Animated WebP loop** (1280 px, 30 fps, ≤ 5 MB) with a PNG poster, linking to the MP4 | GitHub serves a repository `.webp` as `content-type: image/webp` (checked, §4.2) and the README already shows WebP screens; `<video>` with a repository path is not playable (the raw host sends MP4 as `application/octet-stream` + `nosniff`, checked) |
| Inline player in the README | Only through a **`github.com/user-attachments/...` URL**, which a person creates by dragging the MP4 into GitHub's web editor (≤ 10 MB on a free plan). `launch.sh encode` writes `smartsched-launch-attach.mp4` (≤ 9.8 MB) for that | GitHub docs: video attachments 10 MB (free) / 100 MB (paid) (§4.1); reported: GitHub expands a bare user-attachments URL into a `<video>` element |
| GIF | **Kept only as a fallback**, not for new media | 10 MB image limit, 256 colours, frame delays in 1/100 s (60 fps impossible, 50 fps max); a GIF of a moving camera costs ~2.5 MB per second at 1040 px (RECORDLY.md §7) |
| AVIF | Written (`smartsched-loop.avif`), **not used in the README yet** | Animated AVIF plays in Chrome, Firefox 113+ and Safari 16.4+, but whether GitHub's raw host labels `.avif` as `image/avif` could not be checked from here (only this repository is reachable); with `nosniff`, a wrong label blocks the image |

## 2. Screen-recording polish tools

| Tool | State on 2026-10-17 | Relevance |
|---|---|---|
| **Recordly** ([releases](https://github.com/webadderallorg/Recordly/releases), fetched 2026-10-17) | Latest **v1.4.0, 2026-09-08** ("Latest"): Windows 10 cursor style, window capture on Windows, improved motion blur, auto-caption fix. **v1.3.5-beta.2, 2026-07-11**: animated zoom-region transitions, auto-zoom/FPS-bitrate fixes, click effects that stay visible when the cursor is hidden, editable caption timeline with SRT/VTT sidecar export. No keystroke overlay in the release notes. AGPL-3.0, fork of OpenScreen | Its project format and headless smoke export are already driven by `scripts/record` (RECORDLY.md §1-2). Under software WebGL it renders 17.5 s in 780 s, so it is not the launch renderer; the `.recordly` projects stay for hand editing on a Mac |
| **Screen Studio** ([review, daveswift.com](https://daveswift.com/screen-studio/); [screensnap.pro, 2026-05](https://www.screensnap.pro/es/blog/screen-studio-for-windows)) | macOS only, no Windows version planned (reported 2026-05). Auto-zoom on clicks, cursor smoothing, motion blur on cursor/zoom/pan, keystroke overlays, Whisper captions | The look we reproduce: spring camera, enlarged cursor with click ripples, keystroke chips, burned-in captions. Not scriptable, not usable in a headless container |
| **Remotion** (npm `remotion` **4.0.536, published 2026-10-16**; `@remotion/lottie` 4.0.536, same day; [LICENSE](https://cdn.jsdelivr.net/npm/remotion@4.0.529/LICENSE.md)) | React compositions rendered frame by frame in headless Chrome; `@remotion/lottie` wraps `lottie-web`. Licence: free for individuals, for-profit organisations with **up to 3 employees**, non-profits and evaluation; **everyone else needs a Company License**; "In Remotion 5.0, the license will slightly change" | Technically the best fit and the same principle as our renderer. Not adopted: a university deployment or a company contributor would need a paid licence to re-render the video, and a 100+ package toolchain for one page is out of proportion. Our renderer is ~400 lines on dependencies the repository already has (Playwright, lottie-web, ffmpeg) |
| **Motion Canvas** (npm `@motion-canvas/core` **3.17.2, 2024-12-14**, MIT) | No release in 22 months | Canvas-drawn animation, not built around real UI captures; stale |
| **Lottie / dotLottie / Rive** (npm `lottie-web` 5.13.0 2025-05-21 MIT; `@lottiefiles/dotlottie-web` 0.81.0 2026-10-06 MIT; `@rive-app/canvas` 2.45.0 2026-10-17 MIT) | dotLottie is a zipped Lottie with a WASM (ThorVG) player; Rive has its own state-machine format and editor | Our four animations are Lottie JSON (`docs/lottie/*.json`). `lottie-web`'s SVG renderer is vector, so `goToAndStop(frame)` at any size is crisp, and fractional frames give 60 fps motion from 30 fps sources. dotLottie/Rive would add a format and a player for no gain here |

## 3. Why not Remotion (in one paragraph)

**Update 2026-10-17 (owner):** Remotion free licence: individual open-source project, owner-confirmed 2026-10-17. The
licence is therefore no longer a reason. The renderer stays the one in `scripts/record/launch/` for this release
because it was already rendering the first cut when the owner allowed Remotion, it is deterministic and resumable on
this shared host (chunked, crash-retrying workers), and it needs no new packages; switching would re-implement the
same compositing for no visible gain. A Remotion port remains a one-to-one mapping (below) if the owner wants
explainer videos edited in Remotion Studio; it would live in `scripts/record/remotion/` with its own pinned
package.json and render with `--browser-executable` pointing at `/opt/pw-browsers` (no browser download),
`--concurrency=2`, under `nice`.

The original reasoning, before the owner's confirmation:

Remotion is the state of the art for "video as React", and its renderer works exactly like ours: a page per frame,
screenshots, ffmpeg. The deciding facts were the licence (§2: a Company License for for-profit organisations over 3
people, and a change announced for 5.0) and that the repository already pins every piece the job needs. If the owner
holds a Remotion licence later, `story.mjs` maps onto a Remotion composition one to one (scenes = `<Sequence>`, the
camera track = an `interpolate`d transform, `@remotion/lottie` for the Lottie layers).

## 4. What GitHub renders today

### 4.1 Documentation ([Attaching files](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files), fetched 2026-10-17)

- Images and GIFs: PNG, GIF, JPEG, SVG; **10 MB**.
- Videos: **MP4, MOV, WebM**; **10 MB** for repositories of users/organisations on a free plan, **100 MB** on a paid plan.
- "Codec support varies by browser … We recommend H.264 for greatest compatibility."
- [Changelog 2022-05-19](https://github.blog/changelog/2022-05-19-option-to-prevent-animated-images-from-playing-automatically/):
  GitHub stops "animated images, like GIFs" from autoplaying when the system asks for reduced motion, or when the
  user turns autoplay off; then each animated image gets play/pause controls.

### 4.2 Checked from this container

| Check | Result |
|---|---|
| Rendered README (`GET /repos/ArioMoniri/classroombookings/contents/README.md?ref=claude/focused-wright-ktt0ss`, `Accept: application/vnd.github.html+json`) | `<picture>` + `<source media="(prefers-color-scheme: dark)">` kept; `<img src="….webp">` kept; GIFs get `data-animated-image` (the pause/reduced-motion control above), **WebP images do not** |
| `raw.githubusercontent.com/…/bookings-day-light.webp` | `200`, `content-type: image/webp`, `x-content-type-options: nosniff` |
| `raw.githubusercontent.com/…/find-room.mp4` | `200`, `content-type: application/octet-stream`, `nosniff`: a `<video src="docs/…mp4">` cannot play it (and GitHub's sanitizer is reported to strip a repository-path `<video>` anyway) |
| `github.com/<repo>/raw/<branch>/…gif` | `302` to raw.githubusercontent.com (images in the README load from there) |
| `<video>` / `user-attachments` behaviour | Could not be checked (`api.github.com/markdown` and other repositories are not reachable from this session). Reported ([Forgejo issue, 2026-05](https://forge.barrettruth.com/barrettruth/nix/issues/16)): GitHub turns a bare `github.com/user-attachments/assets/<uuid>` line into `<video>`; the attribute set is not documented |
| GitHub mobile app | No documentation found. The app renders README HTML in a web view; GIF and WebP decode in iOS 14+ and Android web views. A phone also gets the vertical MP4 link |

### 4.3 Consequences for the README

1. Top of the README: `<a href="docs/launch/media/smartsched-launch.mp4"><img src="docs/launch/media/smartsched-hero.webp" width="100%"></a>` (the desktop hero since 2026-10-18; it was the phone loop `smartsched-loop.webp`, now linked under it).
   Because GitHub does not pause WebP for reduced motion, the loop is short (10 s), calm (no flashes), and wrapped in
   `<picture><source media="(prefers-reduced-motion: reduce)" srcset="…poster.png">`; whether GitHub keeps that media
   query is to be confirmed on the rendered README after the commit (command in docs/launch/README.md §4).
2. Inline playback needs one manual step by a maintainer (drag `smartsched-launch-attach.mp4` into the README editor
   on github.com and keep the generated URL on its own line). Until then the MP4 link opens GitHub's file view.
3. GIF budget rules (RECORDLY.md) stay for the per-feature clips that are still GIFs.

## 5. Encoders (this container: ffmpeg 6.1.1, libx264 0.164, SVT-AV1 1.7.0, libaom 3.8.2, libwebp 1.3.2)

| Encoder | Use | Settings and why |
|---|---|---|
| libx264 (H.264 High) | launch MP4, vertical MP4, attach MP4 | `-profile:v high -preset slow -tune animation -crf 15…` (lowest CRF of the ladder that fits the byte budget; 2026-10-18, was 18…28), BT.709, `yuv420p`, keyframe every 4 s, `+faststart` (the moov atom first: playback starts before the download ends) |
| libsvtav1 | `smartsched-launch-av1.webm` | `-preset 5 -crf 34 -g 240`, 10-bit (`yuv420p10le`: no banding on the soft gradients). SVT-AV1 upstream is at 4.x ([Phoronix, 2026-01-25](https://www.phoronix.com/search/AV1)); 1.7.0 here is older but produces standard AV1 |
| libx265 (HEVC) | not used | Plays in Safari and on Apple/Android hardware, but not in Firefox or Chrome on Linux without system codecs; AV1 + H.264 cover the same ground royalty-free |
| libwebp_anim | README loop | lossy, quality 80 → 50 ladder until ≤ 5 MB at 1280 px / 30 fps |
| SVT-AV1 in the `avif` muxer | `smartsched-loop.avif` | written for later (§1) |

## 6. Sources

- Recordly releases: <https://github.com/webadderallorg/Recordly/releases> (v1.4.0 2026-09-08; v1.4.0-beta.1 2026-09-05; v1.3.5-beta.2 2026-07-11), fetched 2026-10-17.
- Recordly coverage: <https://www.digitalcitizen.life/recordly-1-3-5-beta-2-brings-reliability-fixes-caption-tools-and-smoother-screen-recording-workflows/>, <https://www.abduzeedo.com/recordly-free-open-source-screen-recorder-auto-zoom> (undated in the snippets).
- Remotion licence: <https://cdn.jsdelivr.net/npm/remotion@4.0.529/LICENSE.md>; versions from <https://registry.npmjs.org/remotion> and `@remotion/lottie` (4.0.536, 2026-10-16), fetched 2026-10-17. Lottie in Remotion: <https://www.remotion.dev/docs/lottie>.
- npm registry (fetched 2026-10-17): `@motion-canvas/core` 3.17.2 (2024-12-14), `lottie-web` 5.13.0 (2025-05-21), `@lottiefiles/dotlottie-web` 0.81.0 (2026-10-06), `@rive-app/canvas` 2.45.0 (2026-10-17).
- Screen Studio: <https://daveswift.com/screen-studio/>, <https://www.screensnap.pro/es/blog/screen-studio-for-windows> (2026-05).
- GitHub: <https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files>; <https://github.blog/changelog/2022-05-19-option-to-prevent-animated-images-from-playing-automatically/>; the rendered-README and raw-host checks in §4.2 (2026-10-17 20:05-20:08 UTC).
- user-attachments `<video>` report: <https://forge.barrettruth.com/barrettruth/nix/issues/16> (2026-05; 404 when fetched on 2026-10-17, quoted from the search index).
- SVT-AV1 4.0: <https://www.phoronix.com/search/AV1> (headline dated 2026-01-25).
