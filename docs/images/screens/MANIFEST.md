# README screenshots

Captured 2026-10-08 by [`scripts/record/screens.mjs`](../../../scripts/record/screens.mjs) from the recording stack
([`scripts/record/stack.sh`](../../../scripts/record/stack.sh)): the real FastAPI backend on SQLite with the real
workbooks of Bahar 2026, Güz 2026-27 and Final 2026 plus the room master, and a production build of the frontend
(`next build` + `next start`). No mock data. Solver runs were made through `POST /runs`
(`stack.sh runs`): run #7 Güz week 3 (FEASIBLE_PARTIAL, 522/548 placed, hard 100) and run #8 Güz whole term
(FEASIBLE_PARTIAL, 519/548, hard 100, published). The shots were taken after the four seeded recordings, so the
booking, the template rule and the Planner account those recordings made are visible.

- Desktop: 1440×900 CSS px at device scale 1. Phone: 390×844 at device scale 2 (780×1688).
- Locale en-GB / tr-TR via the `NEXT_LOCALE` cookie, theme via next-themes' `theme` key, Europe/Istanbul.
- WebP, quality 82 (ImageMagick `-define webp:method=6`). Files: 48, total 2.40 MB.
- Re-take: `scripts/record/stack.sh up && scripts/record/stack.sh runs && node scripts/record/screens.mjs`.

