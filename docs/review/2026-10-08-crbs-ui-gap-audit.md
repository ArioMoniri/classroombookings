# CRBS UI gap audit: every control a classroombookings user can see or click, compared with SmartSched (2026-10-08)

**Method.** This is a static comparison; CRBS was not run. `php -v` works (8.3.6, with mysqli and pdo_mysql), but this container has no MySQL server and no Docker daemon (`/var/run/docker.sock` is missing), so the legacy profile in `smartsched/deploy/legacy` cannot start. For CRBS I read every view in `crbs-core/application/views/**`, the grid components (`components/bookings/{Grid,Slot,Context}.php`, `grid/{Controls,Table,Header}.php`), the controllers, `models/Menu_model.php`, `assets/js/main.js` and `assets/hs/*`, and all of `language/english/*.php`. For SmartSched I read `smartsched/frontend/src/app/**` and `src/components/{bookings,admin,auth,shell,rooms,settings}/**`. I also checked every method in the `lib/api/crbs.ts` client: each one is called from the UI. I then compared the backend routes in `smartsched/backend/app/api/v1/*.py` with what the UI calls, to find MISSING-UI items.

**Status values.** PRESENT = a user can do the same thing. PARTIAL = it exists, but part of it is missing (the row says what). MISSING = no way to do it. MISSING-UI = the backend supports it but no screen exposes it. N/A = not applicable (the CRBS feature is not used in this version, or SmartSched replaces it by design).

**Owners.** *reservation panel* = bookings grid, my-bookings, booking/room sheets and room details. Another agent is working on click-to-reserve, the department view, calendar sync and room details plus alternatives right now; rows that overlap that work are marked **⟂ overlap** and are listed, not re-specified. *admin screens* = `components/admin/**`. *auth/shell* = login, profile, password and app shell. *backend* = `smartsched/backend`.

Paths are shortened as follows. CRBS: `V/` = `crbs-core/application/views/`, `C/` = `crbs-core/application/controllers/`, `G/` = `crbs-core/application/components/bookings/`. SmartSched: `S/` = `smartsched/frontend/src/components/`.

---

