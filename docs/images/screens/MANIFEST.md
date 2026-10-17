# README screenshots

Captured 2026-10-16 by [`scripts/record/screens.mjs`](../../../scripts/record/screens.mjs) on the recording stack
([`scripts/record/stack.sh`](../../../scripts/record/stack.sh)) at commit `1210795` (the redesigned UI): the real
FastAPI backend on SQLite with the real workbooks of Bahar 2026, Güz 2026-27 and Final 2026 plus the room master, and a
production build of the frontend. No mock data. Solver runs through `POST /runs` (`stack.sh runs`): run #7 Güz week 3
(FEASIBLE_PARTIAL, 524/530 placed, hard 100) and run #8 Güz whole term (FEASIBLE_PARTIAL, 517/530, hard 100,
published). The shots were taken after the recordings, so the bookings and the account those recordings made are
visible. The sign-in page and the approval screens are being rebuilt and are not shot this time.

- **KVKK:** instructor names are title + initials (`scripts/record/kvkk_mask.py` on the throwaway database); the
  accounts are roles (the seeded administrator, "Planlama Ofisi"); private calendar-feed links are blurred.
- Desktop: 1440×900 CSS px at device scale 1. Phone: 390×844 at device scale 2 (780×1688).
- Locale en-GB, theme via next-themes' `theme` key, Europe/Istanbul; each signed-in user's profile language is set to
  English for the shot.
- WebP, quality 82 (ImageMagick `-define webp:method=6`). Files: 62, total 3.35 MB.
- Re-take: `scripts/record/refresh.sh` (recordings first, then these shots on the same stack).

