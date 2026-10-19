<h1 align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/brand/readme-header-dark.svg"><img alt="SmartSched" src="docs/images/brand/readme-header-light.svg" width="640"></picture></h1>

<p align="center"><b>Timetabling, exam planning and room booking for a university.</b><br>
<sub>Ders programı, sınav planı ve derslik rezervasyonu: tek bir açık kaynak uygulamada.</sub></p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/HOW_IT_WORKS.md">How it works</a> ·
  <a href="#documentation">Docs</a> ·
  <a href="docs/ROADMAP.md">Roadmap</a> ·
  <a href="#türkçe">Türkçe</a> ·
  <a href=".github/CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  <a href="LICENSE.txt"><img alt="License: AGPL-3.0" src="https://img.shields.io/badge/License-AGPL--3.0-3DA639?style=flat-square"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white">
  <img alt="OR-Tools CP-SAT" src="https://img.shields.io/badge/OR--Tools-CP--SAT-4285F4?style=flat-square&logo=google&logoColor=white">
  <img alt="PostgreSQL 16" src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white">
</p>

<a href="docs/launch/media/smartsched-launch.mp4">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="docs/launch/media/smartsched-hero-poster.png">
    <img alt="SmartSched on the desktop: a full-term solver run that keeps every hard rule is published, a room is found and booked, a class is moved in the timetable" src="docs/launch/media/smartsched-hero.webp" width="100%">
  </picture>
</a>
<sub>▶ <a href="docs/launch/media/smartsched-launch.mp4">Launch video (1080p60, MP4)</a> ·
<a href="docs/launch/media/smartsched-launch-av1.webm">AV1</a> ·
<a href="docs/launch/media/smartsched-launch-vertical.mp4">vertical, for phones</a> ·
<a href="docs/launch/media/smartsched-loop.webp">booking on a phone (loop)</a></sub>

https://github.com/user-attachments/assets/ef9a1d4a-ab84-43d8-abc6-15e5bd7fd8b4

