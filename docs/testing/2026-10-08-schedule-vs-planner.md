# SmartSched timetable compared with the planner's own files (2026-10-08)

The tester played the university classroom planner. They imported the real Bahar, Güz and Final workbooks through the API and
ran the solver as the planner normally would. Then they compared every placed event with the weekly board
(`… derslikler takvimi.xlsx`) and with the definitive rooms in the planning lists.

To re-run: `python smartsched/backend/tools/compare_planner.py --steps import,solve,compare` (see §9).

## Bottom line

- **Lock mode is the default.** SmartSched reproduces the planner's board for 440/667 events in Bahar week 3, 379/529 in Güz week 3 and 274/628 Final exams.
- No locked row ever leaves its list room. Regressions (class c) are 0, and hard = 100 in every lock run.
- **Most other differences come from the planner's files disagreeing with each other** (class e): list rooms that are not board columns, board times that differ from list times, exam times off the 50-minute grid, and non-room venues.
- **Prefer mode has regressions.** 25, 13 and 16 events leave a valid board room. Most are trade-offs. 5 are a bug: two rows of one lecture compete for the same room.
- **Three more SmartSched defects:**
  - R2: exams with no enrolment stay unplaced although free rooms exist.
  - R3: the term run drops two locked classes for all 14 weeks.
  - R4: classes the planner split over several rooms cannot be split.
- **The data-issues report is correct about what it checks.** It misses double bookings outside the room pool. It misses board-only errors. Its list checks disappear in prefer mode.

## 1. Setup

| Item | Value |
|---|---|
| Backend | Real uvicorn, `ENVIRONMENT=dev`, scratch SQLite, `alembic upgrade head` + `app.cli seed-admin` (the `e2e-backend-entry.sh` pattern), `SOLVER_WORKERS=4` |
| Machine | 4 vCPU shared with other agents, load average 7–18 |
| Imports (API) | weekly grid + planning list or exam list for 2026-BAHAR, 2026-GUZ, 2026-FINAL. Bahar: grid 10 134 cells, list 1 524/1 529 rows. Güz: 4 559 cells, 1 036/1 037 rows. Final: 2 615 cells, exam list 921/926 rows |
| Room master | `tests/fixtures/room_master.csv` through `import_room_master`, 87 rooms. **There is no API endpoint for it** (gap) |
| Runs | `POST /runs`, `time_limit_s` 120 (300 for the term), `workers` 4. The prefer runs add `definitive_rooms="prefer"` |

| Run | Instance | Mode | Status | Placed / events | hard / soft | Wall | relax / phase 2 |
|---|---|---|---|---|---|---|---|
| 7 | Bahar week 3 | lock | FEASIBLE_PARTIAL | 649/668 | 100/83 | 77 s | OPTIMAL/OPTIMAL |
| 8 | Bahar term | lock | FEASIBLE_PARTIAL | 642/669 | 100/83 | 267 s | FEASIBLE/OPTIMAL |
| 9 | Güz week 3 | lock | FEASIBLE_PARTIAL | 512/530 | 100/87 | 49 s | OPTIMAL/OPTIMAL |
| 10 | Final | lock | FEASIBLE_PARTIAL | 615/629 | 100/77 | 40 s | OPTIMAL/OPTIMAL |
| 11 | Bahar week 3 | prefer | FEASIBLE_PARTIAL | 641/660 | 100/91 | 124 s | FEASIBLE/FEASIBLE |
| 12 | Güz week 3 | prefer | FEASIBLE_PARTIAL | 525/533 | 100/90 | 123 s | FEASIBLE/FEASIBLE |
| 13 | Final | prefer | FEASIBLE_PARTIAL | 620/629 | 100/93 | 113 s | FEASIBLE/TIMEOUT |

### How the comparison works

- **Planner side:** read with the importers' own parsers. Every finding carries a board sheet and cell and a list row.
- **SmartSched side:** read through the API only.
- **Unit:** one event per week. Joint lectures and exam cohorts count as one event.
- **Board week:** Güz has no week-3 sheet, so Güz week 3 is compared with `28-02 Ekim 2. hafta`.
- **Hard rules checked on the planner's placement:**
  - capacity (exam seats for exams)
  - PC tag
  - a TIP room without a TIP request
  - two classes in one cell
  - an instructor or cohort in two places at once
  - a list room blocked on the board
  - two LOCKED rows in one room at once
