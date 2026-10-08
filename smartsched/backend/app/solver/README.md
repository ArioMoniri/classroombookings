# SmartSched solver (`app/solver`)

Pure Python + OR-Tools CP-SAT. No DB, no HTTP: `solve(SolverInput) -> SolverResult` over the frozen
dataclasses in `model.py` (contract in `docs/ARCHITECTURE.md`).

```
model.py          frozen contract (Room, Event, Constraint, SolverInput, Assignment, Diagnosis, SolverResult)
domains.py        per-event candidate enumeration: time options × room options, hard pruning with reasons
constraints/      registry: one module per constraint kind (prune / apply / score)
context.py        CP-SAT variables, intervals, assumption guards, penalty bookkeeping
build.py          prepare() → domains + pruning; build_model(mode) ; solver parameters
greedy.py         constructive heuristic → complete hint for CP-SAT
cpsat.py          solve(): static check → model → hints → CP-SAT → evaluation → diagnosis
evaluate.py       Violation / Evaluation (pure-Python scoring), scoring.py: evaluate(inp, assignments)
diagnose.py       static checker, assumption cores + deletion shrinking, slack relaxation, explanations
repair.py         repair() (LNS neighbourhood re-solve), validate(), score()
serialization.py  JSON in/out of the contract
seats.py          seat budgets of shared rooms (split exams): targets, allocation, max-flow validation
options.py        structured suggestion options (Diagnosis.params["options"])
weeksplit.py      week segments for term runs (blocked weeks move only those weeks), residual split, merge back
```