SmartSched reads the Excel workbooks a planning office already keeps, places every class it can with a
CP-SAT solver, explains the ones it cannot place, and runs the
[classroombookings](https://www.classroombookings.com/) booking grid on top of the result. It is a
superset of classroombookings: every behaviour of the original is kept and checked by a parity gate.

> [!NOTE]
> SmartSched is young. Most of it was built in October 2026 and is tested on the real 2026 workbooks of one
> university. Several recent screens are tested at unit level only so far; [docs/STATUS.md](docs/STATUS.md)
> says which, and [docs/ROADMAP.md](docs/ROADMAP.md) has the open browser checks.

## See it work

<!-- AUTO:recordings -->

Recorded on the real backend with the real 2026 workbooks, rendered offline at 60 fps (docs/launch/README.md). Instructor names are reduced to initials. Each clip opens its full take (MP4).

<table>
  <tr>
    <td width="33%" valign="top">
      <a href="docs/images/recordings/find-room.mp4"><picture><source srcset="docs/launch/media/clips/find-room.webp" type="image/webp"><img alt="Screen recording: Find a room. Head count and a feature. Rooms that fit come first, near fits after, each with its reason." src="docs/images/recordings/find-room.gif" width="100%"></picture></a>
      <br><sub><b>Find a room.</b> Head count and a feature. Rooms that fit come first, near fits after, each with its reason.</sub>
    </td>
    <td width="33%" valign="top">
      <a href="docs/images/recordings/reserve-panel.mp4"><picture><source srcset="docs/launch/media/clips/reserve-slot.webp" type="image/webp"><img alt="Screen recording: Reserve a free period. Point at a free period, click, confirm. The cell then shows You." src="docs/images/recordings/reserve-slot.gif" width="100%"></picture></a>
      <br><sub><b>Reserve a free period.</b> Point at a free period, click, confirm. The cell then shows You.</sub>
    </td>
    <td width="33%" valign="top">
      <a href="docs/images/recordings/calendar-move.mp4"><picture><source srcset="docs/launch/media/clips/calendar-move.webp" type="image/webp"><img alt="Screen recording: Move a class. Only free rooms that fit are offered. The server checks the move before it is saved." src="docs/images/recordings/calendar-move.gif" width="100%"></picture></a>
      <br><sub><b>Move a class.</b> Only free rooms that fit are offered. The server checks the move before it is saved.</sub>
    </td>
  </tr>
</table>

[More clips](docs/launch/README.md#more-clips) (7 more clips, 11 full takes) are in the launch notes.

<!-- /AUTO:recordings -->

## Why SmartSched

<table>
  <tr>
    <td valign="top">

**Starts from the files you have.** The planning list, the weekly room grid, the exam list and the room master
are read as they are. Each import ends with a report of what was read and what was skipped.

**Never relaxes a hard rule quietly.** A room must seat its class; one class per room, one place per instructor
and cohort; fixed times and labs. A class that cannot be placed is listed with the reason and the fixes that
would place it.

**Booking stays as simple as classroombookings.** Look at the week, click a free period, book. The published
timetable holds its slots, so a booking never collides with a class.

**Runs on your own server.** One command on a Docker host. AI features are off until an administrator turns
them on, and everything else works without a key.

  </td>
    <td width="280" valign="top"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/launch/media/smartsched-loop-poster.png"><img alt="Booking on a phone: Quick reserve picks tomorrow, a free period and a room, then Reserve" src="docs/launch/media/smartsched-loop.webp" width="260"></picture></td>
  </tr>
</table>

<!-- AUTO:parity -->

**CRBS superset gate: PASS**: PASS 179 · GAP 13 · FAIL 0 · MISSING 0 of 192 rows, measured on commit `5d0e6c2` (2026-10-15 22:10 UTC) by `scripts/parity_check.py`. Full table: [`crbs-parity-report.md`](docs/testing/crbs-parity-report.md).

<!-- /AUTO:parity -->

## Features

<table>
  <tr>
    <td width="33%" valign="top"><b>Import</b><br><sub>Planning lists, exam lists, weekly room grids, a room master CSV and a running classroombookings database. xlsx, xls, ods, csv, tsv, json, xml and ics are read without AI, with a dry-run diff first.</sub></td>
    <td width="33%" valign="top"><b>Plan</b><br><sub>OR-Tools CP-SAT for a week, a month, the whole term or the exam period. Generator Studio with a pre-check, partial runs, A/B scenario comparison, invigilator assignment and a minimal-change re-solve.</sub></td>
    <td width="33%" valign="top"><b>Book</b><br><sub>The booking grid by day or by room, recurring and multi bookings, limits and holidays. Quick reserve, find a room by head count and feature, approvals with a reason.</sub></td>
  </tr>
  <tr>
    <td valign="top"><b>Calendars</b><br><sub>Private ICS feeds (my bookings, a room, a department) with Google, Outlook and Apple buttons; push into Google Calendar and Microsoft 365 once an administrator adds the OAuth client.</sub></td>
    <td valign="top"><b>Trust</b><br><sub>An append-only audit log with undo, a publish guard that refuses failed runs, a planner-level validator against the raw workbook rows, and the classroombookings parity gate.</sub></td>
    <td valign="top"><b>Sign-in</b><br><sub>Microsoft Entra ID, Google Workspace, any OpenID Connect issuer, SAML 2.0 and LDAP, with invitations. Tokens are revoked on sign-out, password change and role change.</sub></td>
  </tr>
  <tr>
    <td valign="top"><b>Notifications</b><br><sub>In-app bell, themed e-mails in Turkish and English with guided SMTP setup, channels through Apprise (Telegram, Teams, Slack and more) and signed webhooks for n8n or Zapier.</sub></td>
    <td valign="top"><b>AI on request</b><br><sub>Off by default. A sentence or an uploaded file becomes a rule that a person reviews. Admins pick the provider (Anthropic, OpenAI, Azure, Gemini, Bedrock, a local OpenAI-compatible server) and set budgets.</sub></td>
    <td valign="top"><b>Operations</b><br><sub>One-command Docker deploy, optional HTTPS through Caddy, nightly backups, Prometheus, Loki and Grafana with Turkish dashboards, an operations panel and grouped error tracking.</sub></td>
  </tr>
</table>

Each tile is drawn from the Done items in [`docs/features.yml`](docs/features.yml); the generated list with the
test behind each one is [below](#what-is-built).

### Compared with what it replaces

| | Spreadsheets + classroombookings | SmartSched |
|---|:---:|:---:|
| Booking grid by day or by room, recurring bookings, limits, holidays, roles, LDAP | ✅ | ✅ (parity gate) |
| Reads the planning office's Excel workbooks as they are | ❌ | ✅ |
| Solves the term or the exam period with hard rules, and explains what does not fit | ❌ | ✅ |
| A published timetable that bookings can never collide with | ❌ | ✅ |
| Reservation panel, calendar feeds and push, approvals | ❌ | ✅ |
| Audit log with undo, in-app notifications, an e-mail outbox | ❌ | ✅ |

Where SmartSched behaves differently on purpose (mostly for security), [docs/CRBS_PARITY.md](docs/CRBS_PARITY.md)
lists the difference and its setting.

## Quick start

On any host with Docker Engine 24 or newer and Compose v2, from a clone of this repository:

```bash
cd smartsched/deploy
./deploy.sh --admin-email you@uni.edu.tr
# prints the panel URL and, on a terminal, the admin password once (also ADMIN_PASSWORD in .env)
```

This starts PostgreSQL, the backend, the frontend and nginx, runs the migrations, creates the administrator and
loads the seed profile from `smartsched/deploy/profile.env`: `institution` loads the 2026 workbooks, `empty`
starts with the welcome guide and `/onboarding`. Every setting can be changed later in the admin panel, and a
redeploy never overwrites those changes.

> [!TIP]
> [docs/deploy/ONE-CLICK.md](docs/deploy/ONE-CLICK.md) is the full one-click guide: both seed profiles, every
> deploy-time flag, what the deploy prints and the first-login checklist.

<details>
<summary><b>Deploy-time options, AWS and local development</b></summary>

- `--domain smartsched.uni.edu.tr` sets up HTTPS through Caddy.
- `--org-name`, `--smtp-host` / `--smtp-user` / `--smtp-from`, `--security-contact` and `--ai-provider` are
  written into the database once. `AI_API_KEY` and `SMTP_PASSWORD` come from the environment, never a flag.
- `--observability` starts Grafana, `--backups` installs the nightly backup, `--update` rebuilds and migrates.

**AWS.** One EC2 instance runs the stack and the project's CI, with a monthly budget that stops the instance.
Locally: `python infra/aws/smartsched_aws.py up --pod gracious|universal` (same flags as `deploy.sh`). See
[docs/deploy/AWS.md](docs/deploy/AWS.md).

**Local development.** `scripts/dev.sh --run` creates the Python venv, installs the frontend, seeds an admin into
SQLite and starts the backend on :8000 and the frontend on :3000. The frontend always talks to a real backend.
See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) and [smartsched/deploy/README.md](smartsched/deploy/README.md).

</details>

## Architecture

```mermaid
flowchart LR
  user(["Browser<br/>desktop and phone"])
  files[/"Excel workbooks<br/>room master, exam list"/]
  subgraph host["One Docker host (docker compose)"]
    caddy["Caddy<br/>HTTPS edge, optional"]
    nginx["nginx<br/>security headers, CSRF fence"]
    web["Next.js 16 + React 19<br/>admin panel and booking grid"]
    api["FastAPI backend<br/>importers, bookings, jobs"]
    solver["OR-Tools CP-SAT<br/>solver runs"]
    db[("PostgreSQL 16<br/>row-level security")]
    obs["Prometheus, Loki, Grafana<br/>optional"]
  end
  ext["SMTP, Google and Microsoft calendars,<br/>webhooks, AI providers (opt-in)"]
  user --> caddy --> nginx
  nginx --> web --> api
  nginx -- "calendar feeds" --> api
  files --> api
  api --> solver
  api --> db
  api -.-> ext
  obs -.-> api
```

Solver runs, imports, calendar push, webhooks and the approvals sweep run as jobs inside the backend. The design,
the domain model and the solver contract are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); the pipeline from
import to publish is in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).
Detailed diagrams (C4 context and containers, backend components, key flows, data model, deployment, states) are in
[docs/architecture/](docs/architecture/README.md).

