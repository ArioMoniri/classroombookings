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

- [x] Backend: pre-check as `POST /terms/{id}/studio/precheck` + `/precheck/fix` (static_check + rule checks, plain TR/EN items, fixes applied into the draft; `parse_option` reused for unlock) (studio backend, 2026-10-08)
- [x] Backend: studio draft `GET/PUT /terms/{id}/studio` (per user/term/kind, version + If-Match); runs from drafts via `POST /terms/{id}/studio/generate` (snapshot in `params.studio`)
- [ ] Backend (integration): `solver_bridge.run_schedule` should call `app.services.studio.build_solver_input_for_run` so child runs (chat apply, diagnosis apply) of studio runs keep the draft's exclusions / pins / built-in switches; optionally `POST /runs {draft_id}` delegating to `studio.generate`
- [x] Backend: `POST /studio/constraints/preview`, `POST /studio/constraints/copy`, `/presets` CRUD + apply (studio paths; `/constraints/*` is owned by the integration router)
- [x] Backend: `GET /terms/{id}/studio/classes` (filters faculty/program/year/day/building/mode/status/changed/included/pinned/rule/q), `PUT /studio/meetings/bulk` (enrolment + mode on the section), imported snapshot (lazy, fingerprinted) + `POST /studio/meetings/{id}/revert`
- [ ] Backend: importers could write the imported snapshot at import time (today it is captured lazily before the first studio edit; edits made elsewhere before that count as imported); exam-request edits/snapshots in the studio class list
- [x] Backend: constraint source `UPLOAD` / `BUILTIN` + `constraints.source_ref` column (alembic 0002_studio); `POST /terms/{id}/studio/proposals/accept` stores upload refs there; full catalogue + 14 templates + 2/5/8 weight scale in `GET /studio/meta`
- [ ] Backend (integration): add `source_ref` to `ConstraintOut`; `GET /constraints/kinds` -> `catalog_dict()`; `accept_proposals` (app/ai) could write `source_ref` directly instead of `params._source_ref`
- [ ] Backend: disabling `no_cohort_overlap` per draft is honoured by CP-SAT only (keys sentinel); the greedy stub still checks cohort keys
- [ ] AI: mount `/terms/{id}/elicit` + `/elicit/accept`; preference-file extraction with per-row `source_ref`; plain-language pre-check text
- [ ] Solver: confirm Low/Normal/High = 2/5/8 weight scale; pre-check run-time estimate; `room_reserved_for` kind
- [ ] Frontend: `components/studio/*` (rule card, slot chip, source chip, readiness meter, review tray, upload review, step rail); replace generate-view; switch the propose mock to `/terms/{id}/elicit`

### Phase 5 deploy/devops backlog (devops-engineer, 2026-10-08)

- [ ] Backend: run the CP-SAT call off the event loop (`asyncio.to_thread` / process pool) in `services/solver_bridge.run_schedule`; today a solve blocks its whole uvicorn process (API + healthcheck) for up to `time_limit`
- [ ] Backend: on startup mark `schedule_runs`/`import_jobs` left in `RUNNING`/`QUEUED` by a previous process as `FAILED (interrupted)` (in-process queue loses jobs on restart)
- [ ] Backend: do not serve `/uploads/imports/*` from the public StaticFiles mount (nginx 404s it today); serve room photos only, or require auth
- [ ] Backend: `POST /terms` with no `name` raises `TypeError: Term() got multiple values for keyword argument 'name'` (500): `Term(**body.model_dump(), name=...)` duplicates the key; use `body.model_dump(exclude={"name"})`
- [ ] Backend: import-job `error` returns a full traceback with absolute server paths to API clients; log it, return a short message
- [ ] Backend: commit `smartsched/backend/requirements.lock` (`pip-compile`/`uv pip compile` for py3.12) so Docker builds pin transitive deps; the Dockerfile already uses it as a constraints file when present
- [ ] Frontend: session cookie is `Secure` whenever `NODE_ENV=production`, so plain-http logins from another machine fail silently; add `COOKIE_SECURE=auto` (derive from `X-Forwarded-Proto`) or document TLS-only (deploy/README.md "TLS" does)
- [ ] Frontend: cookie `maxAge` (30 days) outlives the JWT (`JWT_EXPIRE_MINUTES=720`); align them
- [ ] Dedicated worker service (RQ/Celery on Redis, `python -m app.cli worker`) + progress fan-out via pub/sub, before running several backend replicas (deploy/README.md "Scaling")
- [ ] Pin base images by digest and let Renovate/Dependabot bump them
- [ ] Postgres locale: initdb uses `C.UTF-8`; evaluate `--locale-provider=icu --icu-locale=tr-TR` for Turkish ORDER BY (needs a fresh volume)

