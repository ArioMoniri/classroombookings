# Common rules for round-1 loop builders (session focused-wright, 2026-10-16)

Repo: /home/user/classroombookings (backend smartsched/backend = FastAPI + SQLAlchemy + Alembic, frontend
smartsched/frontend = Next.js 15 + React Query + vitest + Playwright). Branch `claude/focused-wright-ktt0ss`
(checked out; a continuation of `claude/gracious-cerf-w1598m`, see docs/HANDOFF.md).

Read first: docs/HANDOFF.md, your lane's section of docs/ROADMAP.md ("Flow loop tickets — round 1", the
line range in your brief), your lane entry in docs/testing/flows/rounds/round-1-tickets.json (`owns`,
`tickets[*].check`, `files`), docs/testing/flows/MOBILE.md (M-01…M-14), docs/testing/flows/README.md
§3 (viewports/browser), §4.2 (own stack), §4.7 (checks on every step), the flow files your tickets cite
(F-xx), and smartsched/frontend/AGENTS.md.

## Hard rules
1. **Never commit, stash, checkout, reset or rebase.** The orchestrator checkpoints your work from the
   working tree. Do not touch files outside your lane's `owns` list; if a fix needs another lane's file,
   describe the exact change in your final report under "Asks for lane X" instead.
2. **Test-first.** A failing test (pytest / vitest / a Playwright spec under smartsched/frontend/e2e named
   `loop-r1-lane<X>.spec.ts`) before the fix. Backend: `source smartsched/backend/.venv/bin/activate`, run
   the suites that cover your files plus `ruff check`/`ruff format --check` and `make type` (or mypy on your
   modules). Frontend: `npx tsc --noEmit`, `npx eslint <your files>`, `node scripts/check-design.mjs`,
   `npx vitest run <your test files>`. Never skip, disable or quarantine a test.
3. **Verify every ticket's `check` on a real stack** at 1440 (mouse) and 390×844 (touch, `isMobile`,
   `hasTouch`, locale tr-TR, Europe/Istanbul) with the Playwright **library** from
   smartsched/frontend/node_modules/playwright (Chromium in /opt/pw-browsers, PLAYWRIGHT_BROWSERS_PATH is
   set). Run MOBILE.md M-01/M-02/M-03/M-05 on your lane's `phone_routes` after your changes.
4. **Own stack only.** `scripts/record/stack.sh` with your own `REC_WORKDIR` under the scratchpad and the
   ports in your brief (`REC_API_PORT`/`REC_WEB_PORT`); `REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`.
   `stack.sh up` imports the real workbooks (2–4 min, prod build); `stack.sh runs` makes solver runs
   (~15 min) only if your check needs a published run. Personas/accounts: README §2 and the §4.4 seed
   (flow-seed.sh lives in the testers' scratch; recreate the accounts you need through the API).
   The host has 4 cores and other builders run at the same time: use `nice`, one stack, `stack.sh down`
   at the end. **Never `pkill -f` by pattern**; kill only PIDs you started.
5. Temporary files go under the scratchpad folder named in your brief, never into the repo (except the
   tests and code you own).
6. Turkish first, English second for every user-facing string (messages/tr.json + en.json keys, backend
   `message_tr`/`message_en`). No raw enum/snake_case keys in the UI. Focus never falls to `<body>` after an
   action. 44 px touch targets, 16 px inputs on phones. No hover-only affordances.
7. Do not weaken the integrity guards (`publish_guard.py`, `pin_guard.py`, `move_guard.py`,
   `run_truth.py`, `precheck.py`): they are read-only for every lane.

## Hand-off (do this yourself before your final message)
- In docs/ROADMAP.md, under each ticket you finished: tick `- [x]` and add an indented line
  `done (<what changed, files, tests, how you verified>; loop-r1-lane<X>-2026-10-16)`. Partly done: keep
  `[ ]`, add `part done (...)` and `open: ...`.
- In docs/testing/flows/rounds/round-1-tickets.json set `status: "done"` (or `"partly"`) and a one-line
  `resolution` on each ticket you touched.
- Append rows to docs/PROGRESS.md (append-only ledger; format
  `| YYYY-MM-DD HH:MM | loop builder (loop-r1-lane<X>-2026-10-16) | round-1 lane <X>: <area> | START/milestone/DONE: … | next |`),
  one START row when you begin, one DONE row at the end (include test counts and commands).
- Final message (BLUF, ≤ 40 lines): tickets done / partly / not done with reasons; files changed; tests
  and checks run with counts; stack checks per ticket (desktop + phone); asks for other lanes; anything
  the orchestrator must decide. Nothing is "done" without its check having passed on the stack.

## Simplicity principle (owner, 2026-10-17; applies to every designer, UX, builder and tester)
Admins and academicians are used to classroombookings' plain tools. Keep every feature, but make each screen
calm and obvious:
- one primary action per screen, in plain Turkish;
- advanced options behind "Gelişmiş" or a sheet, never all at once;
- no dashboards of unexplained numbers;
- defaults that work without configuration;
- the CRBS path (look at the week → click a free slot → book) stays two taps.
Testers report "overwhelming" or "where do I click?" as a **major** finding, with a screenshot.
