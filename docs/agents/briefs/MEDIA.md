# Launch video + mobile optimisation (owner request 2026-10-17 ~20:00 UTC)

Owner's words: "a better, more fancy Recordly video with the previously available Lottie elements. The videos are so
small, look nothing like a launch video, are low quality and laggy on GitHub: replace them with new ones, all
optimised, with mobile views. Separate launch-video and mobile-optimiser subagents, without interfering with the other
subagents; research tools and skills as of October 2026. Designers can use the transitions.dev skill; it has limited
free capacity, so use it wherever it is needed (not everywhere)."

Read COMMON.md (same folder) first; its rules apply (no commits, own ports, never `pkill -f`, nice, scratch only).
Other agents are building in the shared tree right now (see WAVE3.md: AI, security, ops, slot display/quick reserve;
plus round-3 fix lanes in intake, solver, timetable, moderation, bookings/find-room, admin). Never edit their files.

## transitions.dev (FREE plan: the owner has no Pro)
- Use only the **32 free recipes**, already pulled to
  `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/transitions/free/*.md`
  (`npx transitions-dev add <name>` adds a single free one). No Pro skill, no Pro recipes: never run `login`, `skill`
  or `add --pro`.
- The free **Motion Agent**: unlimited scans, but only **10 hosted polish fixes a month for the whole project**: at
  most one per agent, only for a hero moment, named in your report. The key is in the environment variable
  `TRANSITIONS_AGENT_LICENSE` of this session: never write it to any file, log, commit, report or URL.

## Existing media pipeline (reuse, extend, do not fork)
- `scripts/record/**`: stack.sh, journeys/*.mjs (Playwright scripted journeys with captions), record-all.sh,
  screens.mjs, publish.sh (GIF clips + MP4 + posters), refresh.sh, lib/{camera,polish,recordly,screencast,touch}.mjs;
  `docs/recording/RECORDLY.md` (what was tried: CDP screencast → ffmpeg polish is the current default; Recordly
  renderer works but is slow under software WebGL).
- Lottie: sources `docs/lottie/*.json` (hero-solver, nl-to-rules, file-to-rules, precheck-fix; light + dark),
  renders `docs/images/lottie/*`, build script `docs/lottie/build/render.sh`.
- README media block is generated: `docs/images/recordings/clips.json` → `scripts/docs/sync_docs.py` block
  `recordings`; `scripts/record/check_readme.py` runs in pod CI and fails on a missing file.
- Host tools: ffmpeg (libx264, libx265, libsvtav1, libaom, libvpx-vp9, libwebp_anim), ImageMagick, xvfb-run,
  Playwright Chromium (/opt/pw-browsers), node 22. 4 shared cores.

## Remotion (owner, 2026-10-17)
Designer and motion agents may use Remotion for the launch, explainer and README videos (and the welcome-guide hero, WG-09). Rules:
- Use the self-contained project in `scripts/record/remotion/`, with its own pinned package.json; never the app's package.json.
- Render with Chromium from /opt/pw-browsers, using `nice` and `--concurrency=2`.
- Output goes through publish.sh / clips.json.
- Licence: owner confirmed 2026-10-17 that this is an individual open-source project, so the free Remotion licence applies to published videos.
