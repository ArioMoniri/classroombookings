# SmartSched

AI classroom optimizer & scheduler that lives next to the legacy CRBS app. It imports the planning
office's Excel workbooks (course/exam request lists, weekly room grids) and the CRBS database,
builds a 100 %-hard-feasible timetable with OR-Tools CP-SAT (or explains exactly why it cannot),
lets the planner refine it by chatting, and exports weekly boards / iCal / CSV.

See `docs/ARCHITECTURE.md` for the design, `docs/DATA_ANALYSIS.md` for the workbook quirks the
importers handle, and `docs/ROADMAP.md` for phases.

## Backend quickstart (`smartsched/backend`)

Requirements: Python 3.12+, the packages in `pyproject.toml` (`pip install -e ".[dev]"`).

```bash
cd smartsched/backend
cp .env.example .env            # or export the variables below
alembic upgrade head            # create the schema (SQLite by default)
make dev                        # uvicorn on http://localhost:8000, docs at /api/docs
```

On first start the app seeds an admin user from `ADMIN_EMAIL` / `ADMIN_PASSWORD` when the users
table is empty (in `dev`/`test` it also creates missing tables automatically).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./smartsched.db` | Async SQLAlchemy URL; use `postgresql+psycopg://user:pass@host/db` in production |
| `APP_SECRET` | *(insecure default)* | JWT signing key **and** Fernet key for encrypted settings (API keys). Change it. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | – | Seed admin on first start |
| `ENVIRONMENT` | `dev` | `dev` / `test` / `prod` (prod never auto-creates tables) |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON list of allowed origins |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | – / `claude-sonnet-5-5` | Fallbacks when no key is stored through `/settings` |
| `SOLVER_DEFAULT_TIME_LIMIT`, `SOLVER_WORKERS` | `60`, `8` | Solver defaults (overridable per run) |
| `UPLOAD_DIR` | `./uploads` | Uploaded workbooks, room photos (served under `/uploads`) |
| `JWT_EXPIRE_MINUTES` | `720` | Token lifetime |

### Importer CLI

```bash
python -m app.cli import planning-list "Bahar Derslik Planlama Listesi v5.xlsx" --term 2026-BAHAR
python -m app.cli import exam-list     "2026 Final Planlama Listesi v2.xlsx"  --term 2026-FINAL
python -m app.cli import weekly-grid   "2026 bahar derslikler takvimi.xlsx"   --term 2026-BAHAR --year 2026
python -m app.cli import weekly-grid   "2026 final derslikler takvimi v2.xlsx" --term 2026-FINAL --year 2026
python -m app.cli import crbs structure.sql data.sql          # SQL dumps (MySQL → SQLite adapter)
python -m app.cli import crbs --dsn mysql://user:pass@host/crbs   # live server (pip install pymysql)
python -m app.cli solve --term 2026-BAHAR --kind COURSE --horizon TERM
python -m app.cli seed-admin
```

Every importer prints a typed `ImportReport` (rows total/imported/skipped with reasons, warnings
grouped by pattern, created/updated counts per entity). Re-importing the same file updates rows in
place; rows missing from the new file are **archived**, never deleted.

The same importers are exposed as multipart endpoints: `POST /api/v1/imports/planning-list`,
`/exam-list`, `/weekly-grid`, `/crbs` (file(s) or `dsn` form field) → `202 {id}`; poll
`GET /api/v1/imports/{id}` for status and the report.

### Typical API flow

1. `POST /api/v1/auth/login` → bearer token.
2. Import the weekly grid first (room master with capacities), then the planning list for the term.
3. Review `GET /api/v1/requests/meetings?term_id=…&status=NEEDS_REVIEW`; `PUT` fixes;
   `POST /requests/meetings/{id}/check-room {room_ids}` shows conflicts against blocks and the active run.
4. `POST /api/v1/runs {term_id, kind: COURSE|EXAM, horizon: WEEK|MONTH|TERM, horizon_params, params}`
   → `202 {run_id}`; `params.solver` = `auto` (CP-SAT, falls back to the greedy stub) | `cpsat` | `stub`.
   Progress: `GET /runs/{id}` (`stats.progress`, `stats.phase`) or SSE `GET /runs/{id}/events`.
5. `GET /runs/{id}/grid?week=3`, `/assignments`, `/summary`, `/export?format=xlsx|csv|ics`;
   `POST /runs/{id}/assignments/{aid}/move`, `/lock`; `POST /runs/{id}/activate` publishes the run.
6. `GET /api/v1/requests/exams?group_by=merge_key` returns merged exam cohorts (same course, same
   date/time across programmes) with summed enrolment.

### Development

```bash
make check     # ruff + mypy + pytest (≈2–3 min; parses the real fixture workbooks)
make test      # pytest only
make format    # ruff --fix + format
alembic revision --autogenerate -m "…"   # after changing app/models
```

`app/solver` and `app/ai` are owned by the solver/AI agents and have their own gates; the backend
gate excludes them (see `Makefile`).