Not shipped in the image (audit m10): `tests/solver/generators.py` (synthetic + Bahar-like instance
generators with planted feasible solutions) and `tools/calibrate.py` (weight calibration against the
planner's rooms on the real workbooks; the only solver code that imports the bridge and the importers).

Run the tests: `cd smartsched/backend && python -m pytest tests/solver -q`
(`SMARTSCHED_SLOW=1` adds the 1 300-event and exam scale tests). Lint: `ruff check app/solver`,
`mypy app/solver` (strict via `pyproject.toml`).

## Modelling

Period indexes are 1-based and inclusive: an event with `start=4, duration=3` occupies P4–P6 and its
`Assignment.end` is 6. `Block.end` is inclusive too. Days are whatever `SolverInput.days` lists;
internally time lives on a **global period axis** `g = day_pos * periods_per_day + period - 1` so that
one integer describes a (day, period) and intervals never cross a day boundary.

### Domains first, variables second

`domains.build_domains` enumerates for every event

* **time options** `(day, start)`: the single fixed one (`fixed_day`+`fixed_start`, or `locked`),
  otherwise `allowed_days × [earliest_start, latest_end - duration + 1]`;
* **room options**: rooms passing the hard room rules — capacity (`capacity` for courses,
  `exam_capacity` for exams; skipped when the event may split), required/forbidden tags, pins,
  forbids, locked room — minus (time, room) pairs hit by blocks / `room_closed`.

Every pruned option keeps a reason string (`"capacity 58 < 100 (capacity)"`), which the diagnoser
turns into constraint kinds and suggestions without re-solving. Hard constraint modules may prune
further (`prune(doms, c)`), e.g. `day_window`, `building_preference` (hard, targeted),
`no_cohort_overlap` (removes time options that collide with fixed-time events of the same key).

≈ 85 % of the Bahar meetings have a fixed day+time, so they only enumerate rooms: the full instance
is ≈ 1 300 × ~40 room options ≈ 5·10⁴ Booleans, far from the 10⁷ of a naive
`x[event, day, period, room]` grid.

### Variables (per event *e*)

| Variable | Meaning | Count |
|---|---|---|
| `y[e,t]` Bool | takes time option *t* (omitted = constant *true* for fixed-time events) | Σ time options of flexible events |
| `start[e]` Int | global start, domain = allowed values, `start == Σ g_t·y[e,t]` | one per flexible event |
| `z[e,r]` Bool | uses room *r*; `ExactlyOne` (single room) or `min ≤ Σz ≤ max`, `Σ cap_r·z ≥ size` (split exams) | Σ room options |
| interval `(start[e], dur, presence z[e,r])` | optional room occupancy | one per (e, r) |
| interval `(start[e], dur)` | the event itself (cohort / instructor no-overlap) | one per event |
| `placed[e]` Bool | *assume* / *relax* modes only: "event is scheduled at all" | one per event |
| `guard[name]` Bool | *assume* mode only: one assumption literal per actionable group | rooms + keys + locks + constraints |

Flexible events additionally get `occ[e,d,p]` / `on_day[e,d]` literals on demand (`Σ` of the `y`
covering a period / a day) for the exam rules and `day_window`.

### Weeks without per-week copies

Two events conflict only if their week sets intersect. Room occupancy is one **`NoOverlap2D` per
room**: each (event, room) interval is paired with the *week runs* of the event (`1-14` → one box,
`1-5` + `6-14` split events → one box each, odd weeks → several), so events in disjoint weeks share
a room freely and the model holds no per-week variable copies. Blocks are fixed boxes in the same
constraint. Cohort / instructor keys use the same idea in 1-D: one `NoOverlap` per
(key, *week class*) where a week class is a maximal set of events sharing some week.
`SMARTSCHED_ROOM_ENCODING=classes` switches rooms to the week-class encoding too (kept for
benchmarking: on 300 events it converges ~2× slower than the 2-D encoding).

When greedy leaves a few events unplaced, `cpsat._complete_hint` re-solves a small locked
neighbourhood first so the hint is complete (every derived variable — `occ`, `on_day`, group
`used`/`extra`, exam `pen`/`ext` — is valued through `ctx.derive` evaluators); an incomplete hint
on the full Bahar instance meant *no* solution within 90 s, a complete one gives the first solution
at once (1 300 events / 60 rooms / 14 weeks / 7 days: FEASIBLE, hard 100, ≈ 100 s budget spent on
LNS improvement, 4 cores).

Benchmark history (300 Bahar-like events, 60 rooms, 14 weeks, 4 cores):

| encoding | presolve | first solution | optimum (261) |
|---|---|---|---|
| `AtMostOne` per (room, day, period, week class) over `x[e,t,r]` | 18 s (877 k literal occurrences) | 23 s | 29 s |
| intervals + `NoOverlap` per week class, default presolve | > 60 s (probing) | – | – |
| intervals + `NoOverlap2D`, probing off, no hint | 1 s | 6.6 s | > 60 s |
| **intervals + `NoOverlap2D`, probing off, greedy hint** | 1 s | **2.5 s** | **21 s** |

Hence `cp_model_probing_level = 0` (presolve probing over tens of thousands of optional intervals
burns minutes of wall time while reporting almost no deterministic time) and the greedy warm start
in `greedy.py`: locked → fixed-time (by size) → flexible events are placed first-fit into the
cheapest free option; the complete assignment is passed with `AddHint`, so CP-SAT starts from a
feasible incumbent and spends its budget on LNS improvement.

### Objective

Weighted sum of penalty terms. `weight = base_weight(name) × Constraint.weight`, where
`base_weight` comes from `SolverInput.weights` with the defaults in `weights.py`
(`room_preference` 10, `building_preference` 5, `min_capacity_waste` 1 per 10 wasted seats,
`same_room_group` / `same_room_across_weeks` 8 per extra room, `stability_room` 20,
`stability_time` 30, `exam_gap` 10, `max_exams_per_day` 10, `day_window` 5,
`evening_programs_in_buildings` 5, and 20–50 for the *softened* structural rules). The reported
`objective_breakdown` and both scores are computed by `scoring.evaluate` on the extracted
assignments, never read back from CP-SAT, so `solve()` and `validate()` agree by construction
(`stats["objective_value"] == stats["evaluated_penalty"]` is asserted in the tests).

`hard_score` = 100 when there is no hard violation, else `100 × (1 − violated events / events)`;
`soft_score` = `100 × (1 − penalty / worst-case penalty)` where each term reports its own bound.

### Shared exam rooms (`Event.share_room`)

The Final plan seats several small exams in one room under one invigilator, and routinely two *split*
exams in the same room pair (PSI 212 + FZT 260 in A 204 + A 102). Events with `share_room=True` are not
in the room's `NoOverlap2D`; each room with sharing candidates gets a `Cumulative` per week class with
capacity = the room's `exam_capacity` (lecture capacity if no sharing event is an exam). Exclusive
events and blocks enter the same cumulative with demand = capacity, so one non-sharing event in a
room-period excludes everything else.

**Seat rule** (`seats.py`): a sharing event needs `target = min(size, Σ seats of its rooms)` seats in
total (`min` only bites for a trusted, planner-locked room set that is too small: such an event fills
its rooms). A single-room event puts all of them in its room (demand = constant). A split event may
divide its students over its rooms *in any way*, at least one seat per used room: one integer
`seats[e, r] ∈ [z, cap_r·z]` per (split event, room option) with `Σ_r seats = target`, constant over
the event's duration, is the event's demand in room *r*'s cumulative. `validate()` accepts a timetable
iff such an allocation exists per (day, period, week): a max-flow over events → rooms (Gale/Hall
condition), so "A 204 + A 102 seat 122 but the exams need 130" is reported, and so is the subtler case
where the totals fit but one room is over-full (a single-room exam already uses most of A 102). The
static checker runs the same test on locked sharing exams (`locked_overlap` with `params.shared`),
greedy fills sharing rooms seat-aware, and hints value `seats` with a proportional (largest
remainder) allocation.

### Hard constraints that are always hard

`no_room_overlap`, `no_cohort_overlap`, `no_instructor_overlap` cannot be made soft; a
`Constraint(..., hard=False)` of those kinds is kept hard and reported in `stats["warnings"]`.
`capacity`, `fixed_time`, `room_tags`, `room_pin`, `room_forbid` are hard by default and may be
softened explicitly (`Constraint("capacity", {}, hard=False)` → seats short are penalised). Locked
assignments always win (also over the request's fixed day/time — a lock is the planner's decision).

## Real-data modes (D1–D3)

Three `SolverInput` switches, **off by default** in the pure solver (strict semantics, every older test
unchanged) and **on by default** in the bridge (run params `trust_locked_rooms`,
`fixed_conflicts_as_warnings`, `best_effort`; see `solver_bridge.MODE_DEFAULTS`). None of them relaxes
a rule silently: each produces a structured warning per case.

* **`trust_locked_rooms`** — a locked room set is the planner's decision; planning-list enrolments are
  estimates.  Only the planner's own locks are trusted: `Event.lock_trusted=False` marks a lock made by a
  tool (fix button, manual move, AI edit carried into a child run); such a lock must satisfy capacity and
  tags like any placement (review B2: a fix put 135 students into a 58-seat room "as the planner's room"). The locked rooms skip the capacity and tag pruning (`domains._room_options`), split locks
  skip `Σ cap·z ≥ size`, a sharing lock demands `min(size, seats)`, `capacity.score` / `room_tags.score`
  skip the trusted event, and the static checker emits one `trusted_lock_capacity` warning ("ACU 132
  expects 122 students but is locked to A 207 (55 exam / 120 lecture seats)", with bigger rooms as
  suggestions) or `trusted_lock_tags` warning per case. Pins and room bans are never overridden.
* **`fixed_conflicts_as_warnings`** — two *input-fixed* events (locked, or `fixed_day`+`fixed_start`
  with `fixed_time` hard) sharing a cohort/instructor key at overlapping times in shared weeks cannot be
  fixed by any room choice. Cohort/instructor `NoOverlap`s now contain only the key's *flexible* events
  (fixed-vs-flexible overlaps are pruned from the flexible domains, fixed-vs-fixed pairs are known
  statically): a waived pair is simply not related, any other fixed-vs-fixed clash gets an explicit
  "not both placed" clause. The static checker reports one `input_conflict` warning per pair (both
  requests named, "move one of them", "check the instructor name"); `score_keys` skips the pair while
  both sit at their fixed times; flexible events still respect the key against everything (a flexible
  event whose window only fits on top of a fixed pair stays an error).
* **`best_effort`** — on a static error or a CP-SAT infeasibility proof, phase 1 is the slack
  relaxation, warm-started with the greedy placement (complete hint: unhinted events hinted unplaced),
  minimising `(L+1)·#unplaced + #unplaced locked` (lexicographic: the most events, then keep the
  planner's locked ones); phase 2 re-solves the placed events with the normal objective, hinted with
  phase 1. Status stays `INFEASIBLE` (the full request set has no solution; the bridge stores such a run as
  `FEASIBLE_PARTIAL`, keeping `stats.partial`); `assignments` is the partial timetable, `stats.partial=True`, `placed`, `unplaced`, `events_total`, `unplaced_ids`; hard /
  soft scores are evaluated on the placed events (hard 100 = every hard rule holds for them). The first
  diagnosis (`code="partial"`) summarises: "every placed event keeps every hard rule except N accepted
  exception(s) (listed)", with `params.exceptions` = counts by cause (`D1` trusted planner rooms, `D2`
  fixed-time clashes, `D3` unplaced, `week_split`, …; the bridge recounts them with its own warnings);
  every unplaced event is explained (`unplaced`, no cap) unless a static single-event error already names
  it.  A search that ends without any solution (`UNKNOWN`) keeps the checked warm start as a `TIMEOUT`
  partial (`stats.partial_reason="timeout"`: the rest is not proven impossible).  The relaxation budget is
  half the time limit (no fixed cap). In relax mode a lock binds only if the event is placed,
  so overlapping locks unplace one event instead of making the relaxation infeasible.

Also: an event locked to *k* rooms may use *k* rooms (`normalize_input`; the Bahar list locks large
lectures to `A 101 / A 106 / …` while the request is a single-room event).

## Week segments for term runs (`weeksplit.py`)

A request is one event over all its weeks with one room set, so on a term run a single blocked week
(an ETKİNLİK / exam cell in the planner's grid, a `room_closed` week, another lock holding the room only
in some weeks) used to exclude the room for the whole term (Bahar term: 14 `locked_ineligible`).
`split_blocked_weeks(inp)` splits such events into **week segments** — same day and periods every week,
a room change only in the affected weeks:

* a **locked** event whose locked room is blocked / held by another lock in some weeks keeps the
  planner's lock for the other weeks; the affected weeks become unlocked segments at the same time
  (planner's rooms first in their preferences; they need seats for the full group: the trust in the
  planner's too-small room does not carry over to another room).  The lock with more weeks yields, so a one-week special event keeps its
  room.  A room that is never free is left to the static checker (`locked_ineligible` / `locked_overlap`);
* an **unlocked fixed-time** event for which no eligible room is free in every week is partitioned by a
  greedy maximum cover (the room free in most weeks takes them).  `profile_split=True` also splits
  events whose free rooms merely change between weeks (more freedom, larger model; off by default).

Segments get new negative ids, labels `"MAT 112 §1 [w9]"`, inherit every key/tag/group, are named by the
constraints that named the event (`event_ids`, `groups`), get `previous` re-keyed by weeks, and form one
soft `same_room_across_weeks` group (marked `week_segments`), so one room for all weeks is still
preferred.  Every split is reported (`week_split` warning: `reason` = `blocked` / `locked_clash` /
`no_common_room` / `no_room_all_weeks`, `kept_weeks`, `moved_weeks`, `uncovered_weeks`).

`solve_segmented(inp)` = split → `solve` → (best effort) **residual round** (skipped when its validated
hint cannot complete any more request, `residual_gain`, review M5): fixed-time events left
unplaced are covered by the rooms that are free in their weeks *given the rest of the timetable* and
re-solved hinted with the previous timetable; the round is kept only if it places more original events
completely (then more event-weeks) without losing hard score.  `to_original(split, result)` translates
back: segments in the same rooms are merged into one assignment, diagnosis ids (and `params.busy/clashes`
holders) map to the original events, `stats.placed` counts events placed in *every* week,
`stats.partially_placed(_ids)` the others, `stats.week_split` the counts.  The bridge does this for every
CP-SAT run with multi-week events (run param `split_blocked_weeks`, default on).

The relaxation objective knows the segments (`build._relax_objective`): lexicographically (1) requests not
completely placed, (2) unplaced event-weeks of segmented requests, (3) planner-locked events kept, (4)
closeness to the warm start's rooms (`diagnose.relaxation_diagnosis`: the greedy hint follows the soft
preferences, the relaxation has none, so maximising the placement no longer scatters the planner's rooms).

Bahar full term (`docs/testing/2026-10-08-real-data-feasibility.md`): 648 → 658/684 placed, roomed
567 → 577/603, planner-roomed 512 → 523/532, hard 100.  Week 1 alone (HAZIRLIK, Adli Tıp Staj, TOEFL …
blocks) admits at most 578/603 roomed events (week-1 relaxation proven OPTIMAL), so "every week of every
event" cannot reach the week-3 rate on this data.

## Bridge (`services/solver_bridge.py`) and the planner-level check

The bridge rewrites the planner's problem (joint lectures merged, fallback sizes, the planner's locks
trusted, week segments), so "hard 100" is also checked on the planner's problem:
`app/services/planner_check.py` compares the stored rows with the raw request rows (time, weeks, the
planner's lock, every room in or outside the pool, blocks, capacity, PC/TIP, cohort / instructor, every
request placed or named) and accepts an exception only when the run reports it (`D1`, `D2`, `D3`,
`week_split`, `outside_pool`, `manual`, `missing_enrolment`).  `python -m tools.validate_planner` runs it on
the real workbooks; `tests/test_planner_level_real.py` is the regression gate.  Bridge rules (review B1/M1):

* joint lectures merge only rows the planner put into the same room set at one time (lock mode: the locked
  set, prefer mode: the definitive set), or unlocked rows of the same course (leading zeros normalised)
  with a shared instructor; a shared instructor never joins a locked row or another course; a group with
  two different locked sets is not merged; the merged size is the **sum** (never clipped in lock mode: a
  too-small locked room is a reported `trusted_lock_capacity`); every request is stored with its own
  periods, weeks and — when the group sits in its planner rooms — its own definitive rooms;
* prefer mode, D1 for hints: a group seated by the planner in fewer seats gets the planner's seat count as
  size **only for the planner's set** (every other room that cannot seat the full group is forbidden),
  reported as `trusted_hint_capacity` / `joint_lecture_clipped`; a week segment moved out of a lock needs
  seats for the full group;
* a request without enrolment gets a fallback size (median of the course's other sections, else of the
  programme year, else of the term), a `missing_enrolment` warning and no `min_capacity_waste` term
  (`exclude_event_ids`, understood by every constraint selector);
* exam cohorts span the group's periods (latest end) and a partly locked group keeps the locked rooms.

## Determinism with several workers

CP-SAT's parallel search returns *some* optimum.  When the relaxation proves its optimum, a canonical
stage fixes it and keeps the placement with the most students (then a fixed id rank, `build.stable_rank`
— splitmix64, no Python hash randomisation); when the main solve proves optimality, a second stage fixes
the objective and picks the optimum with the smallest pseudo-random (event, room) / (event, time) rank.
Both canonical stages run on **one worker with a deterministic time limit** (`build.CANONICAL_DETERMINISTIC_S`,
review M2), so whether they prove their optimum no longer depends on machine load, and the tie-break ranks
of the canonical optimum use a wide range (`CANONICAL_RANKS`) so that ties between optima are unlikely.
So a fixed input and seed give the same timetable with `workers > 1` whenever the stages are proven
(`tests/test_planner_level_real.py::test_bahar_week3_is_deterministic`); time-limited, unproven solves can
still differ between runs (use `workers=1` for bit-for-bit runs).

## Planner rooms as hints (`definitive_rooms="prefer"`) and weights

* greedy: locks first, then a **preference pass** (fixed-time events take their preferred room *set* if
  it is free, largest first), then the rest; room costs use the model's weights;
* after the relaxation, `greedy.prefer_rooms` moves placed events back into their free preferred rooms
  (validated) before phase 2;
* `room_preference` units: a multi-room event uses its first `max_rooms` listed rooms for free (the
  planner's set is the first choice, not only its first room);
* bridge: an event may use as many rooms as the planner's set; D1 for hints (`trust_definitive_capacity`,
  default = `trust_locked_rooms`): a group the planner seats in fewer seats than its expected enrolment
  gets the planner's seat count as size (one `trusted_hint_capacity` warning per case), merged joint
  lectures too;
* bridge: only the planner's choice *inside* the room pool becomes a hint — a LOCKED row whose rooms are
  all outside the pool (lab/office without capacity) keeps them (`needs_room=False`, `outside_room_pool`)
  exactly as with locks; before, 81 Bahar week-3 rows competed for pooled rooms they never used and
  pushed planner-roomed classes out (placed 600 → 641 of 660).

`python -m tools.calibrate` (not shipped in the image) grid-searches weight sets on Bahar week 3, Güz week 3 and the Final
(rows + summary + choice as JSON with `--out`); results and the chosen defaults are in
`docs/testing/2026-10-08-real-data-feasibility.md` ("Weight calibration").

## Day sweep after a time-limited search (`cpsat.day_sweep`, `cpsat.polish_preferred`)

On the real Bahar week (~640 placed events, 58 rooms) a 45 s CP-SAT search stops far from the optimum
(objective 1694 vs bound 1262), although with the times fixed the room choice only couples events of the
same day.  When the warm start is complete (a solution is guaranteed) and the events span more than one
day, the main search gets `SEARCH_SHARE` (60 %) of the remaining time; if it ends FEASIBLE (not proven),
each day is re-solved on its own — that day's unlocked events pinned to their current day/start, the
day's locked events as they are, hinted with the current rooms — and a day's new rooms are kept only if
the *whole* timetable still has no hard violation and its total penalty strictly drops (soft terms
linking days, e.g. `same_room_group`, are part of that check).  `polish_preferred` then tries single
moves into a free preferred room set under the same rule.  Proven optima are never touched
(determinism above).  Bahar week 3 prefer mode, 90 s: penalty 1694 → ~1300, exact reproduction 83 → 89 %.
Stats: `sweep_days`, `sweep_improved_days`, `sweep_penalty_before/after`, `sweep_s`,
`polish_preferred_moves` (phase 2 of a best-effort run: `phase2_sweep_*`).

### Diagnosis codes and params

`Diagnosis.code` names the case, `Diagnosis.params` carries its facts, and
`params["options"]` holds one structured action per suggestion (`options.py`: `move`, `release_room`,
`unlock`, `relax`, `split`, `manual` with their arguments), so the run-report fixes
(`services/diagnosis_fixes.py`) and the studio pre-check (`services/precheck.py`) never parse wording.

| code | severity | params |
|---|---|---|
| `bad_time`, `no_time`, `all_blocked`, `out_of_horizon` | error / info | `day`/`start`/`duration`, `reasons`, `categories` (`no_time`: reason category → count), `weeks` |
| `no_room` | error | `reason` (`pin`/`tags`/`capacity`/`pin_vs_lock`/`rules`), `size`, `missing_tags`, `missing_pins`, `largest_room`, `largest_capacity`, `pinned_rooms`, `locked_rooms`, `pin_vs_lock`, `fitting_rooms`, `excluded` (collapsed reason categories), `reasons` |
| `fixed_conflict` / `input_conflict` | error / warning | `noun`, `key`, `kind`, `keys` (`[[kind, key], …]`), `day`, `start` |
| `trusted_lock_capacity` / `trusted_lock_tags` | warning | `rooms`, `room_codes`, `seats`, `size`, `fitting_rooms` / `missing_tags`, `forbidden_tags` |
| `trusted_hint_capacity` (bridge, prefer mode) | warning | `size`, `seats`, `room_codes`, `request_id` |
| `locked_overlap` | error | `rooms`, `room_codes`, `day`, `period`, `shared` (+ `week`, `need`, `seats` for shared rooms) |
| `locked_ineligible`, `locked_blocked` | error | `rooms`, `room_codes`, `reasons`, `categories`, `day`, `start`, `end` |
| `pigeonhole` | error | `n`, `day`, `period`, `week`, `rooms` |
| `unplaced` | error | `size`, `duration`, `day`/`start`/`end` (fixed time), `problem` (`capacity`/`rooms_busy`/`clash`/`excluded`), `busy` (`[{room, capacity, day, start, end, holders}]`), `clashes` (`[{kind, key, day, start, end, holders}]`), `free`, `excluded` (reason category → count), `fitting_rooms`, `largest_capacity` |
| `week_split` | warning | `reason`, `kept_weeks`, `moved_weeks`, `uncovered_weeks`, `rooms`/`room_codes`/`affected_rooms`, `segments` |
| `core`, `unplaced_summary`, `partial` | error / warning | `minimal` (core), `exceptions` / `reason` (partial) |
| `missing_enrolment`, `joint_lecture_clipped`, `outside_pool_overlap` (bridge) | warning | `request_ids`, `size`, `sizes`, `sources` / `seats`, `room_codes` / `rooms`, `day`/`date`, `start`, `end` |
| `manual_lock`, `joint_lecture_rejected` (bridge) | info | `origin` / `room_sets` |
| `empty_scope` (bridge) | error | `kind`, `course_requests`, `exam_requests` (the run is `FAILED`) |
| `timeout`, `relax_timeout`, `no_core`, `internal` | warning / error | — |

## Diagnosis (`diagnose.py`)

Never relax silently; explain instead. Three rungs, cheapest first:

1. **Static checker** before the big model: events larger than every eligible room, tags no room
   has, pins to unknown rooms, fixed times outside the grid, overlapping locked assignments, locks on
   ineligible/blocked rooms, fixed-vs-fixed cohort/instructor clashes, pigeonhole overloads (more
   fixed-time events in a slot/week than eligible rooms). Each `Diagnosis` names the events, the
   kinds and concrete suggestions (split across named rooms, release block X, move to P10 …).
2. **Assumption core**: a satisfaction-only copy (`mode="assume"`, no objective, `num_workers=1`,
   as CP-SAT requires) with `placed[e]` per event and one guard per room, cohort key, instructor
   key, locked event, same-room group and exam rule. `SufficientAssumptionsForInfeasibility` gives
   the initial core; deletion-based shrinking re-solves without one literal at a time under a
   per-probe time limit and keeps the literal only if the model becomes feasible without it.
   Interval presences are `base ∧ guard`, so a false guard switches the whole group off.
3. **Slack relaxation** (`mode="relax"`): minimise the number of unplaced events (ties: keep locked
   events placed; warm-started with the greedy placement). Every unplaced
   event is explained by `explain_event`: rooms that fit but are busy (and by whom), rooms excluded
   by capacity/tags/pins/bans, cohort/instructor clashes with named events, free alternatives and
   alternative periods on the same day.

The budget is `time_limit/2` (it scales with the limit); stats record `core_initial`, `core_final`,
`core_probes`, `core_minimal` (the core is called *minimal* only when every deletion probe was decided),
`unplaced`.  Core suggestions never propose softening room / cohort / instructor overlaps (always hard).
Explanations of multi-room events offer room **sets** whose seats hold the event (`use A101+A106 at …`,
alternative periods likewise, at most `max_rooms` rooms); releasing a busy room is suggested only when it
completes such a set. The structured `Diagnosis` objects are the only source of truth for the
LLM rendering in `app/ai`.

## Repair and validation (`repair.py`)

`repair(inp, assignments, changed_event_ids, time_limit_s, keep_changed=True, radius=1)` locks every
assignment except the *neighbours* of the changed events (events sharing a room slot, a cohort key
or an instructor key at an overlapping time, within `radius` conflict hops); with `keep_changed`
the edited events are locked to their new position (that is the user's intent), otherwise they are
freed too. The residual model is tiny, `previous=assignments` drives the stability objective and the
hints, and an impossible edit comes back `INFEASIBLE` with a diagnosis.

`validate(inp, assignments) -> list[Violation]` and `score(inp, assignments)` run the same
constraint modules in pure Python (no CP-SAT) for the API's manual/AI edits.

## Adding a constraint kind

1. Create `constraints/<kind>.py` exposing
   * `prune(doms: Domains, c: Constraint) -> None` (optional; only for hard rules; remove time
     options / rooms with a reason string that ends in `(<kind> #<id>)`),
   * `apply(ctx: ModelContext, c: Constraint) -> None` — add hard clauses through the `ctx`
     helpers (`guard(name)`, `add_at_most_one`, `add_not_both`, `add_linear_le`, `add_false`,
     intervals) or soft terms with `ctx.add_penalty(name, literal_or_int_expr, units, weight)`;
     use `ctx.time_lit`, `ctx.room_use`, `ctx.occupies`, `ctx.on_day`, `ctx.and_lit`,
   * `score(ev: Evaluation, c: Constraint) -> None` — the same rule on finished assignments:
     `ev.hard(kind, event_ids, message)` or `ev.soft(kind, event_ids, message, penalty)` plus
     `ev.add_bound(kind, worst_case)` for the soft score.
2. Register it in `constraints/__init__.py` (`Handler(kind, apply, score, prune, implicit=…,
   may_soften=…, default_hard=…)`). `implicit=True` kinds are always active and derive their
   default from `Event` fields; a targeted `Constraint` (`event_ids` / `cohort` / `program` /
   `match` / `instructor` selectors, see `_common.select_events`) adds to the default, an untargeted
   one reconfigures it (hard/soft, weight).
3. Add `DEFAULT_WEIGHTS[kind]` in `weights.py` and a test triple in `tests/solver/test_constraints.py`:
   minimal feasible, minimal infeasible whose diagnosis names the kind and the events, and a
   soft-weight case where changing the weight changes the choice.

## Generators (`tests/solver/generators.py`)

`generators.generate(GenParams)` plants a conflict-free solution (rooms, cohorts, instructors,
HAZIRLIK morning blocks) and derives the events from it, so instances are feasible by construction
and the planted assignments double as `previous` for stability/repair tests. `from_fixture_like`
uses the real room master (60 rooms, TIP rooms for medicine, PC labs, evening programmes after P13 in
B/C). `tests/solver/data/tiny.json` is a hand-written five-event instance used by the tests and as
an example of the JSON format (`serialization.py`).
