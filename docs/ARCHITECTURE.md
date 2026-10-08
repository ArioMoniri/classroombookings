# SmartSched Architecture

**SmartSched** is the new, from-scratch "AI optimizer & schedulerizer" that lives next to the legacy
classroombookings (CRBS, PHP/CodeIgniter 3 + MySQL) app in this repository. CRBS stays untouched as the
data source we import from; SmartSched replaces the manual Excel planning workflow with:

1. **Import** (Excel request lists, weekly grids, legacy CRBS DB, and later the live university panel).
2. **Optimize** (OR-Tools CP-SAT model with hard/soft constraints, explanations when infeasible).
3. **Converse** (Claude API: natural-language preferences before generation and edits after).
4. **Publish** (weekly/monthly/term/exam timetables, exports back to Excel/iCal/CRBS bookings).

```
repo root
├── crbs-core/, index.php, assets/ …      legacy CRBS (unchanged)
├── docs/                                 analysis, roadmap, research, agents protocol
├── .claude/agents/                       subagent definitions (design-pro, strict-reviewer, …)
└── smartsched/
    ├── backend/        Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, OR-Tools CP-SAT, Anthropic SDK
    │   ├── app/
    │   │   ├── main.py            FastAPI app factory, routers, CORS, lifespan
    │   │   ├── core/              config (pydantic-settings), db session, security (JWT, Fernet), logging
    │   │   ├── models/            SQLAlchemy ORM (see Domain model)
    │   │   ├── schemas/           Pydantic I/O schemas
    │   │   ├── api/v1/            routers: auth, settings, terms, rooms, sections, requests, imports,
    │   │   │                       runs, assignments, constraints, chat, exports, health
    │   │   ├── importers/         normalize.py (TR text/time/room parsing), planning_list.py,
    │   │   │                       exam_list.py, weekly_grid.py, crbs_legacy.py
    │   │   ├── solver/            PURE PYTHON, DB-agnostic: model.py (dataclasses), cpsat.py,
    │   │   │                       constraints/*.py, diagnose.py (infeasibility), repair.py (LNS)
    │   │   ├── ai/                anthropic client, tool schemas, prompt → ConstraintDiff, chat loop
    │   │   ├── services/          orchestration: build SolverInput from DB, persist results, export
    │   │   └── workers/           background job runner (in-process asyncio queue; Celery-ready)
    │   ├── alembic/
    │   ├── tests/                 pytest; fixtures/ holds the real Excel files
    │   └── pyproject.toml
    ├── frontend/       Next.js 16 (App Router) + TypeScript + Tailwind 4 + motion; admin panel
    ├── deploy/         docker-compose.yml, Dockerfiles, nginx, .env.example, deploy.sh (one click)
    └── README.md
```

## Design principles

- **Solver is a pure function**: `solve(SolverInput) -> SolverResult`. No DB, no HTTP. This lets the
  solver, the importers, and the UI be built and tested in parallel.
- **Everything is a constraint object**: file-derived rules, admin toggles, and LLM-extracted
  preferences all become `Constraint` rows with `hardness ∈ {hard, soft}`, `weight`, `source`, and the
  original natural-language text, so the UI can show *why* a decision was made and the admin can flip a
  soft rule to hard or delete it.