## Screenshots

<details>
<summary><b>31 screens by role.</b> Real 2026 data with instructors as initials; light or dark follows your GitHub theme.</summary>

**Staff who book rooms**

<table>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/bookings-day-dark.webp"><img alt="Booking grid for A Blok on the next teaching day: rooms as rows, periods as columns, timetable classes holding their slots and free cells marked Free" src="docs/images/screens/bookings-day-light.webp" width="320"></picture><br><sub>Booking grid by day</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/bookings-room-dark.webp"><img alt="Booking grid for room A 101 across the week, with its timetable classes and free periods" src="docs/images/screens/bookings-room-light.webp" width="320"></picture><br><sub>Booking grid by room</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/reserve-sheet-dark.webp"><img alt="The booking sheet open on a free period: room, date, period, an optional note and the Reserve button" src="docs/images/screens/reserve-sheet-light.webp" width="320"></picture><br><sub>Reservation panel</sub></td></tr>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/free-slots-dark.webp"><img alt="Free slots view: the free periods of the day grouped by room, each a button that books it" src="docs/images/screens/free-slots-light.webp" width="320"></picture><br><sub>Free slots list</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/room-details-dark.webp"><img alt="Room details for A 101: seats, building and features, its day, the next free slot and other rooms free at the same time" src="docs/images/screens/room-details-light.webp" width="320"></picture><br><sub>Room details</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/find-room-dark.webp"><img alt="Find a room: date, time, head count and the computer lab feature, with ranked free rooms and their reasons" src="docs/images/screens/find-room-light.webp" width="320"></picture><br><sub>Find a room</sub></td></tr>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-sync-dark.webp"><img alt="Sync to calendar, switched on by the administrator: private feed links for my bookings, a room and a department with copy, Google, Outlook and Apple buttons; the link addresses are blurred because they carry a private token" src="docs/images/screens/calendar-sync-light.webp" width="320"></picture><br><sub>Calendar sync</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/my-bookings-dark.webp"><img alt="My bookings: upcoming bookings with totals, CSV export and the calendar feed" src="docs/images/screens/my-bookings-light.webp" width="320"></picture><br><sub>My bookings</sub></td></tr>
</table>

**Academic staff**

<table>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-week-dark.webp"><img alt="Calendar Week view of the busiest room in week 3 of the published Güz timetable" src="docs/images/screens/calendar-week-light.webp" width="320"></picture><br><sub>A room's week</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-inspector-dark.webp"><img alt="The class inspector next to the week: when and where, seats, instructor as initials, and why the class is in this room" src="docs/images/screens/calendar-inspector-light.webp" width="320"></picture><br><sub>Class inspector</sub></td></tr>
</table>

**Coordinators and administrators**

<table>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/dashboard-dark.webp"><img alt="Dashboard for Güz 2026-27: room use this week, classes that still need a room, requests waiting for review, use through the day and by building" src="docs/images/screens/dashboard-light.webp" width="320"></picture><br><sub>Dashboard</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/onboarding-review-dark.webp"><img alt="Onboarding review of the Final 2026 exam planning list: the proposed term and the items that need a decision" src="docs/images/screens/onboarding-review-light.webp" width="320"></picture><br><sub>Onboarding review</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/import-dark.webp"><img alt="Import page: the kinds of workbook it reads, a drop zone and the import history" src="docs/images/screens/import-light.webp" width="320"></picture><br><sub>Imports</sub></td></tr>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-scope-dark.webp"><img alt="Generator Studio scope step: term, classes or exams, a week, a month or the whole term" src="docs/images/screens/studio-scope-light.webp" width="320"></picture><br><sub>Studio: scope</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-rules-dark.webp"><img alt="Generator Studio rules step: rules as sentences grouped into Must and Try to" src="docs/images/screens/studio-rules-light.webp" width="320"></picture><br><sub>Studio: rules</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-precheck-dark.webp"><img alt="Generator Studio pre-check: problems in the data grouped by kind, each with fixes" src="docs/images/screens/studio-precheck-light.webp" width="320"></picture><br><sub>Studio: pre-check</sub></td></tr>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-report-dark.webp"><img alt="Run report for Güz week 3: classes placed with every hard rule kept, the soft score and what could not be placed" src="docs/images/screens/run-report-light.webp" width="320"></picture><br><sub>Run report</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-diagnoses-dark.webp"><img alt="Classes without a room, each with the reason, the rooms that would fit and what holds them, and fixes" src="docs/images/screens/run-diagnoses-light.webp" width="320"></picture><br><sub>Unplaced classes</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-data-issues-dark.webp"><img alt="Problems found in the workbooks themselves, grouped, with an Excel export" src="docs/images/screens/run-data-issues-light.webp" width="320"></picture><br><sub>Problems in the data</sub></td></tr>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-board-dark.webp"><img alt="Calendar Board view for week 3: rooms as columns, periods as rows, classes as blocks" src="docs/images/screens/calendar-board-light.webp" width="320"></picture><br><sub>Calendar: board</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-term-dark.webp"><img alt="Calendar Term view of the Bahar 2026 board: room use for each day of the term" src="docs/images/screens/calendar-term-light.webp" width="320"></picture><br><sub>Calendar: term</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/classes-dark.webp"><img alt="All classes of the term grouped by faculty with status, programme, instructor initials, size and room" src="docs/images/screens/classes-light.webp" width="320"></picture><br><sub>All classes</sub></td></tr>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/classes-inspector-dark.webp"><img alt="All classes with one class open in the inspector" src="docs/images/screens/classes-inspector-light.webp" width="320"></picture><br><sub>All classes: inspector</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/rooms-dark.webp"><img alt="Rooms as cards with seats, exam seats, features and use per weekday" src="docs/images/screens/rooms-light.webp" width="320"></picture><br><sub>Rooms</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/audit-dark.webp"><img alt="Audit log filtered to bookings with one change expanded to its before and after values" src="docs/images/screens/audit-light.webp" width="320"></picture><br><sub>Audit log</sub></td></tr>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/room-features-dark.webp"><img alt="Setup, Rooms, Features: typed features adopted from the room master's tags, with the values per room" src="docs/images/screens/room-features-light.webp" width="320"></picture><br><sub>Room features</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/admin-users-dark.webp"><img alt="Setup, Users: accounts with role and last sign-in" src="docs/images/screens/admin-users-light.webp" width="320"></picture><br><sub>Users</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/admin-roles-dark.webp"><img alt="Setup, Roles: roles with booking limits and permissions" src="docs/images/screens/admin-roles-light.webp" width="320"></picture><br><sub>Roles</sub></td></tr>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/settings-ai-dark.webp"><img alt="Settings, AI: the AI intake and vision switches, off by default, with the KVKK notice" src="docs/images/screens/settings-ai-light.webp" width="320"></picture><br><sub>AI policy</sub></td></tr>
</table>

