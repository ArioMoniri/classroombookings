# Real-backend end-to-end run (2026-10-08, integration-engineer)

FastAPI backend on SQLite with the real Bahar workbooks, Next.js frontend in real mode (no MSW), and
Playwright `e2e/real-backend.spec.ts`. All numbers below were measured in this container (8 vCPU).

## 1. Backend setup

```bash
cd smartsched/backend
export ENVIRONMENT=dev DATABASE_URL=sqlite+aiosqlite:///$PWD/e2e.db \
       ADMIN_EMAIL=admin@smartsched.local ADMIN_PASSWORD='Admin-2026!' \
       APP_SECRET=e2e-secret-e2e-secret-e2e-secret-0000 UPLOAD_DIR=$PWD/e2e-uploads \
       CORS_ORIGINS='["http://localhost:3100","http://127.0.0.1:3100"]'
python -m app.cli import weekly-grid tests/fixtures/bahar_derslikler_takvimi_2026.xlsx --term 2026-BAHAR --year 2026
python -m app.cli import planning-list tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx --term 2026-BAHAR
python -m app.cli seed-admin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

| Step | Result |
|---|---|
| Both imports (`time`) | **28.6 s** wall; 79 rooms (A 204 = 156 seats, A 201-203 TIP), 19 weeks, 1 271 sections, 1 524 requests (231 NEEDS_REVIEW), 5 rows skipped (no course code) |
| Grid import side effect | two FEASIBLE runs: #1 COURSE / #2 EXAM "Grid import: …" = the planner's published board (origin `IMPORT`) |

## 2. CP-SAT runs through the API

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@smartsched.local","password":"Admin-2026!"}' | jq -r .access_token)
curl -s -X POST localhost:8000/api/v1/runs -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"term_id":1,"kind":"COURSE","horizon":"WEEK","horizon_params":{"weeks":[3]},"params":{"solver":"cpsat","time_limit_s":120}}'
# poll GET /runs/{id} (and GET /health every 2 s)
```

| Run | Status | Time | Events / rooms | Diagnoses |
|---|---|---|---|---|
| #3 week 3 (first attempt) | **FAILED** `no such column: constraints.source_ref` | – | – | see finding F1 |
| #4 week 3, cpsat, 120 s limit | **INFEASIBLE** (`solver_status=STATIC_INFEASIBLE`) | solver 0.05 s, < 3 s end to end | 685 events (149 joint-lecture groups merged), 57 rooms (22 without capacity dropped) | 356 |
| #5 full term (TERM, 15 weeks), cpsat, 300 s limit | **INFEASIBLE** (static) | solver 0.35 s, 3 s end to end | 686 events, 57 rooms | 390 |
| #7 week 7, created from the UI (/generate) | INFEASIBLE (static) | < 3 s | 683 | 359 |

`/health` answered in ≤ 12 ms throughout (solve now runs in a worker thread).

