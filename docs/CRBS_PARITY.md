# CRBS → SmartSched parity: users, rooms and bookings

Source read for this analysis (branch `claude/gracious-cerf-w1598m`):
`crbs-core/application/{controllers,controllers/settings,controllers/setup,controllers/setup/rooms}`,
`models/*.php`, `libraries/{Permission,Userauth,Auth_local,Auth_ldap,Events,Changelog,Dates}.php`,
`permissions/{SystemPermissions,BookingPermissions}.php`, `components/bookings/{Context,Slot,Grid}.php`,
`components/bookings/agent/{BaseAgent,SingleAgent,MultiAgent,UpdateAgent}.php`, `helpers/booking_helper.php`,
`core/{MY_Controller,MY_Lang}.php`, `migrations/*.php`, `modules/install/**` and
`modules/install/resources/{structure,data}.sql`.

Status columns: **before** = SmartSched before this work (2026-10-08), **after** = what the backend in
`smartsched/backend` provides now. *exists* = equivalent already present, *partial* = some of it,
*missing* = absent. Where SmartSched deliberately behaves differently, the row says so.

---

## 1. Permission model (CRBS 2.15)

`Permission::can()` resolves `group.action` names through two rule classes:

* `SystemPermissions::system()/setup()`: the user's **role** permissions only.
* `BookingPermissions::book_single()/book_recur()` and `room.view`: the **role** permissions **plus** the
  room ACL entries (`auth_acl` + `auth_acl_permissions`) whose entity is the room or its room group and
  whose context is the user, the user's role or the user's department (`Auth_model::user_room_permissions`).
  Checks made without a room (`has_permission(X)` with no room id) see only role permissions; for
  example, `booking_cancelable()` asks this first so that admins bypass the date checks.

The 28 permissions that `data.sql` ships, and the default roles:

| Permission | Administrator | Teacher | Used by (CRBS) |
|---|:-:|:-:|---|
| `system.bypass_maintenance_mode` | ✓ | | `Bookings::__construct` (maintenance gate) |
| `system.export_bookings` | ✓ | | `Export` controller |
| `system.view_all_sessions` | ✓ | | `Context::init_session`, `Bookings::change_session` |
| `setup.authentication` | ✓ | | `settings/Authentication` (LDAP) |
| `setup.departments` | ✓ | | `Departments` |
| `setup.roles` | ✓ | | `Roles` |
| `setup.rooms` | ✓ | | `setup/rooms/{Rooms,Groups,Fields}` |
| `setup.rooms_acl` | ✓ | | `setup/rooms/Acl`, `setup/Access_checker` |
| `setup.schedules` | ✓ | | `Schedules`, `Periods` |
| `setup.sessions` | ✓ | | `Sessions`, `Holidays`, `Room_schedules` |
| `setup.settings` | ✓ | | `settings/{General,Organisation}`, `setup/Language` |
| `setup.timetable_weeks` | ✓ | | `Weeks` |
| `setup.users` | ✓ | | `Users` (incl. CSV import), `Access_checker` |
| `room.view` | ✓ | ✓ | `Rooms_model::get_bookable_rooms` (role-level = all rooms; otherwise ACL rooms only) |
| `book_single.create` | ✓ | ✓ | `Slot::check_free_constraints`, `SingleAgent`, `MultiAgent` |
| `book_single.edit_other_booking` | ✓ | | `booking_editable()`, `UpdateAgent` |
| `book_single.cancel_other_booking` | ✓ | | `booking_cancelable()`, `BaseAgent::get_actions` ("replace") |
| `book_single.set_user` | ✓ | | book on behalf of another user |
| `book_single.set_department` | ✓ | | set booking department |
| `book_single.view_other_notes` | ✓ | ✓ | `booking_notes_viewable()`, `Slot::checked_booked` |
| `book_single.view_other_users` | ✓ | | `booking_user_viewable()` |
| `book_recur.create` … `book_recur.view_other_users` (7) | ✓ (all) | `view_other_notes` | same as above, for recurring bookings |

Role booking limits (`auth_roles.max_active_bookings`, `range_min`, `range_max`, `recur_max_instances`)
can be overridden per user in `users_constraints` with a type per limit: `R` = use the role value,
`U` = use the user value, `X` = unlimited (`Users_model::get_constraints`).

### SmartSched mapping

| CRBS | SmartSched (after) | Notes |
|---|---|---|
| `auth_permissions` | `permissions` (name, group, description) | All 28 CRBS names kept verbatim, plus three SmartSched names: `planning.view`, `planning.edit`, `planning.admin` (scope *system*) |
| `auth_roles` | `roles` (+ `code`: `ADMIN` / `PLANNER` / `VIEWER` / `TEACHER` for seeded roles, null for custom roles) | Booking limits are the same four nullable columns |
| `auth_roles_permissions` | `role_permissions` | |
| `users.role_id` | `users.role_id` (FK) **and** `users.role` (the role `code`, or `CUSTOM`), kept in sync | The old coarse `role` string stays for the JWT, the frontend and existing checks (`user.role != "ADMIN"`) |
| `users_constraints` | `user_constraints` (R/U/X per limit) | |
| `auth_acl` + `auth_acl_permissions` | `room_acl` + `room_acl_permissions` | entity `room`/`room_group`, context `user`/`role`/`department` |
| `has_permission(p, room_id)` | `app/services/bookings_perms.py::has_permission(session, user, p, room_id)` | role ∪ ACL, same as `BookingPermissions` |

Seeded roles (migration `0003_crbs_parity` and `seed_admin()`; no other data is seeded):

| Role (code) | Permissions | Origin |
|---|---|---|
| Administrator (`ADMIN`) | all 31 | CRBS role 1 + the planning permissions |
| Teacher (`TEACHER`) | `room.view`, `book_single.create`, `book_single.view_other_notes`, `book_recur.view_other_notes` | CRBS role 2, verbatim from `data.sql`; the self-service staff role |
| Planner (`PLANNER`) | `planning.view`, `planning.edit`, `system.view_all_sessions`, `system.export_bookings`, `system.bypass_maintenance_mode`, `room.view`, all 14 `book_single.*` / `book_recur.*` | the existing SmartSched planner, unchanged in what it can reach |
| Viewer (`VIEWER`) | `planning.view`, `room.view`, `book_*.view_other_notes`, `book_*.view_other_users` | the existing read-only SmartSched viewer |

