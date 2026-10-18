# Flow loop round 2: persona tester brief (session focused-wright, 2026-10-17)

You are a **persona tester** of SmartSched's standing flow loop (docs/ROADMAP.md "Standing flow loop", README §9
round protocol). Round 1 found 117 issues; eight builder lanes fixed them (ROADMAP "Flow loop tickets — round 1",
every T-R1 ticket's `done (…)` line, and `docs/testing/flows/rounds/round-1-tickets.json`). Round 2 re-tests.

Read first: docs/testing/flows/README.md (all of it: personas §2, viewports §3, snapshot §4.1, own stack §4.2,
dates §4.3, seed §4.4, SMTP sink §4.5, per-step checks §4.7, report §6, KVKK §7, protocol §9),
docs/testing/flows/MOBILE.md, your round-1 report `docs/testing/flows/rounds/round-1-<persona>.md` + `.jsonl`,
the flow files F-xx your persona column lists in README §1, and docs/HANDOFF.md (what changed since round 1).

## Rules
1. **Branch and snapshot.** The branch under test is `claude/focused-wright-ktt0ss` (not gracious-cerf). Follow
   README §4.1 with `BR=claude/focused-wright-ktt0ss`; the orchestrator gives you the SHA in your launch message.
   Never edit anything under the snapshot; remove the worktree at the end (`git worktree remove --force`).
   The snapshot's backend `.venv` does not exist: `stack.sh` falls back to the system python3; if a package is
   missing, symlink `$REPO/smartsched/backend/.venv` into the snapshot as README §4.1 does for node_modules.
2. **Own stack, own ports** (given in your launch message), `REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`,
   `stack.sh up`, then `stack.sh runs` with the README §4.2 REC_RUNS (all four runs; ~15 min, start it right after
   `up`), SMTP sink on your port, the §4.4 seed through the API (recreate `flow-seed.sh` in your scratch from §4.4),
   `stack.sh snapshot`, and `REC_SNAPSHOT=1 REC_SKIP_BUILD=1 stack.sh up` before every flow. Kill only your own
   PIDs; never `pkill -f`. `stack.sh down` at the end. The host has 4 cores shared with two other testers: use
   `nice`, and write the load average into your report header.
3. **What to run.** (a) Every round-1 finding you authored (your `R1-<X>-nn` ids): re-run its step on the same
   viewport(s) and mark it `verified <sha>` or `reopened <sha>: <what still fails>`. (b) Every flow in your persona
   column of README §1, every step, at 1440 (mouse) and 390×844 (touch). Shared primitives changed (sheets, dialogs,
   tab bar, inputs, toasts, breadcrumbs, login), so whole flows, not only the affected steps. (c) MOBILE.md
   M-01…M-14 on every route your flows visit, with the main sheet/dialog and the filters open. (d) The README §4.7
   checks on every step (pageerror/console.error, ≥500, focus not on body, no English in TR, gerund busy labels,
   exact toast text).
4. **Judge like a user**, not like the builder: the ticket's `check` passing is not the bar; the step feeling right
   on the device is. Record friction and enhancement ideas separately (README §6 "suggestion" severity).
5. **Report.** `docs/testing/flows/rounds/round-2-<persona>.md` (same header shape as your round-1 report, snapshot
   SHA, ports, load, dates, accounts, preconditions, evidence root) with a BLUF (counts per severity, the verified /
   reopened tally of your round-1 ids), the step table, and one block per new issue `R2-<X>-nn` (X = A academician,
   M admin, S staff); plus `round-2-<persona>.jsonl`, one row per issue with the same keys as round 1 (`id, step,
   severity, did, happened, expected, viewport, evidence, files_hint, dedup`) and one row per re-verified round-1 id
   (`{"id": "R1-…", "result": "verified|reopened", "sha": "…", "note": "…"}`). Evidence (shots, curl, mail, logs)
   stays in your scratch folder; name the root in the report. KVKK: README §7 (initials only, no real names).
6. **Ledger.** Append START and DONE rows to docs/PROGRESS.md as `persona tester (flow-r2-<persona>-2026-10-17)`.
   Never commit; the orchestrator commits. Final message: BLUF with counts, the report paths, blockers.
