# SmartSched developer guide

SmartSched plans a university's classrooms and exam rooms and books them. It lives next to the legacy
classroombookings (CRBS) app in this repository and is a superset of it. It imports the planning
office's Excel workbooks (course and exam request lists, weekly room grids), a room master CSV and the
CRBS database. It builds a timetable that breaks no hard rule with OR-Tools CP-SAT, or explains exactly
which classes it could not place and why. Staff then book the free periods around the published
timetable.

This guide is for developers. For the product overview, screenshots and the roadmap, see the
[root README](../README.md). For deployment, see [deploy/README.md](deploy/README.md).

## Architecture in brief

```
smartsched/
├── backend/     Python 3.12+, FastAPI, SQLAlchemy 2 (async), Alembic, OR-Tools CP-SAT, Anthropic SDK
│   ├── app/
│   │   ├── main.py         app factory, routers, lifespan (dev migrations, admin seed, job recovery,
│   │   │                   calendar-sync outbox recovery, approvals sweeper)
│   │   ├── core/           config (pydantic-settings), DB session, security (JWT + token version, Fernet),
│   │   │                   safe upload intake, throttling, logging
│   │   ├── models/         SQLAlchemy ORM          schemas/   Pydantic I/O
│   │   ├── api/v1/         REST routers (see "API overview")
│   │   ├── importers/      normalize.py + planning_list, exam_list, weekly_grid, room_master, crbs_legacy;
│   │   │                   settings.py (IMPORT_* variables)
│   │   ├── solver/         pure Python, no DB or HTTP: solve(SolverInput) -> SolverResult
│   │   ├── ai/             Claude client, strict tool catalogue, elicitation, preference-file ingest, chat
│   │   ├── services/       see below
│   │   ├── workers/        queue.py (in-process asyncio jobs; CP-SAT in a worker thread), run_jobs.py,
│   │   │                   integrations.py (calendar push + webhook outbox), approvals_sweeper.py (every 60 s)
│   │   └── cli.py          python -m app.cli
│   ├── alembic/versions/   0001 … 0016 (one head)
│   ├── tools/              validate_planner.py, compare_planner.py, calibrate.py, crbs_lang_import.py
│   └── tests/              pytest; fixtures/ holds the real 2026 workbooks; parity/ holds the CRBS gate
├── frontend/    Next.js 16 App Router, TypeScript strict, Tailwind 4, TanStack Query, dnd-kit, motion, zod;
│                messages/ holds 14 languages
└── deploy/      docker compose, deploy.sh, nginx, Caddy, legacy CRBS image, validate.sh, pod-ci/
```

The main service modules (`app/services/`):

| Module | Purpose |
|---|---|
| `solver_bridge.py` | DB -> `SolverInput` -> persisted results; run modes D1-D4, locks and `lock_trusted` |
| `planner_check.py` | re-checks a stored run against the raw request rows (planner-level hard score) |
| `studio.py`, `studio_classes.py`, `studio_rules.py`, `precheck.py`, `diagnosis_fixes.py` | Generator Studio, pre-check and fix buttons |
| `data_issues.py`, `conflicts.py`, `calendar_views.py`, `grid.py`, `exports.py` | run report, conflicts after publishing, calendar, exports |
| `events.py` | `publish_event`: the one hook for booking, series and approval changes (see below) |
| `audit.py`, `bookings_undo.py` | append-only audit log and undo |
| `approvals.py` | approval rules, designated approvers, `PENDING` requests, holds, expiry, decisions |
| `calendar_feeds.py`, `calendar_connectors.py`, `webhooks.py` | ICS feeds with hashed tokens, Google / Microsoft push outbox, signed webhooks |
| `find_room.py`, `rooms_features.py` | find-a-room ranking, typed room features and facets |
| `bookings*.py` | CRBS parity: grid, permissions (`bookings_perms.py`: no-escalation rule), limits, recurring, users, LDAP, e-mail, i18n, settings |

Design rules that the code relies on:

