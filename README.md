<h1 align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/brand/readme-header-dark.svg"><img alt="SmartSched" src="docs/images/brand/readme-header-light.svg" width="640"></picture></h1>

<p align="center">
  <b>Timetabling, exam planning and room booking for a university.</b><br>
  Reads the planning office's Excel workbooks, places every class it can with a CP-SAT solver without breaking
  a hard rule, explains each class it cannot place, and runs classroombookings' booking grid on top.
</p>

<p align="center">
  <a href="LICENSE.txt"><img alt="License: AGPL-3.0" src="https://img.shields.io/badge/License-AGPL--3.0-3DA639?style=flat-square"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white">
  <img alt="OR-Tools CP-SAT" src="https://img.shields.io/badge/OR--Tools-CP--SAT-4285F4?style=flat-square&logo=google&logoColor=white">
  <img alt="PostgreSQL 16" src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white">
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/hero-solver-dark.gif">
    <img alt="Animation (illustration): coloured class blocks fill a grid of rooms by periods, each placed block is ticked, and a badge shows a hard-rule score of 100/100" src="docs/images/lottie/hero-solver-light.gif" width="560">
  </picture>
</p>

## What it does

- **Reads the workbooks the office already keeps**: the planning list of every section, the weekly room grid,
  the exam list and a room master, each import with a report of what was read and skipped. An empty
  instance can start from the onboarding page, which recognises the files and proposes the term.
- **Plans a week, a month, the whole term or the exam period** with OR-Tools CP-SAT. Hard rules (a room
  seats the class, one class per room, one place per instructor and cohort, fixed times, labs) are never
  relaxed quietly; a class that cannot be placed is listed with the reason and fixes.