### Phase 3 AI layer backlog (ai-engineer, 2026-10-08)

- [ ] Backend deps: add `python-docx>=1.1` and `pypdf>=4` to `smartsched/backend/pyproject.toml` (+ lock); `app/ai/ingest.py` imports them lazily and returns HTTP 400 "not installed" without them (installed in the dev env, not declared)
- [x] Settings default model (decided 2026-10-08: `claude-opus-5-5`): `settings_service.SPECS["anthropic_model"]` defaults to `claude-sonnet-5-5` while the claude-api skill / RESEARCH §4.3 recommend `claude-opus-5-5`; decide and align (AI layer falls back to `claude-opus-5-5` only when the setting is empty)
- [ ] Constraints table: add a `source_ref` JSON column; today upload refs live in `params["_source_ref"]` (studio backend agent)
- [ ] Chat-created constraints are term-wide (`term_id`) so they carry over to grandchild runs; add a run-scoped option ("only for this run") with inheritance through `parent_run_id` in `build_solver_input`
- [ ] Week-limited room rules (`room_pin`/`room_forbid` with weeks other than room_closed) are flagged needs_review: the solver applies room rules to all weeks of an event; implement meeting splitting by week pattern ("PHAR 240 moves to A 206 from 23 Feb")
- [ ] Moves to another day/period of a fixed-time request are rejected by the validator (`fixed_time` hard); offer "move + update the request" as one op in the diff UI instead of a separate `set_section_field`
- [ ] Exam runs: section edits only touch meeting requests; add exam-request edits (enrolment, room count) and exam-specific chat tools (split across rooms)
- [ ] Streaming chat (SSE) with `eager_input_streaming` + client-side tool-input validation; today `POST /runs/{id}/chat` returns when the loop ends
- [ ] Red-team eval before launch (RESEARCH Recommendations 3): paraphrase / re-ordering / ambiguous room names / prompt-injection in uploaded files, measured against a fixed expected-constraint set
- [ ] Persist the model id + verifier result per applied diff on the child run (audit, RESEARCH §4.3 step 6) - partly there via `chat_messages.tool_calls` usage + `stats.mode`
- [ ] OCR for scanned PDFs (currently reported as "no extractable text")

### Phase 6 integration backlog (integration-engineer, 2026-10-08)

- [x] Importer: B 207 (only `PC` room) has capacity 0 in the Bahar grid header and A 103/104/105 carry no `PC` tag → every "Bilg. Lab. Zorunlu" request is unplaceable; seed lab capacities/tags from the Bahar `Sayfa2` room buckets (22 rooms have no capacity)
- [x] Bridge/solver "room-only" mode: instructor/cohort clashes between two fixed-time requests (Bahar: 118 + 68) cannot be fixed by rooms; report them as input warnings and drop the key only for the clashing fixed pair, so the room plan is still produced
- [x] Product decision: "trust LOCKED definitive rooms" switch (64 Bahar locked rooms are smaller than the expected enrolment); joint lectures are already clipped to the planner's room and reported in `stats.merged_joint_lectures_clipped`
- [x] Solver: `share_room` for split (multi-room) exams — the Final plan seats two split exams in one room pair (79 remaining locked overlaps)
- [x] Solver/bridge: persist the relaxation's partial placement of an INFEASIBLE run as a draft so the grid is not empty
- [x] Dev DB: run Alembic on dev startup (or document "delete the dev DB"); `create_all` + later `alembic upgrade` do not compose (studio tables / `constraints.source_ref`)
- [ ] Imports still parse workbooks on the event loop (10–25 s for Bahar); move parsing to a worker thread like the solve
- [ ] Re-record `smartsched/frontend/src/lib/api/__fixtures__/real/*.json` (contract test) whenever backend schemas change; a CI job could run the backend, record and diff
- [ ] Dashboard: KPI deltas vs. the previous run/week (the fake "+3 pt / −2" were removed); stats tiles on the run report read `stats.unplaced/conflicts`, which CP-SAT runs do not set