- **Classes:**
  - a, planner error
  - b, SmartSched improvement
  - c, SmartSched regression
  - d, unplaced
  - e, data issue
  - neutral: moved, both choices valid
  - match (kept): equals the board although the board breaks a rule SmartSched trusts under D1

## 2. Summary per instance

| Instance (run) | Compared | a | b | c | neutral | d | e | match (kept) | board-only cells |
|---|---|---|---|---|---|---|---|---|---|
| bahar-w3 (7) | 667 | 8 | 24 | 0 | 4 | 18 | 173 | 440 (113) | 28 |
| bahar-term (8) | 9 301 event-weeks | 136 | 322 | 0 | 54 | 350 | 2 275 | 6 164 (1 584) | 967 |
| guz-w3 (9) | 529 | 17 | 8 | 0 | 14 | 17 | 94 | 379 (115) | 75 |
| final (10) | 628 | 6 | 0 | 0 | 0 | 14 | 334 | 274 (57) | 11 |
| bahar-w3-prefer (11) | 657 | 18 | 22 | 25 | 4 | 16 | 177 | 395 (86) | 28 |
| guz-w3-prefer (12) | 532 | 27 | 8 | 13 | 17 | 7 | 107 | 353 (95) | 75 |
| final-prefer (13) | 628 | 34 | 0 | 16 | 0 | 9 | 324 | 245 (47) | 11 |

**Main data-issue sub-classes (lock runs):**

- **Bahar week 3:**
  - 80 events are in a list room that is not a board column (labs and offices: A 7xx/8xx, B 501, C 102/104, D 202/302)
  - 46 events have different times on the board and in the list; 16 of them are off the 50-minute grid
  - 11 rows are list-only
  - 10 have a list room different from the board
  - 13 have every board cell taken by another row of the same lecture
- **Final:** 221 of 334 are exam times off the grid. For example, the list says 14:00–16:00, so SmartSched snaps the start down to P7 (13:30) and holds the room one period longer.
- **Non-room venues (CASE, office, ONLINE):** 8 Bahar, 14 Güz and 19 Final events still get a classroom, because the importer sets `needs_room=true`.

## 3. Top 20 planner errors (fix these in the files)

Board files: Bahar = `2026 bahar derslikler takvimi.xlsx`, Güz = `2026-2027 Güz derslikler takvimi.xlsx`, Final = `2026 final derslikler takvimi v2.xlsx`.
List = sheet `Sayfa1`.

