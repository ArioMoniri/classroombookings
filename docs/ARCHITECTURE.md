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
    │   │   ├── api/v1/            routers: auth, settings, terms, rooms, reference, requests, imports,
    │   │   │                       runs, constraints, chat, studio, presets, calendar, data_issues, health;
    │   │   │                       CRBS parity: bookings, booking_admin, room_admin, roles, users, departments,
    │   │   │                       holidays, org; wave 1: room_features, find_room, approvals, audit;
    │   │   │                       integrations: calendar_sync, webhooks
    │   │   ├── importers/         normalize.py (TR text/time/room parsing), planning_list.py,
    │   │   │                       exam_list.py, weekly_grid.py, crbs_legacy.py
    │   │   ├── solver/            PURE PYTHON, DB-agnostic: model.py (dataclasses), cpsat.py,
    │   │   │                       constraints/*.py, diagnose.py (infeasibility), repair.py (LNS)
    │   │   ├── ai/                anthropic client, tool schemas, prompt → ConstraintDiff, chat loop
    │   │   ├── services/          orchestration: build SolverInput from DB, persist results, export,
    │   │   │                       planner_check, events (publish_event), audit, approvals, calendar
    │   │   │                       feeds/connectors, webhooks, find_room, bookings_* (CRBS parity)
    │   │   └── workers/           in-process asyncio job queue (runs, imports), integrations outbox,
    │   │                           approvals sweeper
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
- **Only the planner's locks are trusted**: with `trust_locked_rooms` (D1) a planning-list LOCKED row keeps
  its room even when the room is too small (reported as a waived exception). A lock carried from a parent
  run by a fix button, a manual move or an AI edit sets `Event.lock_trusted=False` and must pass the
  capacity and tag checks like any placement (`app/solver/domains.py`, `app/ai/chat.py`).
- **One hook for booking-side changes**: every booking, series and approval mutation goes through
  `app/services/events.publish_event` (see "Event bus").

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
| Booking enhancements wave 1 | `room_custom_fields` typed (BOOLEAN/NUMBER/SELECT/MULTISELECT/TEXT, filterable, solver_tag; alembic 0012), `audit_events` (append-only, triggers; 0014), `approver_scopes`, `approval_rules`, `approval_requests`, `approval_decisions`, `inapp_notifications` (0015) — docs/product/wave1-api.md |
| Calendar sync (alembic 0011) | `calendar_feed_tokens` (SHA-256 of the token only), `calendar_connections` (Fernet-encrypted OAuth tokens), `calendar_event_links`, `calendar_event_revisions`, `calendar_sync_jobs` (outbox), `oauth_states`, `webhook_endpoints`, `webhook_deliveries` — docs/product/calendar-sync-api.md |
| `users.token_version` (alembic 0006) | raised to revoke every token of the user (see "Sessions and token revocation") |

### Migrations (Alembic chain)

Generated from `smartsched/backend/alembic/versions` by `scripts/docs/sync_docs.py` (do not edit the block).

<!-- AUTO:migrations -->

24 migrations in [`alembic/versions`](../smartsched/backend/alembic/versions); single head **`0028_p19_gaps`**. A new migration goes on top of it (`alembic heads` must print one line).

| # | Revision | Revises | Summary (first line of the docstring) |
|---:|---|---|---|
| 1 | `0001` | (base) | initial schema |
| 2 | `0002_studio` | `0001` | generator studio: drafts, presets, imported snapshots, constraints.source_ref |
| 3 | `0003_crbs_parity` | `0002_studio` | CRBS parity: roles/permissions, room groups/ACL/custom fields, booking calendar, bookings, outbox, translations… |
| 4 | `0004_review_fixes` | `0003_crbs_parity` | Review 2026-10-08 fixes: chat-apply claims (M2), job heartbeats (M6), canonical cohort keys in stored constraint… |
| 5 | `0005_crbs_legacy_ids` | `0004_review_fixes` | CRBS parity audit B4: ``legacy_crbs_id`` on the parity tables, so that importing a CRBS database twice updates the… |
| 6 | `0006_token_version` | `0005_crbs_legacy_ids` | Parity B-AUTH-11: ``users.token_version`` |
| 7 | `0011_integrations` | `0006_token_version` | Calendar sync and outgoing webhooks (docs/product/calendar-sync-api.md): hashed feed tokens, event revisions, Google /… |
| 8 | `0012_room_features` | `0011_integrations` | Booking enhancements wave 1, P10 typed room features (docs/product/booking-enhancements.md §4.1)… |
| 9 | `0013_find_room` | `0012_room_features` | Booking enhancements wave 1, T1 find a room (docs/product/booking-enhancements.md §4.2): bookings remember what they… |
| 10 | `0014_audit_events` | `0013_find_room` | Booking enhancements wave 1, P7 audit log (docs/product/booking-enhancements.md §4.6): the append-only… |
| 11 | `0015_approvals` | `0014_audit_events` | Booking enhancements wave 1, P1 approval workflows (docs/product/booking-enhancements.md §4.3, user decisions… |
| 12 | `0016_course_code_keys` | `0015_approvals` | Course codes: one course per code key (planner comparison follow-up, importer item 1b) |
| 13 | `0017_course_code_fold` | `0016_course_code_keys` | Course codes: Turkish letters folded in the code key (product-owner decision 2026-10-15) |
| 14 | `0018_ai_proposal_decisions` | `0017_course_code_fold` | AI proposal decisions: every reviewed AI / upload / learned proposal and its outcome |
| 15 | `0019_publish_guard_term_locks` | `0018_ai_proposal_decisions` | Publish guard + per-term write lock (review 2026-10-15 D4 / D8) |
| 16 | `0020_council` | `0019_publish_guard_term_locks` | ingestion council: council_jobs, council_steps, council_artifacts |
| 17 | `0021_outbox_queue` | `0020_council` | E-mail outbox on the integrations queue (ROADMAP Phase 11): ``notification_outbox`` gains ``next_attempt_at`` (when… |
| 18 | `0022_kvkk_signoff_unseed` | `0021_outbox_queue` | KVKK sign-off is never seeded (admin persona 2026-10-15 M-18) |
| 19 | `0023_learning` | `0022_kvkk_signoff_unseed` | Phase 19 learning lane (P19-L1) + catalogue batch (P19-C4) + priority columns (P19-M2) |
| 20 | `0024_moderation_indexes` | `0023_learning` | Phase 19 moderation read models (P19-M1): indexes for a person's sections across terms and a term's sections of one… |
| 21 | `0025_approval_first` | `0024_moderation_indexes` | Approval-first bookings (owner requirement 2026-10-15; docs/ROADMAP.md "Approval-first bookings") |
| 22 | `0026_sso_entra` | `0025_approval_first` | Sign-in with Microsoft Entra ID (owner decisions 2026-10-15; app/services/sso.py, docs/deploy/sso-entra.md) |
| 23 | `0027_notify_channels` | `0026_sso_entra` | Notification channels ("Bildirim kanalları"; owner decision 2026-10-15, docs/product/2026-10-15-integrations-options.md) |
| 24 | `0028_p19_gaps` | `0027_notify_channels` | Phase 19 backend gaps: program wizard drafts (P19-W-01) and person / programme priority (P19-P-04) |

<!-- /AUTO:migrations -->

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
    share_room: bool = False; lock_trusted: bool = True
    priority: int = 0                                # coordinator priority (higher wins), -100..100; relaxation tiers

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
    # Event.lock_trusted (default True): only planning-list LOCKED rows are trusted under D1; locks carried from a
    # parent run (fix button, MANUAL, AI edit) set lock_trusted=False and must pass capacity and tag checks
    fixed_conflicts_as_warnings: bool = False  # D2 fixed-vs-fixed key clash = input warning for that pair
    best_effort: bool = False                  # D3 infeasible -> maximum placement, stats.partial/placed/unplaced
    # who loses in a best-effort placement (app/solver/policy.py, user decision 2026-10-15): "lock_first"
    # (trusted locks, then Event.priority, then most requests/weeks) or "most_classes_first"; bridge: run param
    # relaxation_policy > settings key term.<id>.relaxation_policy > lock_first
    relaxation_policy: Literal["lock_first","most_classes_first"] = "lock_first"
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
    # every result: stats.waived_rules / waived_violations + a "waived_rules" warning when a built-in hard rule
    # (capacity, room_tags, room_pin, room_forbid, fixed_time) runs as soft: hard 100 then covers the rest only
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
| `POST /auth/logout` | revokes every token of the user (token version) |
| `/bookings/*`, `/booking-admin/*`, `/room-admin/*`, `/org/*`, `/roles`, `/departments`, `/holidays` | CRBS parity (docs/CRBS_PARITY.md §4) |
| `/calendar/*`, `/webhooks/*` | calendar feeds, Google / Microsoft push connectors, integration settings, webhooks (docs/product/calendar-sync-api.md) |
| `/room-admin/features*`, `GET /rooms/facets`, `POST /rooms/find`, `/approvals/*`, `/approval-rules`, `/me/notifications`, `/audit/*` | booking enhancements wave 1 (docs/product/wave1-api.md) |

The full route list is in smartsched/README.md ("API overview") and the live OpenAPI at `/api/docs`.

## AI layer

- SDK: `anthropic` (Python). The model is chosen under Settings → AI (default and alternatives per
  RESEARCH §4.3; `ANTHROPIC_MODEL` is only the fallback). Key stored encrypted with `APP_SECRET` (Fernet).
  Never logged.
- **Pre-generation**: free text ("TIP rooms only for medicine; keep pharmacy in C block Mondays;
  no lectures after 17:30 for first-year nursing") → tool-use call `propose_constraints` returning a
  list of typed `Constraint` objects with `hardness`, `weight`, `nl_text`. Admin reviews/accepts.
- **Post-generation**: chat on a run → tools `move_event`, `swap_rooms`, `lock_assignment`,
  `add_constraint`, `remove_constraint`, `explain_assignment`, `re_solve(stability=True)`; each tool
  is validated by the solver (never trust the model's claim), result summarised back to the admin.
- **Explanations**: Diagnosis objects are rendered to Turkish/English prose by the model with the
  structured data as the only source of truth.
- **Uploaded content and KVKK**: text or images from uploaded files go to the Claude API only when an
  administrator has turned on `ai.intake_enabled` / `ai.vision_enabled` through `PUT /ai/policy` with the
  KVKK acknowledgement (`app/ai/policy.py`; both off by default, every change audited). Otherwise the file
  is read on the server and its units are left for a person. Text the planner types is not governed by
  these switches.
- Always load the `claude-api` skill before editing `app/ai/*`.

## Intake formats (Ingestion Council)

Uploads go through the council's format registry (`app/council/formats.py`): magic bytes decide the format, every
format has its own caps, and a bomb is refused at upload (400 / 413) before a job exists. Structured formats are read
on the server; the AI route only runs when an administrator has enabled AI intake, and every row it produces waits for
a person's review. Generated from the registry entries by `scripts/docs/sync_docs.py`:

<!-- AUTO:formats -->

12 formats registered in [`app/council/formats*.py`](../smartsched/backend/app/council), detected by magic bytes first (the extension only breaks ties). Limits not listed are the `FormatLimits` defaults.

| Format | Label | Extensions | Route | Limit | Registered in |
|---|---|---|---|---|---|
| `xlsx` | Excel workbook | .xlsx .xlsm | structured: read on the server, no AI | 25 MiB | `formats_builtin.py` |
| `ics` | iCalendar | .ics .ical .ifb | structured: read on the server, no AI | 10 MiB | `formats_ics.py` |
| `xls` | Excel 97-2003 workbook | .xls | structured: read on the server, no AI | 20 MiB | `formats_sheets.py` |
| `ods` | OpenDocument spreadsheet | .ods | structured: read on the server, no AI | 20 MiB | `formats_sheets.py` |
| `xml` | XML | .xml | structured: read on the server, no AI | 10 MiB | `formats_sheets.py` |
| `csv` | CSV / TSV | .csv .tsv | structured: read on the server, no AI | 15 MiB | `formats_text.py` |
| `json` | JSON | .json | structured: read on the server, no AI | 10 MiB | `formats_text.py` |
| `docx` | Word document | .docx | AI-assisted: off by default; every row reviewed | 15 MiB | `formats_builtin.py` |
| `pdf` | PDF | .pdf | AI-assisted: off by default; every row reviewed | 15 MiB | `formats_builtin.py` |
| `image` | image | .png .jpg .jpeg .webp .gif | AI-assisted: off by default; every row reviewed | 10 MiB | `formats_builtin.py` |
| `eml` | e-mail | .eml | AI-assisted: off by default; every row reviewed | 15 MiB | `formats_mail.py` |
| `txt` | plain text | .txt .md .text | AI-assisted: off by default; every row reviewed | 2 MiB | `formats_text.py` |

Recognised but refused, with a hint: `doc` (legacy .doc files are not read; save the file as .docx); `ppt` (legacy .ppt presentations are not read; export the slides as PDF); `pptx` (presentations are not read; export the slides as PDF); `odf-other` (OpenDocument text and presentations are not read; save the file as .docx or PDF); `zip` (zip archives are not unpacked; upload the files inside it); `ole2-other` (this Office file is not a workbook the council can read; save it as .xlsx).

<!-- /AUTO:formats -->

## Event bus (booking side)

```
booking / series / approval change (inside its DB transaction)
  └─ app/services/events.publish_event(action, entity, items, actor, ...)
       1. audit.record            -> audit_events row (parent + one child per booking for bulk changes);
                                     the row id is what POST /audit/{id}/undo targets
       2. bookings_events (legacy) -> e-mail notifications through notification_outbox, when `notify` names one
       3. subscribers             -> workers/integrations.on_domain_event, registered for
                                     booking.*, series.*, approval.*:
                                       calendar_connectors.queue_bookings  (calendar_sync_jobs outbox)
                                       webhooks.on_event                   (webhook_deliveries, if enabled)
```

Actions are the audit action names: `booking.create`, `booking.move`, `booking.update`, `booking.cancel`,
`booking.restore`, `series.create`, `approval.request`, `approval.step`, `approval.approve`,
`approval.reject`, `approval.expire`, `approval.withdraw`. Subscribers run after the flush and before the
commit; a failing subscriber is logged and never propagated, so a broken webhook cannot undo a booking.
Anything that talks to the outside world only enqueues an outbox row; `app/workers/integrations.py`
delivers them (retries 1 min, 5 min, 30 min, 2 h, 6 h) and picks up rows left by a previous process on
start. In-app notifications for approvals are written by `services/approvals.py` into
`inapp_notifications` (`GET /me/notifications`); approvers and requesters also get e-mail through the
outbox. Administration tables (users, roles, rooms, ACLs, settings) are audited by a session flush hook,
with secrets redacted and client networks stored as an HMAC of the /24.

Audit rules: `audit_events` refuses UPDATE and DELETE by trigger (SQLite and PostgreSQL; a future KVKK
retention job must drop and recreate the trigger in its own migration). Undo is allowed for booking
create, series create, move and cancel when nothing later changed the same booking, within
`bookings.audit_undo_hours` (24 h) or before the booking starts, and when the caller holds the permission
the inverse action needs (`services/bookings_undo.py`).

## Calendar sync

- **Feeds** (`services/calendar_feeds.py`): `GET /api/v1/calendar/feeds/{token}/mine.ics`,
  `/room/{id}.ics`, `/department/{id}.ics`, `/room-group/{id}.ics`. The token is the credential; only
  its SHA-256 is stored (`calendar_feed_tokens`), a user may hold several, revoke one or reset all.
  RFC 5545 output with ETag / 304 and throttling. nginx does not log the feed paths. Links are built from
  `PUBLIC_URL` (or the admin setting `integrations.public_url`). The older `/ics/{token}/…` links use the
  same engine.
- **KVKK switch**: `integrations.calendar_sync_enabled` (default **off**; `calendar_sync_signoff` is
  `null` on a new install). Sync counts as on only with a real sign-off (an admin's user id and an ISO date),
  recorded when an admin switches it on via `PUT /calendar/admin/settings`; migration `0022` un-seeds the
  former default sign-off. Off turns every token feed into a 404; each change records an audit event.
- **Push connectors** (`services/calendar_connectors.py`): Google Calendar and Microsoft 365. They are
  available only after an administrator stores the organisation's OAuth client under
  `PUT /calendar/admin/settings` (client secrets Fernet-encrypted; none ships with the product, so
  `configured: false` until then). Per user: PKCE + state, encrypted tokens, calendar choice,
  create / update / delete through the `calendar_sync_jobs` outbox, refresh and re-auth. Verified against
  mocked provider APIs; not yet against a live tenant (docs/deploy/calendar-oauth.md).
- **Webhooks** (`services/webhooks.py`): administrator-registered endpoints with an event list, signed
  with HMAC-SHA256 over `"<timestamp>.<body>"`, retried, logged, redeliverable, switched off after five
  failed deliveries in a row (the creator gets an in-app note). `integrations.webhooks_enabled` is off by
  default because webhooks send data off the server; payloads carry no notes and no e-mail addresses.

## Approvals

`services/approvals.py`, rules in `approval_rules` per room, room group or room type (e.g. TIP, PC),
approvers designated per user (`approves_for`, `approver_scopes`). A booking or series that matches a
rule is stored as `PENDING` and the API answers `202`; an optional tentative hold keeps the slot. Steps
can be multi-stage; lead time is in working days; requests expire. Decisions: approve, reject, reject with
a suggestion, approve in another room, approve a subset of a series; competing requests for the same
slot are rejected when one is approved. Every transition is audited and notified (e-mail + in-app).
Expiry and hold release run lazily on every approvals call and in `workers/approvals_sweeper.py` every
60 s (not started when `ENVIRONMENT=test`). With no rule, booking behaves as in CRBS.

### Approval-first mode and notification delivery

`bookings.approval_mode` is `rules` (the CRBS behaviour above) or `all`. With `all`, every request for an empty slot goes to an admin first; the institution seed sets it once. A rejection needs a `reason_code` and a written reason, which the requester sees. `services/notify_dispatch.py` sends every notice (approval requested, decided or withdrawn; booking created or cancelled; room owner) to each recipient's enabled channels. Each recipient sets these at `/me/notification-preferences`. Duplicates are stopped by idempotency keys in `notification_deliveries`. An approver gets one message per submission (`group_id`), queued until the transaction commits.

The channels are in-app, e-mail and `services/channels/**`:
- browser push (pywebpush, VAPID)
- Telegram
- WhatsApp Cloud API, or an optional wuzapi bridge
- SMS
- Teams/Slack department posts, through Apprise

`channels.register()` adds them at start-up. Their outbox drains in `workers/integrations.py`, retrying from 1 min to 6 h. Every channel stays off until an admin enters the institution's sender and records a KVKK sign-off; the sign-off is checked again at send time. Users only link their own address, and linking is their opt-in. Messages are link-only by default. Secrets and addresses are encrypted. Push endpoints and webhook hosts are allowlisted and DNS-checked. Setup: `docs/deploy/notification-channels.md`.

## Sessions and token revocation

A JWT carries `uid`, the role code and `tv` = `users.token_version` (`core/security.py`). A request whose
`tv` differs from the user's current version answers 401. `revoke_tokens` raises the version on
`POST /auth/logout`, an own password change, an administrator setting the password or a reset code,
disabling the account, a role change and deleting the role. Sign-out therefore ends the user's sessions
on every device (a deliberate difference from CRBS, CRBS_PARITY row B-AUTH-11). The own password change
signs the current browser in again with the new password.

Permission changes follow the no-escalation rule (`services/bookings_perms.py`: `may_grant_role`,
`missing_permissions`): nobody grants a role, manages an account or creates, edits or deletes a role whose
permissions they do not all hold.

## Frontend (admin panel)

Next.js App Router, TypeScript strict, Tailwind 4, `motion` (framer-motion) for animated components,
TanStack Query for data, Zustand for UI state, `@dnd-kit` for drag-drop, `lucide-react` icons. Pages:
Dashboard (utilisation, pending requests, last runs), Import wizard, Rooms (grid/cards, photos),
Requests inbox, Generate (horizon picker + preference prompt), Timetable (room × period grid, week
switcher, conflicts highlighted, drag-drop), Run report (scores, diagnoses, fixes), Chat edit panel,
Settings (API key, model, weights). Fully responsive (phone to 4K), dark mode. CRBS screens (booking
grid with the reservation panel, my bookings, admin setup) live under `/bookings`, `/my-bookings` and
`/admin/*`. 14 languages (`messages/*.json`: the 13 CRBS languages plus Turkish) with per-key English
fallback and organisation overrides from `GET /org/i18n`.

## Deployment

`smartsched/deploy/docker-compose.yml`: `db` (postgres:16), `backend` (uvicorn, 2 workers + solver
worker), `frontend` (next start), `proxy` (nginx), optional `crbs` (php-apache + mysql) profile for the
legacy app, optional `caddy` TLS edge. `deploy.sh` = generate `.env`, build, migrate, seed admin, wait
for health. Jobs (solver runs, imports, calendar push, webhooks, the approvals sweep) run inside the
backend process; with several replicas each job stays in the replica that accepted it, and a dedicated
worker service is planned (smartsched/deploy/README.md, "Scaling").

The AWS pod (docs/deploy/AWS.md) is one EC2 instance running this stack plus the pod CI, controlled by
`infra/aws/POD_ACTION` (`up`, `status`, `logs`, `stop`, `start`, `cost`, `down destroy`) through
`.github/workflows/aws-bootstrap.yml` with a GitHub OIDC role. The pod writes its secrets to SSM itself
(the administrator password in `/smartsched/admin_password`); a $100 budget action and an idle stop cap
the cost.

## Testing & quality gates

- Backend: `make check` (ruff, mypy, pytest without the slow marker) and `make test-slow`; the real Excel
  fixtures are imported in tests; the solver has feasible / infeasible / soft-weight tests per constraint
  kind and scale tests behind `SMARTSCHED_SLOW=1`.
- Planner level: `python -m tools.validate_planner` imports the fixtures, solves Bahar week 3, Güz week 3,
  the Final exams and the Bahar term like `POST /runs`, and checks each stored run against the raw request
  rows (`services/planner_check.py`); any unwaived finding fails.
- CRBS superset gate: `scripts/parity_check.py` runs the API acceptance tests of every inventory row on
  the real Bahar import and maps UI rows to Playwright titles (docs/CRBS_PARITY.md §9).
- Frontend: `npm run check` (tsc, eslint, vitest); Playwright specs run only against a real backend
  (`E2E_REAL=1`; `deploy/pod-ci/gates/e2e-backend-entry.sh` imports the Bahar fixtures, seeds the admin,
  solves the term and pins the booking clock). There is no mock API.

### Pod CI flow

```
systemd timer (2 min) -> podci poll -> git ls-remote (token from SSM) -> new head? -> SQLite queue
worker (one job at a time, flock):
  prepare -> validate -> backend -> infra -> frontend -> e2e-real -> parity -> planner -> images -> watchdog
  -> deploy (deploy branch only; every blocking gate green; the commit is still the branch head)
  -> commit statuses "pod-ci" and "pod-ci/<gate>"; results at /ci/ on the panel
```

Gate dependencies: `validate`, `backend`, `infra`, `frontend`, `images`, `watchdog` need `prepare`;
`e2e-real` needs `frontend` and `backend`; `parity` and `planner` need `backend`. `watchdog` is the only
non-blocking gate. A gate whose dependency failed is reported as an error, never green. Definitions:
`smartsched/deploy/pod-ci/podci/gates.py`; scripts: `smartsched/deploy/pod-ci/gates/*.sh`.
`.github/workflows/smartsched.yml` is manual-only.
