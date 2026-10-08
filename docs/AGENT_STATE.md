# Agent state and resume guide

Purpose: if the session or usage limit is reached, a new session can pick up every workstream from this file plus
`docs/PROGRESS.md` (append-only ledger), `docs/ROADMAP.md` (phases + backlog), `docs/AGENTS.md` (roles, scope fences,
hand-off format) and `.claude/agents/*.md` (agent definitions). The orchestrator refreshes this file at every watchdog
check-in. Last refresh: **2026-10-08 11:50 UTC**, branch `claude/gracious-cerf-w1598m` at `c8e9138`.

## How to resume after an interruption

1. `git pull` on `claude/gracious-cerf-w1598m`; read this file, the last 30 lines of `docs/PROGRESS.md`, and `git log --oneline -20`.
2. Run `python3 scripts/watchdog.py` (stale agents) and `cd smartsched/backend && make check`, `cd smartsched/frontend && npm run check`.
3. For each **running** workstream below whose work is not finished, relaunch an agent of the listed type with
   "You are RESUMING <workstream>. Read docs/AGENT_STATE.md (your row), the last ledger lines for your name, and
   `git log -p --since=<last milestone time> -- <your scope>`; continue from the 'Next' column; keep the same scope fence."
4. Agents never commit; the orchestrator checkpoints with `git add -A && git commit -m "wip: agent progress checkpoint"`
   and pushes. No GitHub Actions on push (billing); CI runs on the AWS pod.
5. Report to the user in BLUF: what was done, what is needed — briefly.

## Running workstreams (as of the last refresh)

| # | Workstream (agent type) | Scope fence (write) | Goal | Last milestone (ledger) | Next |
|---|---|---|---|---|---|
| 1 | Solver follow-up (solver-engineer) | `app/solver/**`, `services/{solver_bridge,data_issues,dashboard}.py`, `api/v1/{runs,data_issues,dashboard}.py` (status only), `schemas/runs.py`, tests, run-status labels in frontend `components/runs/*` | per-week term splitting (Bahar term ≥96 % placed), weight calibration (course ≥85 %, exam ≥50 % reproduction), planner data-issues report + xlsx, FEASIBLE_PARTIAL status, planner-facing TR/EN diagnoses, exam overflow + board-vs-list groups | 10:21 planner TR/EN texts + unplaced-first ordering; later writing `app/solver/calibrate.py` | finish calibration, data-issues endpoint, measurements in `docs/testing/2026-10-08-real-data-feasibility.md` |
| 2 | Review fixes (backend-engineer) | many backend files: `core/safe_files.py`, `core/export_safety.py`, exports, imports, queue, studio*, chat.py, constraints.py, runs.py (small edits) | fix B1–B3, M1–M13 of `docs/review/2026-10-08-backend-ai-studio-review.md`, U1–U6 from the usability test, cheap minors; **own the whole backend `make check` going green** | 11:24 U1–U6 done (cohort-key helper, draft race, merged ids, real key probe, exam weeks, İ folding) | remaining minors, widen gate (app/ai, app/api types), all tests green, finding→fix→test table |
| 3 | CRBS parity bug fixes (backend-engineer) | `services/bookings*.py`, `api/v1/{bookings,booking_admin,org,terms,room_admin,rooms}.py`, `importers/crbs_legacy.py`, `core/security.py`, models/booking.py, new alembic rev | B1–B16 + missing 2–6 of `docs/review/2026-10-08-crbs-parity-audit.md`; CRBS-default behaviour with settings, safer security defaults | 11:48 B4 importer retargeted (roles, users with legacy hashes, constraints, groups, ACL, schedules, sessions, weeks, holidays, bookings) | remaining B-items, i18n/date-pattern endpoints, check_session_dates, tests |
| 4 | Glass redesign — shell & pages (frontend-engineer) | `app/layout.tsx`, `components/providers.tsx`, `components/shell/**`, login, `app/(app)/{dashboard,import,generate,runs,settings}/**`, `components/{dashboard,import,studio,runs,chat,settings,common}/**`, `lib/api/shell-extra.ts`, messages (append) | apply Liquid Glass v2 + motion skill; ⌘K course search; remember term/run/week; partial-run amber status; free components only (reverseui free if terms allow, else own); permissions-based nav (import `components/admin/nav-items.ts`); stable `data-testid`s for recordings | 10:49 appearance wired; shell = SidebarGlass + capsules + mobile tab bar; later editing command palette, run view | dashboard/run report/chat/studio/import/settings restyle, screenshots, A1–A12 self-review |
| 5 | Glass redesign — calendar, classes, rooms (frontend-engineer) | `components/{timetable,classes,requests,rooms}/**`, `app/(app)/{timetable,classes,requests,rooms}/**`, `lib/api/{classes,calendar}.ts`, backend new files `api/v1/calendar.py`, `services/calendar_views.py`, `schemas/calendar.py` | six calendar lenses, `/classes` all-classes view (provenance, saved views, export with "SmartSched Derslik"), rooms; TanStack grouping instead of paid tables; test ids | 10:40 backend calendar endpoints; later writing classes page, bulk move, calendar data hook | finish lenses + DnD + inspector, rooms, e2e/calendar.spec.ts, motion audit |
| 6 | CRBS booking & admin screens (frontend-engineer) | `app/(app)/{bookings,my-bookings,admin}/**`, `app/setup/**`, `app/reset-password/**`, `components/{bookings,admin}/**`, `lib/api/crbs.ts`, `lib/permissions.ts`, small backend edit for `bookings.show_ungrouped_rooms` | full CRBS UI: grid (displaytype/d_columns, grid_highlight, print, room popup, icons, week colours), my bookings + ICS, all admin screens, setup wizard, reset password, profile language; ungrouped rooms hidden by default with toggle | 11:41 /bookings grid with tabs, date picker, single/recurring sheet, multi-select | my-bookings, admin screens, setup/reset, e2e/bookings.spec.ts |

