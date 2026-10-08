<h1 align="center">SmartSched</h1>

<p align="center">
  An AI timetable optimizer and scheduler for university classrooms and exams, built alongside classroombookings.
</p>

<p align="center">
  <a href="https://www.gnu.org/licenses/agpl-3.0.html"><img alt="License: AGPLv3" src="https://img.shields.io/static/v1?label=License&message=AGPLv3&color=3DA639&style=flat-square"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white">
  <img alt="OR-Tools CP-SAT" src="https://img.shields.io/badge/OR--Tools-CP--SAT-4285F4?style=flat-square&logo=google&logoColor=white">
  <img alt="Claude API" src="https://img.shields.io/badge/Claude-API-D97757?style=flat-square&logo=anthropic&logoColor=white">
  <a href="https://github.com/ArioMoniri/classroombookings/actions/workflows/smartsched.yml"><img alt="SmartSched CI" src="https://github.com/ArioMoniri/classroombookings/actions/workflows/smartsched.yml/badge.svg"></a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/hero-solver-dark.gif">
    <img alt="Animation: course requests flow into the CP-SAT solver and come out as a conflict-free room-by-period timetable" src="docs/images/lottie/hero-solver-light.gif" width="720">
  </picture>
</p>

SmartSched replaces a hand-maintained Excel planning process. A planner imports the term's requests,
presses Generate, and gets a timetable that breaks no hard rule, or a list of exactly what is
impossible and how to fix it. The planner then refines the result by chatting in Turkish or English.

