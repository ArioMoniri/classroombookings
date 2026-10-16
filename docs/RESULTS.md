# Measured on the real data

Moved from the README on 2026-10-15.

From [docs/testing/2026-10-08-real-data-feasibility.md](testing/2026-10-08-real-data-feasibility.md),
section "Review fixes": the planning office's 2026 workbooks, default run settings, 4 vCPU shared with
other work, CP-SAT with 4 workers. A *request* is one row of the planning or exam list; *placed* means
placed in every week of the run. "Planner-level hard" re-checks the stored timetable against the raw
workbook rows, independently of the solver.

| Instance | Requests placed | Solver events placed | Planner-level hard | Violations |
|---|---|---|---|---|
| Bahar 2026, whole term (300 s limit) | 838 / 883 (94.9 %) | 682 / 720 | 100 | 0 |
| Bahar 2026, week 3 (120 s) | 845 / 882 (95.8 %) | 689 / 719 | 100 | 0 |
| Güz 2026-27, week 3 (120 s) | 626 / 653 (95.9 %) | 522 / 548 | 100 | 0 |
| Final 2026 exams (120 s) | 724 / 729 (99.3 %) | 624 / 629 | 100 | 0 |

Every exception behind these numbers is the planner's own data and is reported per class (locked rooms
smaller than the enrolment estimate, fixed-time clashes of one instructor or cohort, missing
enrolments). The same report records an earlier mistake: before the review fixes the solver reported
hard 100 while the planner-level check found 134, 68 and 56 violations on the Bahar, Güz and Final week
runs (for example 136 students seated in a 72-seat room), because the bridge clipped merged groups to
the room. The placement rates went down a little when that was fixed. Earlier still, the same Bahar
data ended *infeasible within 0.05 s, with 356 diagnoses and no timetable*.

When the planner's rooms are only hints instead of locks, the solver picks exactly the planner's room
set for 89.5 % of the placed Bahar week 3 requests and 94.9 % of the Güz ones; for the Final exams it is
74.1 % exact and 93.4 % sharing at least one room, every run with planner-level hard 100.

These figures were measured on 2026-10-08. The importer changed after that (non-room venues such as
CASE or ONLINE need no room, course codes with leading zeros are merged, a missing week sheet is
reported), so the counts of the next run will differ. The pod CI gate `planner` now repeats this check
on every commit (`python -m tools.validate_planner`, the four instances above at 120 s each) and fails
the run on any planner-level violation.

The recordings and screenshots on this page come from a fresh import of the same workbooks and two
runs made through the API for Güz 2026-27: week 3 placed 522 of 548 solver events (the row above) and
the whole term 519 of 548, both with hard score 100.