Route guards: the existing `Viewer` / `Planner` / `Admin` dependencies now check `planning.view` /
`planning.edit` / `planning.admin`. `/users` checks `setup.users`. Every new route names its CRBS
permission (see §4). A user whose `role_id` is still empty (rows created before the migration, or by an
importer) is resolved by the `role` code, so nothing that worked before breaks.

---

## 2. Feature matrix

Legend for *Perm.*: the CRBS permission that guards the feature (`login` = any signed-in user).

### 2.1 Install, setup and organisation

| # | CRBS feature (controller::action / model) | What it does | Perm. | Data | Before | After | SmartSched endpoint |
|---|---|---|---|---|---|---|---|
| 1 | `install/Install::{check,config,info}`, `Installer::execute` | Wizard: requirements check, DB config check, school name, first admin (role 1), default settings, `structure.sql` + `data.sql` | none (only when not installed) | `settings`, `users`, seeded tables | partial (admin from env only) | exists | `GET /org/setup/requirements` (the CRBS **requirements step**: Python version, image library, LDAP module = warning only, writable uploads folder, database and schema; public only while no user exists, then `setup.settings`; an `err` blocks the install), `GET /org/setup-status` (public checklist), `POST /org/setup` (public, only while the users table is empty and the requirements hold, else 409: org name, timezone, first admin). Parity rows B-SETUP-01/02 |
| 2 | `Upgrade` controller | Upgrade a v1 install (copy images, write config, run migrations) | none | all | exists (Alembic + entrypoint) | exists | `alembic upgrade head`; `0003_crbs_parity` |
| 3 | `setup/Dashboard`, `Menu_model::setup_menu` | Setup menu filtered by `setup.*` permissions | any `setup.*` | | missing | exists | `GET /auth/permissions` (the UI builds the menu) + `GET /org/setup-status` |
| 4 | `settings/Organisation::index` | School name, website, logo upload (jpg/png/gif ≤1600 px) | `setup.settings` | `settings` (crbs) | missing | exists | `GET/PUT /org/settings`, `POST/DELETE /org/logo` |
| 5 | `settings/General::index` | Bookings display type (day/room), columns (periods/rooms/days), timezone, login message (on/off + text), maintenance mode (on/off + message), date patterns (long/weekday/time) | `setup.settings` | `settings` (crbs, dates, features) | partial (`timezone` only) | exists | `GET/PUT /org/settings` |
| 6 | `bookings_show_name` / `bookings_show_user_*` (migrations 2020-09, 2025-03) | Show booking owner names to other users. Since 2.15 this is the Teacher role's `view_other_users` permissions | `setup.settings` | role permissions | missing | exists | `PUT /org/settings {bookings_show_name}` adds/removes `book_single.view_other_users` + `book_recur.view_other_users` on the Teacher role (the CRBS migration's semantics) |
| 7 | `num_max_bookings` (migration 2020-06) | Global cap of active bookings (pre-roles); since 2.15 the role's `max_active_bookings` | `setup.settings` | role | missing | exists | `PUT /org/settings {max_active_bookings}` sets the Teacher role limit; it is also readable there |
| 8 | Room groups feature toggle (`use_room_groups`, migration 2023-04; always on since 2.8) | Group rooms in the grid | `setup.settings` | `settings` | missing | exists | `PUT /org/settings {use_room_groups}`; when off, the grid shows all visible rooms in one list |
| 9 | Maintenance mode gate (`Bookings::__construct`) | Booking pages show only the message unless `system.bypass_maintenance_mode` | bypass perm | | missing | exists | every `/bookings/*` route returns 503 `{detail: message}` unless the user has the bypass permission |
| 10 | `Login::index` login message, logo | Shown on the login page | public | | missing | exists | `GET /org/public` (name, logo, login message, maintenance, `ldap_enabled`, `setup_required`) |
| 11 | `setup/Language`, `MY_Lang::load_from_db`, table `lang` | Enabled languages + default; DB overrides of any translation string `(language, set, key, text)` | `setup.settings` | `lang`, `settings` (lang) | partial (UI has TR/EN files) | exists | `GET /org/translations?language=`, `PUT /org/translations` (upsert list), `DELETE /org/translations/{id}`; languages in `/org/settings` |
| 12 | `Changelog` library, `Dashboard::changelog[_status]` | "What's new" indicator per user (last viewed timestamp) | login | `settings` (changelog, user.N) | missing | exists | `GET /org/changelog` (entries parsed from `smartsched/backend/CHANGELOG.md`, `unread` flag), `POST /org/changelog/seen` |
| 13 | `Events` library, `EventType::USER_LOGGED_IN` | In-process event hooks (`register`, `trigger`) | code | | missing | exists | `app/services/bookings_events.py` (`on`, `emit`); events `user.logged_in`, `booking.created`, `booking.updated`, `booking.cancelled`, `series.created`, `password.reset_requested`; `GET /org/events` lists them and their handlers |

### 2.2 Authentication and users