| # | Sev. | Where | Rule | What | Suggested fix |
|---|---|---|---|---|---|
| 1 | High | Bahar list rows 2, 1001 (MAT 112 §1) and 1022 (HEM 236); board `'16 - 22 Şubat'!CT9` | double booking + capacity | Both are LOCKED to A 204 on Thursday 13:30–15:50 and 15:10–16:40. MAT 112 §1 has 180 students for 156 seats, so it is unplaced every week | Move HEM 236 to D 106 or A 206. Split MAT 112 §1, or use A 203 (TIP, needs approval) |
| 2 | High | Bahar rows 404/467 (PSK 254 §1), 434 (EHM 312 §1), 382 (ING 102 §8) | double booking | All three hold C 602 on Wednesday 09:20–10:00 | Give EHM 312 §1 (15 students) C 604 or B 201 |
| 3 | High | Bahar rows 813 (PTL 184 §1), 942 (EHM 312 §1); board `CW29` | double booking | Both LOCKED to C 601 on Thursday 16:00–16:40 | Move EHM 312 §1 to C 603 |
| 4 | High | Bahar rows 435 (BES 640), 436 (BES 560); board `CQ37` | double booking + instructor | Both hold C 501 on Thursday evening, with the same instructor | Fix one of the times |
| 5 | High | Bahar rows 200/202 (BME 528, BME 650) vs 389 (BME 528 §1); board `EE10`, `EK30` | list double booking; list differs from board | The list has both in B 204 on Friday; the board has B 201 | Change rows 200 and 202 to B 201 |
| 6 | High | Bahar rows 622 (FZT 132), 636 (ING 302 §10) | double booking | Both LOCKED to A 106 on Monday 10:10–12:30 | Drop A 106 from ING 302 §10's nine-room set |
| 7 | High | Bahar row 1057 (RAD 282); board `AQ23`, weeks 4–10 | room blocked + capacity | Locked to C 601, which is blocked "Pulmoner" in weeks 4–10. 80 students for 72 seats | Lock it to D 106 or A 206 for the whole term |
| 8 | High | Bahar rows 137, 397, 941, 1211, 1521; board week 1 `P23/AS23/BV23/CY23/EB23` | room blocked | Locked to C 603, which is blocked "Adli Tıp Staj" in week 1 | Mark week 1 as elsewhere, or remove the block |
| 9 | High | Bahar row 669 (PDL 212 §1); board week 1 `B9` | room blocked | A 101 holds "diyaliz toplantı" in week 1 | Same as #8 |
| 10 | High | Bahar rows 257/275/442 (MBG 034 §1); board `CJ29` | capacity | 80 students in B 407 (30 seats) | Check the enrolment, or use C 301/C 302 |
| 11 | High | Bahar rows 1050/1051 (MBG 012 §1), 188 (MBG 532 §1); board `AN26` | capacity | 80 students in C 504 (40 seats) | Use a 72-seat C room |
| 12 | High | Final rows 37, 39, 851 (SYB 256/356/456); board `'1 - 5 Haziran'!N30`, `P24`, `'15 - 21 Haziran'!G3` | room blocked | The exam rooms are blocked "syb staj sunum" at the exam time | If the presentation is the exam, delete the block cell |
| 13 | High | Final rows 602/573 (ODY 102/108); board `'8 - 12 Haziran'!P23/Q23` | room blocked + instructor | Locked to C 603/C 604, which are blocked HAZIRLIK at that time. Same invigilator | Use free rooms (e.g. A 204), or merge the sessions |
| 14 | High | Final rows 407/346 (MBG027); board `DF33-DI33` | missing PC | A computer lab was requested, but the exam is in B 202–B 205 | Use A 103/A 104/B 207 |
| 15 | High | Final rows 105–108 (NUT401–404); board `AT29/AU29/AT31/AU31` | exam capacity | 50 students in C 604 (20 exam seats) and C 605 (16) | Use C 401 + C 402, or A 204 |
| 16 | High | Final row 78 (ACU132); board `AQ9` | exam capacity | 122 students in A 207 (55 exam seats) | Add A 204 + A 206 |
| 17 | Med | Final rows 180/181 (BIL102); board `BQ11` | exam capacity | 200 students in A 204 (74 exam seats) | Split over 3 large rooms |
| 18 | Med | Güz row 403 (MBG 033 §1); board `'28-02 Ekim 2. hafta'!BX9` | capacity | 80 students in A 308 (42 seats) | Check the enrolment; use C 201 |
| 19 | Med | Güz rows 25–28, 234, 251, 252, 617–619 (ten PHAR §1 classes); board columns AB/BE/DK | capacity | 70–80 students in B 406 (30 seats) | Check B 406 in the room master, or move them |
| 20 | Med | Bahar rows 29, 31, 62, 69; board `DW3`, `DZ4` (the same pattern in Güz rows 739/743/779) | instructor clash | Cemre SAVAŞAN is in A 204 and A 207 at once on Friday P2 | Shift one block by one period |

**Also worth a look:**
- MBT 698 needs a PC lab but is in C 205.
- About 12 overlapping Güz rows name NAFİYE ÇİĞDEM AKTEKİN, probably as the coordinator rather than the instructor.
- Several lectures are listed twice with different room sets: BES 548, CSE 102 §1, EHM 312 §1, ENG 106 §1/§2.
- Code spellings differ: `SYS 18`/`SYS 018`, `SYS 19`/`SYS 019`.
- 113 Bahar, 115 Güz and 57 Final events are kept although the planner's placement breaks a rule (mostly rooms too small, trusted under D1).

## 4. SmartSched regressions (with repro)

Repro pattern:
- `GET /api/v1/runs/{run}/assignments?week={wk}&day={d}&room={room_id}` shows who holds the board room.
- `GET /api/v1/runs/{run}` shows the diagnosis.

**R1. Prefer mode leaves the board room: 54 events, Medium.**

| Category | Bahar | Güz | Final | Verdict |
|---|---|---|---|---|
| Held by **the same lecture's other row** (SYS 18 vs SYS 018 §1, ACY 284 §1, ADS 294, ADS 284, SYS 19) | 4 | 1 | 0 | **Bug.** Prefer mode does not merge these rows; lock mode does |
| Displaced by another class (mostly split ING/ENG rows) | 13 | 12 | 7 | Trade-off. Two Final cases (DYZ292, BIL102) also lose a requested room |
| Uses a subset of the planner's multi-room set | 8 | 0 | 4 | Known limitation |
| Adds an extra shared exam room | 0 | 0 | 4 | Weak |
| The planner's room is free but another is chosen | 0 | 0 | 1 | **Regression**: PHAR342 (exam 632, run 13), board B 204/205/206, SmartSched A 104/B 204/B 205, B 206 free |

