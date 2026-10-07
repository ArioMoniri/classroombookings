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
generators.py     synthetic + Bahar-like instance generators (planted feasible solutions)
serialization.py  JSON in/out of the contract
```

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

The Final plan seats several small exams in one room under one invigilator. Events with
`share_room=True` (single-room only; split exams stay exclusive) are not in the room's
`NoOverlap2D`; instead each room with sharing candidates gets a `Cumulative` per week class with
demand = event size and capacity = the room's `exam_capacity` (lecture capacity if no sharing event
is an exam). Exclusive events and blocks enter the same cumulative with demand = capacity, so one
non-sharing event in a room-period excludes everything else. `validate()` checks the seat budget per
(room, day, period, week); the static checker skips sharing pairs in its lock/pigeonhole tests and
`explain_event` reports "shared seats exceed N" when that is the blocker.

### Hard constraints that are always hard

`no_room_overlap`, `no_cohort_overlap`, `no_instructor_overlap` cannot be made soft; a
`Constraint(..., hard=False)` of those kinds is kept hard and reported in `stats["warnings"]`.
`capacity`, `fixed_time`, `room_tags`, `room_pin`, `room_forbid` are hard by default and may be
softened explicitly (`Constraint("capacity", {}, hard=False)` → seats short are penalised). Locked
assignments always win (also over the request's fixed day/time — a lock is the planner's decision).

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
3. **Slack relaxation** (`mode="relax"`): minimise the number of unplaced events. Every unplaced
   event is explained by `explain_event`: rooms that fit but are busy (and by whom), rooms excluded
   by capacity/tags/pins/bans, cohort/instructor clashes with named events, free alternatives and
   alternative periods on the same day.

The budget is `min(time_limit/2, 120 s)`; stats record `core_initial`, `core_final`,
`core_probes`, `unplaced`. The structured `Diagnosis` objects are the only source of truth for the
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

## Generators

`generators.generate(GenParams)` plants a conflict-free solution (rooms, cohorts, instructors,
HAZIRLIK morning blocks) and derives the events from it, so instances are feasible by construction
and the planted assignments double as `previous` for stability/repair tests. `from_fixture_like`
uses the real room master (60 rooms, TIP rooms for medicine, PC labs, evening programmes after P13 in
B/C). `tests/solver/data/tiny.json` is a hand-written five-event instance used by the tests and as
an example of the JSON format (`serialization.py`).