### UI polish backlog (screenshot pass, 2026-10-08)

- [ ] `/timetable` run selector truncates its label ("…Feasible · 1(") on desktop and mobile
- [ ] `/timetable` throws React hydration error #418 in production (page recovers)
- [ ] Run page sticky header is translucent; hero text shows through when the chat panel scrolls — make it opaque or scroll the chat independently
- [ ] Mock room photos use random picsum images; replace with neutral tiles or real room photos (phase 7 live import)
- [ ] Every Playwright config should use its own port (`PW_PORT`) so parallel agents don't share a server and mock state

### Phase 9 real-data feasibility backlog (solver-engineer, 2026-10-08)

- [ ] Week-granular blocks for TERM runs: a 14-week lecture whose locked room is blocked by the grid in one week (ETKİNLİK, exam) is unplaced for the whole term (Bahar term: 14 `locked_ineligible`); model "all weeks except w" (split the event's weeks around blocked weeks) instead of dropping the room
- [ ] `api/v1/runs.py` `TERMINAL`, dashboard `GOOD`, studio filters: if a dedicated `FEASIBLE_PARTIAL` status is ever wanted, add it there first (today a best-effort run is `INFEASIBLE` + `stats.partial/placed/unplaced/events_total`, labelled "Partial · placed/total" in the UI)
- [ ] Studio drafts: expose the run modes (`trust_locked_rooms`, `fixed_conflicts_as_warnings`, `best_effort`, `definitive_rooms`) as draft switches; pre-check uses the defaults
- [ ] Unlocked exam runs (`definitive_rooms=prefer`): the relaxation stops at FEASIBLE within 60 s below the greedy placement (greedy fallback is used); tune (LNS-only phase, hint completion for `seats[e, r]`)
- [ ] Reproduction rate unlocked is 69–73 % (courses) / 6 % (exams): calibrate `room_preference` vs `min_capacity_waste` weights against the planner's definitive rooms
- [ ] Period snapping: ends 10 min into a period still claim it (BES 640 19:50 vs BES 560 20:00 both in P15); consider a ≥ ½-period rule with planner sign-off
- [ ] Planner data fixes surfaced by the report: 7 Bahar / 3 Güz locked room overlaps, 131 Bahar fixed-vs-fixed instructor/cohort clashes (`input_conflict`), Final exams locked to rooms blocked by the Final grid (SYB 256/356/456, ODY 102/108)


### Phase 8 Generator Studio frontend backlog (frontend-engineer, 2026-10-08)
- [ ] Rule list virtualisation for > 40 cards (compact density is in; `@tanstack/react-virtual` over variable-height cards is not).
- [ ] Slot pickers and class edits as bottom sheets on coarse pointers (they are popovers at every width today).
- [ ] Write-it box: highlight the source sentence while hovering a proposal (needs a mirrored overlay; the textarea can't highlight).
- [ ] Upload: per-file server stages (Reading → Finding rules) need `GET /terms/{id}/preferences/uploads/{upload_id}` or SSE; today the UI shows real upload % and then one "Reading and finding rules" stage. "Files used" history (rail, advanced) not built.
- [ ] Provenance panel: show 2 context rows and the header for Excel (needs `context_rows` from the backend); shows the excerpt only today.
- [ ] Classes: Weeks inline editor, "Paste a column from Excel" (method h), bulk "Pin to room…" / "Set preferred building…" / Export, row ⋯ menu "Make a rule from this row", exam-kind columns (date, rooms needed, venue request).
- [ ] Studio run status via SSE `GET /runs/{id}/events` (1 s polling of `GET /runs/{id}` today), "Must-rules broken" is not reported by the backend while running.
- [ ] Undo after reload: the stack is in memory; revert-to-imported covers class edits only.
- [ ] Global sidebar auto-collapse on /generate below 1440 px (navigation-shell §3.1) — not done to avoid overriding the persisted user choice.
- [ ] Export draft as JSON (advanced).
- [ ] Contract fixtures for the studio routes recorded from the real backend (`src/lib/api/__fixtures__/real/studio_*.json`) so `contract.test.ts` catches drift.