- **Publishes the timetable into a booking system**: the classroombookings grid, a reservation panel,
  find-a-room, approvals, calendar feeds and an audit log with undo. It is a superset of
  [classroombookings](https://www.classroombookings.com/), checked behaviour by behaviour by a parity gate
  ([how](docs/CLASSROOMBOOKINGS.md)).
- **Uses AI only where you ask for it**: with an Anthropic key, a sentence or an uploaded file becomes a rule
  that a person reviews before it is used. Everything else works without a key.

<!-- AUTO:parity -->

**CRBS superset gate: PASS**: PASS 179 · GAP 13 · FAIL 0 · MISSING 0 of 192 rows, measured on commit `5d0e6c2` (2026-10-15 22:10 UTC) by `scripts/parity_check.py`. Full table: [`crbs-parity-report.md`](docs/testing/crbs-parity-report.md).

<!-- /AUTO:parity -->

<table>
  <tr>
    <td align="center" width="50%"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/nl-to-rules-dark.gif">
      <img alt="Animation: a Turkish sentence becomes a typed rule card that can be reviewed before it is used" src="docs/images/lottie/nl-to-rules-light.gif" width="360">
    </picture><br><sub>A sentence becomes a rule you review (illustration).</sub></td>
    <td align="center" width="50%"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/file-to-rules-dark.gif">
      <img alt="Animation: rows of an uploaded preference file become rule cards, each linked to its source row" src="docs/images/lottie/file-to-rules-light.gif" width="360">
    </picture><br><sub>Rules read from a file keep a link to their row (illustration).</sub></td>
  </tr>
</table>

## See it work

Recorded on the real backend with the real 2026 workbooks (instructor names reduced to initials). Each clip links to the full take (MP4).

<table>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/reserve-panel.mp4"><img alt="Screen recording: on the booking grid for A Blok the pointer rests on an empty period of room A 103, which shows Reserve; a click opens the booking sheet, Reserve is pressed, the cell shows You and a toast confirms the booking." src="docs/images/recordings/reserve-slot.gif" width="100%"></a>
      <br><sub><b>Reserve a free period.</b> Point at a free period and it offers Reserve; one more click books it.</sub>
    </td>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/reserve-panel.mp4"><img alt="Screen recording: the pointer drags across three free periods of one room in the booking grid, and the booking sheet opens with the three periods selected and a Reserve 3 periods button." src="docs/images/recordings/reserve-drag.gif" width="100%"></a>
      <br><sub><b>Book several periods.</b> Drag across three free periods: one sheet books them together.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/find-room.mp4"><img alt="Screen recording: on Find a room, with the date and time already set, the head count is typed and the computer lab feature is chosen; the search shows the free room that fits with a Reserve button, then the nearly fitting alternatives, each with its reason." src="docs/images/recordings/find-room.gif" width="100%"></a>
      <br><sub><b>Find a room.</b> A head count and the computer-lab feature: what is free and fits, then the nearest alternatives, each with its reason.</sub>
    </td>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/audit-undo.mp4"><img alt="Screen recording: in the audit log a booking.move event is expanded to show its room before and after; Undo is pressed, the dialog says the booking is put back as it was and conflicts are checked again, and the undo is confirmed." src="docs/images/recordings/audit-undo.gif" width="100%"></a>
      <br><sub><b>Undo from the audit log.</b> A booking move with the room before and after; Undo moves it back.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/calendar-move.mp4"><img alt="Screen recording: from the class inspector of a class in the published timetable, Move opens a dialog listing the rooms that are free and fit; one is picked and the dialog shows the server's check that the move keeps every rule." src="docs/images/recordings/calendar-move.gif" width="100%"></a>
      <br><sub><b>Move a class.</b> Only free rooms that fit are offered, and the server checks the move before it is saved.</sub>
    </td>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/studio-rule-fix.mp4"><img alt="Screen recording: the Generator Studio's pre-check lists problems in the term's data grouped by kind; one problem card names the classes involved and its fix is applied." src="docs/images/recordings/precheck-fix.gif" width="100%"></a>
      <br><sub><b>Pre-check and fix.</b> The Generator Studio tests the plan against the term's data and applies one of its fixes.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/images/recordings/onboarding-intake.mp4"><img alt="Screen recording: on Onboarding the Final 2026 exam planning workbook is dropped with AI switched off; it is read and classified, the review shows the proposed term and an item to decide, and the term is committed." src="docs/images/recordings/onboarding.gif" width="100%"></a>
      <br><sub><b>Onboard an empty instance.</b> Drop the exam planning workbook, AI off: it is classified, a term is proposed, reviewed and committed.</sub>
    </td>
  </tr>
</table>

<details>
<summary><strong>Every recording</strong> (full takes, MP4)</summary>

<table>
  <tr>
    <td width="25%" valign="top"><a href="docs/images/recordings/reserve-panel.mp4"><img alt="Still from the reservation panel: a click, a drag, room details recording" src="docs/images/recordings/reserve-panel-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/reserve-panel.mp4">Reservation panel: a click, a drag, room details</a> · <a href="docs/images/recordings/reserve-panel-tr.mp4">Türkçe</a></sub></td>
    <td width="25%" valign="top"><a href="docs/images/recordings/find-room.mp4"><img alt="Still from the find a room recording" src="docs/images/recordings/find-room-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/find-room.mp4">Find a room</a></sub></td>
    <td width="25%" valign="top"><a href="docs/images/recordings/audit-undo.mp4"><img alt="Still from the audit log with undo recording" src="docs/images/recordings/audit-undo-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/audit-undo.mp4">Audit log with undo</a></sub></td>
    <td width="25%" valign="top"><a href="docs/images/recordings/calendar-move.mp4"><img alt="Still from the move a class in the calendar, undo recording" src="docs/images/recordings/calendar-move-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/calendar-move.mp4">Move a class in the calendar, undo</a></sub></td>
  </tr>
  <tr>
    <td width="25%" valign="top"><a href="docs/images/recordings/studio-rule-fix.mp4"><img alt="Still from the studio: a rule from a template, the pre-check and a fix recording" src="docs/images/recordings/studio-rule-fix-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/studio-rule-fix.mp4">Studio: a rule from a template, the pre-check and a fix</a></sub></td>
    <td width="25%" valign="top"><a href="docs/images/recordings/onboarding-intake.mp4"><img alt="Still from the onboarding an empty instance recording" src="docs/images/recordings/onboarding-intake-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/onboarding-intake.mp4">Onboarding an empty instance</a></sub></td>
    <td width="25%" valign="top"><a href="docs/images/recordings/room-booking.mp4"><img alt="Still from the book a room with a note, my bookings recording" src="docs/images/recordings/room-booking-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/room-booking.mp4">Book a room with a note, My bookings</a></sub></td>
    <td width="25%" valign="top"><a href="docs/images/recordings/admin-user.mp4"><img alt="Still from the create an account and pick its role recording" src="docs/images/recordings/admin-user-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/admin-user.mp4">Create an account and pick its role</a></sub></td>
  </tr>
  <tr>
    <td width="25%" valign="top"><a href="docs/images/recordings/run-report-fix.mp4"><img alt="Still from the run report: apply a suggested fix recording" src="docs/images/recordings/run-report-fix-poster.png" width="100%"></a><br><sub><a href="docs/images/recordings/run-report-fix.mp4">Run report: apply a suggested fix</a></sub></td>
  </tr>
</table>

</details>

## Features

<!-- AUTO:status only=done -->

Done 43 · Backend only 0 · In progress 1 · Planned 0. Done items only; the full list is in [`docs/STATUS.md`](docs/STATUS.md) (source: [`docs/features.yml`](docs/features.yml)).

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

<!-- /AUTO:status -->

Where every feature stands, including the parts that are backend only so far: [docs/STATUS.md](docs/STATUS.md).

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/precheck-fix-dark.gif">
    <img alt="Animation (illustration): a readiness gauge fills to green with a tick while the pre-check issues beside it are fixed and ticked one by one" src="docs/images/lottie/precheck-fix-light.gif" width="480">
  </picture>
</p>

## Quick start

**Docker, one command** (Docker Engine 24+ with Compose v2):

```bash
cd smartsched/deploy
ADMIN_EMAIL=you@uni.edu.tr ./deploy.sh   # writes .env with random secrets, builds, starts, waits for /api/v1/health
# SmartSched is up at http://localhost:8080; the admin password is ADMIN_PASSWORD in .env
```

This starts PostgreSQL, the FastAPI backend, the Next.js frontend and nginx (`--tls` adds Caddy HTTPS,
`--legacy` also runs the original classroombookings, `--update` rebuilds and migrates). What the first boot
loads depends on the branch's seed profile (`smartsched/deploy/profile.env`): this branch is `institution`
(the planning office's Bahar, Güz and Final workbooks, the room master, their preference rules and the learned
suggestions), the universal branch `claude/smartsched-universal` is `empty` (the setup wizard and
`/onboarding`). Details: [smartsched/deploy/README.md](smartsched/deploy/README.md).

**On AWS, one push**: one EC2 instance runs the stack behind Caddy TLS and the project's CI, controlled by
the first line of `infra/aws/POD_ACTION` (`up`, `status`, `stop`, `start`, `cost`, `down destroy`) through a
GitHub OIDC role, with a 100 USD/month budget that stops the instance:

```bash
echo "up $(date -u +%FT%TZ)" > infra/aws/POD_ACTION      # the timestamp makes every push a change
git add infra/aws/POD_ACTION && git commit -m "pod: up" && git push
```

See [docs/deploy/AWS.md](docs/deploy/AWS.md) for the panel URL, the admin password (in SSM) and the costs.

**Local development** (Python 3.12+, Node 22+): `scripts/dev.sh --run` sets up a venv and `npm ci`, a SQLite
database with a seeded admin, the backend on :8000 and the frontend on :3000. The frontend always talks to
the real backend; there is no mock mode. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) has the checks, CI gates
and how to load the real 2026 data.