**On a phone**

<table>
<tr><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-bookings-dark.webp"><img alt="Bookings on a phone: the free slots list" src="docs/images/screens/mobile-bookings-light.webp" width="260"></picture><br><sub>Bookings</sub></td><td valign="top"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-timetable-dark.webp"><img alt="Calendar Day view on a phone" src="docs/images/screens/mobile-timetable-light.webp" width="260"></picture><br><sub>Timetable</sub></td></tr>
</table>

</details>

## What is built

Built on 17–18 October 2026 and still settling. These are built but wait for their browser check on a running
stack ("e2e pending"); each has a ticket in [docs/ROADMAP.md](docs/ROADMAP.md):

<details>
<summary><b>Built, browser check pending</b> (9 areas)</summary>

- **Helper (Yardımcı):** search pages, rooms, courses and people without AI, live cards that preview, confirm and undo an action, and notes kept only when you press Hatırla. Backend done; palette, sheet and cards part done, e2e pending. [helper.md](docs/design/v3/helper.md)
- **Adaptive scheduling:** season profiles (draft, activate, revert), peak hours, demand forecast with 80 % ranges and exam-period load. Backend done; the exam date advisor and the /admin/weeks and /analytics screens part done, e2e pending. [Research](docs/research/2026-10-17-adaptive-scheduling.md)
- **Calendar export:** "Derslerim" and department classes as subscription links, .ics files and Google / Microsoft push. Backend done; the "Takvimime ekle" sheet and admin settings part done, e2e pending; "Sınav görevlerim" in progress. [Research](docs/research/2026-10-17-calendar-export.md)
- **Welcome guide:** a welcome sheet per role, a short tour, the "Başlarken" checklist and Yönetim › Karşılama rehberi. Backend done; screens part done, e2e pending. [welcome-guide.md](docs/design/v3/welcome-guide.md)
- **Voice:** speak into the AI fields; the transcript is shown for review, audio is never stored. Backend done; microphone button and admin screen part done, e2e pending. [Research](docs/research/2026-10-17-voice-ai.md)
- **Sign-in:** two-step sign-in (authenticator app, recovery codes), passkeys, remembered devices and sessions, and linking a Google, OIDC or SAML account in Profil › Güvenlik. Backend done; screens part done, e2e pending. [auth.md](docs/design/v3/auth.md)
- **Charts:** dashboard, AI usage, operations and run-score charts with keyboard access and a table twin done (unit level); bookings per week, audit events per day and personal statistics part done; e2e pending. [charts.md](docs/design/v3/charts.md)
- **Re-import keeps admin edits:** a workbook upload is a preview first and lists what changes and which of your edits are kept. Done, e2e pending. [Audit](docs/testing/audits/2026-10-17-no-mock-and-editability.md)
- **Editable class periods:** the Ders saatleri page (/admin/schedules) sets the 18 period times and every screen reads them; term weeks get a kind (Ders, Sınav, Tatil, Bütünleme). Part done, e2e pending. [Audit](docs/testing/audits/2026-10-17-no-mock-and-editability.md)

</details>

<details>
<summary><b>Every Done feature with its evidence</b> (generated from <code>docs/features.yml</code>)</summary>

<!-- AUTO:status only=done -->

Done 67 · Backend only 7 · In progress 2 · Planned 0. Done items only; the full list is in [`docs/STATUS.md`](docs/STATUS.md) (source: [`docs/features.yml`](docs/features.yml)).

