# Strict solver review (2026-10-08, strict-reviewer, read-only)

The reviewer's independent checker (no `app.solver` code) and the planner-level checker are copied to
`smartsched/backend/tools/review/` (`check.py`, `check_db.py`, `issues_check.py`).
The scratch inputs and outputs were not copied.

## Verdict

- **Solver level (SolverInput → SolverResult): trustworthy.** All 12 real-data results had 0 unwaived hard violations:
  lock, strict, prefer and day-sweep modes, fix re-solves and determinism re-runs.
  The strict-mode run had no waivers at all.
- **Planner level (saved assignments vs raw rows): not trustworthy.** The bridge changes the problem: it merges requests,
  shrinks group sizes to the room, treats missing enrolment as 0, and trusts locks made by the fix button.
  So "hard 100" is proved for a different problem than the planner's.
- **Impossible on this data:** strict rules with every request placed. Strict Bahar week 3 places at most 556/668. The causes, all in the planner's data:
  - 172 fixed-time cohort or instructor clash pairs
  - 33 bad locks (too small, missing tag, or blocked)
  - 7 lock pairs on the same room at the same time
  - 33 classes larger than any room (MAT 112 has 180 students; the largest room, A 204, has 156)

## Status (2026-10-08, solver-engineer: review fixes)

Planner-level validator ported to `smartsched/backend/app/services/planner_check.py` (typed, lint-clean,
used by the API after manual moves) with `tools/validate_planner.py` for the real workbooks;
`tests/test_planner_level_real.py` is the regression gate (Bahar week 3, Final, determinism, fix cases;
Bahar term with `SMARTSCHED_SLOW=1`); `tools/review/` deleted, `--exclude tools/review` removed from the
Makefile.  Numbers: `docs/testing/2026-10-08-real-data-feasibility.md`, "Review fixes".

| Finding | Status | Where |
|---|---|---|
| B1 merges | **fixed** — no instructor chain into a locked row or another course; union-find groups checked for two locked sets; union lock; sum size (no clip in lock mode, `trusted_lock_capacity` reports it); prefer-mode clip only for the planner's set (`joint_lecture_clipped`, others forbidden); members stored with own periods / weeks / own definitive rooms | `solver_bridge.merge_joint_lectures`, `clip_to_planner_rooms`, `_member_placements` |
| B2 fix-button locks | **fixed** — `Event.lock_trusted` (only planning-list LOCKED rows trusted); explanations offer room *sets* within `max_rooms`; `_place` keeps the set or answers 422; child runs report `manual_lock` | `model.py`, `domains.trusted_lock`, `diagnose.room_set_for`, `diagnosis_fixes._place` |
| M1 size 0 | **fixed** — fallback size (course sections / cohort / term median), `missing_enrolment` warning + data-issues group, no waste term | `solver_bridge.SizeFallback`, `data_issues` |
| M2 determinism | **fixed** — canonical stages on 1 worker with a deterministic limit (relaxation stage on the contested neighbourhood), wide tie-break ranks, exchange of interchangeable rows; **deterministic mode** (`workers=1`: every stage budgeted in deterministic time) gives bit-identical timetables across processes; multi-worker runs are reproducible only when every stage is proven (not always the case under load 20+) | `build.Clock`, `build.make_solver`, `cpsat._canonical_optimum`, `diagnose._canonical_placement`, `diagnose.canonical_exchange` |
| M3 partial honesty | **fixed** — every unplaced event explained (no cap); summary lists the accepted exceptions by cause (TR/EN) | `diagnose.explain_unplaced`, `accepted_exceptions`, `persist_result` |
| M4 manual moves | **fixed** — re-validated at planner level (hard score, status, violations in the response); a week move splits the row | `api/v1/runs.py` |
| M5 budgets | **fixed** — relaxation budget = half the limit; residual round skipped when its validated hint gains nothing; the "643 proven optimal" claim corrected | `cpsat.relax_budget`, `weeksplit.residual_gain` |
| M6 data issues | **fixed** — merged events over capacity, `outside_pool_overlap`, missing enrolments, list checks in every definitive-rooms mode, "listed twice" | `solver_bridge`, `data_issues` |
| MINOR shared-exam seat split | fixed (one constant split per exam in `validate`) | `seats._fixed_split_conflicts` |
| MINOR "minimal" / soft overlaps | fixed (`core_minimal`, no soft-overlap suggestion) | `diagnose.core_diagnosis` |
| MINOR `trusted_hint_capacity` text | fixed (names `trust_locked_rooms`) | `solver_bridge` |
| MINOR clip only for the planner's room | fixed (prefer forbids, week segments need full seats) | `clip_to_planner_rooms`, `weeksplit` |
| MINOR merged time span | fixed | `_member_placements` |
| MINOR COURSE run on an exam term | fixed (FAILED + `empty_scope`) | `solver_bridge._finish_empty_scope` |
| MINOR `parse_definitive_rooms("C 501-502")` | **not done**: `app/importers` was outside this task's write scope | — |
| MINOR Final prefer-mode memory | not done (not measured again) | — |
| MINOR `board_vs_list` weeks | fixed | `data_issues._run_weeks` |
| MINOR phase-2 stats | fixed (all scalar stats as `phase2_*`) | `cpsat._best_effort` |
| MINOR cancel race | fixed (conditional status UPDATE in the commit transaction, both sides) | `run_jobs.commit_unless_cancelled`, `runs._cancel` |
| MINOR UNKNOWN + best effort | fixed (checked warm start as a `TIMEOUT` partial) | `cpsat._timeout_partial` |
| MINOR exam merges | fixed (latest end, partly locked group keeps the locked rooms) | `build_solver_input` |
| MINOR outside-pool double booking | fixed (`outside_pool_overlap` data issue; validator checks every room) | `solver_bridge._outside_pool_overlaps` |

