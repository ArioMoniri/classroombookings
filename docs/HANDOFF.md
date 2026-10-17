# Cross-session hand-off (gracious-cerf ⇄ focused-wright)

This file is written for the orchestrator session that ran `claude/gracious-cerf-w1598m` and hit the
weekly usage limit on **2026-10-16 ~15:20 UTC**, and for whoever resumes after that. A second session
(`focused-wright`) picked the work up on its own branch so nothing is pushed to `gracious-cerf` behind
that session's back.

## Where the work is

| What | Value |
|---|---|
| Continuation branch | `claude/focused-wright-ktt0ss` (starts as a fast-forward of `gracious-cerf` tip `455f9703`) |
| Start point | `455f9703` (the last gracious-cerf commit). Local tag `handoff/focused-wright-start`; the cloud git proxy refuses pushes to `refs/tags/*`, so the tags exist only in that container and **this table is the authoritative list of checkpoints** |
| Checkpoints (safe points) | 1 = `ced0e02b` lane F2 hand-off (T-R1-42, T-R1-39). Later rows are appended to the progress log below with their SHA |
| Pod CI / deploy | still polls `claude/gracious-cerf-w1598m` + `claude/smartsched-universal` (`deploy/pod-ci/podci/config.py`); the continuation branch is **not** built by the pod until it is merged back |

**To resume on gracious-cerf when its session is back:** `git fetch origin && git merge --ff-only
origin/claude/focused-wright-ktt0ss` on `claude/gracious-cerf-w1598m` (it is a strict descendant; no
merge commit needed), then push. If gracious-cerf moved in the meantime, use a normal merge and keep
`alembic heads` at one. Then read the "Open work" table below and `docs/AGENT_STATE.md`.

## State at the hand-off (what the limit interrupted)

Round 1 of the flow loop (ROADMAP "Flow loop tickets — round 1", `docs/testing/flows/rounds/round-1-tickets.json`)
had 8 builder lanes. At `455f9703`:

| Lane | Done (code landed) | Open | Notes |
|---|---|---|---|
| A touch/keyboard/shell | T-R1-01…09 (all; A2 finished 00:00 UTC) | — | ticked |
| B approvals/bookings | T-R1-10, 11, 14, 15, 16, 17, 18, 19, 20 (B2 finished 00:10 UTC) | T-R1-13 UI grouping re-check in round 2 (id reuse fixed in 80cffb43) | |
| C intake/council | T-R1-21–26 | T-R1-25 "rename one instructor" part | needs an owner decision: a stable person key (staff number column) or the merge-review flow |
| D KVKK | T-R1-27, 28, 29 | — | ticked |
| E i18n/admin | T-R1-31…38 (E2 finished 00:20 UTC) | T-R1-30 part (login SSO hint label → sweeper) | |
| F dashboard/learning | T-R1-39, 40, 41, 42 (all; F2 finished 23:40 UTC) | — | ticked |
| G test plan/tooling | T-R1-43, 44, 45 | — | ticked |
| H studio/runs/timetable | T-R1-46…50 (H finished 00:20 UTC) | — | ~40 min of WIP swept into checkpoints `b53ee1b`, `5fa0ceb` (runs/publish-run.tsx, studio/generate-step.tsx, program-wizard/generate-step.tsx, services/studio.py, tr_grammar.py); + lane-A hand-ons (/classes segments, move-dialog selects, inspector "more" button) |
| Integrity (solver-engineer) | R1-M-02..06, 10, 11, 12; R1-S-01, 02, 06, 07, 09, 17; R1-S-04 part | 2 follow-ups (pin guard by programme/text at write time; R1-S-04 root cause) | |
| E2E stabilisation | fixes landed | "two green full gate runs + mobile" not confirmed | last milestone 07:25: 154 passed / 18 failed / 3 flaky |

Owner decisions still open (ROADMAP): R1-M-07 (KVKK AI default), R1-S-37 (forced edit on the live plan),
the locked-class self-move (recommend: keep as re-deciding the lock), T-R1-25 person key.

## What focused-wright does, in order

1. Scaffolding (this file, registry reset, start tag). Status: done.
2. Round-1 builders for the open lanes: A2, B2, E2, F2, H, in parallel, same scope fences as
   `round-1-tickets.json` `owns`. Agents never commit; the orchestrator checkpoints and pushes.
3. Gates on HEAD (backend `make check`, frontend `npm run check`, e2e gate per `deploy/pod-ci/gates`).
4. Round 2 re-test (three persona testers → suggester → builders) until no blocker/major.
5. Stabilisation, universal sync, deploy via `infra/aws/POD_ACTION`, README media, BLUF.

## Environment notes for the resuming session

- The AWS keys injected into the focused-wright container were temporary and expired at 22:48 UTC on
  2026-10-16 (`AWS_CREDENTIAL_EXPIRATION`); `infra/aws/smartsched_aws.py status` refuses to run after that.
  Pod control therefore stays on the documented path: push `infra/aws/POD_ACTION` on the deploy branch
  (OIDC role). A scratch venv with boto3 for the helper is under the session scratchpad only.