<details>
<summary><strong>Screenshots</strong>, by role (real 2026 data, light or dark following your GitHub theme)</summary>

**Staff who book rooms**

<table>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/bookings-day-dark.webp">
      <img alt="Booking grid for A Blok on the next teaching day: rooms as rows, periods as columns, timetable classes holding their slots and free cells marked Free" src="docs/images/screens/bookings-day-light.webp" width="480">
    </picture><br><sub>Booking grid by day</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/bookings-room-dark.webp">
      <img alt="Booking grid for room A 101 across the week, with its timetable classes and free periods" src="docs/images/screens/bookings-room-light.webp" width="480">
    </picture><br><sub>Booking grid by room</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/reserve-sheet-dark.webp">
      <img alt="The booking sheet open on a free period: room, date, period, an optional note and the Reserve button" src="docs/images/screens/reserve-sheet-light.webp" width="480">
    </picture><br><sub>Reservation panel</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/free-slots-dark.webp">
      <img alt="Free slots view: the free periods of the day grouped by room, each a button that books it" src="docs/images/screens/free-slots-light.webp" width="480">
    </picture><br><sub>Free slots list</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/room-details-dark.webp">
      <img alt="Room details for A 101: seats, building and features, its day, the next free slot and other rooms free at the same time" src="docs/images/screens/room-details-light.webp" width="480">
    </picture><br><sub>Room details</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/find-room-dark.webp">
      <img alt="Find a room: date, time, head count and the computer lab feature, with ranked free rooms and their reasons" src="docs/images/screens/find-room-light.webp" width="480">
    </picture><br><sub>Find a room</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-sync-dark.webp">
      <img alt="Sync to calendar, switched on by the administrator: private feed links for my bookings, a room and a department with copy, Google, Outlook and Apple buttons; the link addresses are blurred because they carry a private token" src="docs/images/screens/calendar-sync-light.webp" width="480">
    </picture><br><sub>Calendar sync</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/my-bookings-dark.webp">
      <img alt="My bookings: upcoming bookings with totals, CSV export and the calendar feed" src="docs/images/screens/my-bookings-light.webp" width="480">
    </picture><br><sub>My bookings</sub></td>
  </tr>
