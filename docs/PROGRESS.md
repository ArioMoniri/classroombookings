# Progress ledger (append-only; see docs/AGENTS.md)

| time (UTC) | agent | phase | status | next |
|---|---|---|---|---|
| 2026-10-07 22:10 | orchestrator | 0 | data analysed, architecture/roadmap/agents docs written, deps installed | launch researcher, backend, solver, design agents |
| 2026-10-07 22:15 | design-pro (grid/dashboard/report/tokens) | 1 | started: Mobbin + component-site research for timetable grid, dashboard, run report, tokens | write docs/design/{timetable-grid,dashboard,run-report,tokens}.md |
| 2026-10-07 22:15 | backend-engineer | 1 | started: reading specs, exploring fixtures | models, normalize, importers |
| 2026-10-07 22:15 | design-pro (B: import/inbox/generate-chat/rooms/settings/shell) | 4 | started; reading architecture/data docs, researching Mobbin + component sites | write docs/design/{import-wizard,requests-inbox,generate-and-chat,rooms,settings-and-auth,navigation-shell}.md |
| 2026-10-07 22:16 | frontend-engineer | 4 | started: reading docs; scaffolding Next.js app under smartsched/frontend | scaffold + shadcn + deps, then shell/auth, API client + MSW, grid, pages, tests |
| 2026-10-07 22:19 | solver-engineer | 2 | started: model.py absent → creating per contract; building cpsat/diagnose/repair/generators/tests under app/solver | cpsat core + tests |
| 2026-10-07 22:19 | backend-engineer | 1 | fixtures explored (grid: 7 day blocks of 29 cols, header rows 2/22, 18 slots; lists: 25/14 cols); scaffolding project | core+models |
| 2026-10-07 22:25 | design-pro (B) | 4 | research done (12 Mobbin refs, 8 component sites, licences checked); wrote navigation-shell, import-wizard, requests-inbox | write generate-and-chat, rooms, settings-and-auth |
| 2026-10-07 22:25 | backend-engineer | 1 | models done (20 tables, create_all ok); solver contract model.py written | normalize.py TDD |
| 2026-10-07 22:28 | design-pro (grid/dashboard/report/tokens) | 1 | done: docs/design/{tokens,timetable-grid,dashboard,run-report}.md written; 30+ Mobbin refs, 8 component sites checked (licences: beUI/evilcharts/beautifului MIT; kobra/reverseui/transitions.dev non-OSS → reference only; Kinetics unverified); contrast ratios computed | frontend-engineer: build from specs; verify beUI LICENSE on first import; answer open questions in each doc |
| 2026-10-07 22:29 | design-pro (B) | 4 | DONE: 6 surface specs in docs/design (navigation-shell, import-wizard, requests-inbox, generate-and-chat, rooms, settings-and-auth) with refs, IA, interaction, components+licences, responsive, a11y, open questions | frontend-engineer builds shell + import + inbox first; orchestrator decides on kobra Pro purchase; backend adds test-ai transient key + run revert/activate endpoint |
| 2026-10-07 22:30 | backend-engineer | 1 | normalize done (263 tests green) | planning/exam/grid/crbs importers |
| 2026-10-07 22:36 | solver-engineer | 2 | milestone: cpsat core + 19 constraint modules + diagnose/repair/validate/generators written; smoke solve OPTIMAL, validate==solve breakdown | benchmark 300/1300 events, tests, mypy/ruff, README |
| 2026-10-07 22:38 | frontend-engineer | 4 | scaffold done (Next 16, Tailwind 4, shadcn base-nova, deps); tokens → globals.css; i18n TR/EN; typed zod client + MSW mock API (61 rooms, runs #1 feasible/#2 infeasible) with vitest green; shell + auth (cookie JWT proxy, proxy.ts guard, sidebar/topbar/⌘K/drawer) compiling | pages: dashboard, import, requests, rooms, generate, runs + grid, settings |
| 2026-10-07 22:45 | backend-engineer | 1 | importers done (planning/exam/grid/crbs green on real fixtures) | stub solver, bridge, queue, API |
| 2026-10-07 22:59 | solver-engineer | 2 | milestone: 45 solver tests green (per-kind feasible/infeasible/soft-weight, diagnosis, repair, 300-event medium in ~16s); interval/NoOverlap2D encoding + greedy warm start chosen after benchmarking AtMostOne (18s presolve) | slow 1300-event run, mypy/ruff, README |
| 2026-10-07 23:02 | backend-engineer | 1 | API (43 paths), services, queue, stub solver, alembic 0001, CLI, README done; lint+mypy green | full make check |
