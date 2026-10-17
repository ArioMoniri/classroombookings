# Development

Moved from the README on 2026-10-15.

```
smartsched/
  backend/    FastAPI, SQLAlchemy 2, Alembic, OR-Tools CP-SAT, Anthropic SDK; tests/fixtures holds the real workbooks
  frontend/   Next.js 16, TypeScript, Tailwind 4, TanStack Query, dnd-kit, motion; 14 message files in messages/
  deploy/     docker compose, deploy.sh, nginx, Caddy, the legacy CRBS image, pod CI
infra/aws/    the AWS pod (boto3 CLI, IAM, user data) and POD_ACTION
scripts/      dev.sh, record/ (recordings and screenshots), parity_check.py, watchdog.py, agent_state.py
docs/         architecture, roadmap, data analysis, product contracts, design specs, test reports
```

| Command | What it runs |
|---|---|
| `make -C smartsched check` | backend ruff, mypy and the fast pytest suite (including the real workbooks), frontend tsc, eslint and vitest |
| `make -C smartsched check-all` | the above plus the solver and AI gates and `deploy/validate.sh` |
| `cd smartsched/backend && make test-slow` | the heaviest real-workbook tests |
| `cd smartsched/backend && python -m tools.validate_planner` | solve Bahar week 3, Güz week 3, the Final exams and the Bahar term and check each run at planner level |
| `python3 scripts/parity_check.py` | the CRBS superset gate; writes `docs/testing/crbs-parity-report.md` (`--report PATH` to write elsewhere) |
| `E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test` | every Playwright spec against a real backend started with `smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh` |

End-to-end tests run only against a real backend. There is no mock API: without `E2E_REAL=1` every
spec skips with a pointer to the setup. The e2e backend imports the real Bahar 2026 workbooks, seeds
an administrator, solves the term and pins the booking clock inside Bahar 2026.

CI runs on the AWS pod, not on GitHub-hosted runners. A systemd timer polls the repository every two
minutes, runs one job at a time in Docker, posts a commit status per gate and shows the results at
`/ci/` on the panel ([smartsched/deploy/pod-ci/README.md](../smartsched/deploy/pod-ci/README.md)):

| Gate | What it checks |
|---|---|
| `prepare` | builds the Python CI image and pulls the Playwright image |
| `validate` | `smartsched/deploy/validate.sh` (compose, env completeness, no secrets, pinned images, nginx) |
| `backend` | ruff, mypy, pytest, the solver gate and `alembic upgrade head` |
| `infra` | tests for `infra/aws` and the pod CI itself |
| `frontend` | `npm run check` (tsc, eslint, vitest) |
| `e2e-real` | every Playwright spec against the real backend with the Bahar fixtures, then a check that the build holds no mock code |
| `parity` | the CRBS superset gate |
| `planner` | `tools/validate_planner.py` on the four real instances; any planner-level violation fails |
| `images` | `docker build` of the backend, frontend and legacy CRBS images |
| `watchdog` | the agent ledger report (not blocking) |

The pod redeploys the deploy branch only when every blocking gate is green and the commit is still
the head of that branch. `.github/workflows/smartsched.yml` is manual-only (backend, frontend, Docker
build and stack smoke jobs, without the e2e, parity and planner gates); `aws-bootstrap.yml` is the
only workflow that runs on its own, and only when `infra/aws/POD_ACTION` changes.

Configuration is through environment variables (`DATABASE_URL`, `APP_SECRET`, `JWT_SECRET`,
`PUBLIC_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ANTHROPIC_API_KEY`, `SOLVER_WORKERS`, …), listed with
comments in `smartsched/backend/.env.example` and `smartsched/deploy/.env.example` and described in
[smartsched/README.md](../smartsched/README.md). In production the backend refuses to start with a default,
short or shared secret. The Anthropic key can also be stored, encrypted, under Settings → AI.

More documentation:

| Document | Contents |
|---|---|
| [smartsched/README.md](../smartsched/README.md) | developer guide: modules, environment, make targets, CLI, API |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | design principles, domain model, solver contract, event bus, API surface |
| [docs/DATA_ANALYSIS.md](DATA_ANALYSIS.md) | the workbook shapes, column meanings and quirks |
| [docs/ROADMAP.md](ROADMAP.md) | phases, decisions and backlog |
| [docs/CRBS_PARITY.md](CRBS_PARITY.md) | classroombookings behaviour and the deliberate differences |
| [docs/product/](product) | API contracts: calendar sync, booking enhancements wave 1 |
| [docs/design/](design) | UI specs, including the Liquid Glass system and the calendar |
| [docs/universal/](universal) | universal onboarding: [Ingestion Council architecture](universal/ARCHITECTURE.md), [2026 research](universal/RESEARCH-2026.md), [Ruflo dev harness](universal/RUFLO.md) |
| [docs/testing/](testing) | test reports: real-data feasibility, real-backend end to end, CRBS parity, planner comparison |
| [docs/deploy/AWS.md](deploy/AWS.md), [docs/deploy/calendar-oauth.md](deploy/calendar-oauth.md) | the AWS pod; setting up the Google and Microsoft OAuth clients |
| [docs/AGENTS.md](AGENTS.md), [docs/PROGRESS.md](PROGRESS.md), [docs/AGENT_STATE.md](AGENT_STATE.md) | SmartSched is built by parallel Claude Code agents: their protocol, ledger and resume guide |

## Recordings and screenshots

The README's recordings and screenshots are made by `scripts/record/`; see [recording/RECORDLY.md](recording/RECORDLY.md).

## Load the real 2026 data

The planning office's workbooks for Bahar 2026, Güz 2026-27 and the 2026 finals are in
`smartsched/backend/tests/fixtures/`.

```bash
cd smartsched/backend && source .venv/bin/activate
python -m app.cli import weekly-grid   tests/fixtures/bahar_derslikler_takvimi_2026.xlsx --term 2026-BAHAR --year 2026
python -m app.cli import planning-list tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx --term 2026-BAHAR
python -m app.cli import room-master   tests/fixtures/room_master.csv
python -m app.cli solve --term 2026-BAHAR --kind COURSE --horizon TERM --time-limit 300
```

Importing a weekly grid also stores the planner's own published board as a run, so the calendar has
something to show straight away. The same importers are on the Import page. The CRBS importer reads
SQL dumps (`import crbs structure.sql data.sql`) or a live server (`import crbs --dsn mysql://…`).
Requests and room grids are read today from the office's three workbook shapes (`.xlsx`), a room
master CSV and the CRBS database. Reading requests and schedule maps from other formats is planned
in Phase 19 ([Roadmap](ROADMAP.md)).