</table>

**Academic staff**

<table>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-week-dark.webp">
      <img alt="Calendar Week view of the busiest room in week 3 of the published Güz timetable" src="docs/images/screens/calendar-week-light.webp" width="480">
    </picture><br><sub>A room's week</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-inspector-dark.webp">
      <img alt="The class inspector next to the week: when and where, seats, instructor as initials, and why the class is in this room" src="docs/images/screens/calendar-inspector-light.webp" width="480">
    </picture><br><sub>Class inspector</sub></td>
  </tr>
</table>

**Coordinators and administrators**

<table>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/dashboard-dark.webp">
      <img alt="Dashboard for Güz 2026-27: room use this week, classes that still need a room, requests waiting for review, use through the day and by building" src="docs/images/screens/dashboard-light.webp" width="480">
    </picture><br><sub>Dashboard</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/onboarding-review-dark.webp">
      <img alt="Onboarding review of the Final 2026 exam planning list: the proposed term and the items that need a decision" src="docs/images/screens/onboarding-review-light.webp" width="480">
    </picture><br><sub>Onboarding review</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/import-dark.webp">
      <img alt="Import page: the kinds of workbook it reads, a drop zone and the import history" src="docs/images/screens/import-light.webp" width="480">
    </picture><br><sub>Imports</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-scope-dark.webp">
      <img alt="Generator Studio scope step: term, classes or exams, a week, a month or the whole term" src="docs/images/screens/studio-scope-light.webp" width="480">
    </picture><br><sub>Studio: scope</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-rules-dark.webp">
      <img alt="Generator Studio rules step: rules as sentences grouped into Must and Try to" src="docs/images/screens/studio-rules-light.webp" width="480">
    </picture><br><sub>Studio: rules</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/studio-precheck-dark.webp">
      <img alt="Generator Studio pre-check: problems in the data grouped by kind, each with fixes" src="docs/images/screens/studio-precheck-light.webp" width="480">
    </picture><br><sub>Studio: pre-check</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-report-dark.webp">
      <img alt="Run report for Güz week 3: classes placed with every hard rule kept, the soft score and what could not be placed" src="docs/images/screens/run-report-light.webp" width="480">
    </picture><br><sub>Run report</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-diagnoses-dark.webp">
      <img alt="Classes without a room, each with the reason, the rooms that would fit and what holds them, and fixes" src="docs/images/screens/run-diagnoses-light.webp" width="480">
    </picture><br><sub>Unplaced classes</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/run-data-issues-dark.webp">
      <img alt="Problems found in the workbooks themselves, grouped, with an Excel export" src="docs/images/screens/run-data-issues-light.webp" width="480">
    </picture><br><sub>Problems in the data</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-board-dark.webp">
      <img alt="Calendar Board view for week 3: rooms as columns, periods as rows, classes as blocks" src="docs/images/screens/calendar-board-light.webp" width="480">
    </picture><br><sub>Calendar: board</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/calendar-term-dark.webp">
      <img alt="Calendar Term view of the Bahar 2026 board: room use for each day of the term" src="docs/images/screens/calendar-term-light.webp" width="480">
    </picture><br><sub>Calendar: term</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/classes-dark.webp">
      <img alt="All classes of the term grouped by faculty with status, programme, instructor initials, size and room" src="docs/images/screens/classes-light.webp" width="480">
    </picture><br><sub>All classes</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/classes-inspector-dark.webp">
      <img alt="All classes with one class open in the inspector" src="docs/images/screens/classes-inspector-light.webp" width="480">
    </picture><br><sub>All classes: inspector</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/rooms-dark.webp">
      <img alt="Rooms as cards with seats, exam seats, features and use per weekday" src="docs/images/screens/rooms-light.webp" width="480">
    </picture><br><sub>Rooms</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/audit-dark.webp">
      <img alt="Audit log filtered to bookings with one change expanded to its before and after values" src="docs/images/screens/audit-light.webp" width="480">
    </picture><br><sub>Audit log</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/room-features-dark.webp">
      <img alt="Setup, Rooms, Features: typed features adopted from the room master's tags, with the values per room" src="docs/images/screens/room-features-light.webp" width="480">
    </picture><br><sub>Room features</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/admin-users-dark.webp">
      <img alt="Setup, Users: accounts with role and last sign-in" src="docs/images/screens/admin-users-light.webp" width="480">
    </picture><br><sub>Users</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/admin-roles-dark.webp">
      <img alt="Setup, Roles: roles with booking limits and permissions" src="docs/images/screens/admin-roles-light.webp" width="480">
    </picture><br><sub>Roles</sub></td>
  </tr>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/settings-ai-dark.webp">
      <img alt="Settings, AI: the AI intake and vision switches, off by default, with the KVKK notice" src="docs/images/screens/settings-ai-light.webp" width="480">
    </picture><br><sub>AI policy</sub></td>
  </tr>