Full-term Bahar diagnoses by category (run #5): 118 instructor clashes between fixed-time requests,
68 cohort clashes between fixed-time requests, 65 "no eligible room", 64 "locked assignment uses a room
that is not eligible" (planner's room smaller than the expected enrolment), 34 pigeonhole overloads
(more fixed-time events in a slot than eligible rooms), 14 merged joint lectures without a room,
13 locked overlaps. Because every Bahar request has a fixed day/time (671 of 685 events), the solver only
chooses rooms; the clashes above are properties of the input that no room choice can fix — the run is
correctly reported infeasible *with explanations*, but produces no timetable. See findings F2–F4.

Measured effect of the bridge changes (same data, `build_solver_input` + `cpsat.solve`):

| Instance | Before | After |
|---|---|---|
| Güz week 3 (COURSE) — joint-lecture merge | 556 diagnoses (143 locked overlaps, 250 instructor clashes) | 169 (9 locked overlaps, 51 instructor clashes) |
| Bahar week 3 (COURSE) | – | 356 |
| Final (EXAM, 630 events, 554 locked) — `share_room` | 112 locked-overlap diagnoses, 33 of them between two single-room exams | 79, **0** between single-room exams; the rest involve a split (multi-room) locked exam, which the solver keeps exclusive (F5) |

## 3. Frontend in real mode + Playwright

```bash
cd smartsched/frontend
E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test   # builds with NEXT_PUBLIC_API_MOCK=0, serves :3100
# optional: E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD, E2E_TERM_CODE (default 2026-BAHAR)
```

`playwright.config.ts` runs only `real-backend.spec.ts` when `E2E_REAL=1` (and ignores it otherwise, so
`npm run e2e` stays the mock smoke suite).

Result: **1 passed (30.9 s)**. The spec covers:

1. login with the seeded admin (cookie lifetime now = JWT `expires_in`);
2. dashboard tiles equal `GET /dashboard` (1 271 sections, 231 needs review), real building × day
   heatmap (A Mon 22 %, C Wed 51 % for the board's week 15);
3. requests inbox lists Bahar rows; rooms page shows **A 204 (156)**;
4. /generate → one-week run (#7) → run report with diagnosis cards (INFEASIBLE, see above);
5. grid of the feasible imported board (#1) shows events;
6. move dialog → first slot the client preview accepts → `POST …/move` 200 `ok=true`; DB check:
   `ACU244` → Sunday P13–P14, `is_locked=1`, `origin=MANUAL`;
7. settings load, users tab lists the admin.

Bugs found by this run and fixed in scope: generate page crashed ("Invalid time value") on a week without
a start date (`Yaz Dönemi` sheet) → `formatDate` tolerant + test; `GET /dashboard` failed zod validation
(raw TermOut with `end_date: null`, RunOut stats with lists) → `adapters.dashboard`; COURSE runs were
seeded with the EXAM board as stability parent → same-kind parent; naive backend datetimes were read as
local time (3 h off in Türkiye) → `adapters.utcIso`; course "split" suggestions were offered as
applicable → not applicable for COURSE runs. A frontend contract test (`src/lib/api/contract.test.ts`)
now parses payloads recorded from this backend (`src/lib/api/__fixtures__/real/*.json`).

## 4. Findings reported (out of integration scope)

- **F1 (schema drift, studio/backend)**: the model gained `constraints.source_ref` (+ studio tables);
  a dev DB created earlier by `create_all` lacked the column and every run FAILED until
  `alembic stamp 0001 && alembic upgrade head` — which then failed on the studio tables that the dev
  `create_all` had already created; I added the column via the failed upgrade and `alembic stamp head`.
  Dev startup should run migrations (or the docs should say "delete the dev DB").
- **F2 (importer)**: `B 207` is the only PC-tagged room and has capacity 0 in the Bahar grid header, so
  the bridge drops it; A 103/104/105 (computer labs per DATA_ANALYSIS) carry no `PC` tag → every
  "Bilg. Lab. Zorunlu" request has no eligible room. 22 rooms have no capacity at all.
- **F3 (modelling)**: instructor/cohort clashes between two *fixed-time* requests (118 + 68 in Bahar)
  make the room-assignment problem infeasible although rooms cannot resolve them; suggest a bridge/solver
  mode that reports them as input warnings and drops the key only between the clashing fixed pair.
- **F4 (modelling)**: planning-list enrolments are *expected* numbers; 64 locked definitive rooms are
  smaller than the request (e.g. ACU 132: 122 students locked to A 207, 55 exam seats). Joint lectures
  are clipped to the planner's rooms (reported in `stats.merged_joint_lectures_clipped`); single rows
  are not. Needs a product decision ("trust LOCKED rooms" switch).
- **F5 (solver)**: `share_room` only applies to single-room events (`domains.shares_room`); the Final
  plan routinely seats two split exams in the same room pair (PSI 212 + FZT 260 in A 204 + A 102).
- **F6 (solver UX)**: an INFEASIBLE run persists no assignments, so the grid is empty; the relaxation
  phase already computes a partial placement (`relaxation_diagnosis` → `placed`) that could be persisted
  as a draft.
- **F7 (dashboard)**: the board run's utilisation week defaults to the calendar week (15 on 2026-10-08,
  after the Bahar term); fine, but the subtitle "15 haftanın 15. haftası" reads oddly after term end.
