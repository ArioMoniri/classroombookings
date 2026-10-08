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
| 8 Generator Studio | one easy screen to shape a run: pick/adjust the list of classes (include, exclude, pin, edit size/day/time), change preferences per course/program/room, write rules in Turkish/English, upload preference files (Excel/CSV/Word/PDF/text) that AI turns into reviewable rules, reusable presets, live feasibility pre-check, plain-language summary before Generate | design-pro, backend-engineer, ai-engineer, frontend-engineer | planner builds and runs a scenario without help; every input becomes a visible, editable rule |

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
- [ ] Backend: add `GET /dashboard` summary, `/users` CRUD, `/runs/{id}/chat*` (proposal apply/undo), `/constraints/propose`, `/runs/{id}/diagnosis/{id}/apply` — the frontend ships these as MSW mocks only (frontend-engineer)
- [ ] Backend: `AssignmentOut` should carry `size`/`enrolment`, `program_name`, `instructor`, `conflict` so the grid's capacity/TIP checks and tooltips work on real data (frontend adapts with defaults today)
- [ ] Frontend: SSE run progress (`/runs/{id}/events`) instead of 1 s polling; streaming chat replies
- [ ] Frontend: grid resize handle, context menu, move-scope popover (all weeks / this week / from week), undo/redo history (⌘Z) per timetable-grid.md §4.2–4.3
- [ ] Frontend: requests board (kanban) view, chip editor for free-text room requests, saved views
- [ ] Frontend: room photo upload (`POST /rooms/{id}/photo`), lightbox, capacity-range filter histogram
- [ ] Frontend: settings/terms editor, user deactivate/reset-password, dirty-state guard, audit history
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
- [ ] **Exam room sharing**: the real Final plan puts several small exams in one room at the same time (grid cells like `MAT 102 / MAT 112`); the solver contract models one event per room-slot, so an EXAM run with the planner's locked definitive rooms is reported INFEASIBLE (`no_room_overlap`+`fixed_time` ×112 on 2026-FINAL). Needs a `shared_room` option (sum of cohort sizes ≤ exam capacity) in the contract and bridge
- [ ] 20 rooms referenced by the Final list (labs, D 3xx, A 7xx…) have no exam capacity in any grid header; add a room-master CSV import or admin bulk edit so capacity-0 rooms are not dropped from solver input

### Phase 8 Generator Studio backlog (from docs/design/generator-studio.md, 2026-10-08)

- [ ] Backend: `POST /runs/precheck` (wrap solver static_check, reuse `services/diagnosis_fixes.py` for fix actions applied to the draft)
- [ ] Backend: studio draft `GET/PUT /terms/{id}/studio`; `POST /runs` accepts `draft_id` / `exclude_event_ids`
- [ ] Backend: `POST /constraints/preview` (affected count), `POST /constraints/copy`, `/presets` CRUD + apply
- [ ] Backend: `PUT /sections/{id}`, `PUT /requests/meetings/bulk`, imported-value snapshot + revert, class-list filters (faculty, year, building, mode, changed, rule)
- [ ] Backend: constraint source `UPLOAD` / `BUILTIN` + `source_ref`; `GET /constraints/kinds` returns the full TR/EN catalogue
- [ ] AI: mount `/terms/{id}/elicit` + `/elicit/accept`; preference-file extraction with per-row `source_ref`; plain-language pre-check text
- [ ] Solver: confirm Low/Normal/High = 2/5/8 weight scale; pre-check run-time estimate; `room_reserved_for` kind
- [ ] Frontend: `components/studio/*` (rule card, slot chip, source chip, readiness meter, review tray, upload review, step rail); replace generate-view; switch the propose mock to `/terms/{id}/elicit`