| # | CRBS feature | What it does | Perm. | Data | Before | After | SmartSched endpoint |
|---|---|---|---|---|---|---|---|
| 14 | `Login`, `Userauth::log_in`, `Auth_local::verify` | Username + password; disabled users refused; legacy `sha1:` hashes upgraded; `lastlogin` stamped | public | `users` | partial (e-mail login) | exists | `POST /auth/login {email \| username, password}`: e-mail or username (Turkish-insensitive), stamps `last_login_at`, emits `user.logged_in`, returns `password_change_required` |
| 15 | `Auth_ldap::authenticate/verify` | Bind as `bind_dn_format` (`:user`), optional search (`base_dn`, `search_filter`), map attributes with templates (`:givenName :sn`), create the user (default role + department) when `ldap_create_users`, refuse disabled users, keep a local password copy; fall back to local auth when the server is unreachable | public | `settings` (auth), `users` | missing | exists | same `POST /auth/login`; `app/services/bookings_ldap.py` with `ldap3`; settings at `GET/PUT /org/auth/ldap`, `POST /org/auth/ldap/test` (`setup.authentication`) |
| 16 | `force_password_reset` (2.11), `MY_Controller::check_password_reset`, `Profile::new_password` | Admin marks a user; after login (local auth) every page redirects to "set new password"; new password must differ | login | `users` | missing | exists | flag on the user; every authenticated route except `/auth/me`, `/auth/change-password`, `/auth/permissions` returns 403 `password_change_required`; `POST /auth/change-password` |
| 17 | Password reset (CRBS: admin sets a password; no e-mail flow) | | `setup.users` | `users` | partial (`POST /users/{id}/password`) | exists (extended) | `POST /users/{id}/reset-token` → one-time token shown to the admin, or e-mailed when SMTP is configured; `POST /auth/password-reset/request {email}` (public, never reveals whether the account exists); `POST /auth/password-reset/confirm {token, password}` |
| 18 | `Profile::{index,edit,save}` | Own e-mail, first/last/display name, extension, password, language | login | `users`, `settings` (user.N) | missing | exists | `GET/PUT /auth/profile` |
| 19 | `Users::index` | List with search (username, names, e-mail), role and department filters, sort, paging | `setup.users` | `users` | partial (no filters) | exists | `GET /users` (unchanged) + `GET /users/search?q=&role_id=&department_id=&enabled=&sort=&limit=&offset=`; `sort` follows CRBS's `sort_map` (username, displayname, lastlogin, enabled, role **name**, department **name**; comma-separated keys, `-` = descending, NULLs first ascending like MySQL) in Turkish alphabetical order (Ç after C, İ/I, Ö, Ş, Ü). Fixed 2026-10-08 by the superset gate (B-USERS-01): names were sorted by code point (İpek before Çağla) and role / department by code / id |
| 20 | `Users::add/edit/save_user` | username (≤32, `[A-Za-z0-9-_.@]`), role, department, enabled, e-mail, names, display name, extension, force reset, password (optional when LDAP), per-user constraints | `setup.users` | `users`, `users_constraints` | partial | exists | `POST/PUT /users` now accept `username, role_id, department_id, firstname, lastname, displayname (= full_name), ext, force_password_reset`; `GET/PUT /users/{id}/constraints` |
| 21 | `Users::delete`, `Users_model::Delete` | Refuses own account; deletes the user's bookings and series, ACLs, constraints; clears room ownership | `setup.users` | many | partial | exists | `DELETE /users/{id}` (bookings keep their history: `user_id` → NULL, as the FK says; ACL rows, constraints and ownership are removed) |
| 22 | `Users::import`, `process_import`, `add_user` | CSV `username, firstname, lastname, email, password, role, department`; optional header; defaults for password/role/department/enabled/force reset; existing usernames skipped; per-row status (`success`, `username_exists`, `password_empty`, `invalid`, …) | `setup.users` | `users` | missing | exists | `POST /users/import` (multipart CSV + defaults) → per-row results. UTF-8 (with/without BOM), `;` or `,`, Turkish names. CRBS bug fixed: CRBS reads `force_password_reset` from the role column; SmartSched reads an optional 8th column |
| 23 | Display name (`users.displayname`) | Shown instead of username | | | exists (`full_name`) | exists | `displayname` is an alias of `users.full_name` |

### 2.3 Roles, constraints, departments

| # | CRBS feature | What it does | Perm. | Data | Before | After | SmartSched endpoint |
|---|---|---|---|---|---|---|---|
| 24 | `Roles::index/add/edit/delete`, `Roles_model::set_permissions` | Role name, description, the four limits, permission checkboxes grouped system/setup/room/book_single/book_recur; delete clears `users.role_id` and role ACLs | `setup.roles` (reads also `setup.users`) | `auth_roles*` | missing | exists | `GET/POST /roles`, `GET/PUT/DELETE /roles/{id}`, `GET /permissions` (grouped and scoped like `Permissions_model::get_scoped`). The Administrator role cannot be deleted or stripped of `setup.roles` (lock-out guard). **No-escalation rule** (user decision 2026-10-08, deliberately stricter than CRBS, which lets a role editor tick any permission): a role editor may only put permissions they hold into a role, may only edit or delete roles whose permissions they all hold, and cannot raise their own role; the same rule guards user management (a role is granted only by someone holding all its permissions; Administrator also needs `setup.roles`). 403 names the missing permissions; the UI greys them out. Parity rows B-ROLES-08/09, DIFF-noesc |
| 25 | `users_constraints` R/U/X | Per-user override of each limit | `setup.users` | | missing | exists | `GET/PUT /users/{id}/constraints`; effective values in `GET /bookings/context` |
| 26 | `Departments` CRUD, `Departments_model::delete` | name (≤50), description; delete clears users' department and department ACLs | `setup.departments` | `departments` | partial (programmes) | exists | `GET/POST /departments`, `PUT/DELETE /departments/{id}` |

**Departments = programmes (deliberate).** CRBS departments are the units staff belong to. The
university's units are the *Bölüm/Program* values of the planning lists, which SmartSched already
stores in `programs` (100 in the Bahar list), and the legacy CRBS importer already maps CRBS
departments to programmes (`programs.legacy_crbs_department_id`). So a department **is** a `programs` row
(`description` and `icon` columns added). Deleting a programme that imported sections or exam requests
use is refused with 409, because re-importing the workbook would recreate it.

### 2.4 Rooms

| # | CRBS feature | What it does | Perm. | Data | Before | After | SmartSched endpoint |
|---|---|---|---|---|---|---|---|
| 27 | `setup/rooms/Groups` (+ `save_pos`) | Room groups: name (≤32), description, ordering, assign rooms | `setup.rooms` | `room_groups` | partial (free-text `rooms.room_group`) | exists | `GET/POST /room-admin/groups`, `PUT/DELETE /room-admin/groups/{id}` (`room_ids` assigns members), `PUT /room-admin/groups/order`, `POST /room-admin/groups/from-buildings` (one group per real building A/B/C/D) |
| 28 | `setup/rooms/Rooms::add/edit/save_room` | name (≤20), group, owner (user), location (≤40), bookable, notes, icon, photo upload, custom field values | `setup.rooms` | `rooms`, `roomvalues` | partial (code, capacity, tags, bookable, notes, photo) | exists | `GET /room-admin/rooms`, `PUT /room-admin/rooms/{id}` (group, owner, location, icon, notes, bookable), `PUT /room-admin/rooms/order`, `POST/DELETE /room-admin/rooms/{id}/photo`; codes/capacity stay on `/rooms` |
| 29 | `Rooms::save_pos` | Manual room order inside a group | `setup.rooms` | `rooms.pos` | partial (`pos` column) | exists | `PUT /room-admin/rooms/order` |
| 30 | `setup/rooms/Fields` | Custom fields of type `TEXT`, `CHECKBOX`, `SELECT` (options one per line); delete removes values | `setup.rooms` | `roomfields`, `roomoptions`, `roomvalues` | partial (`rooms.custom_fields` JSON) | exists | `GET/POST /room-admin/fields`, `PUT/DELETE /room-admin/fields/{id}`, `GET/PUT /room-admin/rooms/{id}/fields`. Values are also mirrored into `rooms.custom_fields` by field name, so the AI layer and the existing room UI see them |
| 31 | `setup/rooms/Acl` | ACL per room or room group for a user, role or department, with booking permissions | `setup.rooms_acl` | `auth_acl*` | missing | exists | `GET /room-admin/acl?entity_type=&entity_id=`, `POST /room-admin/acl`, `PUT/DELETE /room-admin/acl/{id}` |
| 32 | `setup/Access_checker::{index,user,room}` | Unified effective permissions for one user in one room (role ∪ ACL) | `setup.rooms_acl` or `setup.users` | | missing | exists | `GET /booking-admin/access-check?user_id=&room_id=` → `{from_role, from_acl, effective: {group: {permission: bool}}}` |
| 33 | `Rooms::info`, `Rooms::photo`, `Rooms_model::room_info` | Room info card: group, location, owner, notes, custom fields | login | | partial | exists | `GET /bookings/rooms/{id}` |
| 34 | `Rooms_model::get_bookable_rooms`, `Room_groups_model::get_bookable` | Rooms a user may see in the grid: bookable, and `room.view` from the role (all rooms) or from ACLs | login | | missing | exists | `GET /bookings/rooms?room_group_id=`. Deviation: CRBS hides rooms without a group; SmartSched shows them as "ungrouped" because imported rooms have no group until an admin creates one |
| 35 | Room owner (`rooms.user_id`; migration 2025-04 gives owners `book_single.cancel_other_booking` via ACL) | Owner sees others' bookings of their room on the dashboard | login | | missing | exists | `owner_user_id`; setting an owner creates the same ACL (room, user, `book_single.cancel_other_booking`); `GET /bookings/owned-rooms` |