| Feature | Area | Evidence |
|---|---|---|
| Import of planning lists, exam lists, weekly room grids, a room master CSV and the CRBS database, each with an import report | Planning | [`importers`](smartsched/backend/app/importers) |
| Rules from settings, templates, the workbooks and, with an API key, sentences; AI rules need a person's approval | Planning | [`ai`](smartsched/backend/app/ai) |
| Generator Studio: scope, classes, rules, pre-check with fixes, generate | Planning | [`studio-calendar-sweep.spec.ts`](smartsched/frontend/e2e/studio-calendar-sweep.spec.ts) |
| CP-SAT solver for a week, a month, the whole term or the exam period; partial runs; every unplaced class explained | Planning | [`solver`](smartsched/backend/app/solver) |
| Planner-level validator: stored runs re-checked against the raw workbook rows | Planning | [`validate_planner.py`](smartsched/backend/tools/validate_planner.py) |
| Calendar with six views and an inspector; move with a server check, then undo | Planning | [`calendar.spec.ts`](smartsched/frontend/e2e/calendar.spec.ts) |
| Publish button with a scope confirmation; the publish guard refuses failed runs and keeps one active run per term | Planning | [`studio-calendar-sweep.spec.ts`](smartsched/frontend/e2e/studio-calendar-sweep.spec.ts) |
| Exports to Excel, CSV and iCal | Planning | [`services`](smartsched/backend/app/services) |
| Relaxation policy when not every class fits: lock_first (default) or most_classes_first, per run or per term | Planning | [`relaxation.test.tsx`](smartsched/frontend/src/components/runs/relaxation.test.tsx) |
| Moderation tab: per class, person and request, with priority changes and a minimal-change re-solve with its diff | Planning | [`followup.phase19.spec.ts`](smartsched/frontend/e2e/followup.phase19.spec.ts) |
| Academicians add their own room, building or time wishes for their classes; coordinators accept or reject them with a reason, never applied by themselves | Planning | [`followups-ui.spec.ts`](smartsched/frontend/e2e/followups-ui.spec.ts) |
| Learned suggestions from earlier terms, with a resettable memory (per person, per term or all) | Planning | [`followup.phase19.spec.ts`](smartsched/frontend/e2e/followup.phase19.spec.ts) |
| Programmes from scratch: faculties, programmes, courses, sections and meetings, with the weekly-pattern expander | Planning | [`followup.phase19.spec.ts`](smartsched/frontend/e2e/followup.phase19.spec.ts) |
| Scenario comparison (A/B runs side by side), utilisation heatmaps, invigilator assignment | Planning | [`analytics.spec.ts`](smartsched/frontend/e2e/analytics.spec.ts) |
| Structured intake through the Ingestion Council: xlsx, xls, ods, csv, tsv, json, xml and ics, read without AI, with a dry-run diff | Intake | [`intake.spec.ts`](smartsched/frontend/e2e/intake.spec.ts) |
| AI-assisted intake of pdf, docx, txt, eml and images; every extracted row needs a coordinator's review; off by default | Intake | [`rows-panel.tsx`](smartsched/frontend/src/components/onboarding/rows-panel.tsx) |
| Schedule map to a baseline import run, so a re-solve keeps the published board | Intake | [`intake.spec.ts`](smartsched/frontend/e2e/intake.spec.ts) |
| Intake memory: confirmed column mappings and lexicon additions remembered per file signature | Intake | [`intake.spec.ts`](smartsched/frontend/e2e/intake.spec.ts) |
| Booking grid by day or by room; single, recurring and multi bookings, limits, holidays, timetable weeks; the published timetable blocks its slots | Bookings | [`bookings.spec.ts`](smartsched/frontend/e2e/bookings.spec.ts) |
| Reservation panel: click a free slot, drag to book several periods, reasons on cells you cannot book, a Free slots list, a department view, room details with other free rooms | Bookings | [`reserve.spec.ts`](smartsched/frontend/e2e/reserve.spec.ts) |
| Calendar sync: private ICS feed links (my bookings, a room, a department) with Google / Outlook / Apple buttons; room feeds carry the published classes | Bookings | [`test_a14_class_feeds.py`](smartsched/backend/tests/test_a14_class_feeds.py) |
| Typed room features and find-a-room with ranked results and reasons | Bookings | [`wave1.spec.ts`](smartsched/frontend/e2e/wave1.spec.ts) |
| Approvals by designated approvers: rules per room, room group or room type, PENDING requests, an inbox, a sweeper | Bookings | [`wave1.spec.ts`](smartsched/frontend/e2e/wave1.spec.ts) |
| Append-only audit log with a viewer, CSV export and undo of booking create, series create, move and cancel | Bookings | [`wave1.spec.ts`](smartsched/frontend/e2e/wave1.spec.ts) |
| In-app notifications (bell) next to the e-mail outbox | Bookings | [`wave1.spec.ts`](smartsched/frontend/e2e/wave1.spec.ts) |
| Approval-first bookings: every request can go to an admin first; a rejection needs a reason; per-user notification preferences | Bookings | [`approval-first.spec.ts`](smartsched/frontend/e2e/approval-first.spec.ts) |
| Organisation switch for calendar sync with a dated KVKK sign-off; off turns every feed link into a 404 | Bookings | [`approval-first.spec.ts`](smartsched/frontend/e2e/approval-first.spec.ts) |
| Google Calendar and Microsoft 365 push, once an administrator enters the organisation's OAuth client | Bookings | [`calendar-push-admin.test.tsx`](smartsched/frontend/src/components/settings/calendar-push-admin.test.tsx) |
| Signed outgoing webhooks (HMAC-SHA256) with an SSRF guard, off by default | Bookings | [`approval-first.spec.ts`](smartsched/frontend/e2e/approval-first.spec.ts) |
| CRBS legacy upgrade: import a running classroombookings database with a dry-run report | Bookings | [`shell-admin-sweep.spec.ts`](smartsched/frontend/e2e/shell-admin-sweep.spec.ts) |
| CRBS superset gate: every classroombookings behaviour and screen has an acceptance test | Bookings | [`parity_check.py`](scripts/parity_check.py) |
| Conflict resolver after publishing, booking policies, a public day view, KVKK retention of audit rows | Bookings | [`wave2.spec.ts`](smartsched/frontend/e2e/wave2.spec.ts) |
| No privilege escalation: nobody grants or edits a role whose permissions they do not all hold | Identity and notifications | [`test_crbs_fixes_org.py`](smartsched/backend/tests/test_crbs_fixes_org.py) |
| Sign-out, a password change, disabling an account and a role change revoke the user's tokens on every device | Identity and notifications | [`0006_token_version.py`](smartsched/backend/alembic/versions/0006_token_version.py) |
| Microsoft Entra ID sign-in pinned to the university tenant, with invites and a break-glass local admin | Identity and notifications | [`sign-in.spec.ts`](smartsched/frontend/e2e/sign-in.spec.ts) |
| Notification channels through Apprise (push, Telegram, WhatsApp/SMS, Teams/Slack); users only link an address | Identity and notifications | [`channels.spec.ts`](smartsched/frontend/e2e/channels.spec.ts) |
| Turkish and English interface; other stored language codes are kept and shown in English | Languages | [`languages.spec.ts`](smartsched/frontend/e2e/languages.spec.ts) |
| One-command Docker deploy (PostgreSQL, FastAPI, Next.js, nginx; optional TLS edge and legacy CRBS) | Platform, CI and docs | [`deploy.sh`](smartsched/deploy/deploy.sh) |
| Pod CI on a single AWS node: every gate in Docker for each new commit, then deploy; idle auto-stop and a budget cap | Platform, CI and docs | [`gates.py`](smartsched/deploy/pod-ci/podci/gates.py) |
| Seed profiles (institution or empty) and per-branch AWS pods | Platform, CI and docs | [`seed`](smartsched/deploy/seed) |
| Docs that update themselves: generated blocks from the sources of truth, checked in pod CI | Platform, CI and docs | [`sync_docs.py`](scripts/docs/sync_docs.py) |
| Design-system overhaul from the UI/UX review (sizing, controls, columns, de-AI changes) | Platform, CI and docs | [`visual-quality.spec.ts`](smartsched/frontend/e2e/visual-quality.spec.ts) |
| Mobile optimisation of every screen (390 and 768 px) | Platform, CI and docs |  |
| PostgreSQL row-level security on per-person tables (notifications, consents, DSR, feed tokens, AI usage, teacher wishes, bookings, approvals) | Platform, CI and docs | [`test_w3_sec_rls_postgres.py`](smartsched/backend/tests/test_w3_sec_rls_postgres.py) |
| Security hardening: rate limits (login, reset, SSO, password change, AI, uploads), body-size fence, CSP / HSTS / frame / permissions headers, CSRF fence, security.txt, CSV formula escaping | Platform, CI and docs | [`test_w3_sec_hardening.py`](smartsched/backend/tests/test_w3_sec_hardening.py) |
| Operations panel /admin/ops: service status cards (API, DB, queues, mail, disk, errors, Grafana / Prometheus / Loki, pod CI, last deploy), firing alerts, request/latency mini chart, Grafana links + same-origin panels, Loki log tail | Platform, CI and docs | [`w3-ops.spec.ts`](smartsched/frontend/e2e/w3-ops.spec.ts) |
| Grouped error tracking: backend exceptions / 5xx, ERROR log records with a traceback and browser errors (window.onerror, unhandled rejections, error boundaries) as PII-scrubbed groups with new / acknowledged / resolved / ignored, 90-day retention, optional Sentry | Platform, CI and docs | [`test_w3_ops_observability.py`](smartsched/backend/tests/test_w3_ops_observability.py) |
| Prometheus metrics (/metrics, multiprocess-safe; routes by template, DB pool, queues, outbox, bookings, approvals, login failures, AI calls hook, guard refusals, TLS expiry) + observability compose profile (Prometheus, Loki, Alloy, Grafana with 6 Turkish-first dashboards, 15 alert rules) behind the admin session at /grafana/ | Platform, CI and docs | [`README.md`](smartsched/deploy/observability/README.md) |
| AI provider gateway chosen by admins: Anthropic (default), OpenAI, Azure OpenAI, OpenRouter, any OpenAI-compatible base URL (Ollama / vLLM), Google Gemini, AWS Bedrock and Vertex AI (Claude); keys write-only and encrypted, models synced from each provider's API, a test call, one provider + model + effort + fallback per AI feature with a global default | Platform, CI and docs | [`test_w3_ai_providers.py`](smartsched/backend/tests/ai/test_w3_ai_providers.py) |
| AI usage metering per user (feature, provider, model, input / output / cache tokens, estimated cost from a versioned price table, latency, outcome, reason, prompt hash + length, never the text) with org monthly budget, per-user daily / monthly limits (default, per role, per person), reservation before the call, 80 % alerts (bell + e-mail) and a user banner, hard limit refused in Turkish | Platform, CI and docs | [`test_w3_ai_gateway.py`](smartsched/backend/tests/ai/test_w3_ai_gateway.py) |
| AI guardrails: deterministic scope classifier (code, translation, essays, general questions), prompt-injection detection in typed text and uploads (TR + EN: override, role-play, system-prompt / key exfiltration, tool-call smuggling, encoded payloads), spotlighting preamble, output check (offered tools, schema, no links / code), per-feature caps, per-user rate and concurrency limits, KVKK transfer basis per provider; refusals logged with a reason and visible to admins; red-team self-test | Platform, CI and docs | [`test_w3_ai_guardrails.py`](smartsched/backend/tests/ai/test_w3_ai_guardrails.py) |
| Guided SMTP setup shared by every admin: 12 provider presets (Google app password / OAuth2 / relay, Microsoft 365 OAuth2 XOAUTH2, Amazon SES, SendGrid, Mailgun, Postmark, Brevo, Resend, Yandex 360, campus server) with console steps and copy values, write-only encrypted secrets, KVKK md. 9 acknowledgement for providers abroad, SPF / DKIM / DMARC check with Turkish guidance, test e-mail with an SMTP transcript excerpt and Turkish error hints, 'Son değişiklik', send the mail that waited | Platform, CI and docs | [`test_w3b_mail_smtp.py`](smartsched/backend/tests/test_w3b_mail_smtp.py) |
| Themed HTML + plain-text e-mails for every message (25 kinds, TR + EN): one renderer app.emails.render(kind, locale, **ctx) -> (subject, html, text), table layout, 600 px, dark-mode safe, bulletproof VML button, preheader, CID logo, escaped values, variants per provider / reason / state; admin subject and intro overrides per kind and language with live desktop / phone preview and test send | Platform, CI and docs | [`test_w3b_mail_render.py`](smartsched/backend/tests/test_w3b_mail_render.py) |
| Slot display set by administrators (Ayarlar › Ders saatleri, also /bookings › Görünüm): period rows or time blocks (15/30/60 min drawn onto the periods), label period / time / both (schedule name or ordinal, start or range), density compact / standard / comfortable, first / last visible period, hide short slots and the weekend, default view for desktop and phone, quick-reserve lengths; live preview with the real grid, list and chips; every booking surface reads one useSlotDisplay() | Bookings | [`w3-slot.spec.ts`](smartsched/frontend/e2e/w3-slot.spec.ts) |
| Quick reservation /reserve (Hızlı rezervasyon): day chips, a slot in the admin's unit, an optional length, how many people and feature chips, a short ranked list of free rooms (own waiting request marked), one primary that says Rezerve et or Talep et, a receipt with the real undo (POST /audit/{id}/undo) or Talebi geri çek; 2 taps for the next free slot, keyboard and screen-reader complete, one thumb at 390 | Bookings | [`w3-slot.spec.ts`](smartsched/frontend/e2e/w3-slot.spec.ts) |
| Integrations gallery (Yönetim › Entegrasyonlar, /admin/integrations): organisation-wide connector cards for identity, e-mail, calendar, channels, webhooks / automation and AI with status words, last check, last change (who, when), Kur / Yönet, a Kullanımda switch through each area's own endpoint, Dikkat isteyen row, search, deep links, phone rows and a setup sheet embedding each area's panel | Platform, CI and docs | [`w3-hub.spec.ts`](smartsched/frontend/e2e/w3-hub.spec.ts) |
| Guided n8n / Activepieces / Pipedream / Zapier webhook setup: platform steps, paste the trigger URL, signing secret shown once with copy, headers and an HMAC-SHA256 check snippet per platform, test event with the delivery result | Platform, CI and docs | [`integrations-gallery.test.tsx`](smartsched/frontend/src/components/admin/integrations/integrations-gallery.test.tsx) |
| Several identity providers set by administrators and shared by all of them (Kimlik sağlayıcıları): Microsoft Entra (tenant pin kept), Google Workspace (hosted-domain pin), any OpenID Connect issuer with discovery (Okta, Keycloak, Auth0, Authentik, ADFS presets) and SAML 2.0 (Shibboleth / eduGAIN / YETKİM; signxml behind an optional import, 'kütüphane gerekli' without it), plus LDAP; per provider: label and /login order, allowed domains, invite-only, sign-up role (eligible roles only), group/claim mapping bounded by its creator's permissions, write-only encrypted secret, audit, Son değişiklik + version conflict | Platform, CI and docs | [`test_w3b_idp_oidc.py`](smartsched/backend/tests/test_w3b_idp_oidc.py) |
| Guided identity-provider setup (5 steps): console values built from the public URL with Kopyala (redirect URI, entity id, ACS, scopes, logout URL, SP metadata), discovery / metadata check rows, a real test login in a popup that reports the claims (no account, no stored token), provider errors translated into cause + fix + step, then Etkinleştir | Platform, CI and docs | [`identity-wizard.test.tsx`](smartsched/frontend/src/components/identity/identity-wizard.test.tsx) |
| Invitations per provider: invite by e-mail with the provider or a local password (set from the link), themed invitation e-mail (W3-MAIL send_kind), resend, renew, revoke (disables the unused placeholder, T-R1-35), bulk invite from a Turkish Excel CSV; account_created e-mail on self sign-up and local acceptance | Platform, CI and docs | [`test_w3b_idp_invites.py`](smartsched/backend/tests/test_w3b_idp_invites.py) |
| /login with several providers: equal-weight buttons in the admins' order (Microsoft and Google branding), at most 3 + 'Diğer giriş yolları', invite shows only the invited method, provider error codes domain / invite_provider in TR/EN | Platform, CI and docs | [`identity-wizard.test.tsx`](smartsched/frontend/src/components/identity/identity-wizard.test.tsx) |
| Calendar export for academicians (backend): 'Derslerim' and 'Bölümümün dersleri' from the published run only, as scope-bound revocable subscription links (classes.ics, department-classes/{id}.ics), one-off .ics files and push into a dedicated 'SmartSched – Derslerim' Google (calendar.app.created) / Microsoft calendar; stable class UIDs across re-publishes and room moves, SEQUENCE on every change, CANCELLED tombstones, Europe/Istanbul VTIMEZONE, RFC 7986 NAME/SOURCE, version-key ETag/304 + Last-Modified, 1 MB cap; department rule (own, taught, calendar.department_feed); per-scope approval with consent id and audit; verified accounts for push (identity, Workspace hd, Entra tid, own e-mail / institution domain, admin-allowed domains); nightly repair 03:30 | Platform, CI and docs | [`test_cal_06_push.py`](smartsched/backend/tests/test_cal_06_push.py) |
| Welcome guide per role (backend): audiences from permissions + the instructor link (academician, staff, approver, dept_admin, viewer, planner, admin; never role codes), one server-decided automatic surface per call (first sign-in sheet, 'Sonra' back after 3 days at most twice, role-change delta with only the new audiences, admin 'show again', else one wave-3 feature hint for accounts created before its release, 60 days), self-ticking 'Başlarken' checklist from real rows and audit events (booking, decision, channel, calendar link, intake commit, run, publish, org/mail/rooms/users), deep-link / kiosk / embed / maintenance suppression; admin switches, TR/EN text overrides with version conflict (409 stale naming the editor), completion stats with groups under 5 hidden; RLS owner-only progress rows; KVKK export + erasure | Platform, CI and docs | [`test_wg_01_welcome.py`](smartsched/backend/tests/test_wg_01_welcome.py) |
| Class size edit on /classes is real (RF-01): PUT /requests/meetings/{id} {enrolment} writes the section's enrolment (audited section.update), PUT /requests/exams/{id} {enrolment} the exam's head count (audited exam_request.update); time-shaped or out-of-range values answer 422 | Planning | [`test_rf1_catalog_editability.py`](smartsched/backend/tests/test_rf1_catalog_editability.py) |
| Invite sheet e-mail switch on /admin/users (RF-03): 'Davet e-postası gönder' on by default when SMTP is set up and sends send_email; without SMTP 'E-posta ayarlanmadı' with a link to /admin/email; sent / failed toast | Platform, CI and docs | [`rf1-invite-mail.test.tsx`](smartsched/frontend/src/components/admin/rf1-invite-mail.test.tsx) |
| Yönetim › Katalog (RF-05): view, edit and delete the imported instructors, courses, programmes, faculties and the term's sections; one searchable list per entity, 'Yeni', edit sheet with 'Son değişiklik: <ad>, <zaman>', advanced fields behind 'Gelişmiş', delete that names its consequences and is refused while the record is in use (sections are archived); planning.view reads, planning.edit writes, every write audited | Planning | [`catalog-admin.test.tsx`](smartsched/frontend/src/components/admin/catalog/catalog-admin.test.tsx) |
| Two-step sign-in and passkeys (backend): authenticator app (stdlib RFC 6238, ±1 step, replay refused, secret Fernet-encrypted), ten single-use argon2id recovery codes shown once, sign-in challenge step (signed single-use token, 5 tries, lockout 5 → 15 min doubling), passkeys via py_webauthn 3.0.1 as second factor and passkey-only sign-in (UV required) with RP ID = public host, trusted devices 0/7/30 days, organisation policy off / optional / required_for_roles with grace and setup token, 10-minute re-auth window, password minimum 12 (8 with 2FA); SSO-only accounts get no local factor; admin MFA reset (reason + identity check, audited, e-mailed) and password-reset link by e-mail (local accounts only, token never shown); nine security e-mails | Platform, CI and docs | [`test_au_b_mfa_api.py`](smartsched/backend/tests/test_au_b_mfa_api.py) |

