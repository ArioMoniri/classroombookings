# SmartSched frontend

Next.js 16 (App Router) admin panel for SmartSched: import the term's requests, generate a timetable with
the CP-SAT backend, inspect the run report, drag events around the room × period grid, and refine the
plan in chat. TypeScript strict, Tailwind 4 + shadcn/ui (base-nova style on `@base-ui/react`), `motion`,
TanStack Query/Table/Virtual, Zustand, `@dnd-kit`, zod.

## Run

```bash
scripts/dev.sh --run              # from the repo root: starts the backend (:8000) and this app (:3000)
# or, with the backend already running:
cd smartsched/frontend
npm install
cp .env.example .env.local        # NEXT_PUBLIC_API_URL = the backend
npm run dev                       # http://localhost:3000
```

The UI always talks to the real FastAPI backend; there is no mock or demo mode. Sign in with the
administrator the backend seeds from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (see `smartsched/backend/.env`).

| Script | What it does |
|---|---|
| `npm run dev` / `build` / `start` | Next.js dev server / production build / serve the build |
| `npm run check` | `tsc --noEmit && eslint . && vitest run` — the quality gate |
| `npm run test` | vitest only (unit tests live next to the code as `*.test.ts(x)`) |
| `npm run e2e` | Playwright against the real backend (builds, starts on :3100; needs `E2E_REAL=1` and a running e2e backend, see below) |
| `npm run typecheck` / `lint` | the individual gates |

Playwright: Chromium is expected under `PLAYWRIGHT_BROWSERS_PATH` (defaults to `/opt/pw-browsers`, build
1194 = Playwright 1.56). Never run `playwright install` on the shared container.

### Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI base URL. The browser never calls it directly: `src/app/api/v1/[...path]/route.ts` proxies `/api/v1/*` to it and attaches the JWT from the httpOnly cookie. |

### Auth flow

