<h1 align="center">SmartSched</h1>

<p align="center">
  Classroom and exam planning for a university, built on top of classroombookings.
</p>

<p align="center">
  <a href="https://www.gnu.org/licenses/agpl-3.0.html"><img alt="License: AGPLv3" src="https://img.shields.io/static/v1?label=License&message=AGPLv3&color=3DA639&style=flat-square"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white">
  <img alt="OR-Tools CP-SAT" src="https://img.shields.io/badge/OR--Tools-CP--SAT-4285F4?style=flat-square&logo=google&logoColor=white">
</p>

SmartSched is for the office that plans a faculty's rooms each term, and for the staff who book those
rooms. Today that office works in Excel: a planning list of every section, a weekly room grid, a room
list, and a lot of checking by hand. SmartSched reads those workbooks as they are, places every class
it can into a room and a period without breaking a hard rule, and says plainly which classes it could
not place and why.

It is a superset of [classroombookings](https://www.classroombookings.com/) (CRBS): rooms, room
groups, periods, sessions, holidays, single and recurring bookings, roles and permissions all work
the way they do in CRBS, checked row by row by a parity gate. The planning side (imports, the solver,
the calendar, the run report) is new. The legacy PHP app is still in this repository and SmartSched
can import its database.

<p align="center">
  <a href="docs/images/recordings/import-generate.mp4">
    <img alt="Screen recording: the weekly room grid and the planning list of Bahar 2026 are imported into an empty term, each with an import report; week 3 is generated in the Generator Studio; the run report shows how many classes were placed with every hard rule kept, then the first class that could not be placed, with its reason and suggested fixes." src="docs/images/recordings/import-generate.webp" width="960">
  </a>
  <br>
  <sub>From two Excel files to a checked timetable: import the Bahar 2026 workbooks, generate week 3, read the report.
  Waits for the import jobs and the solver are cut. <a href="docs/images/recordings/import-generate.mp4">MP4</a></sub>
</p>

Four more recordings, each under a minute, all made against the real backend with the real 2026 data
(how: [Recordings and screenshots](#recordings-and-screenshots)).

<table>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/calendar-move.mp4"><img alt="Screen recording: room A 204's week in the calendar; a class is opened in the inspector, moved to a free room that the server confirms fits, and the move is undone." src="docs/images/recordings/calendar-move.webp"></a>
      <br><sub><b>Calendar.</b> Open a class, move it to a free room the server has checked, undo. <a href="docs/images/recordings/calendar-move.mp4">MP4</a></sub>
    </td>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/studio-rule-fix.mp4"><img alt="Screen recording: in the Generator Studio a rule is added from a template, the pre-check reports problems in the term's data, and one suggested fix is applied." src="docs/images/recordings/studio-rule-fix.webp"></a>
      <br><sub><b>Generator Studio.</b> Add a rule from a template, run the pre-check, apply one of its fixes. <a href="docs/images/recordings/studio-rule-fix.mp4">MP4</a></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/room-booking.mp4"><img alt="Screen recording: the day booking grid for A building; a free period in room A 203 is picked, a note is added and the booking is saved; it then appears under My bookings." src="docs/images/recordings/room-booking.webp"></a>
      <br><sub><b>Bookings.</b> Pick a free period, add a note, book it, find it under My bookings. <a href="docs/images/recordings/room-booking.mp4">MP4</a></sub>
    </td>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/admin-user.mp4"><img alt="Screen recording: Setup, Users; a new account for the planning office is created and given the Planner role in the role picker." src="docs/images/recordings/admin-user.webp"></a>
      <br><sub><b>Administration.</b> Create an account and pick its role; roles you could not grant are greyed out. <a href="docs/images/recordings/admin-user.mp4">MP4</a></sub>
    </td>
  </tr>
</table>

## Quick start

### Docker, one command

Docker Engine 24+ with the Compose v2 plugin is all the host needs.

```bash
cd smartsched/deploy
./deploy.sh        # writes .env with random secrets, builds, starts, waits for /api/v1/health
# SmartSched is up at http://localhost:8080; the admin login is ADMIN_EMAIL / ADMIN_PASSWORD in .env
```

This starts PostgreSQL, the FastAPI backend, the Next.js frontend and nginx. Useful flags:
`--tls` adds a Caddy HTTPS edge, `--legacy` also runs the original classroombookings (PHP 8.3 and
MySQL 8.4) for live imports, `--update` pulls, rebuilds and migrates, `--down` stops the stack and
keeps the data. The full list, backups and sizing are in
[smartsched/deploy/README.md](smartsched/deploy/README.md).

### On AWS

One EC2 instance (t4g.large) runs the whole stack behind Caddy TLS, plus the project's CI. It is
created and controlled by pushing one word (`up`, `status`, `stop`, `start`, `down`) to
`infra/aws/POD_ACTION`; a GitHub OIDC role does the AWS calls, so no keys are stored. A budget
action stops the instance at 100 USD a month and an alarm stops it after an idle hour; running all
month costs about 57 USD in us-east-1. Setup and costs: [docs/deploy/AWS.md](docs/deploy/AWS.md).

### Local development

Python 3.12+ and Node 22+.

```bash
scripts/dev.sh --run     # venv + npm ci, SQLite, seeded admin, backend :8000, frontend :3000
```

The admin is your `git config user.email` (or `DEV_ADMIN_EMAIL`) with a random password printed once.
The frontend always talks to the real backend.

### Load the real 2026 data

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

## How it works

1. **Import.** Planning lists, exam lists and weekly room grids are read from the office's workbooks;
   a room master CSV corrects capacities and tags. Turkish day names, dotted times, comma decimals,
   room spellings such as `A 101`, `A101` and `B Blok Bilg. Lab.` and multi-value cells are normalised
   ([docs/DATA_ANALYSIS.md](docs/DATA_ANALYSIS.md)). Every import ends with a report of what was read,
   what was skipped and why.
2. **Rules.** Settings, rule templates, the workbooks themselves and, with an Anthropic API key,
   sentences in Turkish or English all become the same thing: a typed rule that is either *Must*
   (hard) or *Try to* (soft, weighted), with a link to where it came from. Nothing written by the AI is
   used until a person accepts it.
3. **Pre-check.** Before solving, the Generator Studio checks the plan against the data and lists what
   cannot work (a locked room that is too small, two classes locked into one room at once), each with
   fixes.
4. **Solve.** OR-Tools CP-SAT places classes into rooms and periods for a week, a month or the whole
   term (14 weeks), or exams into exam slots.
5. **Validate and explain.** Scores are computed again in plain Python from the finished timetable, so
   the solver, manual moves and AI edits are judged by the same code. Anything not placed is explained
   one class at a time.

<table>
  <tr>
    <td align="center" width="50%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/nl-to-rules-dark.gif">
        <img alt="Animation: a Turkish sentence becomes a typed rule card that can be reviewed before it is used" src="docs/images/lottie/nl-to-rules-light.gif" width="360">
      </picture>
      <br><sub>With an API key, a sentence becomes a rule you review before it is used (illustration).</sub>
    </td>
    <td align="center" width="50%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/file-to-rules-dark.gif">
        <img alt="Animation: rows of an uploaded preference file become rule cards, each linked to its source row" src="docs/images/lottie/file-to-rules-light.gif" width="360">
      </picture>
      <br><sub>Rules read from an uploaded file keep a link to their source row (illustration).</sub>
    </td>
  </tr>
</table>

### Hard rules, waived exceptions and partial runs

The hard rules are: a room seats the class, a room holds one class at a time, a cohort and an
instructor are in one place at a time, fixed times stay fixed, and a class that needs a lab gets one.
SmartSched never relaxes one of them quietly.

Real planning data breaks these rules in a few known ways, and the planner usually knows. A class is
locked into a room with fewer seats than its enrolment estimate; two fixed classes of the same
instructor overlap; two rows lock the same room at the same time. SmartSched does not overrule the
planner here. It keeps the planner's decision, records each case as a *waived exception* with the
class and the room named, and lists them under *Problems in your data* in the run report, grouped and
exportable to Excel. Three switches control this, all on by default and all per run:
trust the planner's locked rooms, treat clashes between fixed classes as warnings, and keep the best
partial timetable when not everything fits
([solver README](smartsched/backend/app/solver/README.md#real-data-modes-d1d3)).

When not every class can be placed, the run is **partial**, labelled for example
*Partial · 522/548 placed*. A relaxation first proves the largest number of classes that can be
placed, keeping the planner's locks where it can; the placed classes are then optimised for the soft
rules. Every placed class keeps every hard rule (hard score 100, checked independently). Each class
left out is listed with the reason (for example: *every room that fits is taken at that time*, with
the rooms and what holds them) and with fixes such as freeing a named room. Applying a fix creates a
new run; the old one stays as it was.

Claude is optional and is never the planner. It turns sentences and files into rule proposals,
proposes edits from the chat panel, and writes explanations. Every proposal goes through the same
validation as a manual move. Import, solving, the calendar, bookings and manual edits work without a
key. Details: [solver README](smartsched/backend/app/solver/README.md),
[AI README](smartsched/backend/app/ai/README.md), [research notes](docs/RESEARCH.md).

## Measured on the real data

From [docs/testing/2026-10-08-real-data-feasibility.md](docs/testing/2026-10-08-real-data-feasibility.md):
the planning office's 2026 workbooks, the run settings a planner gets by default, 4 vCPU shared with
other work, CP-SAT with 4 workers.

| Instance | Status | Classes placed | Placed in the planner's locked rooms | Hard score | Wall time |
|---|---|---|---|---|---|
| Bahar 2026, whole term (14 weeks) | partial | 643 / 669 (96.1 %) | 511 / 523 (97.7 %) | 100 | 252 s |
| Bahar 2026, week 3 | partial | 649 / 668 (97.2 %) | 515 / 522 (98.7 %) | 100 | 51 s |

For the term, both the relaxation and the second phase finish proven optimal, so 643 is the most this
data allows under the hard rules, not a time-limit result. Of the 12 locks that are not kept, 8 are
errors in the planner's own data (7 pairs of locked rows holding the same room at the same time, and
one class locked to a room the grid blocks).

When the planner's rooms are only hints instead of locks, the solver chooses the planner's room for
**89.7 %** of course classes (855 / 953, Bahar and Güz week 3) and **80.9 %** of exams, with every hard
rule kept. Before this work, the same Bahar data ended *infeasible within 0.05 s, with 356 diagnoses
and no timetable*.

The recordings and screenshots on this page come from a fresh import of the same workbooks and two
runs made through the API for Güz 2026-27: week 3 placed 522 of 548 classes and the whole term 519
of 548, both with hard score 100.

The classroombookings side is checked by the CRBS superset gate
([docs/testing/crbs-parity-report.md](docs/testing/crbs-parity-report.md)): 182 rows, one per CRBS
behaviour, audit item or screen, each tied to API tests on the real Bahar data and, where there is a
screen, to a Playwright test against the real backend. The run committed on 2026-10-08 at 15:00 UTC
passed: 153 rows pass, 29 are declared gaps with a reason and a proposed fix, none fail; 109 API tests
ran. The gate runs in CI, so the report file always shows the latest run.

## Screenshots

All screenshots show the real 2026 data, at 1440 px wide, in light or dark mode following your GitHub
theme.

**Dashboard.** Room use for the week, classes that still need a room, requests waiting for review,
and use by building and day for the published run.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/dashboard-dark.webp">
  <img alt="Dashboard for Güz 2026-27, week 3: room use 26 percent, 29 classes still needing a room in run 8, 141 requests waiting for review, a line chart of rooms in use through the day and a building by day heat map" src="docs/images/screens/dashboard-light.webp" width="960">
</picture>

**Generator Studio.** Scope, classes, rules, pre-check and generate, with a running summary of what
will happen.

<table>
  <tr>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-scope-dark.webp">
      <img alt="Studio scope step: the term, classes or exams, one week, a month or the whole term, and a sentence saying how many classes will be planned in how many rooms" src="docs/images/screens/studio-scope-light.webp" width="480">
    </picture></td>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-rules-dark.webp">
      <img alt="Studio rules step: one-click common rules, and the term's rules listed as sentences grouped into Must and Try to" src="docs/images/screens/studio-rules-light.webp" width="480">
    </picture></td>
  </tr>
  <tr>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-precheck-dark.webp">
      <img alt="Studio pre-check: the plan is blocked, with problems grouped by kind, such as classes locked to a room that does not fit, and a card naming two classes locked into the same room with fix buttons" src="docs/images/screens/studio-precheck-light.webp" width="480">
    </picture></td>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-report-dark.webp">
      <img alt="Run report for a partial run: 522 of 548 placed with no rule broken, 26 unplaced, soft preference score 88, and the first class without a room with its fixes" src="docs/images/screens/run-report-light.webp" width="480">
    </picture></td>
  </tr>
</table>

**Run report.** Each class that could not be placed, with the reason and fixes; below it, the problems
found in the workbooks themselves.

<table>
  <tr>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-diagnoses-dark.webp">
      <img alt="Classes without a room: each card names the class, its size and time, the rooms that would fit and which classes hold them, with options to free one of those rooms" src="docs/images/screens/run-diagnoses-light.webp" width="480">
    </picture></td>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-data-issues-dark.webp">
      <img alt="Problems in your data: fixed-time instructor clashes, planned rooms too small, classes without an enrolment, fixed-time cohort clashes, lectures listed twice, with an Excel download" src="docs/images/screens/run-data-issues-light.webp" width="480">
    </picture></td>
  </tr>
</table>

**Calendar.** Six views of one run (Board, Week, Day, Month, Term, Agenda) and an inspector that shows
when and where a class is, why it is there and what conflicts with it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-board-dark.webp">
  <img alt="Calendar Board view for week 3: the rooms of A building as columns, periods as rows, classes as coloured blocks with seats used and the instructor" src="docs/images/screens/calendar-board-light.webp" width="960">
</picture>

<table>
  <tr>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-week-dark.webp">
      <img alt="Calendar Week view of room A 204: Monday to Friday with the room's classes and markers where classes share the room" src="docs/images/screens/calendar-week-light.webp" width="480">
    </picture></td>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-inspector-dark.webp">
      <img alt="Class inspector next to the week: time and room, seats used, instructor and programme, and a checklist of why the class is in this room" src="docs/images/screens/calendar-inspector-light.webp" width="480">
    </picture></td>
  </tr>
  <tr>
    <td colspan="2"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-term-dark.webp">
      <img alt="Calendar Term view of the planner's Bahar 2026 board: a heat map of room use for each day of the 15 weeks" src="docs/images/screens/calendar-term-light.webp" width="960">
    </picture></td>
  </tr>
</table>

**All classes and rooms.** Every section of the term with its status, programme, instructor, size and
room; every room with its seats, tags and use through the week.

<table>
  <tr>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/classes-dark.webp">
      <img alt="All classes: 1,036 classes grouped by faculty with status, course, programme, year, instructor, students and room, and filters for unplaced, issues, changed and evening classes" src="docs/images/screens/classes-light.webp" width="480">
    </picture></td>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/rooms-dark.webp">
      <img alt="Rooms: 87 rooms in 4 buildings as cards with seats, exam seats, floor, tags and a bar per weekday for occupancy" src="docs/images/screens/rooms-light.webp" width="480">
    </picture></td>
  </tr>
  <tr>
    <td colspan="2"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/room-detail-dark.webp">
      <img alt="Room A 204: its week as a grid of periods, a free-slot finder, term occupancy and the list of classes in the week" src="docs/images/screens/room-detail-light.webp" width="960">
    </picture></td>
  </tr>
</table>

**Bookings.** The classroombookings grid: rooms by period for a day, with the published timetable
already in place, and each person's own bookings with a calendar feed and CSV export.

<table>
  <tr>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/bookings-dark.webp">
      <img alt="Booking grid by day for A building: rooms as rows and the 18 periods as columns, slots held by the timetable, and one booking of the signed-in user" src="docs/images/screens/bookings-light.webp" width="480">
    </picture></td>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/my-bookings-dark.webp">
      <img alt="My bookings: upcoming, past and cancelled tabs, one upcoming booking, a calendar subscription link and a CSV export" src="docs/images/screens/my-bookings-light.webp" width="480">
    </picture></td>
  </tr>
</table>

<details>
<summary><strong>Administration, settings, sign-in, phone and Turkish</strong></summary>

<br>

<table>
  <tr>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/admin-users-dark.webp">
      <img alt="Setup, Users: accounts with e-mail, role, department and last sign-in, with search and filters" src="docs/images/screens/admin-users-light.webp" width="480">
    </picture></td>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/admin-roles-dark.webp">
      <img alt="Setup, Roles: the Administrator, Planner, Teacher and Viewer roles, booking limits and permissions grouped like classroombookings" src="docs/images/screens/admin-roles-light.webp" width="480">
    </picture></td>
  </tr>
  <tr>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/setup-requirements-dark.webp">
      <img alt="Setup checklist: what bookings need, in order, and the server requirements with their status" src="docs/images/screens/setup-requirements-light.webp" width="480">
    </picture></td>
    <td><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/settings-appearance-dark.webp">
      <img alt="Settings, Appearance: theme, accent colour, density, reduce motion and reduce transparency" src="docs/images/screens/settings-appearance-light.webp" width="480">
    </picture></td>
  </tr>
  <tr>
    <td colspan="2"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/login-dark.webp">
      <img alt="Sign-in page with e-mail or username, password, a forgot password link and a Turkish and English switch" src="docs/images/screens/login-light.webp" width="960">
    </picture></td>
  </tr>
</table>

On a phone the sidebar becomes a tab bar, and the calendar's Day view becomes a list.

<table>
  <tr>
    <td align="center"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-dashboard-dark.webp">
      <img alt="Dashboard on a phone with the tab bar at the bottom" src="docs/images/screens/mobile-dashboard-light.webp" width="260">
    </picture></td>
    <td align="center"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-calendar-dark.webp">
      <img alt="Calendar Day view on a phone: the week strip and room A 204's classes for Monday as a list" src="docs/images/screens/mobile-calendar-light.webp" width="260">
    </picture></td>
  </tr>
</table>

The interface is in Turkish and English; these two are in Turkish.

<table>
  <tr>
    <td><img alt="The dashboard in Turkish" src="docs/images/screens/dashboard-tr-light.webp" width="480"></td>
    <td><img alt="The Studio rules step in Turkish, with rules shown as Turkish sentences" src="docs/images/screens/studio-rules-tr-light.webp" width="480"></td>
  </tr>
</table>

</details>

## Relation to classroombookings

This repository is a fork of classroombookings by Craig A Rodway. The original PHP app is unchanged at
the root (`crbs-core/`, `index.php`, `assets/`), and `./deploy.sh --legacy` runs it next to
SmartSched. SmartSched imports its database: users with their password hashes, roles, access lists and
bookings. The import is tested on CRBS's own install SQL; an upgrade of a running CRBS server is still a
declared gap in the parity report.

What stays the same: the booking grid by day or by room, single and recurring bookings, booking
limits, holidays and timetable weeks, roles with the CRBS permissions, room access lists, LDAP
sign-in, the CSV export columns. What is added: the planning side, calendar feeds, an e-mail outbox,
and a published timetable that bookings can never collide with. Where SmartSched behaves differently
on purpose (mostly security, such as no privilege escalation in the role editor, or keeping booking
history when a user is deleted), the difference is listed with its setting, if there is one, in
[docs/CRBS_PARITY.md](docs/CRBS_PARITY.md) and asserted by the parity gate.

## Development

```
smartsched/
  backend/    FastAPI, SQLAlchemy 2, Alembic, OR-Tools CP-SAT, Anthropic SDK; tests/fixtures holds the real workbooks
  frontend/   Next.js 16, TypeScript, Tailwind 4, TanStack Query, dnd-kit, motion
  deploy/     docker compose, deploy.sh, nginx, Caddy, the legacy CRBS image, pod CI
infra/aws/    the AWS pod (boto3 CLI, IAM, user data)
scripts/      dev.sh, record/ (recordings and screenshots), parity_check.py, watchdog.py
docs/         architecture, roadmap, data analysis, design specs, test reports
```

| Command | What it runs |
|---|---|
| `make -C smartsched check` | backend ruff, mypy and pytest (including the real workbooks), frontend tsc, eslint and vitest |
| `make -C smartsched check-all` | the above plus the solver and AI gates and `deploy/validate.sh` |
| `E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test` | every Playwright spec against a real backend started with `smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh` |
| `python3 scripts/parity_check.py` | the CRBS superset gate; writes `docs/testing/crbs-parity-report.md` |
| `cd smartsched/backend && SMARTSCHED_SLOW=1 python -m pytest tests/test_real_feasibility.py -q` | the real-data feasibility assertions |

CI runs on the AWS pod, not on GitHub-hosted runners: it polls the repository, runs the gates in
Docker (including the real-backend Playwright run and the parity gate), posts commit statuses and
redeploys the deploy branch when it is green ([smartsched/deploy/pod-ci/README.md](smartsched/deploy/pod-ci/README.md)).
`.github/workflows/smartsched.yml` runs the same gates by hand.

Configuration is through environment variables (`DATABASE_URL`, `APP_SECRET`, `ADMIN_EMAIL`,
`ADMIN_PASSWORD`, `ANTHROPIC_API_KEY`, `SOLVER_WORKERS`, …), documented in
[smartsched/README.md](smartsched/README.md) and `smartsched/deploy/.env.example`. The Anthropic key
can also be stored, encrypted, under Settings → AI; the default model is `claude-opus-5-5`.

More documentation:

| Document | Contents |
|---|---|
| [smartsched/README.md](smartsched/README.md) | developer guide: backend, frontend, CLI, environment, API |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | design principles, domain model, solver contract, API surface |
| [docs/DATA_ANALYSIS.md](docs/DATA_ANALYSIS.md) | the workbook shapes, column meanings and quirks |
| [docs/ROADMAP.md](docs/ROADMAP.md) | phases, decisions and backlog |
| [docs/CRBS_PARITY.md](docs/CRBS_PARITY.md) | classroombookings behaviour and the deliberate differences |
| [docs/design/](docs/design/) | UI specs, including the Liquid Glass system and the calendar |
| [docs/testing/](docs/testing/) | test reports: real-data feasibility, real-backend end to end, CRBS parity |
| [docs/deploy/AWS.md](docs/deploy/AWS.md) | the AWS pod |
| [docs/AGENTS.md](docs/AGENTS.md), [docs/PROGRESS.md](docs/PROGRESS.md) | SmartSched is built by parallel Claude Code agents; their protocol and ledger |

### Recordings and screenshots

Everything above was captured by scripts in [`scripts/record/`](scripts/record/), against the real
backend and a production build of the frontend, never against mock data:

```bash
scripts/record/stack.sh up && scripts/record/stack.sh runs   # import the three terms, make two solver runs
node scripts/record/screens.mjs                                # screenshots, light and dark
scripts/record/record-all.sh /tmp/recordings                   # the five recordings: MP4, animated WebP, poster
```

The recordings are driven by Playwright, captured with Playwright's own video, and finished with
ffmpeg in the style of [Recordly](https://github.com/webadderallorg/Recordly) (camera zoom on the
action, an enlarged cursor, click ripples, captions). Each take also writes a `.recordly` project that
opens in Recordly for hand editing. Recordly's own renderer does run headless in a Linux container but
needs about 13 minutes per 17 seconds of video, so it was not used for these files. Details:
[docs/recording/RECORDLY.md](docs/recording/RECORDLY.md).

---

## Legacy classroombookings

### classroombookings - open source room booking system for schools.

By Craig A Rodway.

[![License: AGPLv3](https://img.shields.io/static/v1?label=License&message=AGPLv3&color=3DA639&style=flat-square)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Twitter Follow](https://img.shields.io/twitter/follow/crbsapp.svg?style=social)](https://twitter.com/crbsapp)

This is a web-based room booking system for schools and is designed to be as easy to use as possible. Set up your bookable rooms, day schedule and timetable for the year. Add user accounts, and allow them to make and manage bookings from anywhere.

It is available to [download and install yourself](https://www.classroombookings.com/self-host/) or there is a great value [hosted service](https://www.classroombookings.com/pricing/).

It is web-based - PHP and MySQL - and currently uses the [CodeIgniter 3](https://codeigniter.com/) framework.

#### Documentation
For installation instructions and configuration guide, please [read the documentation pages](https://www.classroombookings.com/docs/self-hosted/).

#### Bug Reports & Feature Requests
Please check out [GitHub Issues](https://github.com/craigrodway/classroombookings/issues) to view existing issues or open a new bug report.

#### Security
To report any security issues, please email craig@classroombookings.com instead of using the issue tracker.

#### Credits

This project makes use of several third parties, some of which are listed below.

- [CodeIgniter](https://codeigniter.com/) (MIT)
- [Unpoly](https://unpoly.com/) (MIT)
- [FamFamFam Silk Icons](http://www.famfamfam.com/lab/icons/silk/) ([CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), Unmodified)

## Licence

This repository is licensed under the
[GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0.html). See
[LICENSE.txt](LICENSE.txt).
