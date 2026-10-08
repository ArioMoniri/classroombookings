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
