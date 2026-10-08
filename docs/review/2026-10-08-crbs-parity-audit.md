# CRBS parity audit — classroombookings PHP vs SmartSched (2026-10-08, checkout be27d67)

Method: every CRBS controller/model/library/helper/view read; the six `test_crbs_*` suites (33 passed); backend run on SQLite
with the real Bahar workbooks plus a term covering today, the 18-period schedule, room groups from buildings and three
Teacher users; 11 live API probes. Upstream GitHub issues were unreachable (403).

Verdicts over 91 behaviours: **MATCH 52 · DIFFERS 21 · MISSING 6 · BUG 12** (+4 minor bugs merged into rows).
Faithful: permission resolution (role ∪ room/group ACL with user/role/department contexts), R/U/X constraints, active-booking
count, cancel rules, edit field rights, multi-booking, the 24 CSV columns. Improved on CRBS: DB unique key on booking slots
(12 parallel POSTs → one 201), server-decided "replace", escaped LDAP filter, real events.

## Bugs (ranked)

| ID | Sev | Bug | Where | Fix |
|---|---|---|---|---|
| B1 | MAJOR | "Replace" cancels the old booking even when the new instance is then skipped (timetable/block under it) → data loss | `services/bookings.py:723-744`, preview `:632-650` | check conflicts excluding the old booking first; offer only do_not_book; or SAVEPOINT + rollback |
| B2 | MAJOR | Stored XSS via SVG org logo; room photos accept any bytes | `api/v1/org.py:216-232`, `api/v1/room_admin.py:277-294`, `main.py:155` | drop SVG; Pillow re-encode + max 1600 px; `nosniff` + `CSP default-src 'none'` on /uploads |
| B3 | MAJOR | `POST /terms {is_active:true}` stores false (autoflush deactivates itself) → term not selectable, dashboard totals 0 | `api/v1/terms.py:27-29` | exclude self; compute `is_current` from dates like CRBS |
| B4 | MAJOR | CRBS migration yields unusable users (no username/password/role_id, teachers → VIEWER) and bookings as solver blocks, no ACLs/constraints/weeks/owners | `importers/crbs_legacy.py:440-585`, `tests/test_import_crbs.py:95-97` | import into parity tables; carry usernames + hashes; verify `$2y$` bcrypt and `sha1:` then rehash to argon2 |
| B5 | MINOR | Grid says available, POST says 409 range_min (role-level vs room-level book_recur check) | `services/bookings.py:397,1309-1319` | pass room to check_window |
| B6 | MINOR | `PUT /bookings/{id}` with explicit nulls → 500/404/409 | `services/bookings.py:901-906` | reject nulls → 422 |
| B7 | MINOR | Default group and room order ignore configured `pos` | `services/bookings.py:1225,1258-1259` | sort by RoomGroup.pos |
| B8 | MINOR | Org settings accept `javascript:` website, unknown languages/default, free-text date patterns | `api/v1/org.py:171-195`, `schemas/crbs.py:412-427` | http(s) only; shipped languages; pattern option list endpoint |
| B9 | MINOR | CSV formula injection in booking export | `services/bookings_export.py:116` | quote-prefix `= + - @ \t \r` |
| B10 | MINOR | No throttling on login and public reset; each reset revokes earlier tokens | `services/bookings_users.py:200-207`, `api/v1/org.py:488-506` | per-IP/account limits; keep unexpired token |
| B11 | MINOR | ICS hard-codes Europe/Istanbul, no VTIMEZONE | `services/bookings_export.py:170,193-194` | use timezone setting + VTIMEZONE or UTC |
| B12 | MINOR | Changelog "seen" stored as a date | `api/v1/org.py:392-400` | timestamp/version |
| B13 | MINOR | With room groups off, grid uses rooms[0]'s schedule for all rooms | `services/bookings.py:1271` | per-room schedules |
| B14 | MINOR | Clearing a room's group leaves stale free-text `rooms.room_group` | `api/v1/room_admin.py:256-258` | null it too |
| B15 | MINOR | Week view lists days without periods; prev/next lands on them | `services/bookings.py:1268-1269,1322-1374` | CRBS rules (Context.php:438-443, Dates_model.php:193-262) |
| B16 | MINOR | FK CASCADE deletes booking history on period/room delete; owners not notified | `models/booking.py:269,304,317`, `api/v1/rooms.py:92-96` | RESTRICT + soft delete, or 409 with count |

## Missing

1. **MAJOR — the whole CRBS frontend** (grid, booking sheet, recurring preview, multi wizard, details/edit/cancel, staff dashboard,
   my bookings + ICS, profile, users/import, roles, departments, room groups/fields/ACL/access checker, sessions/holidays/schedules/
   weeks, org/general/LDAP/SMTP/outbox/translations, export, conflicts, login logo/message/maintenance/forgot password) — being built.
2. **MAJOR — translations, date patterns and languages are stored but never applied** (CRBS applies overrides on every page and
   formats every date with the patterns).
3. MINOR — changing term dates does not cancel/flag out-of-range bookings (CRBS `check_session_dates`).
4. MINOR — legacy password hash verification (part of B4).
5. MINOR — `grid_highlight` setting; printable bookings page.
6. MINOR — installer requirements step; session create/delete under `setup.sessions` (today needs `planning.edit`).

## Deliberate differences (decided by the orchestrator under the user's rule "inherit CRBS by default, with an option to change")

- **Behaviour/feature differences** default to CRBS behaviour with an org setting to switch: (a) max_active_bookings enforced on
  every single POST, (f) replacements counted in recur_max_instances, (g) maintenance gating dashboard/mine/feeds, (i) `is_current`
  computed from dates, (j) export including ungrouped rooms, (b) recurring set_user/set_department permission names.
- **Security differences** keep the safer behaviour by default, with a setting to restore CRBS behaviour where it is harmless:
  (c) 403 on unauthorised set_user/department, (d) current password required to change it, (e) booking details need room.view
  or ownership; LDAP local fallback only when the directory is unreachable; `ldap.ignore_cert` default false; `setup.users`
  cannot grant Administrator without `setup.roles`; room delete refuses when active bookings exist; owners cannot move a booking
  into the past or beyond range_max; `scope=all` cancel affects only future instances (setting to restore CRBS).
- "What's new" reads the local CHANGELOG.md (no remote feed).
