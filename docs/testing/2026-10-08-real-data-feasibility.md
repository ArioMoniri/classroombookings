# Real-data feasibility (2026-10-08, solver-engineer)

Follow-up of `2026-10-08-real-backend-e2e.md` (§2, findings F1–F7). Goal: the real 2026 Bahar course
data and the 2026 Final exam data produce a timetable whose placed events satisfy every hard rule
(hard 100), plus a correct report of what cannot be placed and why. All numbers measured in this
container (8 vCPU, CP-SAT 8 workers, seed 0) with `build_solver_input` + `app.solver.cpsat.solve`,
i.e. exactly what `POST /runs` executes, on SQLite databases built with the importers.

## Setup

```bash
cd smartsched/backend
python -m app.cli import weekly-grid  tests/fixtures/bahar_derslikler_takvimi_2026.xlsx --term 2026-BAHAR --year 2026
python -m app.cli import planning-list tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx --term 2026-BAHAR
python -m app.cli import room-master  tests/fixtures/room_master.csv        # planner's room corrections (F2)
# Güz: guz_derslikler_takvimi_2026_2027.xlsx + guz_derslik_planlama_2026_2027_v2.xlsx (--term 2026-GUZ)
# Final: final_derslikler_takvimi_2026_v2.xlsx (--term 2026-FINAL) + import exam-list final_planlama_listesi_2026_v2.xlsx
```

Run params (all defaults, `solver_bridge.MODE_DEFAULTS`): `trust_locked_rooms=true` (D1),
`fixed_conflicts_as_warnings=true` (D2), `best_effort=true` (D3), `merge_joint_lectures=true` (D4),
`definitive_rooms="lock"`. For the reproduction rate the same runs were repeated with
`definitive_rooms="prefer"` (LOCKED definitive rooms are only soft room preferences, no lock) and
`"ignore"` (no hint at all).

## Results

"placed" counts solver events (joint lectures merged; exam cohorts merged by `merge_key`). Status is
`INFEASIBLE` whenever at least one event cannot be placed (the full request set has no solution); the
best-effort timetable is stored anyway (`stats.partial`, the UI badge reads "Partial · placed/total").
hard = hard score of the placed events (100 = every hard rule holds for them; validated independently).

| Instance | Events (roomed) | Placed / unplaced | Planner-roomed placed | hard | soft | Solve | Errors by code | Warnings by code |
|---|---|---|---|---|---|---|---|---|
| Bahar week 3 (120 s) | 683 (602) | **662 / 21** (roomed 581/602 = 96.5 %) | **523/531 = 98.5 %** | **100** | 84 | 11 s | locked_overlap 7, unplaced 21 | input_conflict 131, trusted_lock_capacity 33, trusted_lock_tags 1, outside_room_pool 2 |
| Bahar full term (300 s) | 684 (603) | **648 / 36** (roomed 567/603 = 94.0 %) | 512/532 = 96.2 % | **100** | 84 | 20 s | locked_ineligible 14, no_room 11, locked_overlap 7, pigeonhole 2, unplaced 22 | input_conflict 131, trusted_lock_capacity 33, trusted_lock_tags 1, outside_room_pool 2 |
| Güz week 3 (120 s) | 535 (506) | **516 / 19** (roomed 487/506 = 96.2 %) | 433/437 = 99.1 % | **100** | 87 | 9 s | locked_overlap 3, unplaced 19 | input_conflict 58, trusted_lock_capacity 44, trusted_lock_tags 1, outside_room_pool 2 |
| Final exams (120 s) | 629 (573) | **615 / 14** (roomed 559/573 = 97.6 %) | 540/553 = 97.6 % | **100** | 76 | 6 s | no_room 5, locked_ineligible 5 (the same 5 exams), unplaced 9 | input_conflict 105, trusted_lock_capacity 101 (incl. shared rooms), trusted_lock_tags 7, outside_room_pool 1 |

Before (same data, `2026-10-08-real-backend-e2e.md` §2): Bahar week 3 / term **INFEASIBLE within
0.05 s with 356 / 390 diagnoses and no timetable**; Final 79 locked-overlap diagnoses.

"Planner-roomed" = events the planner gave a definitive room inside the bookable pool (LOCKED rows);
all of those that are placed sit in exactly the planner's rooms. Wall time is far below the limit
because the slack relaxation proves the maximum placement optimal (`relax_status=OPTIMAL`) and the
phase-2 objective re-solve of the placed events is optimal too.

### Reproduction rate (definitive rooms not locked)

Share of planner-roomed events whose solver room set equals the planner's definitive room set.