| File | Pixels | Size | Shows |
|---|---|---|---|
| `admin-roles-dark.webp` | 1440×900 | 52 KB | Setup, Roles: roles with booking limits and permissions |
| `admin-roles-light.webp` | 1440×900 | 53 KB | Setup, Roles: roles with booking limits and permissions |
| `admin-users-dark.webp` | 1440×900 | 34 KB | Setup, Users: accounts with role and last sign-in |
| `admin-users-light.webp` | 1440×900 | 35 KB | Setup, Users: accounts with role and last sign-in |
| `audit-dark.webp` | 1440×900 | 36 KB | Audit log filtered to bookings with one change expanded to its before and after values |
| `audit-light.webp` | 1440×900 | 36 KB | Audit log filtered to bookings with one change expanded to its before and after values |
| `bookings-day-dark.webp` | 1440×900 | 57 KB | Booking grid for A Blok on the next teaching day: rooms as rows, periods as columns, timetable classes holding their slots and free cells marked Free |
| `bookings-day-light.webp` | 1440×900 | 58 KB | Booking grid for A Blok on the next teaching day: rooms as rows, periods as columns, timetable classes holding their slots and free cells marked Free |
| `bookings-room-dark.webp` | 1440×900 | 48 KB | Booking grid for room A 101 across the week, with its timetable classes and free periods |
| `bookings-room-light.webp` | 1440×900 | 48 KB | Booking grid for room A 101 across the week, with its timetable classes and free periods |
| `calendar-board-dark.webp` | 1440×900 | 47 KB | Calendar Board view for week 3: rooms as columns, periods as rows, classes as blocks |
| `calendar-board-light.webp` | 1440×900 | 50 KB | Calendar Board view for week 3: rooms as columns, periods as rows, classes as blocks |
| `calendar-inspector-dark.webp` | 1440×900 | 74 KB | The class inspector next to the week: when and where, seats, instructor as initials, and why the class is in this room |
| `calendar-inspector-light.webp` | 1440×900 | 79 KB | The class inspector next to the week: when and where, seats, instructor as initials, and why the class is in this room |
| `calendar-sync-dark.webp` | 1440×900 | 51 KB | Sync to calendar, switched on by the administrator: private feed links for my bookings, a room and a department with copy, Google, Outlook and Apple buttons; the link addresses are blurred because they carry a private token |
| `calendar-sync-light.webp` | 1440×900 | 58 KB | Sync to calendar, switched on by the administrator: private feed links for my bookings, a room and a department with copy, Google, Outlook and Apple buttons; the link addresses are blurred because they carry a private token |
| `calendar-term-dark.webp` | 1440×900 | 52 KB | Calendar Term view of the Bahar 2026 board: room use for each day of the term |
| `calendar-term-light.webp` | 1440×900 | 50 KB | Calendar Term view of the Bahar 2026 board: room use for each day of the term |
| `calendar-week-dark.webp` | 1440×900 | 48 KB | Calendar Week view of the busiest room in week 3 of the published Güz timetable |
| `calendar-week-light.webp` | 1440×900 | 50 KB | Calendar Week view of the busiest room in week 3 of the published Güz timetable |
| `classes-dark.webp` | 1440×900 | 53 KB | All classes of the term grouped by faculty with status, programme, instructor initials, size and room |
| `classes-inspector-dark.webp` | 1440×900 | 65 KB | All classes with one class open in the inspector |
| `classes-inspector-light.webp` | 1440×900 | 59 KB | All classes with one class open in the inspector |
| `classes-light.webp` | 1440×900 | 53 KB | All classes of the term grouped by faculty with status, programme, instructor initials, size and room |
| `dashboard-dark.webp` | 1440×900 | 46 KB | Dashboard for Güz 2026-27: room use this week, classes that still need a room, requests waiting for review, use through the day and by building |
| `dashboard-light.webp` | 1440×900 | 47 KB | Dashboard for Güz 2026-27: room use this week, classes that still need a room, requests waiting for review, use through the day and by building |
| `find-room-dark.webp` | 1440×900 | 56 KB | Find a room: date, time, head count and the computer lab feature, with ranked free rooms and their reasons |
| `find-room-light.webp` | 1440×900 | 58 KB | Find a room: date, time, head count and the computer lab feature, with ranked free rooms and their reasons |
| `free-slots-dark.webp` | 1440×900 | 56 KB | Free slots view: the free periods of the day grouped by room, each a button that books it |
| `free-slots-light.webp` | 1440×900 | 63 KB | Free slots view: the free periods of the day grouped by room, each a button that books it |
| `import-dark.webp` | 1440×900 | 33 KB | Import page: the kinds of workbook it reads, a drop zone and the import history |
| `import-light.webp` | 1440×900 | 34 KB | Import page: the kinds of workbook it reads, a drop zone and the import history |
| `mobile-bookings-dark.webp` | 780×1688 | 36 KB | Bookings on a phone: the free slots list |
| `mobile-bookings-light.webp` | 780×1688 | 38 KB | Bookings on a phone: the free slots list |
| `mobile-timetable-dark.webp` | 780×1688 | 42 KB | Calendar Day view on a phone |
| `mobile-timetable-light.webp` | 780×1688 | 43 KB | Calendar Day view on a phone |
| `my-bookings-dark.webp` | 1440×900 | 40 KB | My bookings: upcoming bookings with totals, CSV export and the calendar feed |
| `my-bookings-light.webp` | 1440×900 | 40 KB | My bookings: upcoming bookings with totals, CSV export and the calendar feed |
| `onboarding-review-dark.webp` | 1440×900 | 45 KB | Onboarding review of the Final 2026 exam planning list: the proposed term and the items that need a decision |
| `onboarding-review-light.webp` | 1440×900 | 47 KB | Onboarding review of the Final 2026 exam planning list: the proposed term and the items that need a decision |
| `reserve-sheet-dark.webp` | 1440×900 | 44 KB | The booking sheet open on a free period: room, date, period, an optional note and the Reserve button |
| `reserve-sheet-light.webp` | 1440×900 | 52 KB | The booking sheet open on a free period: room, date, period, an optional note and the Reserve button |
| `room-details-dark.webp` | 1440×900 | 49 KB | Room details for A 101: seats, building and features, its day, the next free slot and other rooms free at the same time |
| `room-details-light.webp` | 1440×900 | 56 KB | Room details for A 101: seats, building and features, its day, the next free slot and other rooms free at the same time |
| `room-features-dark.webp` | 1440×900 | 44 KB | Setup, Rooms, Features: typed features adopted from the room master's tags, with the values per room |
| `room-features-light.webp` | 1440×900 | 45 KB | Setup, Rooms, Features: typed features adopted from the room master's tags, with the values per room |
| `rooms-dark.webp` | 1440×900 | 42 KB | Rooms as cards with seats, exam seats, features and use per weekday |
| `rooms-light.webp` | 1440×900 | 43 KB | Rooms as cards with seats, exam seats, features and use per weekday |
| `run-data-issues-dark.webp` | 1440×900 | 66 KB | Problems found in the workbooks themselves, grouped, with an Excel export |
| `run-data-issues-light.webp` | 1440×900 | 69 KB | Problems found in the workbooks themselves, grouped, with an Excel export |
| `run-diagnoses-dark.webp` | 1440×900 | 76 KB | Classes without a room, each with the reason, the rooms that would fit and what holds them, and fixes |
| `run-diagnoses-light.webp` | 1440×900 | 77 KB | Classes without a room, each with the reason, the rooms that would fit and what holds them, and fixes |
| `run-report-dark.webp` | 1440×900 | 66 KB | Run report for Güz week 3: classes placed with every hard rule kept, the soft score and what could not be placed |
| `run-report-light.webp` | 1440×900 | 67 KB | Run report for Güz week 3: classes placed with every hard rule kept, the soft score and what could not be placed |
| `settings-ai-dark.webp` | 1440×900 | 40 KB | Settings, AI: the AI intake and vision switches, off by default, with the KVKK notice |
| `settings-ai-light.webp` | 1440×900 | 42 KB | Settings, AI: the AI intake and vision switches, off by default, with the KVKK notice |
| `studio-precheck-dark.webp` | 1440×900 | 72 KB | Generator Studio pre-check: problems in the data grouped by kind, each with fixes |
| `studio-precheck-light.webp` | 1440×900 | 73 KB | Generator Studio pre-check: problems in the data grouped by kind, each with fixes |
| `studio-rules-dark.webp` | 1440×900 | 69 KB | Generator Studio rules step: rules as sentences grouped into Must and Try to |
| `studio-rules-light.webp` | 1440×900 | 70 KB | Generator Studio rules step: rules as sentences grouped into Must and Try to |
| `studio-scope-dark.webp` | 1440×900 | 54 KB | Generator Studio scope step: term, classes or exams, a week, a month or the whole term |
| `studio-scope-light.webp` | 1440×900 | 54 KB | Generator Studio scope step: term, classes or exams, a week, a month or the whole term |