### 2.5 Sessions, schedules, periods, weeks, holidays

| # | CRBS feature | What it does | Perm. | Data | Before | After | SmartSched endpoint |
|---|---|---|---|---|---|---|---|
| 36 | `Sessions` CRUD, `Sessions_model` | Academic years: name, start/end (no overlaps), `is_current` (auto: today in range), `is_selectable`, `default_schedule_id`; delete removes bookings, holidays, dates | `setup.sessions` | `sessions` | partial (`terms`, `is_active`) | exists | **session = term.** `terms` keep name/dates/`is_active` (= `is_current`); `term_booking_settings` adds `is_selectable`, `default_schedule_id`. `GET /booking-admin/sessions`, `PUT /booking-admin/sessions/{term_id}`. Terms may overlap in SmartSched (Bahar and its Final), so a booking stores its `term_id` (B-SESS-14); deleting a term deletes its bookings, holidays and calendar dates like `Sessions_model::delete` (B-SESS-15) |
| 37 | `Bookings::change_session`, `Context::init_session` | Users pick among selectable sessions; `view_all_sessions` sees past/active ones too | login | | missing | exists | `GET /bookings/context` lists the sessions the user may use; `term_id` query on grid routes |
| 38 | `Room_schedules::session/save`, `session_schedules`, `Schedules_model::get_applied_schedule` | Schedule per (session, room group); new sessions copy the default | `setup.sessions` | `session_schedules` | missing | exists | `GET/PUT /booking-admin/sessions/{term_id}/schedules`; ungrouped rooms use the term default |
| 39 | `Schedules` CRUD | name (≤32), description | `setup.schedules` | `schedules` | missing | exists | `GET/POST /booking-admin/schedules`, `PUT/DELETE /booking-admin/schedules/{id}` |
| 40 | `Periods` CRUD | name (≤30), start/end time, bookable, available days 1–7 | `setup.schedules` | `periods` | partial (fixed 18-slot grid) | exists | `GET/POST /booking-admin/schedules/{id}/periods`, `PUT/DELETE /booking-admin/periods/{id}`; `POST /booking-admin/schedules/{id}/periods/from-grid` creates the university's real 18 periods (08:30–22:50). A period's times are mapped onto the 18-period grid (`normalize.time_range_to_periods`, dotted times accepted) so bookings and the solver share one clock; times outside the grid are rejected |
| 41 | `Weeks` CRUD, `Weeks_model` | Timetable weeks (A/B rotation): name (≤20), background colour, text colour derived from brightness | `setup.timetable_weeks` | `weeks` | missing (SmartSched `weeks` are calendar weeks of a term) | exists | `GET/POST /booking-admin/weeks`, `PUT/DELETE /booking-admin/weeks/{id}` (table `timetable_weeks`; `fgcol` computed like `colour_brightness`) |
| 42 | `Sessions::view/save_dates/apply_week`, `Dates_model::set_weeks/apply_week` | Assign a timetable week to each date of a session (calendar), or one week to all dates | `setup.sessions` | `dates.week_id` | missing | exists | `GET/PUT /booking-admin/sessions/{term_id}/dates`, `POST /booking-admin/sessions/{term_id}/apply-week`. Rule: when a term has no mapping at all, every date is bookable and recurrence is weekly; once mapped, unmapped dates are closed (CRBS behaviour) |
| 43 | `Holidays` CRUD, `Dates_model::refresh_holidays` | Named date ranges inside a session (`_date_check`: 422 outside it); no bookings on them; recurring instances skip them; moving / deleting a holiday reopens its dates | `setup.sessions` | `holidays`, `dates.holiday_id` | partial (`weeks.kind = HOLIDAY`) | exists | `GET /holidays?term_id=`, `POST /holidays`, `PUT/DELETE /holidays/{id}`; whole weeks marked `HOLIDAY` in the term calendar count as holidays too |

### 2.6 Bookings