**R2. Size-0 exams stay unplaced although rooms are free: High, bug.**
- All 7 size-0 Final exams are unplaced in prefer mode, and 4 of 7 in lock mode.
- The diagnosis contradicts itself: "every room that fits is taken … Free option: A109", with params `free [A109, A205, A307], clashes []`. Cases: TDS102 (301), BES250 (412), DYZ146 (498).
- FYT118/FYT132 (756/757) and SYS19 (300) have real causes, but their diagnosis text is still misleading.
- The likely cause is seat demand or domain handling for size-0 exams. The relax objective counts placements, not seats.

**R3. The term run drops two locked classes for 14 weeks: High.**
- Run 8 never places PHAR 114 §2 (1153; locked A 306/C 602, Tue 11:00–12:30) or BME 528 §1 (387; locked B 204, Friday). Both are placed in the week-3 run.
- C 602 is taken only in weeks 4–10, by RAD 282's moved segment (planner error #7). B 204 is blocked in week 1 only.
- `split_blocked_weeks` should move a single week, not drop the class for the term.

**R4. No multi-room split without a definitive room set: Medium.**
- Unplaced in Güz week 3 although the board's room sets are free:
  - ENG 105 §1, 85 students (board C 301–C 304)
  - ING 301, 90 students (C 401/C 402)
  - ENG 107 + ING 301 §90, 100 students (C 301/C 302)
- Also unplaced in the Bahar prefer run: NRS 204 + NRS 304, 140 students.

**R5. Lock mode reshuffles board rooms for rows without a definitive room: Low.**
- 4 Bahar and 14 Güz events. Example: Güz ING 101 is in A 106–A 109 on the board, and SmartSched uses C 301.
- This is by design, since the board is not an input, but every Generate moves the English rooms.

## 5. Unplaced events: is the stated reason true?

| Instance | unplaced | confirmed | cohort/instructor busy | not confirmed | board slot free in SmartSched's week |
|---|---|---|---|---|---|
| bahar-w3 | 18 | 18 | 0 | 0 | 0 |
| bahar-term | 350 | 303 | 27 | 20 (R3) | 0 |
| guz-w3 | 17 | 14 | 3 | 0 | 4 (R4) |
| final | 14 | 13 | 0 | 1 (R2) | 0 |
| bahar-w3-prefer | 16 | 14 | 2 | 0 | 1 |
| guz-w3-prefer | 7 | 5 | 2 | 0 | 1 |
| final-prefer | 9 | 1 | 2 | 6 (R2) | 1 |

## 6. Data issues the planner should know about

- **The Güz board has only weeks 1–2,** so a week-3 run has no grid blocks. Run 9 placed 30 classes in rooms that the week-2 board blocks at those times.
- **Final sheet `15 - 21 Haziran`:** its day headers are copied from the week before (9–14 June). The importer trusts the header dates, so 484 blocks get the wrong date. The solver uses week and weekday, so it is not affected.
- **Board codes missing from the list:** 10 Bahar week-3 cells, 53 Güz cells, 150 over the Bahar term.
- **Board cells at times the list does not have:** 18 Bahar, 22 Güz, 11 Final.
- **List rooms that are not board columns:** 80 Bahar, 31 Güz, 52 Final events.
- **Non-room venues get a classroom:** 8 Bahar, 14 Güz, 19 Final events.

## 7. Data-issues report cross-check

| Group | 7 | 8 | 9 | 10 | 11 (prefer) | 12 (prefer) | 13 (prefer) |
|---|---|---|---|---|---|---|---|
| no_free_room | 19 | 28 | 18 | 14 | 19 | 7 | 9 |
| locked_room_blocked | 0 | 3 | 0 | 5 | 0 | 0 | 0 |
| locked_room_overlap | 7 | 7 | 3 | 0 | **0** | **0** | 0 |
| shared_room_overflow | 0 | 0 | 0 | 24 | 0 | 0 | 0 |
| fixed_instructor_clash | 81 | 92 | 51 | 63 | 51 | 40 | 63 |
| fixed_cohort_clash | 59 | 64 | 17 | 75 | 63 | 16 | 75 |
| board_vs_list | 36 | 36 | 17 | 5 | 36 | 17 | 5 |
| locked_room_too_small | 33 | 33 | 44 | 78 | 35 | 47 | 78 |
| missing_tags | 1 | 1 | 1 | 7 | **0** | **0** | **0** |
| week_room_changes | 0 | 11 | 0 | 0 | 0 | 0 | 0 |

