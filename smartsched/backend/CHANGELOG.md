# SmartSched changelog

Shown to signed-in users as "What's new" (`GET /api/v1/org/changelog`). Newest first; one
`## [version] YYYY-MM-DD` heading per release, `### Added` / `### Updated` / `### Fixed` sections.

## [0.4.0] 2026-10-08

### Added
- Bookings for staff (CRBS parity): single, recurring (timetable week + weekday, holidays skipped) and multi-slot bookings, edit and cancel (one, this and future, all), cancellation reasons.
- Roles with permission sets and booking limits (active bookings, booking window, recurring instances), per-user overrides, and the Teacher self-service role.
- Room groups, room owners, locations, icons, custom fields (text, checkbox, list) and room access control by user, role or department, with an access checker.
- Schedules and periods on the university's 18-period grid, timetable weeks with colours, holidays.
- The published timetable blocks bookings, and confirmed bookings block the optimizer.
- CSV export of bookings, iCalendar feeds per user and per room, e-mail notifications with an outbox.
- User CSV import, username or e-mail sign-in, LDAP sign-in, one-time password reset codes, forced password change.
- Organisation settings, login message, maintenance mode, translation overrides, first-run setup.

## [0.3.0] 2026-10-08

### Added
- Generator Studio: classes, rules, uploads, presets, pre-check with fixes, generate and compare.
- Real-data feasibility: room master, computer labs, trusted locks, partial timetables, split exam rooms.

## [0.2.0] 2026-10-08

### Added
- Claude-assisted rules, preference-file ingestion, chat edits with validated apply, explanations.
- One-command deployment, CI, restart recovery of interrupted runs.

## [0.1.0] 2026-10-07

### Added
- Importers for the planning lists, the exam list, the weekly room grids and the legacy CRBS database.
- CP-SAT timetabling with diagnoses of infeasibility and repair.
- Admin panel with the timetable grid, imports, requests, rooms, runs and settings.