| Instance | locked (reference) | unlocked, definitive rooms as soft hints | unlocked, no hint | placed when unlocked |
|---|---|---|---|---|
| Bahar week 3 | 98.5 % | **69.3 %** (359/518; 72.6 % share ≥ 1 room) | 9.5 % (49/518) | 606/670 (hint) · 607/670 (none) |
| Bahar full term | 96.2 % | **70.3 %** (365/519) | – | 605/671 |
| Güz week 3 | 99.1 % | **73.4 %** (323/440) | – | 493/538 |
| Final exams | 97.6 % | **6.2 %** (34/553; 15.4 % share ≥ 1 room) | – | 600/629 |

Unlocked, the solver must respect capacities (trust only applies to locks): 33 Bahar / 44 Güz / 101
Final planner rooms are smaller than the expected enrolment, so those groups cannot be reproduced and
24 Bahar course groups have no room big enough at all (`no_room`) — the planner seats them in smaller
rooms deliberately. The remaining gap comes from the objective: `min_capacity_waste` (1 per 10 empty
seats) outweighs a single `room_preference` (10) when the planner uses a big room for a small group;
for exams the solver prefers splitting/sharing patterns different from the planner's. Raising the
`room_preference` weight (run param `weights`) is the lever if reproduction matters.

## What cannot be placed, and why (all reported per event)

Bahar week 3 (21 unplaced):

* **Locked overlaps in the planner's data** (7 pairs → 6 events; Güz 3): two LOCKED rows hold the same
  room at overlapping periods, e.g. `MAT 112 §1` 13:30–16:00 and `HEM 236` 15:10–16:40 both in A 204 on
  Thursday; `EHM 312 §1` overlaps both `PSK 254 §1` and `ING 102 §8` in C 602. One event per conflict is
  unplaced (the relaxation keeps the most events and, on ties, the locked ones).
* **Fixed-time requests without a definitive room and no free fitting room** (14 — mostly English
  courses `ING 1xx/2xx/3xx` / `ENG 106` with 70–135 students at P1–P5, two merged `EHM 212` groups, `ACY
  106`): every room that fits is held by the planner's locks at that time; the planner's own plan does
  not room them either.
* **`NUT 403`** (flexible, 11 periods): its cohort is busy on both allowed days.
* **Full term only**: 14 locked lectures whose room is blocked by the planner's grid in one of the 14
  weeks (`locked_ineligible`, e.g. an ETKİNLİK cell in week 9) — the solver models a request as one
  14-week event, so a single blocked week excludes the room; 11 `no_room` events for the same reason.
* **Final**: 5 exams whose locked room is blocked by the Final grid itself (`SYB 256`, `SYB 356`,
  `SYB 456`, `ODY 108`, `ODY 102`), 9 more unplaced for room shortage at their slot.

## What changed (summary)

* **F2 room master** — importers: lecture capacity from the Monday header copy of lecture weeks (A 103
  = 47 not 33, A 104 = 41, A 307 = 70), Bahar `Sayfa2` buckets (computer-lab bucket → `PC` on A 103 /
  A 104 / A 105 / B 207; `B BİLGİ LAB` / `B Blok Bilg. Lab.` are B 207), exam-week headers give exam
  capacity only, rooms without any capacity are reported and not bookable (Bahar: 21 + B 207 before the
  room master), `python -m app.cli import room-master <csv>` + `tests/fixtures/room_master.csv` (B 207 =
  60, flagged). Also: a start time at a period's end (15:00) no longer claims that period; exam
  `merge_key` folds `İ`/`I` (`BİF111` = `BIF111`); locked rows in the same room set at overlapping
  times that start together or are the same course/section are one lecture (the room holds the union).
* **D1** `trust_locked_rooms`, **D2** `fixed_conflicts_as_warnings`, **D3** `best_effort`, **F5**
  split-exam room sharing with a per-room seat allocation (max-flow validation) and trusted over-full
  shared rooms — see `smartsched/backend/app/solver/README.md` "Real-data modes" / "Shared exam rooms".
* **F6** falls out of D3: the partial timetable is persisted, the grid shows it.
* **F1** dev SQLite DBs are migrated with `alembic upgrade head` on startup (new DB or `alembic_version`
  present); a legacy `create_all` DB logs the missing columns with the fix.
* Structured `Diagnosis.code` / `params` (+ `params.options` per suggestion); the run-report fixes and
  the studio pre-check dispatch on them instead of the wording.

## Reproduce

`SMARTSCHED_SLOW=1 python -m pytest tests/test_real_feasibility.py -q` (asserts Bahar week 3: hard 100,
≥ 98 % of the planner-roomed events and ≥ 95 % of all room-needing events placed, every unplaced event
explained); the non-slow tests in the same file cover the bridge modes, the Bahar static check and the
locked Final plan.
