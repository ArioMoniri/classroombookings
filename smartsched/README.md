# SmartSched developer guide

SmartSched is an AI classroom and exam timetable optimizer that lives next to the legacy
classroombookings (CRBS) app in this repository. It imports the planning office's Excel workbooks
(course and exam request lists, weekly room grids), a room master CSV and the CRBS database. It builds
a timetable that breaks no hard rule with OR-Tools CP-SAT, or explains exactly why it cannot. The
planner refines the plan by chatting and exports it to Excel, CSV or iCal.

This guide is for developers. For the product overview and screenshots, see the
[root README](../README.md). For deployment, see [deploy/README.md](deploy/README.md).

## Architecture in brief

```
smartsched/
├── backend/     Python 3.12+, FastAPI, SQLAlchemy 2 (async), Alembic, OR-Tools CP-SAT, Anthropic SDK
│   └── app/
│       ├── main.py         app factory, routers, lifespan (dev migrations, admin seed, job recovery)
│       ├── core/           config (pydantic-settings), DB session, security (JWT, Fernet), logging
│       ├── models/         SQLAlchemy ORM          schemas/   Pydantic I/O
│       ├── api/v1/         REST routers (see "API overview")
│       ├── importers/      normalize.py + planning_list, exam_list, weekly_grid, room_master, crbs_legacy
│       ├── solver/         pure Python, no DB or HTTP: solve(SolverInput) -> SolverResult
│       ├── ai/             Claude client, strict tool catalogue, elicitation, file ingest, chat, explain
│       ├── services/       solver_bridge (DB -> SolverInput -> results), studio, precheck, diagnosis fixes
│       ├── workers/        in-process asyncio job queue (CP-SAT runs in a worker thread)
│       └── cli.py          python -m app.cli
├── frontend/    Next.js 16 App Router, TypeScript strict, Tailwind 4, shadcn/ui, TanStack, dnd-kit, zod, MSW
└── deploy/      docker compose, deploy.sh, nginx, Caddy, legacy CRBS image, validate.sh
```

Design rules that the code relies on:

- **The solver is a pure function.** `app/solver` never touches the DB. `services/solver_bridge.py`
  builds a `SolverInput` from the database and persists the `SolverResult`. The frozen contract is in
  `app/solver/model.py` and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
- **Everything is a constraint.** File-derived rules, admin settings, AI proposals and uploaded
  preferences are all `constraints` rows with `kind`, `params`, `hardness`, `weight`, `source`
  (`FILE`, `ADMIN`, `AI`, `UPLOAD`, `BUILTIN`), `nl_text` and `source_ref`.
- **Hard rules are never relaxed silently.** An infeasible run carries `Diagnosis` objects with the
  events, the rule kinds and structured fix options (`params.options`), which the run report and the
  pre-check can apply.
- **Claude never edits the timetable directly.** It proposes; the server resolves ids from the DB and
  the solver validates every change ([app/ai/README.md](backend/app/ai/README.md)).

Component guides: [solver](backend/app/solver/README.md), [AI layer](backend/app/ai/README.md),
[frontend](frontend/README.md), [deploy](deploy/README.md).

## Quick start

The fastest route is the repository script, which sets up both halves:

```bash
scripts/dev.sh --run        # from the repository root; or: make -C smartsched dev
```

It needs Python 3.12+ and Node 22+. It creates `backend/.venv`, installs the backend with
`pip install -e ".[dev]"`, runs `npm ci`, writes `backend/.env` (SQLite, admin `admin@example.com` /
`admin`) and `frontend/.env.local` (real backend), migrates, seeds the admin, and starts the backend
on :8000 and the frontend on :3000. `scripts/dev.sh --mock` (`make -C smartsched dev-mock`) runs the
frontend alone on mock data.

### Backend (`smartsched/backend`)

```bash
cd smartsched/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # then edit APP_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD
make migrate                    # alembic upgrade head (SQLite by default)
make dev                        # uvicorn --reload on http://localhost:8000, OpenAPI at /api/docs
```

