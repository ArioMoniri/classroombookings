# SmartSched Roadmap (2026)

## Goal

Replace the hand-maintained Excel classroom planning process with a web platform where an admin
imports the term's requests, presses **Generate**, gets a 100 % hard-feasible weekly / monthly / term /
exam timetable (or a precise list of what is impossible and how to fix it), refines it by chatting in
Turkish or English, and publishes it — deployable with one command and scalable.

## Definition of Done (project level)

1. `./smartsched/deploy/deploy.sh` brings up DB + backend + frontend on a clean Docker host.
2. All six real workbooks import with ≥ 99 % of rows parsed (rest listed with reasons).
3. CRBS legacy DB import (rooms, periods, sessions, bookings, users, departments) works.
4. Course run for 2026 Bahar (≈1 300 roomed meetings, 60 rooms, 14 weeks) solves in < 5 min with
   zero hard violations, or returns a diagnosis with actionable fixes.
5. Exam run for 2026 Final reproduces a feasible plan with multi-room splits.
6. NL preference → constraint → re-solve loop works end-to-end with the admin's own API key.
7. UI is responsive, dark-mode, animated, with timetable grid + drag-drop + conflict highlighting.
8. CI green; reviewer agents' blocking findings closed; user-tester scenarios pass.

## Phases

| Phase | Scope | Owner agent(s) | DoD |
|---|---|---|---|
| 0 Foundations | data analysis, architecture, roadmap, research, agent protocol | orchestrator, researcher | docs committed |
| 1 Backend + importers | FastAPI skeleton, models, Alembic, importers for A/B/C shapes + CRBS, tests | backend-engineer | `pytest` green; fixtures import; OpenAPI served |
| 2 Solver | CP-SAT core, constraints catalogue, diagnosis, LNS repair, benchmarks | solver-engineer | synthetic + real-data tests green; Bahar run feasible |
| 3 AI layer | settings/API key, constraint elicitation, chat edits, explanations | ai-engineer | mocked-SDK tests; live smoke behind key |
| 4 Frontend | design research (Mobbin + component sites), admin panel, timetable grid, chat | design-pro ×N, frontend-engineer | `tsc`, `eslint`, Playwright smoke green |
| 5 Deploy & CI | compose, Dockerfiles, deploy.sh, GitHub Actions, watchdog | devops-engineer | fresh-host deploy documented & scripted |
| 6 Review & test | strict-reviewer, user-tester, security-review, backlog grooming | reviewers, testers | findings triaged into backlog |
| 7 Live import | connector to the deployed university panel (login details to be supplied) | backend-engineer | rooms/photos/lists synced |

## TDD policy

- Every importer function starts with a failing test on a real fixture row.
- Every solver constraint has (a) a minimal feasible case, (b) a minimal infeasible case whose
  diagnosis names the constraint, (c) a soft-weight case showing the objective moves.
- API routes are tested with `httpx.AsyncClient` against SQLite.
- Frontend components get a vitest render test; critical flows get Playwright.
- No PR/commit without green `make check` (ruff + mypy + pytest + eslint + tsc).

## Backlog / nice-to-have (reviewers add here)

- [ ] Scenario comparison (A/B runs side by side, diff view)
- [ ] Utilisation heatmaps per building/day
- [ ] Request inbox workflow (faculty submits → planner approves)
- [ ] Publishing & versioning with audit trail, change notifications to instructors
- [ ] iCal feeds per room / instructor / programme
- [ ] Invigilator assignment for exams
- [ ] Student-level conflict checking when enrolment lists become available
- [ ] Mobile room display mode (door signs)
- [ ] SSO (LDAP, like CRBS) and role-based access
- [ ] Multi-campus / multi-timezone
- [ ] Solver: two-stage room-domain restriction (K nearest-capacity rooms first, full domains on fallback) to cut time-to-optimal on 1 300-event runs
- [ ] Solver: soft "split exam rooms in the same building / adjacent" term and invigilator-count cumulative for multi-room exams
- [ ] Solver: enumerate several MUSes / smallest MUS (QuickXplain) so the planner sees alternative fixes, not just one conflict set
- [ ] Solver: benchmark on the real Bahar/Final fixtures through the importers once `services.solver_bridge` builds SolverInput from the DB (≥ 95 % definitive-room reproduction regression)
- [ ] Solver: week-level room changes inside one event (an event may switch rooms mid-term) — today one room per event for all its weeks; split events by week pattern upstream
- [ ] Solver: `stub.py` (backend fallback) has one line > 120 chars; drop the stub once the API uses `cpsat` by default

### Backend Phase 1 backlog (backend-engineer, 2026-10-07)

- [ ] Live MySQL CRBS import is implemented (`mysql://` DSN via optional `pymysql`) but only the SQL-dump path is covered by tests; add an integration test against a MySQL service in CI
- [ ] `GET /runs/{id}/export?format=crbs` currently returns the generic CSV; map it to CRBS' booking import format (room name, date, period name, user/department) once the target schema is agreed
- [ ] Venue-request parser (`parse_venue_request`) is regex-based; route the `confidence=low` rows through the AI constraint-elicitation tool (ai-engineer) and surface them in the inbox
- [ ] "Same room as X" requests (`same_room_as`) are stored in notes but not yet turned into `same_room_group` constraints for the solver
- [ ] Section identity uses (course, programme, şube); rows that only differ by class year collapse into one section — revisit if the planning office needs them separate
- [ ] Weekly-grid import stores one `assignment` per cell with `course_codes` list; linking to meeting requests is by (code, day, start period) and takes the first match — add an interactive reconciliation view
- [ ] Job queue is in-process asyncio; swap for Celery/RQ worker (interface in `app/workers/queue.py`) before horizontal scaling
- [ ] Holidays from CRBS only mark whole-week `weeks.kind = HOLIDAY`; partial-week holidays are kept as labels