| File | Pixels | Size | Shows |
|---|---|---|---|
| `admin-roles-dark.webp` | 1440×900 | 51 KB | Setup → Roles: Administrator, Planner, Teacher, Viewer; limits and permissions. |
| `admin-roles-light.webp` | 1440×900 | 54 KB | Setup → Roles: Administrator, Planner, Teacher, Viewer; limits and permissions. |
| `admin-users-dark.webp` | 1440×900 | 27 KB | Setup → Users, incl. the Planner account created in the admin-user recording. |
| `admin-users-light.webp` | 1440×900 | 28 KB | Setup → Users, incl. the Planner account created in the admin-user recording. |
| `bookings-dark.webp` | 1440×900 | 38 KB | Booking grid by day (next teaching day), A building, with the published timetable and the booking made in the room-booking recording. |
| `bookings-light.webp` | 1440×900 | 39 KB | Booking grid by day (next teaching day), A building, with the published timetable and the booking made in the room-booking recording. |
| `calendar-board-dark.webp` | 1440×900 | 47 KB | Calendar Board lens, run #8, week 3: A building rooms × periods. |
| `calendar-board-light.webp` | 1440×900 | 51 KB | Calendar Board lens, run #8, week 3: A building rooms × periods. |
| `calendar-inspector-dark.webp` | 1440×900 | 66 KB | Week lens with the class inspector open (when and where, seats, instructor, why here, conflicts). |
| `calendar-inspector-light.webp` | 1440×900 | 70 KB | Week lens with the class inspector open (when and where, seats, instructor, why here, conflicts). |
| `calendar-term-dark.webp` | 1440×900 | 49 KB | Calendar Term lens on the planner's imported Bahar 2026 board: room use per day for every week. |
| `calendar-term-light.webp` | 1440×900 | 48 KB | Calendar Term lens on the planner's imported Bahar 2026 board: room use per day for every week. |
| `calendar-week-dark.webp` | 1440×900 | 43 KB | Calendar Week lens for the busiest room (A 204), week 3. |
| `calendar-week-light.webp` | 1440×900 | 45 KB | Calendar Week lens for the busiest room (A 204), week 3. |
| `classes-dark.webp` | 1440×900 | 61 KB | All classes of Güz 2026-27 with status, programme, instructor, students and room. |
| `classes-light.webp` | 1440×900 | 60 KB | All classes of Güz 2026-27 with status, programme, instructor, students and room. |
| `dashboard-dark.webp` | 1440×900 | 46 KB | Dashboard, Güz 2026-27 week 3, published run #8: room use, classes still needing a room, review queue, use through the day, building × day heat map. |
| `dashboard-light.webp` | 1440×900 | 48 KB | Dashboard, Güz 2026-27 week 3, published run #8: room use, classes still needing a room, review queue, use through the day, building × day heat map. |
| `dashboard-tr-light.webp` | 1440×900 | 49 KB | Dashboard in Turkish. |
| `login-dark.webp` | 1440×900 | 9 KB | Sign-in page (e-mail or username, password, forgot password, TR/EN switch). |
| `login-light.webp` | 1440×900 | 9 KB | Sign-in page (e-mail or username, password, forgot password, TR/EN switch). |
| `mobile-calendar-dark.webp` | 780×1688 | 41 KB | Calendar Day lens on a phone: week strip and the day's classes as a list. |
| `mobile-calendar-light.webp` | 780×1688 | 42 KB | Calendar Day lens on a phone: week strip and the day's classes as a list. |
| `mobile-dashboard-dark.webp` | 780×1688 | 40 KB | Dashboard on a phone with the tab bar. |
| `mobile-dashboard-light.webp` | 780×1688 | 43 KB | Dashboard on a phone with the tab bar. |
| `my-bookings-dark.webp` | 1440×900 | 30 KB | My bookings: the admin's upcoming booking, calendar subscription, CSV export. |
| `my-bookings-light.webp` | 1440×900 | 31 KB | My bookings: the admin's upcoming booking, calendar subscription, CSV export. |
| `room-detail-dark.webp` | 1440×900 | 64 KB | Room A 204: weekly occupancy grid, free-slot finder, term occupancy, classes of the week. |
| `room-detail-light.webp` | 1440×900 | 64 KB | Room A 204: weekly occupancy grid, free-slot finder, term occupancy, classes of the week. |
| `rooms-dark.webp` | 1440×900 | 59 KB | Rooms: 87 rooms in 4 buildings as cards with seats, exam seats, tags and weekday occupancy. |
| `rooms-light.webp` | 1440×900 | 61 KB | Rooms: 87 rooms in 4 buildings as cards with seats, exam seats, tags and weekday occupancy. |
| `run-data-issues-dark.webp` | 1440×900 | 53 KB | Run #7, problems in the workbooks: instructor/cohort clashes, planned rooms too small, missing enrolments, lectures listed twice, Excel export. |
| `run-data-issues-light.webp` | 1440×900 | 56 KB | Run #7, problems in the workbooks: instructor/cohort clashes, planned rooms too small, missing enrolments, lectures listed twice, Excel export. |
| `run-diagnoses-dark.webp` | 1440×900 | 73 KB | Run #7, classes without a room: reason per class (rooms that fit and what holds them) and fix options. |
| `run-diagnoses-light.webp` | 1440×900 | 75 KB | Run #7, classes without a room: reason per class (rooms that fit and what holds them) and fix options. |
| `run-report-dark.webp` | 1440×900 | 53 KB | Run report of run #7 (Güz week 3, partial 522/548, hard rules kept, soft score, first unplaced class with fixes). |
| `run-report-light.webp` | 1440×900 | 55 KB | Run report of run #7 (Güz week 3, partial 522/548, hard rules kept, soft score, first unplaced class with fixes). |
| `settings-appearance-dark.webp` | 1440×900 | 30 KB | Settings → Appearance: theme, accent, density, reduce motion / transparency. |
| `settings-appearance-light.webp` | 1440×900 | 31 KB | Settings → Appearance: theme, accent, density, reduce motion / transparency. |
| `setup-requirements-dark.webp` | 1440×900 | 34 KB | Setup checklist and server requirements. |
| `setup-requirements-light.webp` | 1440×900 | 35 KB | Setup checklist and server requirements. |
| `studio-precheck-dark.webp` | 1440×900 | 66 KB | Studio pre-check: readiness Blocked, problems grouped by kind, a card naming two classes locked into one room with fixes. |
| `studio-precheck-light.webp` | 1440×900 | 66 KB | Studio pre-check: readiness Blocked, problems grouped by kind, a card naming two classes locked into one room with fixes. |
| `studio-rules-dark.webp` | 1440×900 | 58 KB | Studio rules step: one-click common rules and the term's rules as sentences (Must / Try to), incl. the template rule added by the studio-rule-fix recording. |
| `studio-rules-light.webp` | 1440×900 | 58 KB | Studio rules step: one-click common rules and the term's rules as sentences (Must / Try to), incl. the template rule added by the studio-rule-fix recording. |
| `studio-rules-tr-light.webp` | 1440×900 | 62 KB | Studio rules step in Turkish (rules as Turkish sentences). |
| `studio-scope-dark.webp` | 1440×900 | 51 KB | Generator Studio, scope step: term, classes/exams, horizon, plain sentence of what will be planned. |
| `studio-scope-light.webp` | 1440×900 | 51 KB | Generator Studio, scope step: term, classes/exams, horizon, plain sentence of what will be planned. |

Recordings are in [`../recordings/`](../recordings/): `<journey>.mp4` (H.264, 1600×1060, 30 fps), `<journey>.webp`
(animated, under 3.9 MB, used in the README) and `<journey>-poster.webp`. They are made by
`scripts/record/record-all.sh` (Playwright video + ffmpeg polish, see `docs/recording/RECORDLY.md`) and copied with
`scripts/record/publish.sh`.