## Finished workstreams (output already committed)

Data analysis, architecture, research, design v1 specs, backend Phase 1, CP-SAT solver, AI layer, frontend v1, integration,
real-data feasibility, Generator Studio (design/backend/frontend), deploy + compose, README v1 + Lottie + screenshots v1,
universal edition + council + Ruflo harness (branch `claude/smartsched-universal`), Liquid Glass system, `/motion_designer`
skill + motion spec, calendar/all-classes specs, CRBS parity backend + audit, booking-enhancements product research,
recording pipeline (Recordly), strict review (backend/AI/studio), planner usability test, AWS OIDC role + budget, pod
bootstrap + pod CI.

## Queued waves (start when the listed blockers finish)

| Wave | Starts after | Content |
|---|---|---|
| A | #2, #3 and #1 finish | no-placeholder audit (remove MSW mock mode, stub solver fallback, placeholder photos; e2e on real backend), schedule comparison vs the planner's grids, strict solver review |
| B | #3 and #6 finish | CRBS superset gate (phase 18): acceptance test per behaviour + `scripts/parity_check.py`, 13 CRBS languages + Turkish, legacy upgrade verified against a real CRBS on the pod (`--profile legacy`), side-by-side diff |
| C | wave B | booking enhancements wave 1 (phase 17): room features, find-a-room, notification hub + native Outlook/Google/Teams connectors + webhooks, audit log, approvals by designated admin approvers, conflict resolver, policies, public view, KVKK record; optional Activepieces profile |
| D | #4, #5, #6 finish | screenshots v2, recordings (`scripts/record/record-all.sh`, English captions), README rewrite (plain editorial style, real screenshots) |
| E | each wave | merge `claude/gracious-cerf-w1598m` into `claude/smartsched-universal`; restyle onboarding |

## AWS pod (live)

- Instance `i-0c04b735e03446110` (t4g.large, us-east-1), EIP `98.86.98.164`, panel `https://98-86-98-164.sslip.io`.
- Admin `umutk@getvivax.com`; password in SSM `/smartsched/admin_password` (read with AWS CloudShell).
- Budget `smartsched-monthly-100usd` with stop action at 100 %; idle-stop alarm (CPU < 5 % for 60 min).
- Control by pushing `infra/aws/POD_ACTION` with `up|status|stop|start|cost|down destroy` (OIDC role, no keys).
- Pod CI polls both branches every 2 min, runs the gates in Docker, posts commit statuses, serves `/ci/`, redeploys the deploy branch.

## User decisions to respect (see docs/ROADMAP.md "User decisions" and docs/product/booking-enhancements.md)

BLUF reports; no GitHub Actions on push; no paid UI components; English README/captions; CRBS behaviour by default with
settings; departments = programmes; ungrouped rooms hidden by default with toggle; approvers = designated administrators;
KVKK signed off by the user (AI booking + calendar sync on, switchable); check-in reminders-first; default model
claude-opus-5-5; trust planner-locked rooms with visible data issues.