</table>

**On a phone**

<table>
  <tr>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-bookings-dark.webp">
      <img alt="Bookings on a phone: the free slots list" src="docs/images/screens/mobile-bookings-light.webp" width="260">
    </picture><br><sub>Bookings</sub></td>
    <td valign="top"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/screens/mobile-timetable-dark.webp">
      <img alt="Calendar Day view on a phone" src="docs/images/screens/mobile-timetable-light.webp" width="260">
    </picture><br><sub>Timetable</sub></td>
  </tr>
</table>

</details>

## Documentation

| | |
|---|---|
| [How it works](docs/HOW_IT_WORKS.md) | import, rules, pre-check, solve, validate, publish; hard rules and partial runs; bookings internals |
| [Status](docs/STATUS.md) | where things stand: every feature, the parity gate, the CI gates, decisions (generated) |
| [Measured on the real data](docs/RESULTS.md) | placement rates and planner-level checks on the 2026 workbooks |
| [Relation to classroombookings](docs/CLASSROOMBOOKINGS.md) | what stays the same, what is added, the parity gate; the original CRBS README |
| [Development](docs/DEVELOPMENT.md) | repository layout, checks, CI on the pod, configuration, documentation index |
| [Architecture](docs/ARCHITECTURE.md) · [Data analysis](docs/DATA_ANALYSIS.md) · [CRBS parity](docs/CRBS_PARITY.md) | design, the workbook shapes, behaviour differences |
| [Recordings](docs/recording/RECORDLY.md) | how the GIFs and screenshots on this page are made (`scripts/record/`) |

The plan and backlog are in [docs/ROADMAP.md](docs/ROADMAP.md).

## Licence

A fork of [classroombookings](https://www.classroombookings.com/) by Craig A Rodway, licensed under the
[GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0.html) ([LICENSE.txt](LICENSE.txt)).

<!-- AUTO:last-updated -->

Generated blocks last synced on top of commit `3a4ab04` (committed 2026-10-16 14:47 UTC) by `python3 -I scripts/docs/sync_docs.py`.

<!-- /AUTO:last-updated -->