| # | CRBS feature | What it does | Perm. | Data | Before | After | SmartSched endpoint |
|---|---|---|---|---|---|---|---|
| 44 | `Bookings::index`, `Context`, `Grid`, `Slot` | Grid by **day** (rooms × periods) or by **room** (days × periods of one week), prev/next navigation, room group tabs, room filter, date filter; slot states: available, booked (single/recurring), unavailable (holiday, period not on this weekday, outside session range, limit reached, no permission, outside `range_min`/`range_max`) | login | all | missing | exists | `GET /bookings/grid?display=day\|room&date=&term_id=&room_group_id=&room_id=`; extra state `timetable` = held by the published solver run (or an imported block) |
| 45 | `Bookings::filter(room\|date)` | Room picker and date picker views | login | | missing | exists | `GET /bookings/rooms`, `GET /bookings/dates?term_id=&from=&to=` (each date with timetable week colours, holiday, open/closed) |
| 46 | `SingleAgent` single booking | Date + period + room; department (own, or chosen with `set_department`); user (self, or chosen with `set_user`); notes ≤255; constraint checks; conflict check (`validate_booking`) | `book_single.create` | `bookings` | missing | exists | `POST /bookings` |
| 47 | `SingleAgent` recurring: `get_recurring_dates`, `preview_single_recurring`, `create_single_recurring`, `Bookings_repeat_model::create` | Series = (session, period, room, timetable week, weekday); start/end = a date or "session"; preview lists each instance with actions **book / do not book / replace** (replace only for the owner or with `cancel_other_booking`); holidays skipped; at most `recur_max_instances` booked | `book_recur.create` | `bookings_repeat`, `bookings` | missing | exists | `POST /bookings/recurring/preview`, `POST /bookings/recurring` |
| 48 | `MultiAgent` multi-booking | Select many slots in the grid → `multi_bookings` + `multi_bookings_slots`; step 2: single (per-slot create/user/department/notes) or recurring (per-slot start/end); recurring preview with conflicts; created in one transaction; limit `max_active_bookings` respected | `book_*.create` per room | `multi_bookings*` | missing | exists | `POST /bookings/multi`, `GET/DELETE /bookings/multi/{mb_id}`, `POST /bookings/multi/{mb_id}/create {type, slots, dry_run}` |
| 49 | Notes and department on a booking | | set perms | | missing | exists | fields `notes`, `department_id` |
| 50 | Booking for another user | `set_user` | `book_*.set_user` | | missing | exists | `user_id` field |
| 51 | Conflict detection (`find_conflicts`, `validate_booking`, `no_conflict` rule, migration `cancel_recurring_conflicts`) | One active booking per (date, period, room) | | | missing | exists | **DB unique constraint** on `booking_slots(room_id, date, period)` (one row per occupied grid period of an active booking) + service check against other bookings, the active solver run(s) and blocks; 409 with the conflicting item |
| 52 | `Bookings::view/card`, `booking_user_viewable`, `booking_notes_viewable` | Details; user and notes hidden unless owner or `view_other_users` / `view_other_notes` (room-aware) | login | | missing | exists | `GET /bookings/{id}` (hidden fields come back `null` with `user_hidden` / `notes_hidden`) |
| 53 | `Bookings::view_series` | All instances of a series | login | | missing | exists | `GET /bookings/{id}/series` |
| 54 | `Bookings::edit`, `UpdateAgent` | Edit one instance (date, period, room, department, user, notes) or future/all instances (department, user, notes only); field rights from owner / `edit_other` / `set_*` / `view_other_*` | owner or `edit_other_booking` | | missing | exists | `PUT /bookings/{id}?scope=one\|future\|all` |
| 55 | `Bookings::cancel`, `cancel_single/future/all`, `booking_cancelable` | Cancel one, this and future, or the whole series; owners only for future slots; role-level `cancel_other` cancels anything; stamps `cancelled_at/by` | owner or `cancel_other_booking` | | missing | exists | `POST /bookings/{id}/cancel {scope, reason}`; `cancel_reason` stored (CRBS has the column, never filled; SmartSched fills it, also "replaced by series #N") |
| 56 | `Bookings::cancel_multi` | Cancel many selected bookings | same, per booking | | missing | exists | `POST /bookings/cancel-multi {booking_ids, reason}` |
| 57 | Limits: `Slot::check_free_constraints`, `SingleAgent::check_constraints`, `Users_model::get_scheduled_booking_count` | `max_active_bookings` (future single bookings the user made for themself), `range_min`/`range_max` days from today (single bookings), `recur_max_instances` | | | missing | exists | enforced in `POST /bookings`, `/bookings/recurring`, `/bookings/multi/*/create`; 409 with the limit |
| 58 | `Dashboard::index`, `Bookings_model::{ByUser,ByRoomOwner,TotalNum}` | My next 14 days of single bookings, others' bookings in rooms I own, totals (all / this session / active), my limits | login | | missing | exists | `GET /bookings/dashboard`, `GET /bookings/mine?from=&to=&status=` |
| 59 | `Export`, `Bookings_model::export_unbuffered` | CSV of bookings (24 columns) filtered by session, room group, include cancelled | `system.export_bookings` | | partial (run exports) | exists | `GET /bookings/export.csv?term_id=&room_group_id=&include_cancelled=` (UTF-8 with BOM, so Excel shows Turkish letters) |
| 60 | iCal (not in CRBS) | | | | partial (run ICS) | exists | `GET /bookings/feed/user.ics`, `GET /bookings/feed/room/{id}.ics` (bearer); `POST /bookings/feed/token` + `GET /ics/{token}/user.ics`, `GET /ics/{token}/room/{id}.ics` for calendar apps |
| 61 | E-mail notifications (not in CRBS) | | | | missing | exists | SMTP settings `GET/PUT /org/smtp`, `POST /org/smtp/test`; without SMTP every notification is stored in `notification_outbox` with status `UNSENT` (nothing pretends to send); `GET /booking-admin/outbox`, `POST /booking-admin/outbox/{id}/retry` |
| 62 | Solver integration (SmartSched only) | | | | missing | exists | the active run is shown as `timetable` occupancy; bookings never collide with it; confirmed bookings are solver blocks (`app/services/bookings_solver.py`, one call in `solver_bridge.build_solver_input`); `GET /bookings/conflicts?term_id=` lists bookings that clash with a newly activated run |

---

## 3. Data mapping (SmartSched tables)

