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
| B approvals/bookings | T-R1-10, 11, 12, 13, 14, 17, 18, 19, 20 | T-R1-15, T-R1-16 | landed tickets not yet re-checked nor ticked in ROADMAP |
| C intake/council | T-R1-21–26 | T-R1-25 "rename one instructor" part | needs an owner decision: a stable person key (staff number column) or the merge-review flow |
| D KVKK | T-R1-27, 28, 29 | — | ticked |
| E i18n/admin | T-R1-30, 35, 36, 37, 38 | T-R1-31, 32, 33, 34 | + lane-A hand-on: admin schedule weekday toggles |
| F dashboard/learning | T-R1-39, 40, 41, 42 (all; F2 finished 23:40 UTC) | — | ticked |
| G test plan/tooling | T-R1-43, 44, 45 | — | ticked |
| H studio/runs/timetable | — | T-R1-46, 47, 48, 49, 50 | ~40 min of WIP swept into checkpoints `b53ee1b`, `5fa0ceb` (runs/publish-run.tsx, studio/generate-step.tsx, program-wizard/generate-step.tsx, services/studio.py, tr_grammar.py); + lane-A hand-ons (/classes segments, move-dialog selects, inspector "more" button) |
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

## Progress log (newest first)

- 2026-10-17 00:00 UTC — **lane A2 handed off** 8/8: T-R1-02…09 done and verified at 1440 + 390 touch (keyboard clearance, phone dialog layout, bell sheet, notification cards by role, tab bar/shortcuts/toasts, Turkish accessible names, breadcrumbs, login field messages + permission-based landing). vitest 167, e2e loop-r1-laneA 8/8. Ask routed to lane B2: /my-bookings row M-02 (checkbox hit area cut by chip/date button). Checkpoint 2 = the commit carrying this line.
- 2026-10-16 23:40 UTC — **lane F2 handed off**: T-R1-42 (invigilation pool matches masked/titled exam names; pool line, empty-pool reason + one-tap all-instructors) and T-R1-39 part 2 (board placements feed the moderation match rate, 72 % on Güz) done and verified desktop+phone; tests test_loop_r1_laneF2.py, e2e loop-r1-laneF 6/6. Tag `handoff/focused-wright-1`. Open asks routed: pct() possessive case → lane E2; keyboard-clearance scrollIntoView guard → lane A2; MOBILE.md /exams/invigilation row → orchestrator.
- 2026-10-16 22:30 UTC — session focused-wright started; branch + start tag pushed; registry agents of the
  interrupted session marked stopped/finished with where they left off; builders being launched.