<!-- /AUTO:status -->

</details>

## Privacy, KVKK and security

- **Personal data stays on your server.** Per-person tables (notifications, consents, data requests, feed tokens,
  AI usage, teacher wishes, bookings, approvals) are protected by PostgreSQL row-level security.
- **KVKK tools for the data controller:** a processing inventory, privacy notices, data-subject export and erasure,
  and retention windows for audit rows. Calendar sync stays off until an administrator records a dated KVKK
  sign-off.
- **AI is opt-in.** Every AI switch is off by default and shows the KVKK notice; each provider carries its
  transfer basis. Prompts are metered by hash and length, never stored as text.
- **Hardening:** argon2id passwords, two-step sign-in and passkeys, rate limits, CSP with a nonce, HSTS, a CSRF
  fence, SSRF guards on outgoing URLs, write-only encrypted secrets and CSV formula escaping.

The threat model, every control with its file and test, and the open risks are in [docs/SECURITY.md](docs/SECURITY.md).
To report a vulnerability, follow [.github/SECURITY.md](.github/SECURITY.md); please do not open a public issue.

## Documentation

| | |
|---|---|
| [One-click deploy](docs/deploy/ONE-CLICK.md) | both seed profiles, every deploy-time setting, the first-login checklist |
| [How it works](docs/HOW_IT_WORKS.md) | import, rules, pre-check, solve, validate, publish; hard rules and partial runs |
| [Status](docs/STATUS.md) | every feature, the parity gate, the CI gates and the decisions (generated) |
| [Measured on the real data](docs/RESULTS.md) | placement rates and planner-level checks on the 2026 workbooks |
| [Relation to classroombookings](docs/CLASSROOMBOOKINGS.md) | what stays the same, what is added, the parity gate |
| [Development](docs/DEVELOPMENT.md) | repository layout, checks, CI on the pod, configuration |
| [Architecture](docs/ARCHITECTURE.md) · [Data analysis](docs/DATA_ANALYSIS.md) · [CRBS parity](docs/CRBS_PARITY.md) | design, the workbook shapes, behaviour differences |
| [Security model](docs/SECURITY.md) | threat model, controls, row-level security, residual risks |
| [Recordings](docs/recording/RECORDLY.md) · [Launch notes](docs/launch/README.md) | how the clips and screenshots on this page are made and refreshed |