## 1. Bookings grid (`/bookings`)

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| Display type day / room (org default plus switch) | `G/grid/Controls.php:45-94`, `V/settings/general.php:9-60` | `S/bookings/bookings-view.tsx:175-187` (By day / By room segment) | PRESENT | — | — |
| Column layout periods / rooms / days | `V/columns.php`, `G/grid/Table.php` | `S/bookings/grid-model.ts:57-81`, `bookings-view.tsx:130-131` | PRESENT | — | — |
| Prev / next day or week | `V/bookings_grid/header.php:19-42` | `bookings-view.tsx:189-208` | PRESENT | — | — |
| Date picker popup with week colours, holidays and closed days | `V/bookings_grid/controls/day.php:1-19`, `C/Bookings.php:69` (`filter('date')`) | `S/bookings/date-picker.tsx:1-7`, `bookings-view.tsx:193-202` | PRESENT | SmartSched also adds a Today button and keyboard navigation | — |
| Room picker in room view | `V/bookings_grid/controls/room.php:24-41`, `V/bookings/filter/room.php:1-40` (rooms grouped by room group, group description shown, current room in bold) | `bookings-view.tsx:214-230` (flat `<select>`) | PARTIAL | The list is flat: no room-group headings and no group descriptions. Fix: `<optgroup label={group}>` built from `RoomInfo.group` | reservation panel |
| Session switcher | `V/bookings_grid/controls/session.php`, `G/grid/Controls.php:101-156` (with `view_all_sessions`, options are grouped "Current and future" / "Past"; hidden when there is one current session) | `bookings-view.tsx:231-242` (shown when there is more than one session) | PARTIAL | No current/past grouping. Fix: two `<optgroup>`s built from `sessions[].is_current` and the end date | reservation panel |
| Room-group tabs with room counts "Name (n)" | `G/Grid.php:95-117` (count at :112) | `bookings-view.tsx:260-273` | PARTIAL | No room count. Fix: add `(n)` to the label; the context's `room_groups` needs a `room_count` (backend) or a count from `/bookings/rooms` | reservation panel |
| Week banner (timetable-week colour and name) | `V/bookings_grid/header.php:3-13` (header bar in the week's bg/fg colour), `lang booking.nav.week_commencing` | `bookings-view.tsx:133-146` (colour dot, icon and name in the subtitle) | PRESENT | It is a dot, not a coloured bar; acceptable | — |
| Room name in the column or row header opens the room-info drawer | `V/bookings_grid/table/col_room.php:1-13`, `row_room.php:1-13` | `S/bookings/booking-grid.tsx:209-229` → `room-info-sheet.tsx` | PRESENT | **⟂ overlap** (room details plus other available rooms) | reservation panel |
| Room owner shown under the room name in the header | `col_room.php:14-20`, `row_room.php:14-20` | `booking-grid.tsx:87` shows capacity instead | PARTIAL | The owner is missing from the header. Fix: `sub = [owner, seats].join(" · ")`; `GridRoom` needs `owner` (in `RoomInfo` today) | reservation panel |
| Room-info button next to the room picker (room view) | `controls/room.php:43-54` | `bookings-view.tsx:224-228` | PRESENT | — | — |
| Click an empty slot to book | `V/bookings_grid/table/slot/available.php:43-54` | `bookings-view.tsx:79-101` → `book-sheet.tsx` | PRESENT | The free state is only visible on hover (`booking-grid.tsx:285`, `opacity-0`). **⟂ overlap** (click-to-reserve, visible free state) | reservation panel |
| Click a booked slot to open the details drawer | `slot/booked.php:100-113` | `bookings-view.tsx:96` → `booking-detail-sheet.tsx` | PRESENT | — | — |
| Booked-cell text: user, then notes | `slot/booked.php:13-33` | `grid-model.ts:112-123`, `booking-grid.tsx:286-294` | PRESENT | — | — |
| Hover tooltip with the full notes when they are truncated (over 15 characters) | `slot/booked.php:25-31` (`up-tooltip`) | `booking-grid.tsx:263-296` (the full text is only in `aria-label`) | MISSING | Fix: `title={label}` on the cell button, or a tooltip on `text.secondary` | reservation panel |
| Unavailable-slot popup explaining the reason (holiday, limit, past or future, range_min/max, permissions, period) | `slot/unavailable_*.php` (popup with message and OK) | `bookings-view.tsx:342-381` (`SlotInfoSheet`) | PRESENT | — | — |
| A distinct icon for each unavailable reason (lock, quota stop, past, future) | `slot/unavailable_limit.php:10-16`, `unavailable_permissions.php:10`, `unavailable_range_*.php` | `booking-grid.tsx:26-34` (one `Ban` icon for every reason) | PARTIAL | Fix: map `slot.reason` to an icon (`Lock`, `OctagonX`, `History`, `CalendarClock`) | reservation panel |
| Legend | `G/Grid.php:206-238` | `bookings-view.tsx:383-410` | PRESENT | SmartSched shows more states | — |
| Toggle multi-select, then "Create bookings…" | `G/Grid.php:156-198`, `G/grid/Table.php:96-116` | `bookings-view.tsx:244-256, 307-320` → `multi-book-dialog.tsx` | PRESENT | — | — |
| Multi-select of **booked** slots, then "Cancel bookings…" (bulk cancel from the grid, including other users' bookings for admins) | `slot/booked.php:66-90` (checkbox when `booking_cancelable`), `G/Grid.php:186-194`, `C/Bookings.php:414` (`cancel_multi`), `V/bookings/cancel_multi_confirm.php:17-128` (table: date, period, room, department, user, notes) | none. `grid-model.ts:83-85` lets only free slots be selected; bulk cancel exists only for one's own bookings on `/my-bookings` | MISSING | Admins cannot bulk-cancel other people's bookings anywhere. Fix: in multi mode, let booked cells whose `BookingDetail.can_cancel` is true (expose `can_cancel` on `GridSlot.booking`) be selected, and add a "Cancel n" button in the tray that opens the existing `CancelManyDialog` from `my-bookings-view.tsx:201` (move it to a shared file) | reservation panel (+ backend: `can_cancel` on the grid slot) |
| `?highlight=<booking>` deep link | `G/grid/Table.php:275-290` | `bookings-view.tsx:57, 299`, `booking-grid.tsx:272` | PRESENT | — | — |
| Grid crosshair highlight (`grid_highlight` setting) | `G/grid/Table.php:92-95` | `grid-model.ts:146-151`, `bookings-view.tsx:299` | PRESENT | — | — |
| Print the grid | CRBS `print.css` | `bookings-view.tsx:211-213, 412-456` | PRESENT | — | — |
| Maintenance mode gate with message | `C/Bookings.php:18-44` | `bookings-view.tsx:105-119` (503 screen), `:172` (banner for users who may bypass it) | PRESENT | — | — |
| Error message instead of the grid (no session, no schedule, no rooms) | `G/Grid.php:127-131` | `bookings-view.tsx:275-295` (with a "Fix" link for admins) | PRESENT | — | — |
| Department-separated view | not in CRBS 2.x (departments have only name, description and icon; `structure.sql:145-151`) | — | N/A | This is a SmartSched addition. **⟂ overlap** (department view, colour legend) | reservation panel |

## 2. Create, edit and cancel a booking (sheets and dialogs)

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| Choose one-time or recurring (tabs, shown only when allowed) | `V/bookings/create/single.php:18-26` | `S/bookings/book-sheet.tsx` (`crbs.book.kind`) | PRESENT | — | — |
| Change the **period** inside the create form (dropdown "Name (start - end)") | `V/bookings/create/single/single_form.php:24-38` | `book-sheet.tsx:144-152` (the period is fixed in the title) | PARTIAL | Fix: a period `<select>` built from `grid.periods` that are free for that room and date | reservation panel |
| Department on the booking (with `set_department`) | `single_form.php:52-66` | `book-sheet.tsx:68, 176-184` | PRESENT | — | — |
| "Booked by": book for another user (with `book_*.set_user`) | `single_form.php:80-95` | `book-sheet.tsx:69, 189-197` | PARTIAL | The UI also requires `setup.users`, because the user list comes from `/users/search`. Planners hold `set_user` but not `setup.users`, so they cannot book for someone else. Fix (backend): `GET /bookings/users?q=`, guarded by `book_*.set_user` and returning id and display name; the UI then drops the `setup.users` check (the same applies to the edit form, `booking-detail-sheet.tsx:216`) | backend + reservation panel |
| Notes | `single_form.php:100-112` | `book-sheet.tsx` (`crbs.book.notes`) | PRESENT | — | — |
| Recurring: start (start of session or a specific date) and end (end of session or a specific date) | `V/bookings/create/single/recurring_defaults.php` | `book-sheet.tsx:201-216` | PRESENT | — | — |
| Recurring preview with an action per date (book / do not book / replace / keep) and the existing booking | `recurring_preview.php` | `S/bookings/recurring-preview-table.tsx:1-97`, `recurring-preview.ts` | PRESENT | — | — |
| Limit warnings ("you can create at most n", too many instances) | `lang booking.warning.permitted_limit*`, `booking.error.too_many_instances` | `recurring-preview-table.tsx` (`crbs.recur.limit/overLimit`), `bookings-view.tsx:163-167` (remaining pill) | PRESENT | — | — |
| Multi-booking: one row per slot with an **include** checkbox | `V/bookings/create/multi/single_details.php:60-82` | `S/bookings/multi-book-dialog.tsx:82` (every slot is always sent) | MISSING-UI | Backend `SlotChoice.create` exists (`api/v1/bookings.py:130-137`). Fix: add a checkbox per row in the dialog list (`:150-160`) and send `create:false` | reservation panel |
| Multi-booking: department, user and notes **per row**, with "copy down ↓" | `single_details.php:104-172` (`up-copy-to`), `assets/js/main.js:135-150` | `multi-book-dialog.tsx:56, 166-167` (one shared notes field, no department or user) | MISSING-UI | Backend `SlotChoice.{department_id,user_id,notes}` exists. Fix: per-row fields, or shared department and user selects copied to every choice | reservation panel |
| Multi-booking recurring: start/end defaults and a conflict preview per slot (tabs) | `multi/recur_defaults.php`, `multi/recur_preview.php`, `multi/recur/preview/tab_*.php` | `multi-book-dialog.tsx:84-99` (only a count of what would be created) | PARTIAL | Backend `SlotChoice.recurring_start/end` exists but the UI does not send it. A per-instance replace/keep choice in the multi flow has no backend field. Fix: start and end selects (as in `book-sheet`). Backend: per-instance `actions` in `SlotChoice` | reservation panel + backend |
| Booking details: date, period with times, booked by, department, notes, room fields | `V/bookings/view.php:88-221` | `S/bookings/booking-detail-sheet.tsx:89-127` | PRESENT | — | — |
| Details: **timetable-week row** and **"Occurs: Week A, every Monday"** | `view.php:96-118` | not shown (`BookingDetail.series.{weekday,timetable_week_id}` is already loaded, `lib/api/crbs.ts:141`) | PARTIAL | Fix: two `dt/dd` rows using the week name and colour from `useBookingDates().weeks` | reservation panel |
| Details: room photo | `view.php:216-221` | `booking-detail-sheet.tsx:109-124` (fields only) | PARTIAL | Fix: render `b.room.photo_url` the way `room-info-sheet.tsx:38` does | reservation panel |
| "View all bookings in series" | `view.php:19-26`, `V/bookings/view_series.php` | `booking-detail-sheet.tsx:138-158` | PRESENT | — | — |
| Edit with scope this / future / all, and scope hints | `V/bookings/edit_choice.php`, `edit/form.php` | `booking-detail-sheet.tsx:184-330` | PRESENT | — | — |
| Cancel with scope this / future / all ("Yes, cancel" / "No, keep it") | `V/bookings/cancel_choice.php:10-56` | `booking-detail-sheet.tsx:340-365` (adds an optional reason) | PRESENT | — | — |
| Warning "This is not your own booking." when editing or cancelling someone else's booking | `cancel_choice.php:3-5`, `edit_choice.php:3-5` | none | MISSING | Fix: when `!b.is_owner && (b.can_edit\|\|b.can_cancel)`, show a warning `Alert` above the actions | reservation panel |
| "Show in grid" from the details | `V/dashboard/user_bookings.php:37-44` | `booking-detail-sheet.tsx:130-136` | PRESENT | — | — |

## 3. My bookings / dashboard (`/my-bookings`)

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| Stat tiles: all, this session, active, maximum active, **bookings you can create** | `V/dashboard/stats.php:24-50` | `S/bookings/my-bookings-view.tsx:76-80` (all, session, active and the limit as text) | PARTIAL | "You can create n" is shown only on the grid. Fix: add `remaining` (`dash.data.limits.max_active_bookings - totals.active`) to the subtitle | reservation panel |
| Active bookings list (date, period, time, room, notes) | `V/dashboard/user_bookings.php:1-55` | `my-bookings-view.tsx:85-119, 157-199` (also Past and Cancelled tabs) | PRESENT | — | — |
| Room name in the list opens the room-info drawer | `user_bookings.php:21-27`, `room_bookings.php:96-102` | rows open only the booking details (`:180`) | MISSING | Fix: make the room name a button that opens `RoomInfoSheet` | reservation panel |
| Calendar icon goes to the grid at that date with the booking highlighted | `user_bookings.php:37-44` | one extra click: details → "Show in grid" | PRESENT | — | — |
| "Bookings in my rooms" (room owner; user and notes hidden by permission) | `V/dashboard/room_bookings.php:1-130` | `my-bookings-view.tsx:121-136` | PRESENT | — | — |
| Bulk cancel of one's own bookings | (CRBS does this from the grid) | `my-bookings-view.tsx:103-108, 201-232` | PRESENT | — | — |
| Export bookings to CSV (session, room group, include cancelled) | `V/export/index.php:13-66`, `C/Export.php`; reached from the **Setup menu** (`models/Menu_model.php:149-153`) | `my-bookings-view.tsx:140, 281-330` | PARTIAL | It works but cannot be found from Setup. Fix: add an "Export" card to `S/admin/admin-overview.tsx` (permission `system.export_bookings`) that links to `/my-bookings#export-title` | admin screens |
| Personal ICS feed (SmartSched addition) | — | `my-bookings-view.tsx:234-279` | PRESENT | **⟂ overlap** (calendar sync) | reservation panel |
| Room ICS feed (`/bookings/feed/room/{id}.ics`, `FeedToken.room_feed`) | — | `lib/api/crbs.ts:372` returns `room_feed`; no UI | MISSING-UI | **⟂ overlap** (calendar sync: room, department and group feeds) | reservation panel |

## 4. Login, password and profile

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| Username + password login (local or LDAP) | `V/login/login_index.php:15-54` | `S/auth/login-form.tsx` | PRESENT | — | — |
| Login message, organisation logo and name | `login_index.php:2-4`, `V/layout.php:118-127` | `S/admin/login-extras.tsx:14-45` | PRESENT | — | — |
| Forgot password (SmartSched addition) | — | `login-form.tsx` (`crbs.login.forgot`), `app/reset-password/page.tsx`, `S/admin/reset-password.tsx` | PRESENT | — | — |
| Forced password change after login | `V/profile/new_password.php`, `C/Profile.php:135-161` | `app/login/change-password/page.tsx`, `S/auth/change-password-form.tsx` | PRESENT | — | — |
| Account / profile link in the header ("Display name" → `profile/edit`) | `models/Menu_model.php:33-40` | **No link anywhere.** `S/shell/user-menu.tsx:68` points to `/settings`. `/profile` appears only in `S/admin/nav-items.ts:28` (`ADMIN_SECTION_NAV_ITEMS`), which only `S/shell/breadcrumbs.ts:11` uses. The sidebar and ⌘K (`command-palette.tsx:94`) do not list it | MISSING | A teacher cannot reach their profile, language or password page without typing the URL. Fix: add a "Profile" item (`UserRound`) at the top of `user-menu.tsx:67`; add `/profile` to the ⌘K go-to list | auth/shell |
| Profile edit: e-mail, first/last/display name, extension, language, password | `V/profile/profile_edit.php`, `C/Profile.php:43-131` | `S/admin/profile-view.tsx` | PRESENT | — | — |
| Log out | `Menu_model.php:41-44` | `S/shell/user-menu.tsx:75-77` | PRESENT | — | — |

## 5. Shell, layout and global behaviour

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| Main menu: Bookings, Setup (by permission), Account, Log out | `models/Menu_model.php:10-46` | `S/shell/nav-config.ts:54-61`, `S/admin/nav-items.ts:20-24` | PARTIAL | Account is missing (see §4) | auth/shell |
| Maintenance banner at the top of **every page** while maintenance mode is on | `V/layout.php:86-97` | only on `/bookings` (`bookings-view.tsx:172`) and on login (`login-extras.tsx:38`) | PARTIAL | Fix: a thin banner in `S/shell/app-shell.tsx` driven by `useOrgPublic().maintenance_mode` | auth/shell |
| "What's new" indicator | `V/layout.php:9-10`, `C/Dashboard.php:47-60` | `S/admin/whats-new.tsx` | PRESENT | — | — |
| Footer with the app version (and load time) | `V/layout.php:205-216` | none | MISSING (low) | Fix: show the version in the user-menu label or an About line (from `/org/changelog` or the build env) | auth/shell |
| Sidebar "Users" entry | CRBS → `users` | `S/shell/nav-config.ts:47` → `/settings?tab=users`, the legacy `UsersCard` (`S/settings/settings-view.tsx:259-284`: e-mail, name, role code and password only; no username, `role_id`, department or limits) | PARTIAL | Two user-management screens; the one in the sidebar is the weaker one. Fix: point `nav-config.ts:47` to `/admin/users` and remove or redirect the `users` tab | auth/shell |
| ⌘K action "New room" | — | `S/shell/command-palette.tsx:92` → `/rooms?new=1`; `S/rooms/rooms-view.tsx` ignores `new`, so nothing happens | MISSING (broken action) | Fix: either build a create-room form (see §7) or remove the action | auth/shell |
| Keyboard: Esc closes popups; `accesskey` legends | `G/Grid.php:62,76` (`up-dismissable key`), many `<legend accesskey>` | sheets close on Esc; `S/shell/use-global-shortcuts.ts`, `shortcuts-sheet.tsx`, grid arrow keys `booking-grid.tsx:121` | PRESENT | — | — |
| Toast feedback after actions | `assets/js/main.js:204-230` | `sonner` toasts throughout | PRESENT | — | — |

## 6. Admin: setup menu, users, roles, departments

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| Setup menu grouped System / Dates and times / Resources / Users and security, filtered by permission | `V/setup/index.php`, `Menu_model.php:52-156` | `S/admin/admin-overview.tsx`, `lib/permissions.ts:173-188` | PARTIAL | No Export entry (see §3) | admin screens |
| Users list: search, role and department filters, sortable columns (enabled, username, display name, role, department, last login), paging | `V/users/users_index.php:25-31`, `V/users/filter.php` | `S/admin/users-admin.tsx:51-265` (sort options `:125-132`: username, name, role, last login) | PARTIAL | No sort by **enabled** or **department** (the backend `sort_map` supports both). Fix: two more `<option>`s | admin screens |
| Create / edit user: username, role, department, enabled, e-mail, names, display name, extension, force password change, password | `V/users/users_add.php:18-260` | `users-admin.tsx:319-435` | PRESENT | CRBS asks for the password twice ("Password (confirm)"); SmartSched asks once (`:405`). Low priority | admin screens |
| Per-user constraints R / U / X | `users_add.php:94-170` | `users-admin.tsx:444-499` | PRESENT | — | — |
| Access-checker panel inside the user edit page | `V/users/users_add_side.php:1-5`, `C/setup/Access_checker.php:86-113` | none (only the separate `/admin/access` page) | PARTIAL | Fix: "Check access" link in the user dialog to `/admin/access?user=<id>`; make `access-checker.tsx` read `?user=&room=` | admin screens |
| Delete user (not one's own) | `C/Users.php` (delete), `lang user.delete.*` | `users-admin.tsx` (`crbs.users.deleteTitle`) | PRESENT | SmartSched deliberately keeps the bookings | — |
| Import users from CSV: defaults, results per row, "import more" | `V/users/import/{stage1,stage1_side,stage2}.php` | `users-admin.tsx:539-663` | PRESENT | — | — |
| Admin issues a reset code / sets a password | `users_add.php:173-230` | `users-admin.tsx:500-529` (one-time code or e-mail) | PRESENT | — | — |
| Roles list: name, description, user count, max active bookings | `V/roles/index.php:23-40` | `S/admin/roles-admin.tsx:40-93` | PRESENT | — | — |
| Role edit: name, description, 4 limits, permission checkboxes | `V/roles/add.php` | `roles-admin.tsx:94-208, 209+` | PRESENT | — | — |
| Role edit side panel listing the role's **users** | `V/roles/user_list.php`, `C/Roles.php:52,80` | count only (`roles-admin.tsx:77`) | PARTIAL | Fix: in the role editor, show a "Users (n)" list (from `crbs.users.search({role_id})`) or a link to `/admin/users?role=<id>` (users-admin then needs to read query parameters) | admin screens |
| Departments: list, create, edit, delete (name, description, icon) | `V/departments/departments_{index,add}.php` | `S/admin/departments-admin.tsx` | PRESENT | — | — |

## 7. Admin: rooms, groups, fields, ACL, access checker

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| Room groups: list, create, edit, delete, drag to reorder, pick member rooms | `V/setup/rooms/groups/{index,add_side,view}.php` | `S/admin/rooms-admin.tsx:97-245` | PRESENT | — | — |
| Rooms inside a group: drag to reorder | `C/setup/rooms/Rooms.php:34` (`save_pos`) | `rooms-admin.tsx:246-306` (`orderRooms`) | PRESENT | — | — |
| **Create room** | `C/setup/rooms/Rooms.php:58` (`add`), `V/setup/rooms/rooms/rooms_add.php:17-286` | none (`rooms-admin.tsx` header says codes and capacity stay on `/rooms`; `/rooms` has no create form) | MISSING-UI | Backend `POST /rooms` exists (`api/v1/rooms.py:51`, guard `Planner`). Fix: a "New room" button in `RoomsTab` that opens `RoomForm` in create mode (code, display name, group, capacity) | admin screens + backend (accept `setup.rooms` as well as `planning.edit`) |
| **Delete room** | `C/setup/rooms/Rooms.php:338`, `lang room.delete.warning` | none | MISSING-UI | Backend `DELETE /rooms/{id}` exists (`rooms.py:96`, refused while bookings exist). Fix: a delete action in `RoomRow` with a confirmation that shows the 409 message | admin screens + backend (same guard) |
| Room edit: name, group, location, owner, notes, bookable, photo upload/delete, custom field values | `rooms_add.php:17-210` | `rooms-admin.tsx:346-482` | PRESENT | — | — |
| Custom fields: text / checkbox / select with options | `V/setup/rooms/fields/{index,add}.php` | `rooms-admin.tsx:515-634` | PRESENT | — | — |
| ACL per room or group: add user / role / department, edit permissions, remove | `V/setup/rooms/acl/{index,add,edit,_add_*}.php` | `rooms-admin.tsx:635-775` | PRESENT | — | — |
| Access checker: user × room, with the source of each permission | `C/setup/Access_checker.php:27-85`, `V/setup/access_checker/{index_form,index_result,_result}.php` | `S/admin/access-checker.tsx:1-95` | PRESENT | — | — |
| Access checker opened from a room (room fixed, pick a user) and from a user (user fixed, pick a room) | `Access_checker.php:86-143`, `V/setup/access_checker/{user,room}.php` | none | PARTIAL | Same fix as the user row in §6: deep-link query parameters plus "Check access" buttons in `RoomForm` and `UserForm` | admin screens |

## 8. Admin: sessions, holidays, schedules, periods, weeks

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| Sessions list: current and future vs past, current flag, user-selectable flag | `V/sessions/{index,table}.php`, `C/Sessions.php:37` | `S/admin/sessions-admin.tsx:34-76` | PRESENT | — | — |
| **Create / edit / delete a session** (name, start date, end date, user-selectable, default schedule) | `C/Sessions.php:153-310`, `V/sessions/add.php`, `lang session.delete.warning` | none (only `is_selectable` and `default_schedule_id` can be edited: `bookingAdmin.updateSession`). `lib/api/endpoints.ts:118` only lists terms | MISSING-UI | Backend `POST/PUT/DELETE /terms` exists (`api/v1/terms.py:50,83,124`, guarded by `SessionsEditor`; `PUT` already returns `cancelled_booking_ids`, i.e. CRBS `check_session_dates`). Fix: "New session" plus edit and delete in `sessions-admin.tsx`, with a toast that lists the bookings cancelled when the dates shrink | admin screens |
| Session calendar: paint a timetable week on each date, apply one week to the whole session | `V/sessions/{view,view_apply_week}.php`, `assets/js/main.js:35-120`, `C/Sessions.php:103-150` | `sessions-admin.tsx:127+` (`DatePainter`) | PRESENT | — | — |
| Room schedules: schedule per room group in a session | `V/room_schedules/index*.php`, `C/Room_schedules.php` | `sessions-admin.tsx:77-126` | PRESENT | — | — |
| Holidays: list per session, create, delete | `V/holidays/{index,add}.php`, `C/Holidays.php:26-216` | `S/admin/holidays-admin.tsx:16-113` | PRESENT | — | — |
| **Edit a holiday** (name and dates) | `C/Holidays.php:91-128` | none (`holidays-admin.tsx:31-32` has only create and remove) | MISSING-UI | Backend `PUT /holidays/{id}` exists and `crbs.holidays.update` is already in `lib/api/crbs.ts:880`. Fix: an edit dialog, or editable fields in each row | admin screens |
| Holiday duration column | `V/holidays/index.php` (`holiday.field.duration`) | none | PARTIAL (low) | Fix: show the day count | admin screens |
| Schedules: create, rename, delete | `C/Schedules.php:52-165` | `S/admin/schedules-admin.tsx:52-170` | PRESENT | — | — |
| Schedule **description** | `V/schedules/add.php:20-60` (`schedule.field.description`) | rename only (`schedules-admin.tsx:108`) | PARTIAL | `updateSchedule` already accepts `description`. Fix: add a description field | admin screens |
| Periods: name, start/end time, days, bookable | `V/periods/{index,item_add_edit,item_view}.php` | `schedules-admin.tsx:170-243` (also builds periods from the grid) | PRESENT | — | — |
| Timetable weeks: name, colour, icon; delete warning | `V/weeks/{index,add}.php` | `S/admin/weeks-admin.tsx` | PRESENT | — | — |

## 9. Admin: settings, organisation, language, authentication, e-mail, setup

| Feature | CRBS location | SmartSched location | Status | Gap and smallest fix | Owner |
|---|---|---|---|---|---|
| General settings: display type, columns, grid highlight, timezone, date patterns (long, weekday, time) with preview | `V/settings/general.php:9-210` | `S/admin/org-settings.tsx:39-256` | PRESENT | — | — |
| Login message on/off and text; maintenance mode on/off and message | `general.php:215-300` | `org-settings.tsx` (`crbs.org.loginMessage`, `crbs.org.maintenance*`) | PRESENT | — | — |
| Experimental features | `general.php:300-334` | — | N/A | `features_lang.php` is empty, so CRBS ships no features here | — |
| Organisation: name, website, logo upload/delete | `V/settings/organisation.php:9-80` | `org-settings.tsx` (`crbs.org.name/website/logo/removeLogo`) | PRESENT | — | — |
| Languages: enabled languages and default | `V/setup/language/language.php`, `C/setup/Language.php` | `org-settings.tsx` (`crbs.org.enabledLanguages/defaultLanguage`) | PRESENT | — | — |
| Translation overrides (the CRBS `lang` table) | DB only in CRBS (`MY_Lang::load_from_db`) | `org-settings.tsx:257+` (`TranslationsEditor`) | PRESENT | SmartSched has an editor; CRBS has none | — |
| LDAP: enable, server, port, version, TLS, ignore certificate, bind DN format, base DN, search filter, attribute mapping, create users, default role and department, test | `V/settings/authentication/{ldap,ldap_test,ldap_test_results}.php` | `S/admin/ldap-settings.tsx` | PRESENT | — | — |
| SMTP and outbox (SmartSched addition; CRBS sends no e-mail) | — | `S/admin/email-settings.tsx` | PRESENT | — | — |
| Installer: requirements, configuration, school name, first admin | `modules/install/views/{check,config,info,complete}.php` | `app/setup/page.tsx`, `S/admin/setup-wizard.tsx`, `requirements-list.tsx` | PRESENT | — | — |
| Upgrade from v1 | `V/upgrade/*`, `C/Upgrade.php` | Alembic | N/A | Importing a legacy database is audit B4 (backend) | backend |

---

## Overlap with the reservation-panel agent (listed only, not re-specified)

- Click-to-reserve, with free slots always visible (today only on hover: `booking-grid.tsx:285`).
- Department-separated view and colours. CRBS 2.x has no department colours, only `departments.icon`.
- Calendar sync: the room feed is MISSING-UI (`room_feed` is never shown), and department and group feeds do not exist yet.
- The room-details panel with "other available rooms". The CRBS room-info parts it should keep: photo (enlarge on click as in `C/Rooms.php:43`), location, owner, notes and custom fields. All of these are present in `room-info-sheet.tsx` today, except that the photo cannot be enlarged.

---

## Prioritised list

**P1: blocks a CRBS user or admin from doing something CRBS lets them do**

1. **MISSING: no way to reach Profile** (language, password, details). Add "Profile" to `S/shell/user-menu.tsx:67` and to ⌘K. *(auth/shell)*
2. **MISSING: bulk cancel from the grid**, so admins cannot bulk-cancel other users' bookings anywhere (`slot/booked.php:66-90`, `C/Bookings.php:414`). Let cancellable booked cells be selected in multi mode, add a "Cancel n" button in the tray, and reuse `CancelManyDialog`. Backend: `can_cancel` on `GridSlot.booking`. *(reservation panel + backend)*
3. **MISSING-UI: create / edit / delete sessions** (`POST/PUT/DELETE /terms` exist). *(admin screens)*
4. **MISSING-UI: create and delete rooms** (`POST/DELETE /rooms` exist). The ⌘K "New room" action is dead (`command-palette.tsx:92`). Backend: accept `setup.rooms` on these routes. *(admin screens + backend; the palette fix is auth/shell)*
5. **PARTIAL: "Booked by" requires `setup.users`**, so Planners cannot book or edit for another user. Add `GET /bookings/users` guarded by `set_user`. *(backend + reservation panel)*
6. **MISSING-UI: edit a holiday** (`PUT /holidays/{id}` and `crbs.holidays.update` exist). *(admin screens)*
7. **MISSING-UI: multi-booking per-row include checkbox, department, user and notes (with copy-down), and recurring start/end** (all in the backend `SlotChoice`). Per-instance replace/keep in multi recurring needs a backend field. *(reservation panel + backend)*
8. **PARTIAL: the sidebar "Users" link opens the legacy 4-field form** (`nav-config.ts:47` → `/settings?tab=users`). Point it to `/admin/users`. *(auth/shell)*

**P2: information or controls CRBS shows that SmartSched does not**

9. MISSING: tooltip with the full notes on truncated booked cells (`booking-grid.tsx:263`). *(reservation panel)*
10. PARTIAL: booking details lack the timetable-week row, "Occurs: Week A, every Monday" and the room photo (`booking-detail-sheet.tsx:89-127`). *(reservation panel)*
11. MISSING: "This is not your own booking." warning before editing or cancelling someone else's booking. *(reservation panel)*
12. PARTIAL: room owner not shown under the room name in grid headers (`booking-grid.tsx:87`). *(reservation panel)*
13. PARTIAL: maintenance banner only on `/bookings` and login, not on every page. *(auth/shell)*
14. PARTIAL: Export cannot be found from Admin; add a card to `admin-overview.tsx`. *(admin screens)*
15. PARTIAL: access checker cannot be opened from a user or a room (no `?user=&room=` deep links). *(admin screens)*
16. PARTIAL: the role editor does not list the role's users. *(admin screens)*
17. PARTIAL: the create form cannot change the period (`single_form.php:24-38`). *(reservation panel)*
18. PARTIAL: `/my-bookings` does not show "bookings you can create", and room names there do not open room info. *(reservation panel)*
19. PARTIAL: schedule description cannot be edited. *(admin screens)*

**P3: polish**

20. PARTIAL: room picker not grouped by room group; session picker not split into current/past; room-group tabs without counts. *(reservation panel; the counts need backend)*
21. PARTIAL: one icon for every unavailable reason (CRBS: lock, quota, past, future). *(reservation panel)*
22. PARTIAL: users cannot be sorted by enabled or department; no password-confirm field. *(admin screens)*
23. PARTIAL: no holiday duration column. *(admin screens)*
24. MISSING: app version in the footer or the user menu. *(auth/shell)*
25. PARTIAL: room photo in room info cannot be enlarged (**⟂ overlap**). *(reservation panel)*

**Not gaps (deliberate or N/A).** Experimental features: CRBS ships none. Department colours: not in CRBS 2.x. Deleting a user keeps their booking history (deliberate). v1 upgrade page: Alembic plus importer B4.