| CRBS table | SmartSched | Kind |
|---|---|---|
| `users` | `users` + `username`, `firstname`, `lastname`, `ext`, `role_id`, `department_id`, `last_login_at`, `force_password_reset`, `auth_source`, `calendar_token`, `language`; `email` becomes nullable (CRBS users may have none) | reused, extended |
| `auth_roles`, `auth_permissions`, `auth_roles_permissions` | `roles`, `permissions`, `role_permissions` | new |
| `users_constraints` | `user_constraints` | new |
| `auth_acl`, `auth_acl_permissions` | `room_acl`, `room_acl_permissions` | new |
| `departments` | `programs` + `description`, `icon` | reused, extended |
| `rooms` | `rooms` + `room_group_id`, `owner_user_id`, `location`, `icon` (`notes`, `photo_url`, `pos`, `is_bookable` existed) | reused, extended |
| `room_groups` | `room_groups` | new |
| `roomfields`, `roomoptions`, `roomvalues` | `room_custom_fields`, `room_custom_field_options`, `room_custom_field_values` | new |
| `sessions` | `terms` + `term_booking_settings` (1:1) | reused, extended |
| `schedules`, `periods`, `session_schedules` | `booking_schedules`, `booking_periods` (with `start_period`/`end_period` on the 18-period grid), `term_schedules` | new |
| `weeks` | `timetable_weeks` | new (SmartSched `weeks` are term calendar weeks and stay) |
| `dates` (week_id, holiday_id) | `term_dates` (term_id, date, timetable_week_id); holidays computed from `holidays` | new |
| `holidays` | `holidays` | new |
| `bookings` | `bookings` (+ `term_id`, `start_period`, `end_period`, `multi_booking_id`) and `booking_slots` (unique room/date/grid period of active bookings) | new |
| `bookings_repeat` | `booking_series` | new |
| `multi_bookings`, `multi_bookings_slots` | `multi_bookings`, `multi_booking_slots` | new |
| `settings` (crbs, auth, dates, lang, features, changelog, user.N) | `settings` with prefixed keys `org.*`, `ldap.*`, `smtp.*` (secret values encrypted), `user.{id}.*` | reused |
| `lang` | `translations` | new |
| (none) | `password_reset_tokens`, `notification_outbox` | new |

---

## 4. Endpoints (backend, `/api/v1`)

Guard = permission checked on the route (role ∪ room ACL where a room is involved).

| Method & path | Guard | Body / query → response |
|---|---|---|
| `POST /auth/login` | public | `{email?, username?, password}` → `{access_token, token_type, expires_in, password_change_required}` |
| `GET /auth/me` | login | user + `username, role_id, department_id, permissions[]` |
| `GET /auth/permissions` | login | `{role, permissions[], groups{}}` |
| `GET/PUT /auth/profile` | login | own e-mail, names, ext, language |
| `POST /auth/change-password` | login | `{current_password, new_password}` |
| `POST /auth/password-reset/request` | public | `{email}` → 202 |
| `POST /auth/password-reset/confirm` | public | `{token, password}` |
| `GET /permissions` | `setup.roles` | `{system: {group: [{id,name}]}, bookings: {...}}` |
| `GET/POST /roles`, `GET/PUT/DELETE /roles/{id}` | `setup.roles` | `{name, description, max_active_bookings, range_min, range_max, recur_max_instances, permissions[]}` |
| `GET /users/search` | `setup.users` | filters → `{total, items[]}` |
| `GET/PUT /users/{id}/constraints` | `setup.users` | `{max_active_bookings: {type: R\|U\|X, value}, …}` |
| `POST /users/import` | `setup.users` | multipart `file` + defaults → `{created, results: [{line, status, username}]}` |
| `POST /users/{id}/reset-token` | `setup.users` | → `{token?, expires_at, emailed}` |
| `GET/POST /departments`, `PUT/DELETE /departments/{id}` | GET login; write `setup.departments` | `{name, description, icon}` |
| `GET /holidays?term_id=`, `POST /holidays`, `PUT/DELETE /holidays/{id}` | GET login; write `setup.sessions` | `{term_id, name, date_start, date_end}` |
| `/room-admin/groups…`, `/room-admin/rooms…`, `/room-admin/fields…` | `setup.rooms` | see §2.4 |
| `/room-admin/acl…` | `setup.rooms_acl` | `{entity_type, entity_id, context_type, context_id, permissions[]}` |
| `/booking-admin/sessions…` | `setup.sessions` | see §2.5 |
| `/booking-admin/schedules…`, `/booking-admin/periods/{id}` | `setup.schedules` | see §2.5 |
| `/booking-admin/weeks…` | `setup.timetable_weeks` | `{name, bgcol}` |
| `GET /booking-admin/access-check` | `setup.rooms_acl` or `setup.users` | see #32 |
| `GET /booking-admin/outbox`, `POST /booking-admin/outbox/{id}/retry` | `setup.settings` | |
| `GET /bookings/context` | login | sessions, room groups, display settings, my limits, my active count |
| `GET /bookings/dates` | login | `{term_id, today, weeks[{id,name,bgcol,fgcol}], dates[{date, weekday, term_week, timetable_week_id, holiday, open, reason}]}` |
| `GET /bookings/rooms`, `GET /bookings/rooms/{id}` | `room.view` (role or ACL) | |
| `GET /bookings/grid` | login (+ room visibility) | `{term, date, display, dates[], periods[], rooms[], slots[{date, period_id, room_id, status, reason, label, booking?}], nav{prev,next}}` |
| `POST /bookings` | `book_single.create` (room-aware) | `{room_id, date, period_id, notes?, user_id?, department_id?, term_id?}` → `BookingOut` |
| `POST /bookings/recurring/preview` | `book_recur.create` | `{room_id, period_id, date, start?, end?}` → instances with actions |
| `POST /bookings/recurring` | `book_recur.create` | `{…, notes?, user_id?, department_id?, instances?[{date, action, replace_booking_id?}]}` → `{series, created[], skipped[]}` |
| `POST /bookings/multi`, `GET/DELETE /bookings/multi/{id}`, `POST /bookings/multi/{id}/create` | `book_*.create` per slot | see #48 |
| `GET /bookings/{id}`, `GET /bookings/{id}/series` | login (visibility rules) | |
| `PUT /bookings/{id}?scope=` | owner / `edit_other_booking` | |
| `POST /bookings/{id}/cancel`, `POST /bookings/cancel-multi` | owner / `cancel_other_booking` | `{scope, reason}` |
| `GET /bookings/mine`, `GET /bookings/dashboard`, `GET /bookings/owned-rooms` | login | |
| `GET /bookings/export.csv` | `system.export_bookings` | CSV |
| `GET /bookings/feed/user.ics`, `GET /bookings/feed/room/{id}.ics`, `POST /bookings/feed/token`, `GET /ics/{token}/user.ics`, `GET /ics/{token}/room/{id}.ics` | login / token | ICS |
| `GET /bookings/conflicts` | `planning.view` | bookings clashing with the active run / blocks |
| `GET /org/public`, `GET /org/setup-status`, `POST /org/setup` | public | |
| `GET/PUT /org/settings`, `POST/DELETE /org/logo` | `setup.settings` | |
| `GET/PUT /org/auth/ldap`, `POST /org/auth/ldap/test` | `setup.authentication` | |
| `GET/PUT /org/smtp`, `POST /org/smtp/test` | `setup.settings` | |
| `GET /org/translations`, `PUT /org/translations`, `DELETE /org/translations/{id}` | GET login; write `setup.settings` | |
| `GET /org/changelog`, `POST /org/changelog/seen` | login | |
| `GET /org/events` | `setup.settings` | |