**Missed by the report:**
1. **Double bookings in rooms outside the pool (High).**
   - Bahar: MIK 502/602 in A 805; MBT 687/BIY 598/TRM 660 in A 606; BIO 600/BIY 508 in A 701.
   - Güz: TLT 265 §1 against CHE 110/111 §1 and MBG 111/123 §1 in A 302/A 303.
2. **The list checks vanish in prefer mode (High).** locked_room_overlap goes from 7 to 0 and missing_tags from 1 to 0 (7 to 0 for the Final), although the errors are still in the file.
3. **Board-only errors (Medium):** single-class capacity, instructor clashes caused by board times, and two classes in one cell.
4. **board_vs_list misses (Low):** 12 Bahar, 19 Güz and 29 Final events.
5. **Not reported anywhere:** unknown board codes, board cells at times the list lacks, the missing Güz week-3 board, and the wrong Final sheet-3 dates.
6. **No room-master import endpoint.**

**False alarms:**
- One lecture listed twice is reported as an instructor or cohort clash (Bahar 4 + 11, Güz 2 + 2, Final 3 + 3).
- "Yüz yüze" in the instructor field is reported as a shared instructor (RAD 282 / RAD 106).
- board_vs_list ignores the run's horizon: in the week-3 run, 26 of 36 items concern other weeks.

## 8. UI check

Skipped because of machine load. The frontend agents covered the run report against a real backend.

## 9. Reproduce

```bash
cd smartsched/backend
export ENVIRONMENT=dev DATABASE_URL=sqlite+aiosqlite:///$S/cmp.db UPLOAD_DIR=$S/uploads ADMIN_EMAIL=planner@smartsched.local \
       ADMIN_PASSWORD='<choose one>' APP_SECRET=<random> JWT_SECRET=<random> SOLVER_WORKERS=4
alembic upgrade head && python -m app.cli seed-admin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 &
python tools/compare_planner.py --base-url http://127.0.0.1:8765/api/v1 --email "$ADMIN_EMAIL" \
  --password "$ADMIN_PASSWORD" --database-url "$DATABASE_URL" --work $S/compare --steps import,solve,compare
```

**Outputs:** `runs.json`, `compare.json` (every finding with class, board cell, list row and both placements), `run<id>-data-issues.xlsx` and `log.txt`.

**Reproducibility:** a second fresh backend gave identical lock-mode week numbers. The prefer runs vary because their solves hit the time limit, and the term run varies slightly. R2 and R3 reproduced.

**Caveats:**
- Other agents were editing the solver during these runs; each backend used the code present when it started.
- Matching rows to board cells is heuristic for rows listed once per programme.

## 10. Recommendations

**For the planner:**
- Fix the 20 items in §3. Items 1–9, 12 and 13 cost a class its room today.
- Use one room set and one code spelling per lecture.
- Publish the Güz week-3 board, and fix the Final sheet-3 headers.
- Mark CASE, office and ONLINE rows as needing no room.

**For SmartSched (tracked in docs/ROADMAP.md):**
- R2: size-0 exams, and the self-contradicting diagnosis.
- R3: a term run must not drop a lock for one blocked or contested week.
- R1: merge the rows of one lecture in prefer mode, normalising leading zeros.
- R4/R5: use the board as a soft multi-room hint, or allow splits for large groups.
- **Importer:**
  - no room for non-room venues
  - code normalisation
  - an instructor sanity check
  - sheet-name dates over day headers
- **Data-issues report:**
  - overlaps in rooms outside the pool
  - list checks in every mode
  - board-only checks
  - a "same lecture twice" label
  - a horizon filter
- `POST /imports/room-master`.

The full list of the 54 prefer-mode regressions (run, week, event, board vs SmartSched placement, holder, board cell and list
row) is produced by `compare_planner.py` in `compare.json` (class `c`). The agent hand-off on 2026-10-08 14:55 quoted it in full.