- **The solver is a pure function.** `app/solver` never touches the DB. `services/solver_bridge.py`
  builds a `SolverInput` from the database and persists the `SolverResult`. The frozen contract is in
  `app/solver/model.py` and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
- **Everything is a constraint.** File-derived rules, admin settings, AI proposals and uploaded
  preferences are all `constraints` rows with `kind`, `params`, `hardness`, `weight`, `source`
  (`FILE`, `ADMIN`, `AI`, `UPLOAD`, `BUILTIN`), `nl_text` and `source_ref`.
- **Hard rules are never relaxed silently.** An infeasible run carries `Diagnosis` objects with the
  events, the rule kinds and structured fix options (`params.options`), which the run report and the
  pre-check can apply. Only the planner's own locks are trusted when a locked room is too small; a lock
  made by a fix, a manual move or an AI edit carries `lock_trusted=False` and is checked like any room.
- **Claude never edits the timetable directly.** It proposes; the server resolves ids from the DB and
  the solver validates every change ([app/ai/README.md](backend/app/ai/README.md)).
- **One hook for booking-side changes.** Every booking, series and approval mutation calls
  `events.publish_event` inside its transaction: it writes the audit row, forwards the e-mail event and
  calls the subscribers (`workers/integrations.register()` subscribes the calendar push outbox and the
  webhooks to `booking.*`, `series.*` and `approval.*`). A failing subscriber is logged, never raised.
- **Tokens can be revoked.** Each JWT carries `tv` = `users.token_version`. `security.revoke_tokens`
  raises the version on sign-out (`POST /auth/logout`), password change or reset, disabling the account,
  a role change and role deletion; older tokens answer 401.

Component guides: [solver](backend/app/solver/README.md), [AI layer](backend/app/ai/README.md),
[frontend](frontend/README.md), [deploy](deploy/README.md), [pod CI](deploy/pod-ci/README.md).

## Quick start

The fastest route is the repository script, which sets up both halves:

```bash
scripts/dev.sh --run        # from the repository root; or: make -C smartsched dev
```

It needs Python 3.12+ and Node 22+. It creates `backend/.venv`, installs the backend with
`pip install -e ".[dev]"`, runs `npm ci`, writes `backend/.env` from `backend/.env.example` (SQLite,
a random `APP_SECRET`) and `frontend/.env.local` (real backend), migrates, seeds the admin, and starts
the backend on :8000 and the frontend on :3000. The admin is `DEV_ADMIN_EMAIL`, else your
`git config user.email`, else `admin@smartsched.local`; the password is `DEV_ADMIN_PASSWORD` or a random
one printed once and never stored. The frontend always needs the backend (there is no mock data).

### Backend (`smartsched/backend`)

```bash
cd smartsched/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # then set APP_SECRET (and ADMIN_EMAIL / ADMIN_PASSWORD for the first start)
make migrate                    # alembic upgrade head (SQLite by default)
make dev                        # uvicorn --reload on http://localhost:8000, OpenAPI at /api/docs
```

On start in `dev`, a new or Alembic-managed SQLite database is migrated automatically. A database
created earlier by `create_all` (tables but no `alembic_version`) gets a warning that lists the missing
columns; delete it, or run `alembic stamp 0001 && alembic upgrade head`. In `prod` the app never
changes the schema; the container entrypoint runs `alembic upgrade head`. The admin is seeded from
`ADMIN_EMAIL` / `ADMIN_PASSWORD` only when the users table is empty. In `prod` the backend refuses to
start when `APP_SECRET` or `JWT_SECRET` is missing, a placeholder, shorter than 32 characters or the
two are equal, or when `ADMIN_PASSWORD` is a placeholder or shorter than 12 characters.

| Target | What it runs |
|---|---|
| `make check` | `lint` + `type` + `test` |
| `make lint` | `ruff check` and `ruff format --check` on `app`, `tests` and `tools` (excluding `app/solver` and `tests/solver`, gated separately) |
| `make type` | mypy on `app/api`, `app/ai`, `app/importers`, `app/services`, `app/workers`, `app/core`, the solver contract (`model.py`, `stub.py`) and `tools` |
| `make test` | `pytest -q --ignore=tests/solver -m "not slow"` (API, importers on the real workbooks, studio, AI with a mocked SDK) |
| `make test-slow` | the heaviest real-workbook tests (`-m slow`); CI runs both |
| `make test-all` | both of the above |
| `make format` | `ruff check --fix` + `ruff format` |
| `make dev` / `make migrate` | dev server / `alembic upgrade head` |