SmartSched is a separate application in [`smartsched/`](smartsched/). The legacy classroombookings PHP
app in this repository is unchanged (see [Legacy classroombookings](#legacy-classroombookings)).

## What it does

- **Imports the real planning files.** Course planning lists, exam planning lists and weekly room
  grids from the planning office's Excel workbooks, a room master CSV, and the legacy CRBS database
  (SQL dumps or a live MySQL DSN). Every import returns a report of what was parsed, skipped and why.
- **Generates week, month, term and exam timetables** with OR-Tools CP-SAT. Hard rules (capacity, no
  double-booked rooms, no cohort or instructor clashes, fixed times, room tags) are never relaxed
  silently. When a plan is impossible, the run report names the events and rules in conflict and
  offers fixes you can apply in one click.
- **Takes rules in plain language.** Write preferences in Turkish or English, or upload preference
  files (Excel, CSV, Word, PDF, text). Claude turns them into typed, reviewable rules; nothing is
  applied until you accept it.
- **Refines by chat.** Ask for a move, a swap or a new rule on a finished run. Every proposed change is
  checked by the solver before it becomes a new child run.
- **Drag-and-drop timetable.** A room × period grid with a live conflict preview, a week view, a
  mobile agenda, and exports to Excel, CSV and iCal.
- **One-command deploy.** `smartsched/deploy/deploy.sh` brings up PostgreSQL, the FastAPI backend, the
  Next.js frontend and nginx with generated secrets.

> **Status.** The Generator Studio screen (`/generate`) and the real-data feasibility work are
> **in progress**. On the real 2026 Bahar workbooks a run is currently reported infeasible with a full
> diagnosis (input clashes and room data gaps), not yet a finished timetable. See [Status](#status).

## Screenshot tour

**Overview.** SmartSched at a glance.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/overview-dark.png">
  <img alt="SmartSched overview" src="docs/images/screens/overview-light.png" width="960">
</picture>

**Dashboard.** Sections, requests that need review, recent runs and room utilisation by building and day.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/dashboard-dark.png">
  <img alt="Dashboard with KPI tiles, recent runs and a building by day utilisation heatmap" src="docs/images/screens/dashboard-light.png" width="960">
</picture>

**Timetable.** Rooms down the side, the 18 daily periods across the top. Drag an event to another room
or period; the grid shows conflicts before you drop.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/timetable-day-dark.png">
  <img alt="Day view of the timetable grid: rooms by periods with coloured events" src="docs/images/screens/timetable-day-light.png" width="960">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/timetable-drag-dark.png">
  <img alt="An event being dragged to a new room, with the live conflict preview" src="docs/images/screens/timetable-drag-light.png" width="960">
</picture>

**Run report.** Hard and soft scores, the soft-rule breakdown, and diagnosis cards with fixes.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-report-dark.png">
  <img alt="Run report with score rings and the soft-rule breakdown" src="docs/images/screens/run-report-light.png" width="960">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-diagnoses-dark.png">
  <img alt="Diagnosis cards that explain why events cannot be placed and offer fixes" src="docs/images/screens/run-diagnoses-light.png" width="960">
</picture>

**Chat.** Ask for a change; review the proposed diff; apply it as a new run.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/chat-panel-dark.png">
  <img alt="Chat panel next to the timetable with a proposed change waiting for review" src="docs/images/screens/chat-panel-light.png" width="960">
</picture>

**Generator Studio** (in progress). One guided screen to shape a run: pick the scope, include or leave out classes, add rules in your own words, from templates or from uploaded preference files, then fix problems before you press Generate.

<table>
  <tr>
    <td><picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-scope-dark.png">
  <img alt="Studio scope step with a plain-language summary of what will be planned" src="docs/images/screens/studio-scope-light.png" width="480">
</picture></td>
    <td><picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-classes-dark.png">
  <img alt="Studio class list with include and exclude toggles and changed-field badges" src="docs/images/screens/studio-classes-light.png" width="480">
</picture></td>
  </tr>
  <tr>
    <td><picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-rules-dark.png">
  <img alt="Studio rule cards with Must or Try to, importance, and source chips" src="docs/images/screens/studio-rules-light.png" width="480">
</picture></td>
    <td><picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-precheck-dark.png">
  <img alt="Studio pre-check with readiness meter and one-click fixes" src="docs/images/screens/studio-precheck-light.png" width="480">
</picture></td>
  </tr>
</table>

<details>
<summary><strong>More screenshots</strong></summary>

<br>

**Import report.** Rows parsed, skipped (with reasons) and warnings grouped by pattern.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/import-report-dark.png">
  <img alt="Import report after uploading a planning workbook" src="docs/images/screens/import-report-light.png" width="960">
</picture>

**Requests inbox.** Review parsed meeting and exam requests, fix the ones that need a look, lock rooms.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/requests-dark.png">
  <img alt="Requests inbox table with status filters" src="docs/images/screens/requests-light.png" width="960">
</picture>

**Rooms.** The room master: capacity, exam capacity, tags and building.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/rooms-dark.png">
  <img alt="Rooms page with capacities and tags" src="docs/images/screens/rooms-light.png" width="960">
</picture>

**Settings, AI.** Store the Anthropic API key (encrypted), test it, and pick the model.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/settings-ai-dark.png">
  <img alt="AI settings tab with the masked API key, Test key button and model picker" src="docs/images/screens/settings-ai-light.png" width="960">
</picture>

**Command palette.** Press <kbd>⌘</kbd> <kbd>K</kbd> (or <kbd>Ctrl</kbd> <kbd>K</kbd>) to jump anywhere.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/command-palette-dark.png">
  <img alt="Command palette open over the dashboard" src="docs/images/screens/command-palette-light.png" width="960">
</picture>

**Mobile.** Dashboard, the timetable as an agenda, and the navigation drawer.

<table>
  <tr>
    <td align="center">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-dashboard-dark.png">
        <img alt="Dashboard on a phone" src="docs/images/screens/mobile-dashboard-light.png" width="240">
      </picture>
      <br><sub>Dashboard</sub>
    </td>
    <td align="center">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-agenda-dark.png">
        <img alt="Timetable agenda view on a phone" src="docs/images/screens/mobile-agenda-light.png" width="240">
      </picture>
      <br><sub>Agenda</sub>
    </td>
    <td align="center">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-drawer-dark.png">
        <img alt="Navigation drawer on a phone" src="docs/images/screens/mobile-drawer-light.png" width="240">
      </picture>
      <br><sub>Drawer</sub>
    </td>
  </tr>
</table>

</details>

## How the optimizer works

<table>
  <tr>
    <td align="center" width="33%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/nl-to-rules-dark.gif">
        <img alt="Animation: a sentence in Turkish becomes a typed rule card" src="docs/images/lottie/nl-to-rules-light.gif" width="360">
      </picture>
      <br><sub><b>Words to rules.</b> A sentence becomes a typed rule you can review, edit or reject.</sub>
    </td>
    <td align="center" width="33%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/file-to-rules-dark.gif">
        <img alt="Animation: rows of an uploaded preference file become rule cards linked to their source rows" src="docs/images/lottie/file-to-rules-light.gif" width="360">
      </picture>
      <br><sub><b>Files to rules.</b> Each rule keeps a link to the file row it came from.</sub>
    </td>
    <td align="center" width="33%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/precheck-fix-dark.gif">
        <img alt="Animation: the pre-check finds a problem and a suggested fix resolves it" src="docs/images/lottie/precheck-fix-light.gif" width="360">
      </picture>
      <br><sub><b>Pre-check and fix.</b> Problems are found before solving, with fixes to apply.</sub>
    </td>
  </tr>
</table>

The pipeline:

1. **Import.** Workbooks, the room master and the CRBS database are parsed into terms, weeks, rooms,
   sections, meeting requests, exam requests and pre-occupied blocks.
2. **Normalise.** Turkish day names, dotted times, comma decimals, room spellings (`A 101`, `A101`,
   `B Blok Bilg. Lab.`) and multi-value cells are mapped to canonical values
   ([docs/DATA_ANALYSIS.md](docs/DATA_ANALYSIS.md)).
3. **Rules.** File-derived rules, admin settings and AI-extracted preferences all become one kind of
   object: a constraint with a kind, parameters, hard or soft, a weight, a source and the original text.
4. **CP-SAT.** A static checker runs first. The model uses optional intervals with one `NoOverlap2D`
   per room (weeks on the second axis), a greedy warm start, and a weighted soft objective.
5. **Validate.** Scores are recomputed in pure Python from the finished assignments, so the solver,
   manual moves and AI edits are all judged by the same rules.
6. **Explain.** If the plan is infeasible, the diagnoser finds a small conflicting set (assumption
   cores, then deletion shrinking) and a slack relaxation explains every unplaced event, with fixes.
7. **Chat edits.** Claude proposes a diff (moves, swaps, locks, rule changes). The server re-validates
   it, then either patches the run or re-solves the neighbourhood with a stability objective.

Claude is a translator and narrator, never the planner. Details:
[solver README](smartsched/backend/app/solver/README.md), [AI README](smartsched/backend/app/ai/README.md),
[research report](docs/RESEARCH.md).

```mermaid
flowchart LR
    subgraph Sources
        XL["Excel workbooks<br/>planning lists, exam lists, weekly grids"]
        RM["Room master CSV"]
        CRBS["Legacy CRBS<br/>SQL dump or MySQL"]
        PREF["Preference files and<br/>plain-language rules"]
    end

    subgraph Frontend["Next.js frontend"]
        UI["Admin panel<br/>dashboard, import, requests, rooms,<br/>Generator Studio, timetable, chat, settings"]
        PX["/api/v1 proxy<br/>httpOnly cookie to JWT"]
    end

    subgraph Backend["FastAPI backend"]
        IMP["Importers + normalise"]
        API["REST API /api/v1"]
        Q["In-process job queue"]
        BR["Solver bridge<br/>DB to SolverInput"]
        SOL["CP-SAT solver<br/>check, solve, diagnose, repair"]
        AI["AI layer<br/>strict tool use"]
    end

    DB[("PostgreSQL<br/>SQLite in dev")]
    CL["Claude API"]

    XL --> IMP
    RM --> IMP
    CRBS --> IMP
    PREF --> AI
    UI --> PX --> API
    API --> IMP
    API --> AI
    API --> Q --> BR --> SOL
    AI --> CL
    AI -- "proposals validated by" --> SOL
    IMP --> DB
    BR --> DB
    API --> DB
```

## Quick start

### One-command deploy (Docker)

Requires Docker Engine 24+ with the Compose v2 plugin. Nothing else is needed on the host.

```bash
cd smartsched/deploy
./deploy.sh            # creates .env with random secrets, builds, starts, waits for /api/v1/health
# -> SmartSched is up: http://localhost:8080   admin: ADMIN_EMAIL / ADMIN_PASSWORD from .env
```

| Flag | What it does |
|---|---|
| *(none)* | create `.env` if missing, build, start, wait for health, print the URL and where the admin credentials are |
| `--legacy` | also run the legacy CRBS app (PHP 8.3 + MySQL 8.4) on `127.0.0.1:8081` for live imports |
| `--tls` | add the Caddy HTTPS edge (set `TLS_DOMAIN` and `ACME_EMAIL` in `.env`) |
| `--update` | `git pull --ff-only`, rebuild, restart; migrations run on start. Add `--no-pull` to skip git |
| `--no-build` | start the existing images without building |
| `--logs` / `--status` | follow logs / show container status and health |
| `--down` | stop the stack (data kept). `--down --volumes` deletes all data after a typed confirmation |

Flags combine, for example `./deploy.sh --update --legacy --tls`. The same actions are available as
`make -C smartsched deploy`, `deploy-legacy`, `update`, `down`, `logs` and `status`. TLS, backups,
scaling and sizing are covered in [smartsched/deploy/README.md](smartsched/deploy/README.md).

### Local development (no Docker)

Requires Python 3.12+ and Node 22+.

```bash
scripts/dev.sh --run          # or: make -C smartsched dev
```

This creates a Python venv in `smartsched/backend/.venv`, runs `pip install -e ".[dev]"` and `npm ci`,
writes `.env` files, migrates a SQLite database, seeds an admin (your `git config user.email`, or `DEV_ADMIN_EMAIL`, with a random password printed once,
or `DEV_ADMIN_PASSWORD`), and starts the backend on <http://localhost:8000> (OpenAPI at `/api/docs` in dev only)
and the frontend on <http://localhost:3000>.

`scripts/dev.sh` alone only bootstraps. There is no mock mode: the frontend always talks to the real backend.

### Import the sample data

The real 2026 workbooks are in `smartsched/backend/tests/fixtures/`. With the dev venv active:

```bash
cd smartsched/backend && source .venv/bin/activate

python -m app.cli import room-master   tests/fixtures/room_master.csv
python -m app.cli import weekly-grid   tests/fixtures/bahar_derslikler_takvimi_2026.xlsx --term 2026-BAHAR --year 2026
python -m app.cli import planning-list tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx --term 2026-BAHAR
python -m app.cli import exam-list     tests/fixtures/final_planlama_listesi_2026_v2.xlsx --term 2026-FINAL
python -m app.cli import weekly-grid   tests/fixtures/final_derslikler_takvimi_2026_v2.xlsx --term 2026-FINAL --year 2026

python -m app.cli solve --term 2026-BAHAR --kind COURSE --horizon TERM --solver cpsat
# On Bahar this currently returns INFEASIBLE with a full diagnosis (real-data feasibility work is in progress).
```

Importing a weekly grid also stores the planner's published board as a feasible run, so the timetable
has something to show at once. The CRBS importer takes SQL dumps (`import crbs structure.sql data.sql`)
or a live server (`import crbs --dsn mysql://user:pass@host/crbs`, needs `pymysql`). The same
importers are on the Import page and at `POST /api/v1/imports/*`. In the Docker stack, run the CLI
through `docker compose run --rm backend python -m app.cli …` as described in the deploy README.

## Configuration

Backend settings come from the environment or `smartsched/backend/.env`; the Docker stack reads
`smartsched/deploy/.env`. The important ones:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./smartsched.db` | Async SQLAlchemy URL. Docker derives a `postgresql+psycopg://…` URL when empty |
| `APP_SECRET` | insecure placeholder | JWT signing key and the Fernet key that encrypts stored API keys. Back it up with the DB |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | none | Admin created on first start, only when the users table is empty |
| `ENVIRONMENT` | `dev` | `dev` / `test` / `prod`. Dev migrates SQLite on start; prod relies on the entrypoint's `alembic upgrade head` |
| `CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | JSON list of allowed origins |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | none / `claude-opus-5-5` | Server-wide fallback when no key is stored in Settings |
| `SOLVER_DEFAULT_TIME_LIMIT`, `SOLVER_WORKERS` | `60`, `8` | Solver defaults, overridable per run |
| `UPLOAD_DIR` | `./uploads` | Uploaded workbooks and room photos |
| `JWT_EXPIRE_MINUTES` | `720` | Session lifetime |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Where the Next.js server reaches FastAPI |
| `NEXT_PUBLIC_API_MOCK` | unset | `1` serves mock data instead of the backend (inlined at build time) |

Deployment-only keys (`UVICORN_WORKERS`, `RUN_MIGRATIONS`, `SEED_ADMIN`, resource limits, legacy and
TLS settings) are documented inline in `smartsched/deploy/.env.example`.

**Claude API key.** Sign in as admin and open **Settings → AI**. Paste the Anthropic API key, save, and
press **Test key**. The key is stored encrypted with `APP_SECRET`, shown only as its last characters,
and never logged. The default model is `claude-opus-5-5`; `claude-sonnet-5-5` (lower cost) and
`claude-haiku-5-5` can be selected in the same tab. Import, solving, the timetable and manual edits
work without a key; only plain-language rules, file extraction, chat and model-written explanations
need one.

## Project layout

```
.
├── smartsched/                 SmartSched (new app)
│   ├── backend/                FastAPI, SQLAlchemy 2, Alembic, OR-Tools CP-SAT, Anthropic SDK
│   │   ├── app/
│   │   │   ├── api/v1/         REST routers
│   │   │   ├── importers/      normalise + planning list, exam list, weekly grid, room master, CRBS
│   │   │   ├── solver/         pure-Python CP-SAT model, diagnosis, repair (no DB, no HTTP)
│   │   │   ├── ai/             Claude client, strict tool catalogue, elicitation, ingest, chat
│   │   │   ├── services/       solver bridge, studio, pre-check, settings, exports
│   │   │   ├── models/ schemas/ core/ workers/
│   │   │   └── cli.py          python -m app.cli
│   │   ├── alembic/            migrations
│   │   └── tests/              pytest; fixtures/ holds the real workbooks
│   ├── frontend/               Next.js 16, TypeScript, Tailwind 4, shadcn/ui, TanStack, dnd-kit, MSW
│   ├── deploy/                 docker compose, deploy.sh, nginx, Caddy, legacy CRBS image, validate.sh
│   └── Makefile                make -C smartsched help
├── docs/                       architecture, roadmap, research, data analysis, design specs, testing
├── scripts/                    dev.sh, watchdog.py
├── .claude/agents/             subagent definitions
├── .github/workflows/          smartsched.yml (CI)
└── crbs-core/, index.php, assets/, local/, uploads/   legacy classroombookings (unchanged)
```

## Documentation

| Document | What is in it |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design principles, domain model, solver contract, API surface |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Goal, definition of done, phases, backlog |
| [docs/DATA_ANALYSIS.md](docs/DATA_ANALYSIS.md) | The three workbook shapes, column meanings, quirks, room master, time grid |
| [docs/RESEARCH.md](docs/RESEARCH.md) | State of the art in course, exam and room timetabling; LLM + solver hybrids |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent roles, watchdog, worktrees, hand-off format |
| [docs/PROGRESS.md](docs/PROGRESS.md) | Append-only progress ledger |
| [docs/design/](docs/design/) | UI specs: tokens, navigation shell, dashboard, timetable grid, run report, import wizard, requests inbox, rooms, settings, generate and chat, [Generator Studio](docs/design/generator-studio.md) |
| [docs/testing/](docs/testing/) | Test reports, such as the [real-backend end-to-end run](docs/testing/2026-10-08-real-backend-e2e.md) |
| [smartsched/README.md](smartsched/README.md) | Developer guide: backend, frontend, CLI, environment, API |
| [smartsched/backend/app/solver/README.md](smartsched/backend/app/solver/README.md) | Solver modelling, objective, diagnosis, repair, adding a constraint kind |
| [smartsched/backend/app/ai/README.md](smartsched/backend/app/ai/README.md) | AI flow, safety rules, adding a tool |
| [smartsched/frontend/README.md](smartsched/frontend/README.md) | Frontend scripts, structure, auth, adding pages and components |
| [smartsched/deploy/README.md](smartsched/deploy/README.md) | Services, routing, configuration, scaling, sizing, backups, TLS, troubleshooting |

## Testing and quality gates

| Command | What it runs |
|---|---|
| `make -C smartsched check` | backend `make check` (ruff, ruff format, mypy, pytest including the real fixture workbooks) and frontend `npm run check` |
| `make -C smartsched check-all` | `check` plus the solver and AI gates and `deploy/validate.sh` (what CI runs, minus Docker builds) |
| `cd smartsched/frontend && npm run check` | `tsc --noEmit`, `eslint`, `vitest` |
| `cd smartsched/frontend && npm run e2e` | Playwright smoke tests against the mock API (production build on :3100) |
| `E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test` | Playwright against a running backend ([setup](docs/testing/2026-10-08-real-backend-e2e.md)) |
| `cd smartsched/backend && python -m pytest tests/solver -q` | solver tests; `SMARTSCHED_SLOW=1` adds the 1 300-event and exam scale tests |
| `make -C smartsched validate` | static checks of the deploy files (no Docker daemon needed) |

CI ([`.github/workflows/smartsched.yml`](.github/workflows/smartsched.yml)) runs the backend gate with
migrations on SQLite and Postgres 16, the frontend gate with Playwright, Docker image builds, a full
compose smoke test and the agent watchdog report.

## Roadmap

The full plan and backlog are in [docs/ROADMAP.md](docs/ROADMAP.md). Highlights:

- Finish the Generator Studio: one guided screen with five steps (scope, classes, rules, pre-check,
  generate), where every input becomes a visible, editable rule card.
- Real-data feasibility: a room-only mode that reports fixed-time instructor and cohort clashes as input
  warnings, a "trust locked rooms" switch, shared rooms for split exams, and keeping the partial
  placement of an infeasible run so the grid is not empty.
- Live import from the university panel (credentials pending).
- Dedicated solver workers (RQ or Celery on Redis) before running several backend replicas.
- Scenario comparison, iCal feeds per room, instructor or programme, invigilator assignment, SSO.

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 Foundations | data analysis, architecture, roadmap, research, agent protocol | done |
| 1 Backend + importers | FastAPI, models, Alembic, importers for all workbook shapes + CRBS + room master | done |
| 2 Solver | CP-SAT core, constraint catalogue, diagnosis, LNS repair, benchmarks | done on synthetic instances (1 300 events, 60 rooms, 14 weeks feasible in about 100 s); real Bahar data: see phase 9 |
| 3 AI layer | API key settings, rule elicitation, preference-file ingestion, chat edits, explanations | done (mocked-SDK tests; live smoke test runs only with a key) |
| 4 Frontend | admin panel, timetable grid with drag and drop, run report, chat, TR/EN, dark mode | done |
| 5 Deploy & CI | compose stack, `deploy.sh`, nginx/Caddy, CI workflow, `dev.sh` | done |
| 6 Review & test | integration with the real API, real-backend e2e, reviewers, user testing | in progress (integration and real-backend e2e done) |
| 7 Live import | connector to the university panel | not started |
| 8 Generator Studio | guided run builder: classes, rules in words or files, presets, pre-check | in progress (backend done, frontend being built) |
| 9 Real-data feasibility | importer fixes, room-only mode, locked-room trust, partial output | in progress |

Live status of every agent is in [docs/PROGRESS.md](docs/PROGRESS.md).

## Built with parallel agents

SmartSched was built by a team of Claude Code subagents working in parallel in disjoint directories:
backend, solver, AI, frontend, design, devops, a strict reviewer and a user tester. Each agent has a
definition in [`.claude/agents/`](.claude/agents/), writes progress to the
[ledger](docs/PROGRESS.md), and ends with a fixed hand-off report. The roles, scope fences, watchdog and
worktree rules are in [docs/AGENTS.md](docs/AGENTS.md).

---

## Legacy classroombookings

This repository is a fork of classroombookings. The upstream app below is unchanged and still lives at
the repository root (`crbs-core/`, `index.php`, `assets/`). SmartSched imports its database but does not
modify it. `./deploy.sh --legacy` can run it next to SmartSched.

### classroombookings - open source room booking system for schools.

By Craig A Rodway.

[![License: AGPLv3](https://img.shields.io/static/v1?label=License&message=AGPLv3&color=3DA639&style=flat-square)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Twitter Follow](https://img.shields.io/twitter/follow/crbsapp.svg?style=social)](https://twitter.com/crbsapp)

This is a web-based room booking system for schools and is designed to be as easy to use as possible. Set up your bookable rooms, day schedule and timetable for the year. Add user accounts, and allow them to make and manage bookings from anywhere.

It is available to [download and install yourself](https://www.classroombookings.com/self-host/) or there is a great value [hosted service](https://www.classroombookings.com/pricing/).

It is web-based - PHP and MySQL - and currently uses the [CodeIgniter 3](https://codeigniter.com/) framework.

#### Documentation
For installation instructions and configuration guide, please [read the documentation pages](https://www.classroombookings.com/docs/self-hosted/).

#### Bug Reports & Feature Requests
Please check out [GitHub Issues](https://github.com/craigrodway/classroombookings/issues) to view existing issues or open a new bug report.

#### Security
To report any security issues, please email craig@classroombookings.com instead of using the issue tracker.

#### Credits

This project makes use of several third parties, some of which are listed below.

- [CodeIgniter](https://codeigniter.com/) (MIT)
- [Unpoly](https://unpoly.com/) (MIT)
- [FamFamFam Silk Icons](http://www.famfamfam.com/lab/icons/silk/) ([CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), Unmodified)

## Licence

This repository is licensed under the
[GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0.html). See
[LICENSE.txt](LICENSE.txt).
