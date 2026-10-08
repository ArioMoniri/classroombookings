# No-placeholder audit (2026-10-08, strict-reviewer, read-only)

The user's rule is "no demo, test or placeholder usage across the whole system".
The reviewer verified each finding against a real `next build` (with `NEXT_PUBLIC_API_MOCK=0` and unset), against the backend
OpenAPI route list (176 paths; every frontend API path has a backend route), and in Python (`clean_client_params`, `insecure_reasons`).

| # | Sev | Location | Issue | Owner |
|---|---|---|---|---|
| B1 | BLOCKER | `frontend/src/app/api/v1/[...path]/route.ts:16`, `lib/server/config.ts:8`, `login-form.tsx:22`, `deploy/docker-compose.yml:106,114`, `frontend/.env.example:4` | The MSW mock and the "any e-mail + password admin" login ship in prod. They can be switched on at build time, or at runtime when the build had no `NEXT_PUBLIC_API_MOCK`. The image ships 112 KB of mock chunks. | no-placeholder frontend |
| M1 | MAJOR | `services/run_params.py:37`, `solver_bridge.py:44`, `cli.py:129` | `solver:"stub"` is accepted from the API, and its result is stored as a real run. | solver |
| M2 | MAJOR | `core/config.py:10,19,80` | The secret check runs only when `ENVIRONMENT=="prod"`, and the default secret is public. | no-placeholder backend |
| M3 | MAJOR | `services/seed.py:29-35` | The seeded admin password is never checked, and no reset is forced. | no-placeholder backend |
| M4 | MAJOR | `playwright.config.ts:14`, `smartsched.yml:138`, `e2e/motion-audit.spec.ts` | The bookings and calendar e2e tests run in no gate; motion-audit breaks the mock gate. | no-placeholder frontend |
| M5 | MAJOR | `frontend/src/proxy.ts:7` | `/reset-password` and `/setup` are blocked for signed-out users. | no-placeholder frontend |
| m1 | MINOR | `deploy/.env.example:31` | `admin@example.edu.tr` gets seeded. | no-placeholder backend |
| m2 | MINOR | `infra/aws/smartsched_aws.py:73` | Personal e-mail as the default admin. Won't fix: the user chose this address. | — |
| m3 | MINOR | `frontend/.env.example:6`, `docker-compose.yml:115` | `AUTH_SECRET` is dead config. | no-placeholder backend |
| m4 | MINOR | READMEs | The docs describe the demo login. | no-placeholder frontend |
| m5 | MINOR | `shell-extra.ts:330`, `login-form.tsx:51`, `adapters.ts:338` | Mock-compatibility shims remain in production paths. | no-placeholder frontend |
| m6 | MINOR | `nginx/default.conf:103-104`, `main.py:133` | The OpenAPI docs and redoc are public. | no-placeholder backend |
| m7 | MINOR | `health.py:29-31`, `main.py:136` | The version is hard-coded, and the solver name is exposed. | no-placeholder backend |
| m8 | MINOR | `normalize.py:274`, `frontend/src/lib/time.ts:16`, `dashboard.py:25` | The period grid is hard-coded and duplicated. Moved to the roadmap as a time grid per term. | roadmap |
| m9 | MINOR | `next.config.ts:7` | Wildcard `remotePatterns` turns `/_next/image` into an open proxy. | no-placeholder frontend |
| m10 | MINOR | `app/solver/generators.py`, `calibrate.py` | Synthetic generators live in the prod package. | solver |
| m11 | MINOR | `components/timetable/model/fixtures.ts` | A test fixture sits inside `src/`. | calendar |
| m12 | MINOR | `scripts/dev.sh:52` | The dev admin is `admin@example.com` / `admin`, and dev.sh has a `--mock` mode. | no-placeholder backend |

Checked and clean:
- No test, debug, seed or reset routes.
- Migrations seed only the permission and role catalogue.
- With no AI key the API returns 409, with no fake replies.
- Template explanations are labelled `source:"template"`.
- The dashboard has no hard-coded numbers.
- There is no lorem ipsum or TODO text in the UI.

E2E: real mode must run the real-backend, bookings, calendar, motion-audit and smoke specs, after which the mock gate is removed.
`bookings.spec.ts` needs the backend clock inside Bahar 2026.