## BLOCKER

- **B1. Joint-lecture merging goes wrong** (`solver_bridge.py:178-189,234-238,263,282-286,303-314`).
  - Union-find chains members through a shared instructor.
  - The planner's locked rooms are dropped: only the first member's rooms are kept.
  - The size is clipped to the room's capacity, and nothing warns about it.
  - Bahar week 3: 136 students in C 501 (72 seats); 7 merged events with several room sets; 14 locks lost.
  - Güz week 3: 180 students in A 108 (58 seats).
  - Fix:
    - Reject a group that contains two different locked room sets.
    - Do not merge on a shared instructor when a row is locked or the course codes differ.
    - Lock a valid merge to the union of the members' rooms.
    - Raise a `joint_lecture_clipped` warning and list it as a data issue.
- **B2. Fix-button locks are trusted as "the planner's room"** (`domains.py:76-78`, `diagnosis_fixes.py:257`, `diagnose.py:707-749,826-846`).
  - ING 302 with 135 students moved into A 107 (58 seats), with hard 100 and a false warning.
  - Only 1 of the 4 fixes tested is correct.
  - Fix:
    - Mark solver-made locks as untrusted; only planning-list LOCKED rows get D1.
    - Explain using room sets whose seats add up to at least the size.
    - `_place` keeps the room set, or answers 422.

## MAJOR

- **M1.** Missing enrolment (size 0) turns the capacity check off (`solver_bridge.py:432`).
  33 events in Bahar week 3, 24 in Güz, 7 in Final.
  Needs a `missing_enrolment` data issue and a fallback size.
- **M2.** Results are not deterministic: same input and seed give different timetables.
  `_canonical_optimum` (`cpsat.py:93`) and `_canonical_placement` (`diagnose.py:1013`) do not prove their stage.
  Use one worker with a deterministic time limit.
- **M3.** Partial runs are not fully honest.
  `explain_unplaced` covers only the first 50 events (`diagnose.py:1040`).
  "Every placed class keeps every rule" (`data_issues.py:370`) ignores the waived exceptions.
- **M4.** Manual moves (`runs.py:459-468`) never re-score the run; a forced double booking keeps hard 95.
  A move with `week` cuts a 14-week assignment to one week.
- **M5.** The relaxation is capped at 120 s whatever the time limit (`cpsat.py:361`).
  The claim "643 is proven optimal" did not reproduce on a loaded box.
  A residual week-split round wasted 112 s.
- **M6.** The data-issues report misses cases:
  - 38 of 49 merged events seated above capacity
  - locked overlaps in rooms outside the pool
  - missing enrolments
  It had no false positives.

## MINOR

- Shared-exam seat validation is checked per period, not with one fixed split.
- "Minimal conflict set" is claimed even when shrinking stopped on its budget, and it suggests making no_cohort_overlap soft, which the solver does not allow.
- The `trusted_hint_capacity` text suggests a parameter the API rejects.
- Prefer and week-split modes clip the size for every room, not only the planner's room.
- Merged members are saved with the merged time span.
- A COURSE run on an exam term returns 100 with 0 events.
- `parse_definitive_rooms("C 501-502")` drops the range.
- Final in prefer mode peaks at 1.35 GB of memory.
- `board_vs_list` is not limited to the run's weeks.
- The phase-2 stats are not passed through.
- Cancel race: a cancel can be overwritten by the result commit.
- UNKNOWN status returns no assignments even with best_effort on.
- Exam merges: the end time comes from the first row, and a mixed locked/unlocked group loses its rooms.
- Rooms outside the pool are never checked for double booking.

## Roadmap suggestions

- A strict view per run: the score with no waivers, beside the waived exceptions grouped by cause.
- The planner-level validator in CI and after every edit.
- A deterministic mode for publishable runs.
- Proper multi-day and parallel-section modelling.
- A data-quality gate before solving.
- Invigilator assignment.
- What-if comparison between runs.
- Student-level clash checks.
- Publishing behind an approval step.