After changing `app/models`, add a migration: `alembic revision --autogenerate -m "…"`.

### Frontend (`smartsched/frontend`)

```bash
scripts/dev.sh --run            # from the repo root: backend :8000 (SQLite, migrations, seeded admin) + frontend :3000
# or, with the backend already running:
cd smartsched/frontend
npm ci
cp .env.example .env.local      # NEXT_PUBLIC_API_URL = the backend (default http://localhost:8000)
npm run dev                     # http://localhost:3000
```

There is no mock or demo mode: the UI always talks to the real backend. Sign in with the administrator
seeded from the backend's `ADMIN_EMAIL` / `ADMIN_PASSWORD`, then import your workbooks or the fixtures
in `smartsched/backend/tests/fixtures/`.

| Script | What it runs |
|---|---|
| `npm run dev` / `build` / `start` | Next.js dev server / production build / serve the build |
| `npm run check` | `tsc --noEmit && eslint . && vitest run` (the quality gate) |
| `npm run test` | vitest only |
| `npm run typecheck` / `lint` | the individual gates |
| `npm run e2e` | Playwright on a production build on :3100; needs `E2E_REAL=1` and a running backend (start it with `smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh`), otherwise every spec skips |
| `npm run e2e:ui` | the same in Playwright's UI mode |

The browser never calls FastAPI directly. `src/app/api/v1/[...path]/route.ts` proxies `/api/v1/*` to
`NEXT_PUBLIC_API_URL` and attaches the JWT from the httpOnly cookie. Structure, auth flow and how to add
pages are in [frontend/README.md](frontend/README.md).

Interface languages: `messages/<code>.json` for `tr`, `en`, `cs`, `cy`, `da`, `de`, `es`, `fi`, `fr`,
`it`, `nl`, `pt`, `pt-br`, `sv`. English is the source; the CRBS languages carry the strings CRBS itself
translates, and a missing key falls back to English per key. `python -m tools.crbs_lang_import` (from
`backend/`) regenerates them from `crbs-core/application/language/` and writes
`docs/testing/language-coverage.md`.

State on 2026-10-15: the wave-1 frontend (approvals inbox, find-a-room page, audit viewer, room
features admin, notification bell) is being built. Some of its components are already committed, and
`npm run typecheck` fails on their missing `wave1.*` message keys until that work lands.

### Top-level make targets

`make -C smartsched help` lists them all. The ones used most: `dev`, `check` (backend +
frontend gates), `check-all` (plus solver and AI gates and `deploy/validate.sh`), `e2e`, `validate`,
`deploy`, `deploy-legacy`, `update`, `down`, `logs`, `status`, `watchdog`, `watchdog-check`.

## CLI

Run from `smartsched/backend` with the venv active. `--database-url` (before the subcommand) overrides
`DATABASE_URL`.