## Roadmap

The plan, the open tickets and the owner's decisions are in [docs/ROADMAP.md](docs/ROADMAP.md);
[docs/STATUS.md](docs/STATUS.md) is the generated view of what is done, backend only, in progress or planned.

## Contributing

Bug reports, feature requests and pull requests are welcome. Start with [CONTRIBUTING.md](.github/CONTRIBUTING.md)
(set-up, checks, the generated docs) and the [Code of Conduct](.github/CODE_OF_CONDUCT.md). Questions go
through [SUPPORT.md](.github/SUPPORT.md). Much of SmartSched is built by Claude Code agents working in parallel;
[docs/AGENTS.md](docs/AGENTS.md) describes their protocol, and every change goes through the same checks.

## Türkçe

SmartSched, planlama ofisinin hâlihazırda kullandığı Excel dosyalarını olduğu gibi okur, yerleştirebildiği
her dersi CP-SAT çözücüsüyle derslere ve sınavlara yerleştirir, yerleştiremediklerini nedeni ve çözüm
önerileriyle listeler ve yayımlanan programın üzerinde classroombookings rezervasyon tablosunu çalıştırır.
Arayüz Türkçe ve İngilizcedir.

- **Kurulum:** Docker yüklü bir sunucuda `cd smartsched/deploy && ./deploy.sh --admin-email siz@uni.edu.tr`.
  Ayrıntılar: [docs/deploy/ONE-CLICK.md](docs/deploy/ONE-CLICK.md).
- **KVKK:** kişisel veriler kendi sunucunuzda kalır; yapay zekâ özellikleri varsayılan olarak kapalıdır.
  Ayrıntılar: [docs/SECURITY.md](docs/SECURITY.md).
- **Güvenlik açığı bildirimi:** herkese açık bir issue açmayın; [.github/SECURITY.md](.github/SECURITY.md)
  adımlarını izleyin.

## Licence

A fork of [classroombookings](https://www.classroombookings.com/) by Craig A Rodway, licensed under the
[GNU Affero General Public License v3.0 or later](https://www.gnu.org/licenses/agpl-3.0.html) ([LICENSE.txt](LICENSE.txt)).
To cite SmartSched, use [CITATION.cff](CITATION.cff) or GitHub's "Cite this repository" button.

<!-- AUTO:last-updated -->

Generated blocks last synced on top of commit `2441e9f` (committed 2026-10-19 12:35 UTC) by `python3 -I scripts/docs/sync_docs.py`.

<!-- /AUTO:last-updated -->