On start in `dev`, a new or Alembic-managed SQLite database is migrated automatically. A database
created earlier by `create_all` (tables but no `alembic_version`) gets a warning that lists the missing
columns; delete it, or run `alembic stamp 0001 && alembic upgrade head`. In `prod` the app never
changes the schema; the container entrypoint runs `alembic upgrade head`. The admin is seeded from
`ADMIN_EMAIL` / `ADMIN_PASSWORD` only when the users table is empty.

| Target | What it runs |
|---|---|
| `make check` | `lint` + `type` + `test` |
| `make lint` | `ruff check` and `ruff format --check` (excluding `app/solver`, `app/ai` and their tests) |
| `make type` | mypy on importers, services, workers, core and the solver contract (`model.py`, `stub.py`, strict) |
| `make test` | `pytest -q --ignore=tests/solver` (API, importers on the real workbooks, studio, AI with a mocked SDK) |
| `make format` | `ruff check --fix` + `ruff format` |
| `make dev` / `make migrate` | dev server / `alembic upgrade head` |

After changing `app/models`, add a migration: `alembic revision --autogenerate -m "…"`.

### Frontend (`smartsched/frontend`)

```bash
cd smartsched/frontend
npm ci
cp .env.example .env.local      # the example sets NEXT_PUBLIC_API_MOCK=1; set 0 to use the backend
npm run dev                     # http://localhost:3000
```

| Script | What it runs |
|---|---|
| `npm run dev` / `build` / `start` | Next.js dev server / production build / serve the build |
| `npm run check` | `tsc --noEmit && eslint . && vitest run` (the quality gate) |
| `npm run test` | vitest only |
| `npm run typecheck` / `lint` | the individual gates |
| `npm run e2e` | Playwright smoke tests: production build on :3100 with the mock API |
| `npm run e2e:ui` | the same in Playwright's UI mode |

The browser never calls FastAPI directly. `src/app/api/v1/[...path]/route.ts` proxies `/api/v1/*` to
`NEXT_PUBLIC_API_URL` and attaches the JWT from the httpOnly cookie. In mock mode the same route
answers from the MSW handlers in `src/mocks`. Structure, auth flow and how to add pages are in
[frontend/README.md](frontend/README.md).

### Top-level make targets