`POST /api/v1/auth/login` → route handler forwards to the backend, stores `access_token` in the httpOnly
cookie `smartsched_token`, returns `{ user }` (resolved via `/auth/me` when the backend's `TokenOut`
has no user). `src/proxy.ts` (Next 16's middleware) redirects unauthenticated visits to
`/login?next=…` and authenticated visits to `/login` back to `/dashboard`; `/reset-password` and `/setup`
are public (signed in or not), `/login/change-password` needs the session. 401s from the API clear the
cookie and bounce to login (`ApiErrorBridge` in `src/components/providers.tsx`).

## Structure

```
src/
  app/
    layout.tsx, globals.css        root layout (fonts, providers), design tokens (docs/design/tokens.md)
    login/                         sign-in page
    (app)/                         authenticated shell: dashboard, import, requests, rooms[/id],
                                   generate, runs[/id], timetable, settings
    api/v1/[...path]/route.ts      backend proxy (always the real backend)
    api/auth/logout/route.ts
  proxy.ts                         route guard
  components/
    shell/                         sidebar, top bar, ⌘K palette, term switcher, drawer, shortcuts
    timetable/                     grid centrepiece: day grid (dnd-kit), week grid, agenda, move dialog
    dashboard/ import/ requests/ rooms/ generate/ runs/ chat/ settings/
    common/                        PageHeader, DataTable, NativeSelect, StatusBadge
    ui/                            shadcn primitives — SOURCES.md lists origin + licence of everything
  lib/
    api/schemas.ts                 zod schemas = the API contract (docs/ARCHITECTURE.md)
    api/client.ts                  fetch wrapper (auth, error bus, zod validation)
    api/adapters.ts                normalises FastAPI payloads (Page, grid matrix, masked settings…)
    api/endpoints.ts, hooks.ts     one function + one TanStack hook per route
    i18n/                          light TR/EN i18n (messages/*.json, cookie NEXT_LOCALE)
    time.ts, grid/layout.ts        18-period helpers, span layout + conflict checks (unit-tested)
  test/                            vitest setup + fixtures (never imported by app code)
  stores/ui.ts                     Zustand UI state (sidebar, density, highlight/changed assignment ids)
messages/tr.json, en.json          dictionaries (keys must stay in parity)
e2e/*.spec.ts                      Playwright on the real backend (smoke, real-backend, bookings, calendar,
                                   motion-audit); e2e/global-setup.ts resolves the run ids
```

## How to add a page

1. Create `src/app/(app)/<route>/page.tsx` (server component, exports `metadata`) that renders a client
   component from `src/components/<area>/`. Wrap it in `<Suspense>` when it uses `useSearchParams`.
2. Add the route to `src/components/shell/nav-config.ts` (icon, i18n label key, optional `g <key>`
   shortcut) and a label key to `SEGMENT_LABELS` in `top-bar.tsx` for breadcrumbs.
3. Add strings to **both** `messages/en.json` and `messages/tr.json` — `MessageKey` is derived from the
   English file, so a missing key fails `tsc`.
4. Data: add a zod schema in `lib/api/schemas.ts`, an endpoint in `endpoints.ts`, a hook in `hooks.ts`,
   and, when the payload is new, a recorded real-backend fixture in `src/lib/api/__fixtures__/real/`.
5. Add a `data-testid` to the main container and extend `e2e/smoke.spec.ts` if the page is on the critical path.

## How to add a component

- shadcn primitives: `npx shadcn@latest add <name>` → lands in `src/components/ui`; record the source
  and licence in `src/components/ui/SOURCES.md`. Only MIT/ISC sources are imported; reference-only
  sites (kobra, reverseui, Kinetics, transitions.dev) are re-implemented, never copied.
- Domain components live under `src/components/<area>/`, are client components, small, typed (no `any`),
  read colours only through tokens (`bg-status-locked`, `var(--cat-3)`…), and gate motion with
  `useReducedMotion()`.
- Status is never colour-only: use `StatusBadge` (icon + text) or the `STATUS_ICON` map.

## Design docs

`docs/design/*.md` (navigation-shell, tokens, timetable-grid, dashboard, run-report, import-wizard,
requests-inbox, generate-and-chat, rooms, settings-and-auth) are the specs this UI follows; tokens.md is
the single source of truth for colours and motion and is mirrored in `src/app/globals.css`.

## Backend alignment

The client is written against the FastAPI OpenAPI (`/api/openapi.json`); `lib/api/adapters.ts` bridges the
remaining shape differences (paginated `{items,limit,offset}`, the grid's day × room × cell matrix,
settings secrets as `{set,masked}`, naive UTC datetimes, chat history whose proposed diff rides on the
assistant message's `tool_calls`). `src/lib/api/contract.test.ts` parses payloads recorded from the real
backend (`src/lib/api/__fixtures__/real/`, re-record after backend schema changes).
`GET /dashboard` is composed client-side only when the backend answers 404.

Browser e2e (real backend only). Start the e2e backend (fresh SQLite, the Bahar 2026 workbooks, seeded admin,
a full-term solver run, booking clock pinned to 16 Feb 2026 08:00), then run every spec:

```bash
cd smartsched/backend && E2E_WORKDIR=/tmp/e2e E2E_VENV=none E2E_HOST=127.0.0.1 \
  bash ../deploy/pod-ci/gates/e2e-backend-entry.sh            # serves :8000
cd smartsched/frontend && E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test
```

The pod CI gate `e2e-real` does the same in Docker (see `docs/testing/2026-10-08-real-backend-e2e.md`), plus an
SMTP sink and a second, empty backend for the installer specs, with `CI=1` (one retry, both projects: `chromium`
and `mobile`). Without Docker, the whole gate (e2e-stabilisation 2026-10-16):

```bash
W=$(mktemp -d)                                                  # fresh databases every run
cd smartsched/backend
E2E_WORKDIR=$W/be E2E_VENV=none E2E_HOST=127.0.0.1 E2E_PORT=8000 bash ../deploy/pod-ci/gates/e2e-backend-entry.sh &
python3 ../deploy/pod-ci/gates/smtp-sink.py --host 127.0.0.1 --smtp-port 1025 --api-port 8025 &
# once :8000 is healthy (it reuses nothing, so start it after the import + solve):
E2E_EMPTY=1 E2E_WORKDIR=$W/be-empty E2E_VENV=none E2E_HOST=127.0.0.1 E2E_PORT=8001 bash ../deploy/pod-ci/gates/e2e-backend-entry.sh &
cd ../frontend && CI=1 E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 E2E_EMPTY_API_URL=http://127.0.0.1:8001 \
  E2E_SMTP_HOST=127.0.0.1 E2E_SMTP_PORT=1025 E2E_SMTP_API=http://127.0.0.1:8025 E2E_DB=$W/be/e2e.db \
  npx playwright test            # projects: chromium (all specs but intake), mobile (visual-quality), intake (last)
```

The seeded backend holds the Bahar 2026 list + weekly grid + room master, the 2026 Final board + exam list, the
published Bahar board, the analytics runs ("Bahar 3. hafta (A)" / "(B)", "Final (A)"), calendar.spec's editable
week-3 run and, solved last, the full-term run (`gates/e2e-backend-entry.sh`, `gates/e2e-seed-analytics.py`);
`e2e/global-setup.ts` resolves E2E_BOARD_RUN, E2E_SOLVER_RUN and E2E_EDIT_RUN from them.

Rules for specs (so any spec runs alone, in any order, and again on the same database):
- pin the interface language at the top of the file with `pinLanguage("tr" | "en")` from `e2e/language.ts` (the
  organisation default is Turkish and the signed-in user's profile language wins over the NEXT_LOCALE cookie);
- set preconditions through the API in the spec (KVKK sign-offs such as calendar sync, `approval_mode`,
  `POST /learning/refresh`) and put them back in `afterAll`; give created people, rooms and names a per-run stamp;
- wait on real conditions (a response, the server's state through `expect.poll`), not on time;
- `login()` acknowledges a published privacy notice for the test user (`ackNotice: false` for the notice's own test);
- a spec that changes shared data it cannot put back runs last in its own project (intake);
- design-system controls: `pickSegment` / `pickSegmentById` (a SegmentedControl becomes a select when it does
  not fit), `fillDate` (a DateField commits on blur or Enter), `/rooms?layout=cards` for the room cards (the
  table is the default layout).