- Dev toolchain was bootstrapped with `scripts/dev.sh` (backend `.venv`, frontend `node_modules`); the
  seeded dev admin lives only in the local SQLite file and is not used by any stack.
- Builder stacks use ports 19210/19211 (A2), 19220/19221 (B2), 19230/19231 (E2), 19240/19241 (F2),
  19250/19251 (H); SMTP sinks 2541–2543. Round-2 testers take the re-test rows of README §4.2 (+100).

## Leftovers queued for a sweeper agent (after lane H finishes)

- ~~T-R1-30 part~~ done by the sweeper (code); /login TR hint to be re-checked on a stack in round 2.
- ~~`lib/api/crbs.ts` zod fields~~ done by the sweeper; users-admin.tsx does not yet show `warning` / `summary_text` (optional).
- ~~moderation-console pct(poss)~~ done by the sweeper.
- ~~welcome viewport duplicate~~ removed by the sweeper.
- `tests/test_crbs_languages`: regenerate the locale data after all message-key changes (see the test for the command).
- Owner-decision items stay open: R1-M-07, R1-S-37, locked-class self-move, T-R1-25 person key.

## Progress log (newest first)

- 2026-10-17 05:05 UTC — **round-2 suggester done** (commit 2944f1d9): 35 tickets T-R2-01…35 (1 blocker: intake dry run ≠ commit; 12 major), round-1 tickets 40 verified / 10 reopened. **Round-2 builders launched**: lanes A (shell/ui/auth, :19310), B (bookings/find-room/approvals, :19320), C (intake/council/wizard, :19330), D (moderation/learning UI, :19340), E (studio/runs/timetable, :19350), F (admin/audit/i18n, :19360), S (solver minimal-change re-solve, solver-engineer), G (test-plan drift). The e2e gate agent is still running (:19260).
- 2026-10-17 04:40 UTC — round-2 suggester launched (reports → `Flow loop tickets — round 2` + `rounds/round-2-tickets.json`). Housekeeping for the user: the admin tester left a stray folder `/flow-in-F08` at the container's filesystem root (two copies of the Bahar fixture workbooks, 1.7 MB); the session's safety check refuses to delete a root-level folder, so it stays until a person removes it (`rm -rf /flow-in-F08`). It is outside the repository.
- 2026-10-17 04:30 UTC — **round 2, admin report in** (`rounds/round-2-admin.md`): round-1 ids 27 verified, 7 in part, 3 reopened (R1-M-07 owner decision; R1-M-26 two-period request split into conflict rows; R1-M-35 tenant text); integrity hard rules hold. 27 new: 0 blocker, 6 major (re-check resets per-date choices; re-solve preview publish shows a client error although the server published; minimal re-solve still moves/loses planner-locked rows, reopens R1-S-04; 'Sorun 457' next to '398 kabul edilmiş istisna'; person-level learning reset leaves suggestions open; intake dry-run vs commit counts disagree), 18 minor, 3 suggestions. **All three round-2 reports are in: 68 new findings, 0 blockers, 16 majors.** Next: round-2 suggester → lane builders.
- 2026-10-17 03:30 UTC — **round 2, staff report in** (`rounds/round-2-staff.md`): round-1 ids 27 verified, 6 reopened (R1-S-04 re-solve still loses 17 classes; S-16 Taşı 36 px; S-19 no suggestion for instructor 157; S-22 rail week count; S-24 English refusal on force move; S-31 intake job list lost on reload), 3 inconclusive. 22 new: 0 blocker, 6 major (forced password change never leaves the page; recurring sheet, my-bookings, approvals and find-room phone sizes/sticky actions; withdraw confirm does not trap focus), 14 minor. Waiting for the admin report, then the suggester.
- 2026-10-17 02:00 UTC — **round 2, academician report in** (`rounds/round-2-academician.md`): 40 round-1 ids → 37 verified, 3 reopened (R1-A-17 Yaklaşan list still two rows per span; R1-A-35/36 are unbuilt enhancements FLE-001/006). 19 new: 0 blocker, 4 major (page-level fields under the phone keyboard on /profile and /find-room; confirm dialogs do not trap focus; /find-room Ara not sticky on phones; small controls on /find-room), 10 minor, 2 trivial, 3 suggestions. Waiting for staff and admin reports, then the suggester.
- 2026-10-17 00:45 UTC — **round 2 started** on snapshot `deb38315`: persona testers staff (:19210/19211), academician (:19220/19221), admin (:19230/19231, fresh :19232/19233) re-run every flow of their column at 1440 + 390 and re-verify their round-1 ids; reports go to docs/testing/flows/rounds/round-2-<persona>.md/.jsonl. The e2e gate runs after the testers (load).
- 2026-10-17 00:42 UTC — backend fast gate on HEAD: 1618 passed, 7 failed, all seven resolved: generated language data regenerated (tools.crbs_lang_import), two council LLM tests now expect the localized Turkish lines their Turkish job gets (T-R1-23), an empty ANTHROPIC_MODEL env value counts as unset (settings_service), two tests needed reportlab in the local venv (environment only), one calendar-connector test passed alone (order flake, noted). Round 2 starts on the next pushed commit.
- 2026-10-17 00:38 UTC — **sweeper 2 done**: week-run exports download as smartsched-run<id>-hafta<n>.xlsx/.csv (R1-M-38), ScheduleRun.error in zod feeds the cancelled-run report, solver settings save button and slider thumbs get 44 px on touch (slider primitive, benefits every slider), users-admin shows import warnings and the API summary. pytest 7, vitest 164. Round-2 stack re-checks: export file name, /settings?tab=solver at 390.
- 2026-10-17 00:45 UTC — frontend gate green on HEAD: tsc 0, eslint clean (onboarding set-state-in-effect fixed in a12ab0ba), check-design pass, vitest 159 files / 964 tests. Backend fast suite running; sweeper 2 (runs export name, ScheduleRun.error, solver settings phone sizes) running.
- 2026-10-17 00:20 UTC — **lane H handed off** 5/5: T-R1-46…50 done and verified at 1440 + 390 touch with no AI key (chip → pre-filled template with programme multi-select, Studio scope counts and week wording, cancelled-run report + one server-side problem count + phone publish capsule, timetable start-week move/skip link/focus, wizard undo texts and button); e2e loop-r1-laneH 6/6, vitest 291, pytest 18. Asks → sweeper 2: runs.py export file name for week exports, ScheduleRun `error` in zod, /settings?tab=solver admin inputs (14 px, 36 px save). **Round-1 build phase complete.** Also: README rewritten (short plain sections, recordings first and generated from docs/images/recordings/clips.json by sync_docs `recordings` block, illustration GIFs dropped).
- 2026-10-17 00:25 UTC — **sweeper done**: login SSO hint uses the localised role label (T-R1-30 code part; stack re-check of /login TR hint pending → round 2), CRBS import/room zod fields, moderation header pct(poss), duplicate welcome viewport removed. tsc 0, vitest 47. Interesting for lane E later: users-admin could surface `warning`/`summary_text`.
- 2026-10-17 00:15 UTC — lane E2 addendum: T-R1-12 last part done (org-settings save keeps focus on the form; phone capsule clears the tab bar), e2e loop-r1-laneE 6/6. T-R1-12 is complete.
- 2026-10-17 00:20 UTC — **lane E2 handed off** 8/9: T-R1-31, 32, 33, 34 done; 35, 36, 37, 38 re-verified and ticked; T-R1-30 partly (login SSO hint prints the raw role name → sweeper, components/auth/sign-in-page.tsx). pytest 118, vitest 100, e2e loop-r1-laneE 5/5. Asks: relaxation-term-card phone sizes → lane H; lib/api/crbs.ts zod fields, moderation-console pct(poss) → sweeper. E2 is being resumed once more for the org-settings focus/capsule ask (T-R1-12 part). Checkpoint 4 = the commit carrying this line.
- 2026-10-17 00:10 UTC — **lane B2 handed off** 9/11: T-R1-15, 16 done; 10, 11, 14, 17, 18, 19, 20 re-verified and ticked; T-R1-12 partly (Ayarlar › Rezervasyon onayı › Kaydet focus → lane E2, org-settings.tsx); T-R1-13 partly (correct grouping blocked by multi_booking_id rowid reuse on SQLite in services/bookings.py — orchestrator fixes). e2e loop-r1-laneB 5/5, vitest 194. Checkpoint 3 = the commit carrying this line.
- 2026-10-17 00:00 UTC — **lane A2 handed off** 8/8: T-R1-02…09 done and verified at 1440 + 390 touch (keyboard clearance, phone dialog layout, bell sheet, notification cards by role, tab bar/shortcuts/toasts, Turkish accessible names, breadcrumbs, login field messages + permission-based landing). vitest 167, e2e loop-r1-laneA 8/8. Ask routed to lane B2: /my-bookings row M-02 (checkbox hit area cut by chip/date button). Checkpoint 2 = the commit carrying this line.
- 2026-10-16 23:40 UTC — **lane F2 handed off**: T-R1-42 (invigilation pool matches masked/titled exam names; pool line, empty-pool reason + one-tap all-instructors) and T-R1-39 part 2 (board placements feed the moderation match rate, 72 % on Güz) done and verified desktop+phone; tests test_loop_r1_laneF2.py, e2e loop-r1-laneF 6/6. Tag `handoff/focused-wright-1`. Open asks routed: pct() possessive case → lane E2; keyboard-clearance scrollIntoView guard → lane A2; MOBILE.md /exams/invigilation row → orchestrator.
- 2026-10-16 22:30 UTC — session focused-wright started; branch + start tag pushed; registry agents of the
  interrupted session marked stopped/finished with where they left off; builders being launched.