- **100/100 or explain**: hard constraints are never silently relaxed. If CP-SAT proves infeasible the
  diagnoser isolates minimal conflicting sets and produces human-readable fixes ("BME 419 needs 102 seats
  on Wed P7–P9 but only A 204 (156) is free and it is reserved for TIP; options: release A 204, move to
  P10, split across A 101+A 106").
- **Stability**: re-solves accept `previous_assignments` and minimise perturbation unless told otherwise.
- **Importable, exportable, replaceable**: all state can be rebuilt from the Excel files + CRBS DB.

## Domain model (SQLAlchemy, Postgres in prod / SQLite in tests)

| Table | Key columns |
|---|---|
| `terms` | id, code (`2026-BAHAR`), name, kind (`REGULAR`,`FINAL`,`BUT`,`SUMMER`), start_date, end_date, week_count, periods_json (grid definition), is_active |
| `weeks` | id, term_id, index (1..n), start_date, kind (`LECTURE`,`EXAM`,`HOLIDAY`,`MAKEUP`), label |
| `buildings` | id, code (`A`), name |
| `rooms` | id, building_id, code (`A101` canonical), display_name (`A 101`), floor, capacity, exam_capacity, tags (JSON list: `TIP`,`PC`,`LAB`,`AMPHI`), is_bookable, notes, photo_url, legacy_crbs_room_id |
| `faculties` | id, name, canonical_name |
| `programs` | id, faculty_id, name, canonical_name, is_evening (İÖ) |
| `instructors` | id, full_name, canonical_name, title, email |
| `courses` | id, code (`MAT112`), display_code (`MAT 112`), name, t_hours, u_hours, l_hours, credits, ects |
| `sections` | id, term_id, course_id, program_id, label (şube), class_year, semester_no, enrolment, mode (`F2F`,`ONLINE`,`HYBRID`,`UZEM`,`ASYNC`,`HOSPITAL`,`SIMULATION`,`OTHER`), remote_pct, whole_term_in_room, notes, source_row (JSON copy of the Excel row) |
| `section_instructors` | section_id, instructor_id, role (`PRIMARY`,`SECONDARY`) |
| `meeting_requests` | id, section_id, day (1–7 or null), start_period, end_period, start_time, end_time, weeks (JSON int list), requested_room_text, requested_room_ids (JSON), requested_building, requested_tags (JSON), requested_capacity, flexible_day (bool), definitive_room_text, definitive_room_ids (JSON), status (`NEW`,`PARSED`,`NEEDS_REVIEW`,`LOCKED`), parse_warnings (JSON) |
| `exam_requests` | id, term_id, section_id (nullable), course_code, course_name, program_id, class_year, enrolment, instructor_text, date, start_time, end_time, start_period, end_period, requested_venue_text, requested_room_count, requested_min_capacity, requested_tags, invigilators_requested, on_campus_written, no_exam, definitive_room_text, definitive_room_ids, merge_key (same course across programmes), status |
| `blocks` | id, term_id, room_id, day/date, start_period, end_period, weeks, label (`HAZIRLIK`,`UZEM`,`ETKİNLİK`), source (`GRID_IMPORT`,`ADMIN`,`CRBS`) — pre-occupied slots |
| `constraints` | id, term_id, run_id (nullable → term-wide), kind, params (JSON), hardness, weight, source (`FILE`,`ADMIN`,`AI`), nl_text, enabled, created_by |
| `schedule_runs` | id, term_id, kind (`COURSE`,`EXAM`), horizon (`WEEK`,`MONTH`,`TERM`), horizon_params (JSON: week indexes/dates), status (`QUEUED`,`RUNNING`,`FEASIBLE`,`OPTIMAL`,`INFEASIBLE`,`FAILED`,`CANCELLED`), params (time limit, seed, weights), objective_value, soft_score (0–100), hard_score (0–100), stats (JSON), diagnosis (JSON), parent_run_id (for "edit via prompt"), prompt_text, created_at, finished_at |
| `assignments` | id, run_id, meeting_request_id / exam_request_id, week (nullable = all weeks in pattern), day, date, start_period, end_period, room_ids (JSON, ordered), is_locked, origin (`SOLVER`,`AI_EDIT`,`MANUAL`,`IMPORT`) |
| `chat_messages` | id, run_id, role, content, tool_calls (JSON), created_at |
| `settings` | key, value (encrypted when `is_secret`), is_secret, updated_at — e.g. `anthropic_api_key`, `anthropic_model`, `solver_default_time_limit` |
| `users` | id, email (optional), username (Turkish-insensitive), password_hash, full_name (= CRBS displayname), role_id → `roles`, role (code `ADMIN`,`PLANNER`,`VIEWER`,`TEACHER` or `CUSTOM`, kept in sync), department_id → `programs`, force_password_reset, auth_source (`local`/`ldap`), is_active |
| CRBS parity (bookings) | `roles`/`permissions`/`role_permissions`, `user_constraints`, `room_groups`, `room_custom_fields`(+options/values), `room_acl`(+permissions), `booking_schedules`/`booking_periods` (on the 18-period grid), `term_booking_settings`, `term_schedules`, `timetable_weeks`, `term_dates`, `holidays`, `bookings` + `booking_slots` (unique room/date/period), `booking_series`, `multi_bookings`(+slots), `password_reset_tokens`, `notification_outbox`, `translations` — see docs/CRBS_PARITY.md |
| `import_jobs` | id, kind, filename, status, summary (JSON: rows, created, updated, warnings), created_at |

## Solver contract (`app/solver/model.py`) — frozen for parallel work

```python
@dataclass(frozen=True)
class Room:        id: int; code: str; capacity: int; exam_capacity: int; building: str; tags: frozenset[str]
@dataclass(frozen=True)
class Event:
    id: int                        # meeting_request.id or exam_request.id
    kind: Literal["course","exam"]
    label: str                     # "MAT 112 §1"
    size: int                      # enrolment
    duration: int                  # number of consecutive periods
    weeks: frozenset[int]          # weeks in which the event occupies a room (course) / {week} (exam)
    fixed_day: int | None          # 1..7
    fixed_start: int | None        # period index 1..18
    allowed_days: frozenset[int]   # when day not fixed
    earliest_start: int = 1; latest_end: int = 18
    fixed_date: date | None = None # exams
    required_tags: frozenset[str] = frozenset()      # e.g. {"PC"}
    forbidden_tags: frozenset[str] = frozenset()     # e.g. {"TIP"}
    required_room_ids: frozenset[int] = frozenset()  # hard pin
    preferred_room_ids: tuple[int, ...] = ()         # soft, ordered
    preferred_building: str | None = None
    forbidden_room_ids: frozenset[int] = frozenset()
    min_rooms: int = 1; max_rooms: int = 1           # exams may split
    cohort_keys: frozenset[str] = frozenset()        # "PROG:Psikoloji:Y1" → no overlap within key
    instructor_keys: frozenset[str] = frozenset()    # "INS:canonical name"
    same_room_group: str | None = None               # events sharing this key should share room
    locked: "Assignment | None" = None
    needs_room: bool = True

@dataclass(frozen=True)
class Constraint:   kind: str; params: Mapping[str, Any]; hard: bool; weight: int = 1; id: int | None = None
@dataclass(frozen=True)
class SolverInput:
    rooms: tuple[Room, ...]; events: tuple[Event, ...]; constraints: tuple[Constraint, ...]
    days: tuple[int, ...] = (1,2,3,4,5,6,7); periods_per_day: int = 18; weeks: tuple[int, ...] = tuple(range(1,15))
    blocks: tuple["Block", ...] = ()          # Block(room_id, week|None, day, start, end)
    previous: tuple["Assignment", ...] = ()   # for stability objective
    time_limit_s: float = 60.0; seed: int = 0; workers: int = 8
    weights: Mapping[str, int] = field(default_factory=dict)  # soft objective weights by name
    # real-data modes (app/solver/README.md "Real-data modes"); solver default False, bridge default True
    trust_locked_rooms: bool = False           # D1 a too-small locked room is kept (warning, not violation)
    fixed_conflicts_as_warnings: bool = False  # D2 fixed-vs-fixed key clash = input warning for that pair
    best_effort: bool = False                  # D3 infeasible -> maximum placement, stats.partial/placed/unplaced
@dataclass(frozen=True)
class Assignment:   event_id: int; day: int; start: int; end: int; room_ids: tuple[int, ...]; weeks: frozenset[int]; date: date | None = None
@dataclass
class Diagnosis:    event_ids: list[int]; constraint_kinds: list[str]; message: str; suggestions: list[str]; severity: str
                    code: str = ""   # trusted_lock_capacity | input_conflict | unplaced | no_room | locked_overlap | ...
                    params: dict = {} # structured facts + params["options"]: one structured action per suggestion
@dataclass
class SolverResult:
    status: Literal["OPTIMAL","FEASIBLE","INFEASIBLE","TIMEOUT","ERROR"]
    assignments: list[Assignment]; hard_score: int (0..100); soft_score: int (0..100)
    objective_breakdown: dict[str, int]; diagnoses: list[Diagnosis]; stats: dict[str, Any]
    # best_effort + INFEASIBLE: assignments = maximum placement; stats.partial=True, placed, unplaced,
    # events_total, unplaced_ids; hard/soft scores are those of the placed events (100 = all hard rules hold)
```

Constraint kinds (v1): `capacity`, `no_room_overlap`, `no_cohort_overlap`, `no_instructor_overlap`,
`fixed_time`, `room_tags`, `room_pin`, `room_forbid`, `building_preference`, `room_preference`,
`same_room_across_weeks`, `same_room_group`, `min_capacity_waste`, `exam_gap(cohort, min_periods)`,
`max_exams_per_day(cohort, n)`, `stability`, `room_closed(room, day, periods, weeks)`,
`day_window(program, allowed periods)`, `evening_programs_in_buildings(list)`.

## API surface (`/api/v1`, JSON, JWT bearer)

| Method & path | Purpose |
|---|---|
| `POST /auth/login`, `GET /auth/me` | admin login |
| `GET/PUT /settings` | API key (write-only, masked on read), model, solver defaults |
| `POST /settings/test-ai` | verifies the Claude key with a 1-token call |
| `GET/POST/PUT/DELETE /terms`, `/terms/{id}/weeks` | seasons & week calendar |
| `GET/POST/PUT/DELETE /rooms`, `/buildings` | room master, photos (`POST /rooms/{id}/photo`) |
| `GET /programs`, `/faculties`, `/instructors`, `/courses`, `/sections` | reference data (search, paging) |
| `GET/PUT /requests/meetings`, `/requests/exams` | review/edit parsed requests, lock, set preferences |
| `POST /imports/planning-list`, `/imports/exam-list`, `/imports/weekly-grid`, `/imports/crbs` (multipart or DSN) | importers; `GET /imports/{job_id}` |
| `GET/POST /constraints` | manage constraint objects (toggle hard/soft, weight) |
| `POST /runs` {term_id, kind, horizon, params, prompt?} → 202 {run_id} | generate schedule (async) |
| `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/assignments?week=&day=&room=` | results, diagnosis |
| `POST /runs/{id}/chat` {message} | NL edit: LLM → ConstraintDiff/moves → child run |
| `POST /runs/{id}/assignments/{aid}/move`, `/lock` | manual drag-drop edits with conflict check |
| `GET /runs/{id}/export?format=xlsx|ics|csv|crbs` | exports (xlsx reproduces the weekly grid layout) |
| `GET /runs/{id}/grid?week=` | room × period matrix for the UI |
| `GET /health`, `GET /metrics` | ops |

## AI layer

- SDK: `anthropic` (Python). Model default from settings (`claude-opus-5-5`, per RESEARCH §4.3; admins may pick `claude-sonnet-5-5` for lower cost or `claude-haiku-5-5` for quick triage).
  Key stored encrypted with `APP_SECRET` (Fernet). Never logged.
- **Pre-generation**: free text ("TIP rooms only for medicine; keep pharmacy in C block Mondays;
  no lectures after 17:30 for first-year nursing") → tool-use call `propose_constraints` returning a
  list of typed `Constraint` objects with `hardness`, `weight`, `nl_text`. Admin reviews/accepts.
- **Post-generation**: chat on a run → tools `move_event`, `swap_rooms`, `lock_assignment`,
  `add_constraint`, `remove_constraint`, `explain_assignment`, `re_solve(stability=True)`; each tool
  is validated by the solver (never trust the model's claim), result summarised back to the admin.
- **Explanations**: Diagnosis objects are rendered to Turkish/English prose by the model with the
  structured data as the only source of truth.
- Always load the `claude-api` skill before editing `app/ai/*`.

## Frontend (admin panel)

Next.js App Router, TypeScript strict, Tailwind 4, `motion` (framer-motion) for animated components,
TanStack Query for data, Zustand for UI state, `@dnd-kit` for drag-drop, `lucide-react` icons. Pages:
Dashboard (utilisation, pending requests, last runs), Import wizard, Rooms (grid/cards, photos),
Requests inbox, Generate (horizon picker + preference prompt), Timetable (room × period grid, week
switcher, conflicts highlighted, drag-drop), Run report (scores, diagnoses, fixes), Chat edit panel,
Settings (API key, model, weights). Fully responsive (phone to 4K), dark mode, Turkish/English i18n.

## Deployment

`smartsched/deploy/docker-compose.yml`: `db` (postgres:16), `backend` (uvicorn, 2 workers + solver
worker), `frontend` (next start), `proxy` (nginx), optional `crbs` (php-apache + mysql) profile for the
legacy app. `deploy.sh` = generate `.env`, build, migrate, seed admin, open browser. Horizontal scaling:
backend is stateless; solver jobs go through the DB-backed queue so N workers can run.

## Testing & quality gates

- Backend: `pytest` ≥ 90 % on importers/solver; the real Excel fixtures are parsed in CI; solver has
  synthetic feasibility/infeasibility tests and a "reproduce the human planner" regression (≥ 95 % of
  definitive rooms satisfiable without hard violations).
- Frontend: `vitest` + Playwright smoke (login → import → generate → view grid).
- Lint: `ruff`, `mypy --strict` on solver, `eslint`, `tsc --noEmit`.
- CI: `.github/workflows/smartsched.yml` runs all of the above on every push.