| Command | What it does |
|---|---|
| `python -m app.cli import planning-list FILE --term CODE [--week-count 14]` | course planning list (shape A) |
| `python -m app.cli import exam-list FILE --term CODE` | exam planning list (shape B) |
| `python -m app.cli import weekly-grid FILE --term CODE --year YYYY [--term-kind REGULAR\|FINAL\|BUT]` | weekly room grid (shape C): rooms, weeks, blocks, and the published board as a run |
| `python -m app.cli import room-master FILE` | room master CSV (`code,capacity,exam_capacity,tags,building,floor,bookable[,notes]`); its values win over later workbook imports |
| `python -m app.cli import crbs [FILES…] [--dsn mysql://user:pass@host/db]` | legacy CRBS from SQL dumps or a live MySQL server (`pip install pymysql`) |
| `python -m app.cli solve --term CODE [--kind COURSE\|EXAM] [--horizon WEEK\|MONTH\|TERM] [--week N] [--time-limit 60] [--solver auto\|cpsat\|stub] [--label TEXT]` | create and run a schedule run, print the result |
| `python -m app.cli seed-admin` | create the admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` if no users exist |

Tools (also from `smartsched/backend`):

| Command | What it does |
|---|---|
| `python -m tools.validate_planner [--instances bahar_w3 guz_w3 final bahar_term] [--time-limit 120]` | imports the fixtures, solves like `POST /runs`, checks every run at planner level; exit 1 on any violation (pod CI gate `planner`) |
| `python -m tools.compare_planner …` | compares SmartSched's timetable with the planner's published grids against a running backend ([report](../docs/testing/2026-10-08-schedule-vs-planner.md)) |
| `python -m tools.calibrate …` | solver weight calibration |
| `python -m tools.crbs_lang_import [--check]` | regenerates the language files from CRBS (`--check`: exit 1 when one is stale) |

Sample data (the real 2026 workbooks are committed as test fixtures):

```bash
python -m app.cli import room-master   tests/fixtures/room_master.csv
python -m app.cli import weekly-grid   tests/fixtures/bahar_derslikler_takvimi_2026.xlsx --term 2026-BAHAR --year 2026
python -m app.cli import planning-list tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx --term 2026-BAHAR
python -m app.cli import exam-list     tests/fixtures/final_planlama_listesi_2026_v2.xlsx --term 2026-FINAL
python -m app.cli import weekly-grid   tests/fixtures/final_derslikler_takvimi_2026_v2.xlsx --term 2026-FINAL --year 2026
python -m app.cli import planning-list tests/fixtures/guz_derslik_planlama_2026_2027_v2.xlsx --term 2026-GUZ
python -m app.cli import weekly-grid   tests/fixtures/guz_derslikler_takvimi_2026_2027.xlsx --term 2026-GUZ --year 2026
```

Every importer prints an `ImportReport`: rows total, imported and skipped (with reasons), warnings
grouped by pattern, and created/updated counts per entity. Re-importing a file updates rows in place.
Rows missing from the new file are archived, never deleted. Import the weekly grid (or the room
master) before the planning list so rooms and capacities exist. The quirks the importers handle are in
[docs/DATA_ANALYSIS.md](../docs/DATA_ANALYSIS.md). Two importer switches: `IMPORT_NON_ROOM_VENUES` (a
JSON list of words such as CASE or ONLINE that mark a row as needing no room) and
`IMPORT_GRID_CARRY_FORWARD` (off by default: when the board has fewer week sheets than the term, carry
the last week's blocks forward instead of reporting the missing weeks).

In the Docker stack, run the same commands through the backend container:
`docker compose --env-file .env run --rm backend python -m app.cli …` (see
[deploy/README.md](deploy/README.md)).

## Environment

### Backend

Read by `app/core/config.py` (and `app/importers/settings.py` for `IMPORT_*`) from the environment or
`backend/.env`. Every variable is listed with a comment in `backend/.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev` / `test` / `prod`; anything else fails at start. `prod` never changes the schema and checks the secrets |
| `DEBUG` | `false` | debug logging |
| `DATABASE_URL` | `sqlite+aiosqlite:///./smartsched.db` | async SQLAlchemy URL. Production: `postgresql+psycopg://user:pass@host/db` |
| `CREATE_TABLES_ON_STARTUP` | `true` | migrate a dev/test SQLite database on start (never in `prod`) |
| `SQLITE_BUSY_TIMEOUT_MS` | `15000` | SQLite lock wait |
| `APP_SECRET` | none usable (a placeholder that `prod` refuses) | Fernet key for encrypted settings (API keys, OAuth client secrets) and studio run seals; back it up |
| `JWT_SECRET` | falls back to `APP_SECRET` in dev/test | JWT signing key; required in `prod`, at least 32 characters, different from `APP_SECRET` |
| `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` | `HS256`, `720` | token algorithm and lifetime |
| `METRICS_TOKEN` | none | bearer token for scraping `/metrics` without a user session |
| `CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | JSON list of allowed origins |
| `PUBLIC_URL` | none | how browsers reach the panel; feed links and OAuth redirect URIs are built from it (the admin setting `integrations.public_url` overrides it) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | none | admin seeded when the users table is empty; leave the password empty afterwards |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | none / the built-in default | fallbacks when no key or model is stored through Settings → AI |
| `SOLVER_DEFAULT_TIME_LIMIT`, `SOLVER_WORKERS` | `60`, `8` | solver defaults, overridable per run |
| `SOLVER_MAX_TIME_LIMIT`, `SOLVER_MAX_WORKERS` | `3600`, `16` | upper bounds for a run's `time_limit_s` and workers |
| `MAX_ACTIVE_RUNS_PER_USER` | `3` | queued + running runs per user (429 above) |
| `RUN_HEARTBEAT_S`, `RUN_STALE_AFTER_S` | `15`, `90` | liveness beat of runs and imports; older beats are orphaned at start |
| `RUN_WALL_CLOCK_FACTOR`, `RUN_WALL_CLOCK_MARGIN_S`, `RUN_CANCEL_GRACE_S` | `5`, `300`, `30` | wall-clock cap of a run and the grace period after a stop |
| `UPLOAD_DIR` | `./uploads` | uploaded workbooks and room photos (only `/uploads/rooms` is served publicly) |
| `UPLOAD_MAX_MB` | `25` | any single upload (413 above) |
| `ZIP_MAX_UNCOMPRESSED_MB`, `ZIP_MAX_MEMBER_MB`, `ZIP_MAX_RATIO` | `50`, `20`, `100` | limits for `.xlsx` / `.docx` archives |
| `SHEET_MAX_ROWS`, `SHEET_MAX_COLS` | `20000`, `1024` | sheet size limits |
| `PARSE_ISOLATION`, `PARSE_MEMORY_MB`, `PARSE_TIMEOUT_S` | `process`, `2048`, `300` | workbook parsing in a memory-limited child process (or `thread`) |
| `IMPORT_NON_ROOM_VENUES` | a Turkish + English list | see CLI above |
| `IMPORT_GRID_CARRY_FORWARD` | `false` | see CLI above |
| `SMARTSCHED_SLOW` | unset | `1` enables the slow solver scale tests |

The Claude API key is normally set in the app: **Settings → AI**, paste the key, save, **Test key**
(`POST /api/v1/settings/test-ai`). It is stored encrypted and returned only masked. The model is
chosen on the same screen.

Organisation-level switches live in the database, not in the environment: CRBS behaviour switches
under `GET/PUT /org/settings` ([docs/CRBS_PARITY.md](../docs/CRBS_PARITY.md) §6.1), and calendar sync
under `GET/PUT /calendar/admin/settings` (`calendar_sync_enabled`, on; `webhooks_enabled`, off; feed
history window; the Google and Microsoft OAuth clients, whose secrets are stored encrypted). There is
no settings screen for the calendar ones yet.

### Frontend

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI base URL used by the `/api/v1` proxy (inlined at build time) |

Deployment variables (`UVICORN_WORKERS`, `RUN_MIGRATIONS`, `SEED_ADMIN`, limits, legacy, TLS) are in
`deploy/.env.example`.

## API overview

All routes are under `/api/v1`, JSON, with a JWT bearer token (`POST /auth/login`). The interactive
OpenAPI is at **`/api/docs`** (schema at `/api/openapi.json`).

| Group | Routes |
|---|---|
| Health | `GET /health`, `GET /metrics` |
| Auth and users | `POST /auth/login` (e-mail or username; LDAP when enabled), `POST /auth/logout` (revokes every token of the user), `GET /auth/me`, `GET /auth/permissions`, `GET/PUT /auth/profile`, `POST /auth/change-password`, `POST /auth/password-reset/request`, `/confirm`; `/users` CRUD, `GET /users/search`, `POST /users/import` (CSV), `GET/PUT /users/{id}/constraints`, `POST /users/{id}/reset-token`, `POST /users/{id}/password` |
| Roles and departments | `GET /permissions`, `/roles` CRUD (CRBS permission sets + booking limits; no escalation), `/departments` CRUD (departments are programmes) |
| Bookings (CRBS parity) | `GET /bookings/context`, `/grid`, `/dates`, `/rooms[/{id}]`, `/users`, `/departments/{id}/rooms`; `POST /bookings` (`202` when an approval rule applies), `/recurring/preview`, `/recurring`, `/multi`, `/multi/{id}/create`; `GET/PUT /bookings/{id}`, `/series`, `POST /bookings/{id}/cancel`, `/cancel-multi`; `GET /bookings/mine`, `/dashboard`, `/owned-rooms`, `/conflicts`, `/export.csv`, `/feed/user.ics`, `/feed/room/{id}.ics`, `POST /bookings/feed/token`, `GET /ics/{token}/…` |
| Calendar sync | `GET /calendar/sync`; `POST /calendar/feeds/tokens`, `/feeds/reset`, `DELETE /calendar/feeds/tokens/{id}`, `GET /calendar/feeds/options`; public `GET /calendar/feeds/{token}/mine.ics`, `/room/{id}.ics`, `/department/{id}.ics`, `/room-group/{id}.ics`; `GET /calendar/connectors`, `POST /calendar/connectors/{provider}/connect`, `GET …/callback`, `…/calendars`, `PUT`, `POST …/resync`, `DELETE`; `GET/PUT /calendar/admin/settings`, `GET /calendar/admin/jobs` |
| Webhooks | `GET /webhooks/event-types`, `/webhooks` CRUD, `POST /webhooks/{id}/secret`, `/test`, `GET /webhooks/{id}/deliveries`, `POST /webhooks/deliveries/{id}/redeliver` |
| Room features and find-a-room | `/room-admin/features` CRUD, `POST /room-admin/features/adopt-tags`, `/template`, `/bulk-values` (CSV), `GET /room-admin/features/{id}/impact`, `GET/PUT /room-admin/rooms/{id}/features`, `GET /rooms/facets`; `POST /rooms/find`, `GET /rooms/find/recent` |
| Approvals and notifications | `GET /approvals/inbox`, `/mine`, `/{id}`, `POST /approvals/{id}/decide`, `/withdraw`, `POST /approvals/sweep`, `GET /approvals/rooms/{id}/check`, `GET /approvals/approvers`, `PUT /approvals/approvers/{user_id}`; `/approval-rules` CRUD; `GET /me/notifications`, `POST /me/notifications/read` |
| Audit | `GET /audit`, `GET /audit/export.csv`, `GET /audit/{id}`, `POST /audit/{id}/undo` |
| Booking setup | `/booking-admin/sessions…` (selectable, default schedule, group schedules, date→timetable-week calendar), `/booking-admin/schedules…`, `/booking-admin/periods/{id}`, `/booking-admin/weeks…`, `GET /booking-admin/access-check`, `GET /booking-admin/outbox`; `/holidays` CRUD; `/room-admin/groups…`, `/room-admin/rooms…` (owner, location, icon, order, photo, custom field values), `/room-admin/fields…`, `/room-admin/acl…` |
| Organisation | `GET /org/public`, `GET /org/setup-status`, `POST /org/setup` (first run), `GET/PUT /org/settings`, `POST/DELETE /org/logo`, `GET/PUT /org/auth/ldap`, `POST /org/auth/ldap/test`, `GET/PUT /org/smtp`, `POST /org/smtp/test`, `/org/translations`, `GET /org/i18n`, `GET /org/changelog`, `POST /org/changelog/seen`, `GET /org/events` |
| Settings | `GET/PUT /settings` (API key write-only, masked on read), `POST /settings/test-ai` |
| Terms | `/terms` CRUD, `GET/PUT /terms/{id}/weeks` |
| Rooms | `/buildings`, `/rooms` CRUD, `POST /rooms/{id}/photo` |
| Reference data | `GET /faculties`, `/programs`, `/instructors`, `/courses`, `/sections` |
| Requests | `GET/PUT /requests/meetings[/{id}]`, `POST /requests/meetings/{id}/check-room`, `GET/PUT /requests/exams`, `GET /requests/stats` |
| Imports | `POST /imports/planning-list`, `/exam-list`, `/weekly-grid`, `/room-master`, `/crbs` (multipart, `202 {id}`); `GET /imports`, `/imports/{id}`, `/imports/{id}/file` |
| Constraints | `GET /constraints/kinds`, `/constraints` CRUD |
| Runs | `POST /runs` (`202`), `GET /runs[/{id}]`, `DELETE /runs/{id}`, `POST /runs/{id}/activate`, `GET /runs/{id}/events` (SSE progress), `/assignments`, `/grid?week=`, `/summary`, `/export?format=xlsx\|csv\|ics\|crbs` |
| Edits and fixes | `POST /runs/{id}/assignments/{aid}/move`, `/lock`; `POST /runs/{id}/diagnoses/{idx}/apply` |
| AI | `POST /terms/{id}/elicit`, `/elicit/accept`, `/preferences/upload`; `GET/POST /runs/{id}/chat`, `POST /runs/{id}/chat/apply`, `POST /runs/{id}/explain`; `GET /ai/catalog` |
| Generator Studio | `GET /studio/meta`; `GET/PUT /terms/{id}/studio` (draft, `If-Match`), `/studio/summary`, `/studio/classes`, `/studio/rules`, `POST /terms/{id}/studio/precheck`, `/precheck/fix`, `/proposals/accept`, `/preferences/mapping`, `/generate`; `PUT /studio/meetings/bulk`, `POST /studio/meetings[/{id}]/revert`, `POST /studio/constraints/preview`, `/copy` |
| Presets | `/presets` CRUD, `POST /presets/{id}/apply` |
| Dashboard | `GET /dashboard` |

Contracts for the newer groups: [docs/product/calendar-sync-api.md](../docs/product/calendar-sync-api.md)
and [docs/product/wave1-api.md](../docs/product/wave1-api.md).

A typical flow: log in; import the weekly grid (or room master), then the planning list; review
`GET /requests/meetings?term_id=…&status=NEEDS_REVIEW`; `POST /runs {term_id, kind: COURSE|EXAM, horizon:
WEEK|MONTH|TERM, horizon_params, params}` where `params.solver` is `auto` (CP-SAT, falling back to the
greedy stub), `cpsat` or `stub`; follow `GET /runs/{id}` or the SSE stream; read the grid and
diagnoses; move, lock, apply fixes or chat; `POST /runs/{id}/activate` to publish. The `crbs` export
currently returns the generic CSV (mapping to the CRBS booking format is in the backlog).

## Jobs and runs

Solver runs and imports execute in an in-process asyncio queue inside the backend
(`app/workers/queue.py`); the CP-SAT call itself runs in a worker thread, so the API stays
responsive. Status and progress are written to the `schedule_runs` / `import_jobs` rows with a
heartbeat. Jobs left `QUEUED` or `RUNNING` by a previous process are marked failed on start. Two more
background loops start with the app: the integrations worker (calendar push and webhook deliveries,
retried 1 min / 5 min / 30 min / 2 h / 6 h; rows left by a previous process are picked up on start)
and the approvals sweeper (every 60 s; not started when `ENVIRONMENT=test`). A dedicated worker
service is planned before running several replicas ([deploy/README.md](deploy/README.md), "Scaling").

## Tests

| Command | Scope |
|---|---|
| `make -C smartsched check` | backend `make check` + frontend `npm run check` |
| `make -C smartsched check-all` | `check` + solver gate (`ruff`, strict `mypy`, `pytest tests/solver`) + AI lint + `deploy/validate.sh` |
| `cd backend && make test-slow` | the heaviest real-workbook tests |
| `cd backend && python -m pytest tests/solver -q` | solver: feasible, infeasible and soft-weight cases per constraint kind, diagnosis, repair |
| `cd backend && SMARTSCHED_SLOW=1 python -m pytest tests/solver -q` | adds the 1 300-event / 60-room / 14-week course and 400-exam scale tests |
| `cd backend && python -m pytest tests/ai -q` | AI layer with a scripted fake SDK; `test_live_smoke.py` runs only when `ANTHROPIC_API_KEY` is set |
| `cd backend && python -m tools.validate_planner` | planner-level check of four real runs (pod CI gate `planner`) |
| `python3 scripts/parity_check.py` | CRBS superset gate on the real Bahar data (pod CI gate `parity`); `--dry-run` checks the mapping only |
| `cd frontend && E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test` | every Playwright spec (smoke, real-backend, bookings, calendar, reserve, admin-gaps, languages, motion-audit) against the real e2e backend (`deploy/pod-ci/gates/e2e-backend-entry.sh`; [setup](../docs/testing/2026-10-08-real-backend-e2e.md)) |

Policy ([docs/ROADMAP.md](../docs/ROADMAP.md), "TDD policy"): every importer function starts from a
failing test on a real fixture row; every solver constraint has a feasible, an infeasible and a
soft-weight test; API routes are tested with `httpx` against SQLite.

CI runs on the AWS pod ([deploy/pod-ci/README.md](deploy/pod-ci/README.md)). The gates, in order:
`prepare`, `validate`, `backend`, `infra`, `frontend`, `e2e-real`, `parity`, `planner`, `images`,
`watchdog` (not blocking); then `deploy` on the deploy branch, only when every blocking gate is green
and the commit is still the branch head. `.github/workflows/smartsched.yml` is manual-only and runs a
subset (backend, frontend, Docker build, stack smoke).

## Status

On 2026-10-15:

- Planning: Generator Studio, the solver with partial runs and per-class explanations, the calendar and
  the run report are built. The real-data figures (planner-level hard 100 and 0 violations on four
  instances, 2026-10-08) are in the [root README](../README.md#measured-on-the-real-data) and
  [docs/testing/2026-10-08-real-data-feasibility.md](../docs/testing/2026-10-08-real-data-feasibility.md).
- Bookings: CRBS parity, the reservation panel and calendar feeds are built with screens. Room
  features, find-a-room, approvals, the audit log with undo and in-app notifications are built in the
  backend; their screens are in progress.
- The CRBS superset gate run of 2026-10-15 (commit `bd0db48`): 192 rows, 172 pass, 19 declared gaps,
  1 fail (a stale Alembic-head assertion in `tests/test_wave1_migrations.py`), 0 missing.
- Planned: Phase 19 (multi-format intake, learned suggestions, from-scratch programmes, moderation);
  see the [root README](../README.md#roadmap) and [docs/ROADMAP.md](../docs/ROADMAP.md).

Live status per agent is in [docs/AGENT_STATE.md](../docs/AGENT_STATE.md) and the ledger
[docs/PROGRESS.md](../docs/PROGRESS.md). Screenshots and recordings for the root README are made from a
real-data stack with [`scripts/record/`](../scripts/record/) (`stack.sh`, `screens.mjs`,
`record-all.sh`; see [docs/recording/RECORDLY.md](../docs/recording/RECORDLY.md)).

## Links

- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md): design, domain model, solver contract, event bus
- [docs/ROADMAP.md](../docs/ROADMAP.md): phases and backlog
- [docs/DATA_ANALYSIS.md](../docs/DATA_ANALYSIS.md): workbook shapes and quirks
- [docs/RESEARCH.md](../docs/RESEARCH.md): timetabling and LLM + solver research
- [docs/CRBS_PARITY.md](../docs/CRBS_PARITY.md): classroombookings parity and deliberate differences
- [docs/design/](../docs/design/): UI specs, including [Generator Studio](../docs/design/generator-studio.md)
- [docs/AGENTS.md](../docs/AGENTS.md): agent protocol
- Component guides: [solver](backend/app/solver/README.md), [AI](backend/app/ai/README.md),
  [frontend](frontend/README.md), [deploy](deploy/README.md), [pod CI](deploy/pod-ci/README.md)