`make -C smartsched help` lists them all. The ones used most: `dev`, `dev-mock`, `check` (backend +
frontend gates), `check-all` (plus solver and AI gates and `deploy/validate.sh`), `e2e`, `validate`,
`deploy`, `deploy-legacy`, `update`, `down`, `logs`, `status`, `watchdog`.

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
| `python -m app.cli solve --term CODE [--kind COURSE\|EXAM] [--horizon WEEK\|MONTH\|TERM] [--time-limit 60] [--solver auto\|cpsat\|stub] [--label TEXT]` | create and run a schedule run, print the result |
| `python -m app.cli seed-admin` | create the admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` if no users exist |

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
[docs/DATA_ANALYSIS.md](../docs/DATA_ANALYSIS.md).

In the Docker stack, run the same commands through the backend container:
`docker compose --env-file .env run --rm backend python -m app.cli …` (see
[deploy/README.md](deploy/README.md)).

## Environment

### Backend

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./smartsched.db` | Async SQLAlchemy URL. Production: `postgresql+psycopg://user:pass@host/db` |
| `APP_SECRET` | insecure placeholder | JWT signing key and Fernet key for encrypted settings (API keys). Change it and back it up |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | none | Admin seeded when the users table is empty |
| `ENVIRONMENT` | `dev` | `dev` / `test` / `prod`. `prod` never changes the schema on start |
| `CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | JSON list of allowed origins |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | none / `claude-opus-5-5` | Fallbacks when no key or model is stored through `/settings` |
| `SOLVER_DEFAULT_TIME_LIMIT`, `SOLVER_WORKERS` | `60`, `8` | Solver defaults, overridable per run |
| `UPLOAD_DIR` | `./uploads` | Uploaded workbooks and room photos (only `/uploads/rooms` is served publicly) |
| `JWT_EXPIRE_MINUTES` | `720` | Token lifetime |
| `SMARTSCHED_SLOW` | unset | `1` enables the slow solver scale tests |

The Claude API key is normally set in the app: **Settings → AI**, paste the key, save, **Test key**
(`POST /api/v1/settings/test-ai`). It is stored encrypted and returned only masked. The default model
is `claude-opus-5-5`; `claude-sonnet-5-5` and `claude-haiku-5-5` are selectable.

### Frontend

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI base URL used by the `/api/v1` proxy |
| `NEXT_PUBLIC_API_MOCK` | unset | `1` serves the MSW mock API (any e-mail with password `admin` logs in) |
| `AUTH_SECRET` | none | cookie/session secret |
| `MOCK_SOLVE_MS` | `5000` | duration of a mock solver run |

Deployment variables (`UVICORN_WORKERS`, `RUN_MIGRATIONS`, `SEED_ADMIN`, limits, legacy, TLS) are in
`deploy/.env.example`.

## API overview

All routes are under `/api/v1`, JSON, with a JWT bearer token (`POST /auth/login`). The interactive
OpenAPI is at **`/api/docs`** (schema at `/api/openapi.json`).

| Group | Routes |
|---|---|
| Health | `GET /health`, `GET /metrics` |
| Auth and users | `POST /auth/login`, `GET /auth/me`; `/users` CRUD, `POST /users/{id}/password` |
| Settings | `GET/PUT /settings` (API key write-only, masked on read), `POST /settings/test-ai` |
| Terms | `/terms` CRUD, `GET/PUT /terms/{id}/weeks` |
| Rooms | `/buildings`, `/rooms` CRUD, `POST /rooms/{id}/photo` |
| Reference data | `GET /faculties`, `/programs`, `/instructors`, `/courses`, `/sections` |
| Requests | `GET/PUT /requests/meetings[/{id}]`, `POST /requests/meetings/{id}/check-room`, `GET/PUT /requests/exams`, `GET /requests/stats` |
| Imports | `POST /imports/planning-list`, `/exam-list`, `/weekly-grid`, `/crbs` (multipart, `202 {id}`); `GET /imports`, `/imports/{id}`, `/imports/{id}/file` |
| Constraints | `GET /constraints/kinds`, `/constraints` CRUD |
| Runs | `POST /runs` (`202`), `GET /runs[/{id}]`, `DELETE /runs/{id}`, `POST /runs/{id}/activate`, `GET /runs/{id}/events` (SSE progress), `/assignments`, `/grid?week=`, `/summary`, `/export?format=xlsx\|csv\|ics\|crbs` |
| Edits and fixes | `POST /runs/{id}/assignments/{aid}/move`, `/lock`; `POST /runs/{id}/diagnoses/{idx}/apply` |
| AI | `POST /terms/{id}/elicit`, `/elicit/accept`, `/preferences/upload`; `GET/POST /runs/{id}/chat`, `POST /runs/{id}/chat/apply`, `POST /runs/{id}/explain`; `GET /ai/catalog` |
| Generator Studio | `GET /studio/meta`; `GET/PUT /terms/{id}/studio` (draft, `If-Match`), `/studio/summary`, `/studio/classes`, `/studio/rules`, `POST /terms/{id}/studio/precheck`, `/precheck/fix`, `/proposals/accept`, `/preferences/mapping`, `/generate`; `PUT /studio/meetings/bulk`, `POST /studio/meetings[/{id}]/revert`, `POST /studio/constraints/preview`, `/copy` |
| Presets | `/presets` CRUD, `POST /presets/{id}/apply` |
| Dashboard | `GET /dashboard` |
| Ingestion Council (universal onboarding) | `POST /council/jobs` (multipart, any files, `202`), `GET /council/jobs[/{id}]`, `GET /council/jobs/{id}/events` (SSE), `GET/POST /council/jobs/{id}/review`, `POST /council/jobs/{id}/commit`, `/rerun`, `GET /council/jobs/{id}/records`, `/artifacts`; see [docs/universal/ARCHITECTURE.md](../docs/universal/ARCHITECTURE.md) |

A typical flow: log in; import the weekly grid (or room master), then the planning list; review
`GET /requests/meetings?term_id=…&status=NEEDS_REVIEW`; `POST /runs {term_id, kind: COURSE|EXAM, horizon:
WEEK|MONTH|TERM, horizon_params, params}` where `params.solver` is `auto` (CP-SAT, falling back to the
greedy stub), `cpsat` or `stub`; follow `GET /runs/{id}` or the SSE stream; read the grid and
diagnoses; move, lock, apply fixes or chat; `POST /runs/{id}/activate` to publish. The `crbs` export
currently returns the generic CSV (mapping to the CRBS booking format is in the backlog).

## Jobs and runs

Solver runs and imports execute in an in-process asyncio queue inside the backend
(`app/workers/queue.py`); the CP-SAT call itself runs in a worker thread, so the API stays
responsive. Status and progress are written to the `schedule_runs` / `import_jobs` rows. Jobs left
`QUEUED` or `RUNNING` by a previous process are marked failed on start. A dedicated worker service is
planned before running several replicas ([deploy/README.md](deploy/README.md), "Scaling").

## Tests

| Command | Scope |
|---|---|
| `make -C smartsched check` | backend `make check` + frontend `npm run check` |
| `make -C smartsched check-all` | `check` + solver gate (`ruff`, strict `mypy`, `pytest tests/solver`) + AI lint + `deploy/validate.sh` |
| `cd backend && python -m pytest tests/solver -q` | solver: feasible, infeasible and soft-weight cases per constraint kind, diagnosis, repair |
| `cd backend && SMARTSCHED_SLOW=1 python -m pytest tests/solver -q` | adds the 1 300-event / 60-room / 14-week course and 400-exam scale tests |
| `cd backend && python -m pytest tests/ai -q` | AI layer with a scripted fake SDK; `test_live_smoke.py` runs only when `ANTHROPIC_API_KEY` is set |
| `cd frontend && npm run e2e` | Playwright smoke on the mock API |
| `cd frontend && E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test` | Playwright against a running backend ([setup](../docs/testing/2026-10-08-real-backend-e2e.md)) |

Policy ([docs/ROADMAP.md](../docs/ROADMAP.md), "TDD policy"): every importer function starts from a
failing test on a real fixture row; every solver constraint has a feasible, an infeasible and a
soft-weight test; API routes are tested with `httpx` against SQLite. CI
(`.github/workflows/smartsched.yml`) runs the gates plus migrations on SQLite and Postgres 16, Docker
builds and a compose smoke test.

## Status

The Generator Studio (`/generate`, phase 8) has its backend in place; the frontend screen is **in
progress**. Real-data feasibility (phase 9) is **in progress**: on the 2026 Bahar workbooks a CP-SAT run
is currently reported infeasible with a full diagnosis (fixed-time instructor and cohort clashes,
rooms without capacity or tags, locked rooms smaller than the enrolment), see the
[real-backend e2e report](../docs/testing/2026-10-08-real-backend-e2e.md). Live status per agent is in
[docs/PROGRESS.md](../docs/PROGRESS.md).

## Links

- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md): design, domain model, solver contract
- [docs/ROADMAP.md](../docs/ROADMAP.md): phases and backlog
- [docs/DATA_ANALYSIS.md](../docs/DATA_ANALYSIS.md): workbook shapes and quirks
- [docs/RESEARCH.md](../docs/RESEARCH.md): timetabling and LLM + solver research
- [docs/design/](../docs/design/): UI specs, including [Generator Studio](../docs/design/generator-studio.md)
- [docs/AGENTS.md](../docs/AGENTS.md): agent protocol
- Component guides: [solver](backend/app/solver/README.md), [AI](backend/app/ai/README.md),
  [frontend](frontend/README.md), [deploy](deploy/README.md)