---

## 5. Screens for the frontend agent (do not build here; the UI is being redesigned)

| Screen | Who | Backend |
|---|---|---|
| **Setup wizard** (first run: org name, timezone, admin account) and **Setup checklist** (rooms grouped? schedule? periods? timetable weeks? holidays? roles?) | first visitor / admins | `/org/setup-status`, `/org/setup` |
| **Login** with logo, login message, maintenance banner, username-or-email field, "forgot password", forced password change step | everyone | `/org/public`, `/auth/login`, `/auth/password-reset/*`, `/auth/change-password` |
| **Bookings grid**: day view (rooms × periods, room group tabs) and room view (week × periods), date picker with week colours and holidays, session switcher, legend (available / booked single / booked recurring / timetable / holiday / not allowed), multi-select toggle with a selection tray | all booking roles | `/bookings/context`, `/bookings/grid`, `/bookings/rooms` |
| **Book a slot** sheet: single vs recurring tabs (by permission), notes, department and user pickers (by permission), recurring start/end ("session" or date) | creators | `POST /bookings`, `/bookings/recurring/preview`, `/bookings/recurring` |
| **Recurring preview** table: each date with state and actions (book / skip / replace), limit warning | creators | `/bookings/recurring/preview` |
| **Multi-booking wizard**: selection summary → single details per slot or recurring defaults → recurring preview → result | creators | `/bookings/multi*` |
| **Booking details** card/drawer: room info, period, week, series link, user/notes per visibility, edit and cancel actions | all | `GET /bookings/{id}`, `/series` |
| **Edit booking** form with scope picker (this / this and future / all) | owner / editors | `PUT /bookings/{id}` |
| **Cancel** dialog (single: confirm; series: one / future / all; reason) and **cancel many** confirmation | owner / cancellers | `/bookings/{id}/cancel`, `/bookings/cancel-multi` |
| **Dashboard (staff)**: my upcoming bookings, bookings in rooms I own, totals, my limits, what's new indicator | all | `/bookings/dashboard`, `/org/changelog` |
| **My bookings** list with filters and ICS subscribe link | all | `/bookings/mine`, `/bookings/feed/*` |
| **Profile**: names, e-mail, extension, language, password, calendar token | all | `/auth/profile`, `/auth/change-password`, `/bookings/feed/token` |
| **Users**: list with search/filters, add/edit form (role, department, username, constraints R/U/X), force password change, reset token dialog, delete | `setup.users` | `/users*` |
| **User import**: CSV upload + defaults, results table | `setup.users` | `POST /users/import` |
| **Roles**: list (with user counts), editor with permission groups and the four limits | `setup.roles` | `/roles*`, `/permissions` |
| **Departments** CRUD | `setup.departments` | `/departments*` |
| **Room groups** (drag order, members), **room booking settings** (group, owner, location, icon, notes, photo, bookable, order), **custom fields**, **room ACL** editor, **access checker** | `setup.rooms`, `setup.rooms_acl` | `/room-admin/*`, `/booking-admin/access-check` |
| **Sessions**: list, booking settings (selectable, default schedule), per-group schedules, **calendar** assigning timetable weeks to dates (apply to all), **holidays** | `setup.sessions` | `/booking-admin/sessions*`, `/holidays*` |
| **Schedules & periods** editor (+ "create the 18 university periods") | `setup.schedules` | `/booking-admin/schedules*` |
| **Timetable weeks** with colour picker | `setup.timetable_weeks` | `/booking-admin/weeks*` |
| **Organisation & general settings** (name, website, logo, timezone, date patterns, display type/columns, login message, maintenance, show names, max bookings, room groups toggle, languages) | `setup.settings` | `/org/settings`, `/org/logo` |
| **Authentication (LDAP)** settings with "test" | `setup.authentication` | `/org/auth/ldap*` |
| **E-mail (SMTP)** settings with "send test" and the **outbox** | `setup.settings` | `/org/smtp*`, `/booking-admin/outbox` |
| **Translations** override editor | `setup.settings` | `/org/translations` |
| **Export bookings** (session, room group, include cancelled) | `system.export_bookings` | `/bookings/export.csv` |
| **Conflicts after publishing** (planner): bookings that clash with the newly active run | planners | `/bookings/conflicts` |

---

## 6. Deliberate differences from CRBS

1. **One clock.** CRBS periods are free times per schedule; SmartSched maps every period onto the
   university's 18-period grid so that bookings, the published timetable and the solver use the same
   slots. A period outside the grid is rejected.
2. **The published timetable is occupancy.** Slots held by the active run (or by imported blocks such as
   HAZIRLIK) cannot be booked, and the solver treats confirmed bookings as blocks.
3. **Ungrouped rooms are visible** (CRBS hides them) because imported rooms start without groups.
4. **Terms without timetable-week mapping are fully bookable** with weekly recurrence; CRBS requires
   the mapping (its installer seeds a week and applies it, which SmartSched must not do: no seed data).
5. **Recurring department permission**: CRBS's multi-booking recurring step checks `book_recur.create`
   instead of `book_recur.set_department` (`MultiAgent::process_recurring_defaults`); SmartSched checks
   `set_department`.
6. **CSV import `force_password_reset`** is read from its own (8th) column; CRBS reads the role column.
7. **Deleting a user keeps booking history** (the user link becomes empty) instead of deleting bookings.
8. **Cancellation reasons are recorded**, including automatic ones ("replaced by series #N").

9. **LDAP default role**: as in CRBS, an account created by LDAP gets `ldap.default_role_id` (none when
   unset, so it has no permissions until an admin assigns a role).
10. **`users.role` values** seen by the frontend are now `ADMIN`, `PLANNER`, `VIEWER`, `TEACHER`, `CUSTOM`
    (a custom role) or `NONE` (no role); permissions come from `GET /auth/me` → `permissions[]`.

### 6.1 Switches (audit 2026-10-08, `docs/review/2026-10-08-crbs-parity-audit.md`)

Rule: behaviour differences default to CRBS with an org setting to switch; security differences keep the
safer SmartSched rule, with a setting only where restoring CRBS is harmless. All are flat keys of
`GET/PUT /org/settings` (stored as `bookings.*`, see `app/services/bookings_settings.py`).

| Setting (default) | Default = | `true` / other value = |
|---|---|---|
| `enforce_max_active_on_create` (false) | CRBS: the limit greys out the grid and multi-booking only | `POST /bookings` refuses too (409 `max_active_bookings`) |
| `recur_max_counts_replacements` (false) | CRBS: only "book" instances count against `recur_max_instances` | "replace" counts too |
| `maintenance_gates_lists` (false) | CRBS: maintenance closes the booking pages, not the dashboard | dashboard, my bookings, owned rooms, feeds return 503 too |
| `manual_current_term` (false) | CRBS: the current session is computed from the dates (`auto_set_current`) | `terms.is_active` decides |
| `export_ungrouped_rooms` (false) | CRBS: the CSV leaves rooms without a group out | they are exported |
| `recurring_department_needs_set_department` (false) | CRBS: multi-booking recurring step accepts a department with `book_recur.create` | needs `book_recur.set_department` |
| `ignore_unauthorised_user_department` (false) | safer: 403 `set_user` / `set_department` | CRBS: silently books for yourself / your department |
| `cancel_all_includes_past` (false) | safer: `scope=all` cancels today and later, past instances stay as history | CRBS `cancel_all`: every instance |
| `term_date_change` (`cancel`) | CRBS-like: bookings outside new term dates are cancelled (with a reason; CRBS deletes them) | `confirm`: 409 with the list until `PUT /terms/{id}?confirm=true` |
| `grid_highlight` (false, org) | CRBS `settings/General` | reaches the grid via `GET /bookings/context` → `display.grid_highlight` |
| `ldap.ignore_cert` (false) | safer than CRBS's installer (1) | certificates not checked |

Safer rules without a switch (restoring CRBS would not be harmless): the current password is needed to change
it; booking details need `room.view` or ownership; after the directory *rejects* a password the local copy is
not tried for LDAP accounts (only when it is unreachable); `setup.users` cannot grant Administrator without
`setup.roles`; rooms, periods and schedules with bookings (also cancelled history) cannot be deleted (409 with
counts; make them not bookable); owners cannot move a booking into the past or beyond `range_min`/`range_max`.

**Stricter than CRBS, confirmed by the user (2026-10-08): the no-escalation rule.** Nobody can hand out a
permission they do not hold themselves: role editors (`setup.roles`) create, edit and delete only roles within
their own permissions and cannot raise their own role; user managers (`setup.users`) grant only roles whose
permissions they all hold (Administrator, or any role with `setup.roles`, needs `setup.roles` too) and cannot
take over such accounts (password, reset code, e-mail, disable, delete); the CSV import marks such rows
`forbidden`. CRBS allows all of these. There is no switch back. Tests:
`tests/test_crbs_fixes_org.py::test_no_escalation_role_editors_cannot_grant_permissions_they_lack`,
`::test_setup_users_cannot_grant_or_take_over_administrator_without_setup_roles`, e2e `bookings.spec.ts` #14.

Also from the audit: `GET /org/i18n?language=` (public; shipped e-mail strings merged with the overrides of
that language, plus the date patterns), `GET /org/date-patterns?language=` (CRBS option lists with examples;
`PUT /org/settings` accepts only these), e-mails rendered with the patterns and overridable texts (set
`email`), session create/edit/delete under `setup.sessions`, and the legacy importer filling these tables
(usernames, `$2y$`/`sha1:` hashes verified as CRBS does and rehashed to argon2 at the first login).

## 7. Turkish text handling

Usernames fold `İ`/`I`/`ı`/`i` together and are NFKC/NBSP-cleaned (`app/core/identity.py`); e-mails are
lower-cased the same way; search, role and department matching in the CSV import use `tr_casefold`; the
CSV import reads UTF-8 (with or without BOM) and Windows-1254, with `;` or `,`; period times accept dotted
forms (`18.00`); free text (notes, names, locations, translations) is NBSP-cleaned; the bookings CSV is
UTF-8 with a BOM; ICS text is RFC 5545-escaped and folded on UTF-8 byte boundaries.

## 8. Tests (`smartsched/backend/tests`)

| File | Covers |
|---|---|
| `test_crbs_roles.py` | seeded roles = data.sql + SmartSched roles, permission matrix per role, custom roles, legacy role codes, Administrator lock-out guards, role limits and R/U/X user constraints |
| `test_crbs_bookings.py` | real Bahar grid published: conflicts with the timetable and other bookings (service + DB unique key), unpublished runs, conflicts after activation, recurring across the 23 Nisan holiday and timetable-held dates, replace and `recur_max_instances`, cancel one/future/all and owner/date rules, cancel many, limits (active, window, past), department ACL + group ACL + access checker, multi-booking (atomic, dry run), edit scopes and field rights, booking for another user + outbox + dashboard + room owner, show-names setting, maintenance mode, holidays / timetable weeks / weekday periods, the staff date picker |
| `test_crbs_users.py` | CSV import of real Bahar instructors (cp1254, `;`, header, defaults, statuses), Turkish-insensitive username login, forced password change, reset tokens without and with SMTP (mocked `smtplib`), SMTP failure, LDAP via mocked `ldap3.Connection` (create, update, fallback, disabled, no-create), search, profile, delete keeps booking history |
| `test_crbs_admin.py` | room groups/order/fields/values/owner ACL/photo, schedules and periods (dotted times, grid limits), per-group schedules, departments = programmes, org settings, translations, changelog, events, setup checklist, first-run wizard |
| `test_crbs_export_solver.py` | CSV export columns and Turkish text, ICS feeds (bearer, token, rotation), bookings as solver blocks in `build_solver_input` |
| `test_crbs_migration.py` | `0003_crbs_parity` upgrade from `0002_studio` with an existing user, schema = models, downgrade, upgrade again |
| `test_crbs_fixes_bookings.py`, `test_crbs_fixes_org.py` | the audit fixes B1-B16, MISSING 2-6 and every deliberate-difference switch (both the CRBS default and the switched behaviour), the no-escalation rule, the installer requirements step |
| `test_import_crbs.py` | CRBS's own `structure.sql` + `data.sql` loaded, the legacy importer filling the parity tables, `$2y$` / `sha1:` passwords |
| `parity/` | the **CRBS superset gate** (§9): `inventory.py` (every CRBS behaviour and screen with the tests that prove it), `test_parity_*.py` (acceptance tests for the rows the suites above did not cover, each marked `@pytest.mark.parity("<row>")`), `test_inventory.py` (the inventory is complete and the checker fails failing / missing rows), `plugin.py` (result recorder for `scripts/parity_check.py`) |
