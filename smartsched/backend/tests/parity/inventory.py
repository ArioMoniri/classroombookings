"""The CRBS parity inventory (ROADMAP Phase 18): every classroombookings behaviour and screen SmartSched must
match or exceed, with the automated tests that prove it.

Sources: docs/review/2026-10-08-crbs-parity-audit.md (91 behaviours; the audit kept only its bugs, missing items
and deliberate differences in writing, so the behaviour rows are rebuilt here from docs/CRBS_PARITY.md §1-§2
(features #1-#62) split per CRBS behaviour, plus the audit's bug / missing / difference rows) and the CRBS
screens of docs/CRBS_PARITY.md §5.

A row is proven by
  * ``api``: existing test node ids (``tests/<file>.py::<test>``) — reused, not duplicated — plus every test
    under tests/parity marked ``@pytest.mark.parity("<row id>")``;
  * ``ui``: Playwright test titles (``<spec>::<title>``) in smartsched/frontend/e2e/{bookings,calendar}.spec.ts,
    which pod CI runs against the real backend (gate e2e-real).

``difference`` names a deliberate difference from CRBS (decided by the user or the orchestrator) that the
tests assert; ``gap`` / ``ui_gap`` declare what is not covered yet, why, and the proposed fix. A row without
coverage and without a declared gap fails ``scripts/parity_check.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

TB = "tests/test_crbs_bookings.py::"
TA = "tests/test_crbs_admin.py::"
TU = "tests/test_crbs_users.py::"
TR = "tests/test_crbs_roles.py::"
TE = "tests/test_crbs_export_solver.py::"
FB = "tests/test_crbs_fixes_bookings.py::"
FO = "tests/test_crbs_fixes_org.py::"
TM = "tests/test_crbs_migration.py::"
IC = "tests/test_import_crbs.py::"
RS = "tests/test_review_security.py::"
UI_B = "bookings.spec.ts::"
UI_C = "calendar.spec.ts::"

E2E = {
    1: UI_B + "1. the administrator creates a teacher in Setup → Users",
    2: UI_B + "2. the teacher signs in and sees bookings but no setup or planning screens",
    3: UI_B + "3. the teacher books A 101 on a free slot",
    4: UI_B + "4. a slot held by the timetable (FZT 132, Monday P4) is refused with a clear Turkish message",
    5: UI_B + "5. a recurring booking skips the 23 Nisan holiday",
    6: UI_B + "6. the teacher cancels with a reason (one booking, then the whole series)",
    7: UI_B + "7. the administrator sees it in the CSV export",
    8: UI_B + "8. names and notes follow permissions and the show-names setting",
    9: UI_B + "9. grid orientation (display type × columns), room card and print view",
    10: UI_B + "10. maintenance mode stops bookings for staff, administrators bypass it",
    11: UI_B + "11. profile language (per user, like CRBS)",
    12: UI_B + "12. one-time reset code (shown once) and the reset-password page; setup is closed once done",
    13: UI_B
    + "13. planners see bookings the published timetable overlaps (conflicts after publishing); teachers cannot",
    14: UI_B
    + "14. no escalation: a role manager without planning rights cannot grant, edit or import beyond their own "
    "permissions",
}
CAL_ROOMS = UI_C + "rooms: list with the week's occupancy, detail with grid, free slots and calendar link"
CAL_MOVE = UI_C + "inspector, explain, move with the free-room finder, undo restores the backend"

FRONTEND_UI_GAP = (
    "screen exists (frontend-engineer, CRBS bookings + admin, 2026-10-08) but no Playwright test drives it; "
    "proposed: add a bookings.spec.ts step on the real backend"
)


@dataclass(frozen=True)
class Row:
    id: str
    area: str
    behaviour: str
    crbs: str
    api: tuple[str, ...] = ()
    ui: tuple[str, ...] = ()
    difference: str = ""
    gap: str = ""
    ui_gap: str = ""
    screen: bool = False


def _r(id: str, behaviour: str, crbs: str, *api: str, **kw: object) -> Row:  # noqa: A002
    area = id.split("-")[1] if id.startswith("B-") else "SCREEN" if id.startswith("S-") else id.split("-")[0]
    return Row(id, area, behaviour, crbs, tuple(api), **kw)  # type: ignore[arg-type]


ROWS: tuple[Row, ...] = (
    # ---------------------------------------------------------------- install, setup, organisation (#1-#13)
    _r(
        "B-SETUP-01",
        "First-run installer: organisation name and first administrator, only while no user exists",
        "install/Install, Installer::execute",
        TA + "test_first_run_setup_wizard",
        ui=(E2E[12],),
    ),
    _r(
        "B-SETUP-02",
        "Installer requirements step (runtime, image library, LDAP module, writable uploads, database); "
        "an error blocks the install",
        "Install::check_requirements",
        FO + "test_missing6_installer_requirements_step",
        ui_gap="the wizard's Requirements step exists (frontend 2026-10-08 13:26) but no e2e step loads it on an "
        "empty database; proposed: e2e run against a second, empty backend",
    ),
    _r(
        "B-SETUP-03",
        "Upgrades: schema migrations upgrade and downgrade cleanly",
        "Upgrade controller, migrations/*",
        TM + "test_upgrade_downgrade_roundtrip",
    ),
    _r(
        "B-SETUP-04",
        "Setup checklist (organisation, rooms, groups, schedules, weeks, holidays, roles, SMTP)",
        "setup/Dashboard",
        TA + "test_org_settings_translations_changelog_and_events",
    ),
    _r(
        "B-SETUP-05",
        "Setup menu built from the setup.* permissions the user holds",
        "Menu_model::setup_menu",
        ui=(E2E[2],),
    ),
    _r(
        "B-SETUP-06",
        "Organisation name and website (http/https only)",
        "settings/Organisation",
        TA + "test_org_settings_translations_changelog_and_events",
        FO + "test_b8_valid_values_and_pattern_option_list",
    ),
    _r(
        "B-SETUP-07",
        "Organisation logo (jpg/png/gif, scaled to 1600 px) shown on the login page; removable",
        "settings/Organisation::index",
        FO + "test_b2_logo_is_reencoded_and_svg_is_refused",
        ui_gap="login page does not mount LoginBrand yet (ROADMAP 'Shell follow-ups'); proposed: mount it and add "
        "an e2e assertion",
    ),
    _r(
        "B-SETUP-08",
        "Bookings display type (day/room) and columns (periods/rooms/days)",
        "settings/General",
        TA + "test_org_settings_translations_changelog_and_events",
        ui=(E2E[9],),
    ),
    _r(
        "B-SETUP-09",
        "Time zone setting (validated; used by the feeds)",
        "settings/General",
        TA + "test_org_settings_translations_changelog_and_events",
        FB + "test_b11_ics_uses_the_timezone_setting",
    ),
    _r(
        "B-SETUP-10",
        "Login message (on/off + text) on the public login page",
        "Login::index, settings/General",
        TA + "test_org_settings_translations_changelog_and_events",
        ui_gap="login page does not mount LoginNotices yet (ROADMAP 'Shell follow-ups')",
    ),
    _r(
        "B-SETUP-11",
        "Maintenance mode: booking pages show the message unless system.bypass_maintenance_mode",
        "Bookings::__construct",
        TB + "test_show_names_setting_and_maintenance_mode",
        FB + "test_g_maintenance_closes_bookings_but_not_the_dashboard_unless_switched",
        ui=(E2E[10],),
    ),
    _r(
        "B-SETUP-12",
        "Date patterns (long / weekday / time) from the CRBS option lists, used in e-mails",
        "settings/General, Dates library",
        FO + "test_b8_valid_values_and_pattern_option_list",
        FO + "test_missing2_emails_use_overrides_and_date_patterns",
    ),
    _r(
        "B-SETUP-13",
        "Show booking owners' names to other users (Teacher view_other_users)",
        "migration bookings_show_name / 2.15 roles",
        TB + "test_show_names_setting_and_maintenance_mode",
        ui=(E2E[8],),
    ),
    _r(
        "B-SETUP-14",
        "Global maximum of active bookings (the Teacher role limit)",
        "num_max_bookings migration",
        TA + "test_org_settings_translations_changelog_and_events",
    ),
    _r(
        "B-SETUP-15",
        "Room groups feature toggle (one flat list when off)",
        "use_room_groups",
        TB + "test_ungrouped_rooms_hidden_like_crbs",
        FB + "test_b13_rooms_keep_their_own_schedule_without_room_groups",
    ),
    _r(
        "B-SETUP-16",
        "Enabled languages, default language and database overrides of any text",
        "setup/Language, MY_Lang::load_from_db",
        TA + "test_org_settings_translations_changelog_and_events",
        FO + "test_missing2_i18n_bundle_merges_overrides",
        ui=(E2E[11],),
        ui_gap="the i18n provider does not overlay GET /org/i18n overrides yet (ROADMAP 'Shell follow-ups')",
    ),
    _r(
        "B-SETUP-17",
        '"What\'s new" changelog indicator per user',
        "Changelog, Dashboard::changelog",
        TA + "test_org_settings_translations_changelog_and_events",
        FO + "test_b12_changelog_seen_is_a_version_and_timestamp",
        ui_gap="the shell does not mount WhatsNewIndicator yet (ROADMAP 'Shell follow-ups')",
    ),
    _r(
        "B-SETUP-18",
        "Event hooks (user.logged_in, booking.*, series.created, password.reset_requested)",
        "libraries/Events",
        TA + "test_org_settings_translations_changelog_and_events",
    ),
    _r(
        "B-SETUP-19",
        "Grid highlight setting reaches the grid",
        "settings/General grid_highlight",
        FO + "test_missing5_grid_highlight_reaches_the_grid",
    ),
    _r(
        "B-SETUP-20",
        "Every new setting has its CRBS (behaviour) or safer (security) default and round-trips",
        "settings",
        FO + "test_every_new_setting_has_its_default_and_round_trips",
    ),
    # ---------------------------------------------------------------- authentication (#14-#18)
    _r(
        "B-AUTH-01",
        "Sign in with username or e-mail; usernames fold Turkish İ/I/ı/i and case",
        "Login, Userauth",
        TU + "test_csv_import_of_real_instructors",
        TA + "test_first_run_setup_wizard",
        ui=(E2E[2],),
    ),
    _r(
        "B-AUTH-02",
        "Disabled accounts cannot sign in; their tokens stop working",
        "Userauth::log_in",
        TU + "test_ldap_login_creates_updates_and_falls_back",
    ),
    _r("B-AUTH-03", "Last login is stamped", "Userauth::log_in (lastlogin)"),
    _r(
        "B-AUTH-04",
        "Legacy CRBS password hashes ($2y$ bcrypt, sha1:) verified and upgraded at first login",
        "Auth_local::verify",
        IC + "test_imported_users_log_in_with_their_crbs_passwords",
    ),
    _r(
        "B-AUTH-05",
        "LDAP: bind format, search, attribute templates, create users with default role, refuse "
        "disabled, local fallback when unreachable",
        "Auth_ldap",
        TU + "test_ldap_login_creates_updates_and_falls_back",
    ),
    _r(
        "B-AUTH-06",
        "LDAP settings with a connection test",
        "settings/Authentication",
        TU + "test_ldap_login_creates_updates_and_falls_back",
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "B-AUTH-07",
        "Forced password change after sign-in; the new password must differ",
        "MY_Controller::check_password_reset, Profile::new_password",
        TU + "test_csv_import_of_real_instructors",
    ),
    _r(
        "B-AUTH-08",
        "Password reset by an administrator (one-time code; e-mailed with SMTP) and the public request",
        "Users (admin sets a password)",
        TU + "test_reset_tokens_with_and_without_smtp",
        FO + "test_b10_public_reset_is_throttled_and_keeps_the_earlier_code",
        ui=(E2E[12],),
    ),
    _r(
        "B-AUTH-09",
        "Profile: own e-mail, names, extension, language",
        "Profile::edit/save",
        TU + "test_search_profile_and_delete_keeps_booking_history",
        ui=(E2E[11],),
    ),
    _r(
        "B-AUTH-10",
        "Repeated failed logins are slowed down",
        "(CRBS: none)",
        RS + "test_minor5_login_failures_are_rate_limited",
        FO + "test_b10_public_reset_is_throttled_and_keeps_the_earlier_code",
        difference="superset: CRBS has no throttling (audit B10)",
    ),
    _r(
        "B-AUTH-11",
        "Sign out ends the session",
        "Logout (destroys the PHP session)",
        difference="superset: a JWT cannot be destroyed, so POST /auth/logout bumps users.token_version (JWT claim "
        "tv) and every earlier token of the user answers 401 -- sign-out ends the user's sessions on every device, "
        "not only this browser; password change / admin password set / reset code, disabling the account and a "
        "role change revoke the same way (CRBS keeps other sessions alive); an own password change also ends "
        "the current session (sign in again with the new password)",
    ),
    # ---------------------------------------------------------------- users (#19-#23)
    _r(
        "B-USERS-01",
        "User list: search (username, names, e-mail; Turkish-insensitive), role / department / enabled "
        "filters, sort (CRBS sort_map, Turkish alphabetical), paging",
        "Users::index, Users_model sort_map",
        TU + "test_search_profile_and_delete_keeps_booking_history",
        ui=(E2E[1],),
    ),
    _r(
        "B-USERS-02",
        "Add / edit users: unique username, role, department, enabled, names, display name, extension, "
        "force reset, optional password",
        "Users::add/edit/save_user",
        TR + "test_custom_role_permissions_are_enforced",
        ui=(E2E[1],),
        difference="usernames may hold Turkish letters and up to 255 characters (CRBS: [A-Za-z0-9-_.@], "
        "32); spaces are refused in both",
    ),
    _r(
        "B-USERS-03",
        "Per-user booking limits R / U / X override the role",
        "users_constraints",
        TR + "test_role_limits_and_user_constraints",
        TB + "test_limits_max_active_window_and_past",
    ),
    _r(
        "B-USERS-04",
        "Delete a user: never yourself; ACLs, constraints and room ownership go",
        "Users::delete, Users_model::Delete",
        TU + "test_search_profile_and_delete_keeps_booking_history",
        difference="booking history is kept (user link emptied); CRBS deletes the user's bookings (CRBS_PARITY §6.7)",
    ),
    _r(
        "B-USERS-05",
        "CSV user import with defaults and per-row status (UTF-8 / cp1254, ; or ,)",
        "Users::import/process_import",
        TU + "test_csv_import_of_real_instructors",
        ui=(E2E[14],),
        difference="force_password_reset read from its own 8th column (CRBS reads the role column: CRBS bug)",
    ),
    _r(
        "B-USERS-06",
        "Display name shown instead of the username",
        "users.displayname",
        TU + "test_csv_import_of_real_instructors",
        TE + "test_csv_export_has_crbs_columns_and_turkish_text",
    ),
    # ---------------------------------------------------------------- roles, permissions, departments (#24-#26, §1)
    _r(
        "B-ROLES-01",
        "The 28 CRBS permissions and the Administrator / Teacher roles of data.sql",
        "data.sql auth_permissions / auth_roles",
        TR + "test_seeded_roles_are_the_crbs_defaults_plus_smartsched_roles",
        difference="superset: three planning.* permissions and the Planner / Viewer roles are added",
    ),
    _r(
        "B-ROLES-02",
        "Every route checks its CRBS permission",
        "SystemPermissions / BookingPermissions",
        TR + "test_permission_matrix_per_role",
        TR + "test_custom_role_permissions_are_enforced",
        ui=(E2E[2],),
    ),
    _r(
        "B-ROLES-03",
        "Role CRUD: name, description, the four limits, permissions grouped like CRBS",
        "Roles::index/add/edit, Permissions_model::get_scoped",
        TR + "test_custom_role_permissions_are_enforced",
        TR + "test_role_validation",
        ui=(E2E[14],),
    ),
    _r(
        "B-ROLES-04",
        "Deleting a role empties users.role_id and removes the role's ACL entries",
        "Roles_model::delete",
        TR + "test_custom_role_permissions_are_enforced",
    ),
    _r(
        "B-ROLES-05",
        "The Administrator role cannot be deleted or stripped of setup.roles",
        "(lock-out guard)",
        TR + "test_admin_role_lockout_guards",
        difference="superset: CRBS has no lock-out guard",
    ),
    _r(
        "B-ROLES-06",
        "Users created before roles keep their rights (resolved by role code)",
        "(migration)",
        TR + "test_users_created_before_roles_resolve_by_role_code",
    ),
    _r(
        "B-ROLES-07",
        "Room permissions = role ∪ ACL (room or group; user, role or department context)",
        "Auth_model::user_room_permissions",
        TB + "test_room_acl_by_department_and_access_checker",
        FB + "test_b5_window_uses_the_room_acl_like_the_grid",
    ),
    _r(
        "B-ROLES-08",
        "No escalation: a role editor grants only permissions they hold and edits only roles within them",
        "Roles::save (CRBS allows any)",
        FO + "test_no_escalation_role_editors_cannot_grant_permissions_they_lack",
        ui=(E2E[14],),
        difference="stricter than CRBS, confirmed by the user 2026-10-08 (no-escalation rule)",
    ),
    _r(
        "B-ROLES-09",
        "setup.users cannot grant Administrator (or take an administrator's account over) without setup.roles",
        "Users::save (CRBS allows it)",
        FO + "test_setup_users_cannot_grant_or_take_over_administrator_without_setup_roles",
        ui=(E2E[14],),
        difference="security difference (audit), no switch",
    ),
    _r(
        "B-ROLES-10",
        "Departments CRUD (Turkish-casefold unique names); delete clears users' department and the "
        "department's ACL entries",
        "Departments, Departments_model::delete",
        TA + "test_departments_are_programmes",
        difference="a department is a programme of the planning list; programmes used by imported sections cannot be "
        "deleted (409)",
    ),
    # ---------------------------------------------------------------- rooms (#27-#35)
    _r(
        "B-ROOMS-01",
        "Room groups: name, description, members, order",
        "setup/rooms/Groups (+save_pos)",
        TA + "test_room_groups_order_fields_owner_and_photo",
        FB + "test_b7_grid_follows_group_and_room_positions",
    ),
    _r(
        "B-ROOMS-02",
        "One group per real building in one step",
        "(SmartSched)",
        TB + "test_room_acl_by_department_and_access_checker",
        difference="superset (imported rooms start ungrouped)",
    ),
    _r(
        "B-ROOMS-03",
        "Room booking settings: group, owner, location, icon, notes, bookable",
        "setup/rooms/Rooms",
        TA + "test_room_groups_order_fields_owner_and_photo",
        FB + "test_b14_clearing_a_group_clears_the_legacy_label",
    ),
    _r(
        "B-ROOMS-04",
        "Manual room order inside a group",
        "Rooms::save_pos",
        TA + "test_room_groups_order_fields_owner_and_photo",
        FB + "test_b7_grid_follows_group_and_room_positions",
    ),
    _r(
        "B-ROOMS-05",
        "Custom fields TEXT / CHECKBOX / SELECT; options; deleting a field removes its values",
        "setup/rooms/Fields",
        TA + "test_room_groups_order_fields_owner_and_photo",
    ),
    _r(
        "B-ROOMS-06",
        "Room ACL editor per room or group; only booking / room permissions allowed",
        "setup/rooms/Acl",
        TB + "test_room_acl_by_department_and_access_checker",
    ),
    _r(
        "B-ROOMS-07",
        "Access checker: effective permissions of one user in one room (role ∪ ACL)",
        "setup/Access_checker",
        TB + "test_room_acl_by_department_and_access_checker",
    ),
    _r(
        "B-ROOMS-08",
        "Room info card: group, location, owner, notes, custom fields, photo",
        "Rooms::info/photo",
        TA + "test_room_groups_order_fields_owner_and_photo",
        ui=(E2E[9],),
    ),
    _r(
        "B-ROOMS-09",
        "Only bookable rooms the user may view (room.view from the role or an ACL) are offered",
        "Rooms_model::get_bookable_rooms",
        TB + "test_room_acl_by_department_and_access_checker",
    ),
    _r(
        "B-ROOMS-10",
        "Rooms without a group are hidden from the grid (switch to show them)",
        "Room_groups_model::get_bookable",
        TB + "test_ungrouped_rooms_hidden_like_crbs",
        difference="CRBS default kept; org setting show_ungrouped_rooms shows them (imported rooms start ungrouped)",
    ),
    _r(
        "B-ROOMS-11",
        "Room owner: an ACL to cancel others' bookings of the room, and the owner's dashboard",
        "rooms.user_id, migration 2025-04",
        TB + "test_booking_for_another_user_notifies_and_shows_on_dashboard",
        TA + "test_room_groups_order_fields_owner_and_photo",
    ),
    _r(
        "B-ROOMS-12",
        "Room photo upload (decoded and re-encoded, ≤1600 px) and removal",
        "Rooms::photo",
        TA + "test_room_groups_order_fields_owner_and_photo",
        FO + "test_b2_room_photo_is_decoded_and_reencoded",
    ),
    _r(
        "B-ROOMS-13",
        "Rooms, periods and schedules with bookings cannot be deleted (409 with counts)",
        "Rooms_model::delete (CRBS cascades)",
        FB + "test_b16_deleting_a_period_or_room_keeps_booking_history",
        TA + "test_schedules_periods_and_group_schedules",
        difference="security difference (audit B16): history is never cascaded away; make them not bookable",
    ),
    _r(
        "B-ROOMS-14",
        "Deleting a room group frees its rooms and removes the group's ACL entries",
        "Room_groups_model::delete",
        TA + "test_room_groups_order_fields_owner_and_photo",
        FB + "test_b14_clearing_a_group_clears_the_legacy_label",
    ),
    # ---------------------------------------------------------------- sessions, schedules, weeks, holidays (#36-#43)
    _r(
        "B-SESS-01",
        "Sessions (= terms): dates, selectable, default schedule",
        "Sessions, Sessions_model",
        TA + "test_schedules_periods_and_group_schedules",
    ),
    _r(
        "B-SESS-02",
        "The current session is computed from the dates (switch for the manual flag)",
        "Sessions_model::auto_set_current",
        FB + "test_b3_new_active_term_keeps_its_flag_and_current_is_computed_from_dates",
        FB + "test_dashboard_totals_use_the_current_term",
    ),
    _r(
        "B-SESS-03",
        "Create / edit / delete sessions with setup.sessions",
        "Sessions CRUD",
        FB + "test_missing6_setup_sessions_may_create_and_delete_terms",
    ),
    _r(
        "B-SESS-04",
        "Changing session dates cancels (or asks about) bookings outside the new range",
        "Sessions::check_session_dates",
        FB + "test_missing3_shrinking_a_term_cancels_or_asks_about_bookings_outside",
        difference="CRBS deletes them; SmartSched cancels with a reason (setting term_date_change=confirm asks first)",
    ),
    _r(
        "B-SESS-05",
        "Staff choose among selectable sessions; view_all_sessions reaches the others",
        "Bookings::change_session, Context::init_session",
    ),
    _r(
        "B-SESS-06",
        "Schedule per (session, room group); ungrouped rooms use the session default",
        "Room_schedules, Schedules_model::get_applied_schedule",
        TA + "test_schedules_periods_and_group_schedules",
        FB + "test_b13_rooms_keep_their_own_schedule_without_room_groups",
    ),
    _r(
        "B-SESS-07",
        "Schedules CRUD",
        "Schedules",
        TA + "test_schedules_periods_and_group_schedules",
        FB + "test_b16_deleting_a_period_or_room_keeps_booking_history",
    ),
    _r(
        "B-SESS-08",
        "Periods: name, times (dotted times accepted), bookable flag, weekdays",
        "Periods",
        TA + "test_schedules_periods_and_group_schedules",
        TB + "test_closed_dates_and_wrong_periods",
        difference="one clock: periods map onto the university's 18-period grid; times outside it are refused "
        "(CRBS_PARITY §6.1)",
    ),
    _r(
        "B-SESS-09",
        "The university's 18 real periods in one step",
        "(SmartSched)",
        TA + "test_schedules_periods_and_group_schedules",
        difference="superset",
    ),
    _r(
        "B-SESS-10",
        "Timetable weeks (A/B rotation): name, colours, text colour from brightness",
        "Weeks, Weeks_model",
        TB + "test_closed_dates_and_wrong_periods",
        TB + "test_date_picker_shows_weeks_and_holidays_to_staff",
    ),
    _r(
        "B-SESS-11",
        "Session calendar: a timetable week per date or applied to all; unmapped dates closed",
        "Sessions::save_dates/apply_week",
        TB + "test_closed_dates_and_wrong_periods",
        TB + "test_date_picker_shows_weeks_and_holidays_to_staff",
        difference="a term with no mapping at all is fully bookable and recurs weekly (no seed data; CRBS_PARITY §6.4)",
    ),
    _r(
        "B-SESS-12",
        "Holidays: named ranges inside a session; no bookings; series skip them",
        "Holidays",
        TB + "test_recurring_series_skips_holidays_and_timetable_and_respects_limit",
        TB + "test_closed_dates_and_wrong_periods",
    ),
    _r(
        "B-SESS-13",
        "Week view lists only days with periods; prev / next skip closed days",
        "Context::init_week, Dates_model",
        FB + "test_b15_week_view_hides_days_without_periods_and_navigates_like_crbs",
        ui=(E2E[9],),
    ),
    _r(
        "B-SESS-14",
        "Overlapping sessions (Bahar and its Final); every booking keeps its session",
        "Sessions::_date_check (CRBS refuses overlaps)",
        difference="SmartSched allows overlapping terms (CRBS_PARITY #36); bookings store term_id and the grid "
        "takes term_id",
    ),
    _r(
        "B-SESS-15",
        "Deleting a session deletes its bookings, holidays and calendar dates",
        "Sessions_model::delete",
    ),
    # ---------------------------------------------------------------- bookings (#44-#59)
    _r(
        "B-BOOK-01",
        "Grid by day: rooms × periods, room group tabs",
        "Bookings::index, Grid",
        FB + "test_b7_grid_follows_group_and_room_positions",
        ui=(E2E[3], E2E[9]),
    ),
    _r(
        "B-BOOK-02",
        "Grid by room: one room's week",
        "Grid (room view)",
        TB + "test_published_timetable_and_other_bookings_block_a_slot",
        ui=(E2E[9],),
    ),
    _r(
        "B-BOOK-03",
        "Slot states: available, booked single / recurring, holiday, period not on the day, outside "
        "the session, limit reached, no permission, outside range_min / range_max",
        "Slot",
        TB + "test_published_timetable_and_other_bookings_block_a_slot",
        TB + "test_limits_max_active_window_and_past",
        FB + "test_b5_window_uses_the_room_acl_like_the_grid",
        ui=(E2E[8],),
    ),
    _r(
        "B-BOOK-04",
        "Room picker and room-filtered lists",
        "Bookings::filter('room')",
        TB + "test_room_acl_by_department_and_access_checker",
        FB + "test_b7_grid_follows_group_and_room_positions",
    ),
    _r(
        "B-BOOK-05",
        "Date picker with timetable week colours, holidays, open / closed dates",
        "Bookings::filter('date')",
        TB + "test_date_picker_shows_weeks_and_holidays_to_staff",
    ),
    _r(
        "B-BOOK-06",
        "Single booking: date + period + room, notes",
        "SingleAgent",
        TB + "test_published_timetable_and_other_bookings_block_a_slot",
        ui=(E2E[3],),
    ),
    _r("B-BOOK-07", "Notes at most 255 characters", "bookings.notes max_length[255]"),
    _r(
        "B-BOOK-08",
        "One active booking per (date, period, room); clashes refused with the holder",
        "validate_booking, no_conflict",
        TB + "test_published_timetable_and_other_bookings_block_a_slot",
        ui=(E2E[4],),
        difference="superset: enforced by a database unique key on booking_slots too",
    ),
    _r(
        "B-BOOK-09",
        "Book for another user with set_user",
        "book_*.set_user",
        TB + "test_booking_for_another_user_notifies_and_shows_on_dashboard",
        FB + "test_c_unauthorised_set_user_is_403_or_ignored_like_crbs",
        difference="security difference (c): unauthorised set_user / set_department is 403; setting "
        "ignore_unauthorised_user_department restores CRBS",
    ),
    _r(
        "B-BOOK-10",
        "Department of a booking (own, or chosen with set_department)",
        "book_*.set_department",
        TB + "test_multi_booking_selection_and_atomic_create",
        FB + "test_c_unauthorised_set_user_is_403_or_ignored_like_crbs",
    ),
    _r(
        "B-BOOK-11",
        "Recurring preview and create: book / do not book / replace per date; holidays skipped",
        "SingleAgent::preview/create_single_recurring",
        TB + "test_recurring_series_skips_holidays_and_timetable_and_respects_limit",
        FB + "test_b1_replace_still_works_when_only_the_old_booking_holds_it",
        ui=(E2E[5],),
    ),
    _r("B-BOOK-12", "A series repeats in the same timetable week (A/B rotation)", "get_recurring_dates"),
    _r(
        "B-BOOK-13",
        'Recurring start / end "session" or a date',
        "SingleAgent recurring_start/end",
        FB + "test_cancel_all_keeps_past_instances_unless_switched",
    ),
    _r(
        "B-BOOK-14",
        "recur_max_instances caps the booked instances",
        "SingleAgent::check_constraints",
        TB + "test_recurring_series_skips_holidays_and_timetable_and_respects_limit",
        FB + "test_f_replacements_do_not_count_against_recur_max_unless_switched",
    ),
    _r(
        "B-BOOK-15",
        "Multi-booking: select slots, per-slot single details, atomic create, dry run",
        "MultiAgent",
        TB + "test_multi_booking_selection_and_atomic_create",
        ui_gap="the multi-select tray and wizard exist but no e2e step uses them; proposed: bookings.spec.ts step",
    ),
    _r(
        "B-BOOK-16",
        "Multi-booking recurring step (per-slot start / end, department rule)",
        "MultiAgent::process_recurring_defaults",
        FB + "test_b_multi_recurring_department_uses_book_recur_create_like_crbs",
        difference="behaviour difference (b): CRBS's book_recur.create check is the default; "
        "recurring_department_needs_set_department switches to set_department",
    ),
    _r("B-BOOK-17", "A multi-booking selection belongs to its user and can be discarded", "multi_bookings"),
    _r(
        "B-BOOK-18",
        "Booking details: user and notes hidden unless owner or view_other_users / view_other_notes",
        "Bookings::view, booking_user_viewable",
        TB + "test_published_timetable_and_other_bookings_block_a_slot",
        TB + "test_show_names_setting_and_maintenance_mode",
        ui=(E2E[8],),
    ),
    _r(
        "B-BOOK-19",
        "Booking details need room.view or ownership",
        "Bookings::view (CRBS: any signed-in user)",
        difference="security difference (e), no switch",
    ),
    _r(
        "B-BOOK-20",
        "All instances of a series",
        "Bookings::view_series",
        TB + "test_cancel_one_future_all_and_owner_rules",
    ),
    _r(
        "B-BOOK-21",
        "Edit one / future / all instances with CRBS field rights",
        "Bookings::edit, UpdateAgent",
        TB + "test_edit_scopes_and_field_rights",
        FB + "test_b6_explicit_nulls_are_422",
        ui=(E2E[4],),
    ),
    _r(
        "B-BOOK-22",
        "Owners cannot move a booking into the past or beyond range_max",
        "UpdateAgent",
        FB + "test_owner_cannot_move_a_booking_into_the_past_or_beyond_range_max",
        difference="security difference (audit), no switch",
    ),
    _r(
        "B-BOOK-23",
        "Cancel one / future / all; owners only future slots; role-level cancel_other has no date limit",
        "Bookings::cancel*, booking_cancelable",
        TB + "test_cancel_one_future_all_and_owner_rules",
        ui=(E2E[6],),
    ),
    _r(
        "B-BOOK-24",
        'Cancellation reason recorded (also "replaced by series #N")',
        "bookings.cancel_reason",
        TB + "test_cancel_one_future_all_and_owner_rules",
        TB + "test_recurring_series_skips_holidays_and_timetable_and_respects_limit",
        ui=(E2E[6],),
        difference="superset: CRBS has the column but never fills it",
    ),
    _r(
        "B-BOOK-25",
        "scope=all cancels today and later only (switch for every instance)",
        "cancel_all",
        FB + "test_cancel_all_keeps_past_instances_unless_switched",
        difference="security difference: past instances stay as history; cancel_all_includes_past restores CRBS",
    ),
    _r(
        "B-BOOK-26",
        "Cancel many selected bookings (only those the user may cancel)",
        "Bookings::cancel_multi",
        TB + "test_cancel_one_future_all_and_owner_rules",
        ui_gap="my-bookings cancel-many exists but no e2e step selects several bookings",
    ),
    _r(
        "B-BOOK-27",
        "Limits: max_active_bookings, range_min / range_max, no past single bookings",
        "Slot::check_free_constraints, SingleAgent::check_constraints",
        TB + "test_limits_max_active_window_and_past",
        FB + "test_a_max_active_is_a_grid_rule_in_crbs_and_optional_on_post",
        difference="behaviour difference (a): CRBS checks max_active in the grid only (default); "
        "enforce_max_active_on_create checks POST too",
    ),
    _r(
        "B-BOOK-28",
        "Bookings others made for a user do not count against the user's limit",
        "Users_model::get_scheduled_booking_count",
        TB + "test_limits_max_active_window_and_past",
    ),
    _r(
        "B-BOOK-29",
        "Dashboard: my next 14 days, others' bookings in rooms I own, totals, my limits",
        "Dashboard::index",
        TB + "test_booking_for_another_user_notifies_and_shows_on_dashboard",
        FB + "test_dashboard_totals_use_the_current_term",
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "B-BOOK-30",
        "My bookings with date range and status filters",
        "Bookings_model::ByUser",
        TB + "test_recurring_series_skips_holidays_and_timetable_and_respects_limit",
        ui=(E2E[6],),
    ),
    _r(
        "B-BOOK-31",
        "CSV export: the 24 CRBS columns, session and room group filters, cancelled on request, UTF-8 BOM",
        "Export, Bookings_model::export_unbuffered",
        TE + "test_csv_export_has_crbs_columns_and_turkish_text",
        FB + "test_b9_j_export_neutralises_formulas_and_follows_room_groups",
        ui=(E2E[7],),
        difference="behaviour difference (j): ungrouped rooms left out like CRBS; export_ungrouped_rooms includes them",
    ),
    _r(
        "B-BOOK-32",
        "Export needs system.export_bookings",
        "Export controller",
        TE + "test_csv_export_has_crbs_columns_and_turkish_text",
        TR + "test_permission_matrix_per_role",
    ),
    _r(
        "B-BOOK-33",
        "Maintenance closes the booking pages, not the dashboard (switch for the lists too)",
        "Bookings::__construct",
        FB + "test_g_maintenance_closes_bookings_but_not_the_dashboard_unless_switched",
        difference="behaviour difference (g): CRBS default; maintenance_gates_lists closes the lists too",
    ),
    # ---------------------------------------------------------------- more than CRBS (#60-#62 and the audit fixes)
    _r(
        "X-01",
        "Calendar feeds (ICS) per user and room, bearer or rotating token, time zone aware",
        "(not in CRBS)",
        TE + "test_ics_feeds",
        FB + "test_b11_ics_uses_the_timezone_setting",
        difference="superset",
    ),
    _r(
        "X-02",
        "E-mail notifications through SMTP with an outbox (UNSENT without SMTP, FAILED with the error)",
        "(not in CRBS)",
        TU + "test_reset_tokens_with_and_without_smtp",
        TB + "test_booking_for_another_user_notifies_and_shows_on_dashboard",
        difference="superset",
        ui_gap="SMTP settings + outbox screen exist but no e2e step drives them",
    ),
    _r(
        "X-03",
        "The published timetable is occupancy: bookings never collide with it",
        "(not in CRBS)",
        TB + "test_published_timetable_and_other_bookings_block_a_slot",
        TB + "test_unpublished_runs_do_not_block_but_activation_reports_conflicts",
        ui=(E2E[4], CAL_ROOMS),
        difference="superset (CRBS_PARITY §6.2)",
    ),
    _r(
        "X-04",
        "Confirmed bookings are solver blocks",
        "(not in CRBS)",
        TE + "test_confirmed_bookings_are_solver_blocks",
        ui=(CAL_MOVE,),
        difference="superset",
    ),
    _r(
        "X-05",
        "Bookings that a newly published timetable overlaps are listed for planners",
        "(not in CRBS)",
        TB + "test_unpublished_runs_do_not_block_but_activation_reports_conflicts",
        ui=(E2E[13],),
        difference="superset",
    ),
    _r(
        "X-06",
        "Uploaded images decoded and re-encoded, served with nosniff + CSP; SVG refused",
        "(CRBS: stored XSS)",
        FO + "test_b2_logo_is_reencoded_and_svg_is_refused",
        FO + "test_b2_room_photo_is_decoded_and_reencoded",
        difference="security (audit B2)",
    ),
    _r(
        "X-07",
        "CSV export neutralises spreadsheet formulas",
        "(CRBS: formula injection)",
        FB + "test_b9_j_export_neutralises_formulas_and_follows_room_groups",
        difference="security (audit B9)",
    ),
    # ---------------------------------------------------------------- audit bugs (regressions)
    _r(
        "BUG-B01",
        "Replace never cancels the old booking when something else holds the slot",
        "audit B1",
        FB + "test_b1_replace_never_cancels_when_something_else_holds_the_slot",
        FB + "test_b1_replace_still_works_when_only_the_old_booking_holds_it",
    ),
    _r(
        "BUG-B02",
        "No stored XSS through the logo or room photos",
        "audit B2",
        FO + "test_b2_logo_is_reencoded_and_svg_is_refused",
        FO + "test_b2_room_photo_is_decoded_and_reencoded",
    ),
    _r(
        "BUG-B03",
        "A new active term keeps its flag; current term from the dates",
        "audit B3",
        FB + "test_b3_new_active_term_keeps_its_flag_and_current_is_computed_from_dates",
    ),
    _r(
        "BUG-B04",
        "The CRBS migration fills the parity tables with usable users, roles, ACLs and bookings",
        "audit B4",
        IC + "test_import_crbs_fills_the_parity_tables",
        IC + "test_imported_users_log_in_with_their_crbs_passwords",
        IC + "test_install_scripts_load_into_sqlite",
        gap="verified on CRBS's own install SQL (structure.sql + data.sql) in SQLite, not yet against a running "
        "classroombookings MySQL: Phase 18 part 3 (pod --profile legacy, dry-run report)",
    ),
    _r(
        "BUG-B05",
        "What the grid offers, POST accepts (room-level window)",
        "audit B5",
        FB + "test_b5_window_uses_the_room_acl_like_the_grid",
    ),
    _r("BUG-B06", "Explicit nulls in an edit are 422", "audit B6", FB + "test_b6_explicit_nulls_are_422"),
    _r(
        "BUG-B07",
        "Group and room order follow the configured positions",
        "audit B7",
        FB + "test_b7_grid_follows_group_and_room_positions",
    ),
    _r(
        "BUG-B08",
        "Organisation settings validated (website scheme, languages, patterns)",
        "audit B8",
        FO + "test_b8_org_settings_are_validated",
        FO + "test_b8_valid_values_and_pattern_option_list",
    ),
    _r(
        "BUG-B09",
        "CSV formula injection neutralised",
        "audit B9",
        FB + "test_b9_j_export_neutralises_formulas_and_follows_room_groups",
    ),
    _r(
        "BUG-B10",
        "Login and public reset throttled; a reset request keeps earlier codes",
        "audit B10",
        FO + "test_b10_public_reset_is_throttled_and_keeps_the_earlier_code",
        RS + "test_minor5_login_failures_are_rate_limited",
    ),
    _r(
        "BUG-B11",
        "ICS uses the time zone setting (VTIMEZONE or UTC)",
        "audit B11",
        FB + "test_b11_ics_uses_the_timezone_setting",
    ),
    _r(
        "BUG-B12",
        'Changelog "seen" is a version and timestamp',
        "audit B12",
        FO + "test_b12_changelog_seen_is_a_version_and_timestamp",
    ),
    _r(
        "BUG-B13",
        "Rooms keep their own schedule with room groups off",
        "audit B13",
        FB + "test_b13_rooms_keep_their_own_schedule_without_room_groups",
    ),
    _r(
        "BUG-B14",
        "Clearing a room's group clears the legacy label",
        "audit B14",
        FB + "test_b14_clearing_a_group_clears_the_legacy_label",
    ),
    _r(
        "BUG-B15",
        "Week view without period-less days; CRBS navigation",
        "audit B15",
        FB + "test_b15_week_view_hides_days_without_periods_and_navigates_like_crbs",
    ),
    _r(
        "BUG-B16",
        "Deleting periods / rooms keeps booking history",
        "audit B16",
        FB + "test_b16_deleting_a_period_or_room_keeps_booking_history",
    ),
    # ---------------------------------------------------------------- audit missing items
    _r(
        "MISS-1",
        "The CRBS frontend (grid, sheets, admin screens, login extras)",
        "audit MISSING 1",
        ui=(E2E[3], E2E[9], E2E[14]),
        gap="screens built 2026-10-08; per-screen coverage in the S-* rows; the "
        "shell items (login logo/message, What's new, i18n overlay) are in ROADMAP 'Shell follow-ups'",
    ),
    _r(
        "MISS-2",
        "Translations and date patterns applied",
        "audit MISSING 2",
        FO + "test_missing2_i18n_bundle_merges_overrides",
        FO + "test_missing2_emails_use_overrides_and_date_patterns",
        gap="backend applies them (e-mails, /org/i18n); the frontend overlay is a ROADMAP shell follow-up",
    ),
    _r(
        "MISS-3",
        "Changing term dates handles bookings outside",
        "audit MISSING 3",
        FB + "test_missing3_shrinking_a_term_cancels_or_asks_about_bookings_outside",
    ),
    _r(
        "MISS-4",
        "Legacy password hashes verified",
        "audit MISSING 4",
        IC + "test_imported_users_log_in_with_their_crbs_passwords",
    ),
    _r(
        "MISS-5",
        "grid_highlight and the printable bookings page",
        "audit MISSING 5",
        FO + "test_missing5_grid_highlight_reaches_the_grid",
        ui=(E2E[9],),
    ),
    _r(
        "MISS-6",
        "Installer requirements step; sessions under setup.sessions",
        "audit MISSING 6",
        FO + "test_missing6_installer_requirements_step",
        FB + "test_missing6_setup_sessions_may_create_and_delete_terms",
    ),
    # ---------------------------------------------------------------- deliberate differences (audit decisions)
    _r(
        "DIFF-a",
        "max_active_bookings on every POST (switch)",
        "audit (a)",
        FB + "test_a_max_active_is_a_grid_rule_in_crbs_and_optional_on_post",
        difference="CRBS default; enforce_max_active_on_create",
    ),
    _r(
        "DIFF-b",
        "Recurring department permission name (switch)",
        "audit (b)",
        FB + "test_b_multi_recurring_department_uses_book_recur_create_like_crbs",
        difference="CRBS default; recurring_department_needs_set_department",
    ),
    _r(
        "DIFF-c",
        "403 on unauthorised set_user / set_department (switch)",
        "audit (c)",
        FB + "test_c_unauthorised_set_user_is_403_or_ignored_like_crbs",
        difference="safer default; ignore_unauthorised_user_department restores CRBS",
    ),
    _r(
        "DIFF-d",
        "Current password required to change it",
        "audit (d)",
        TU + "test_search_profile_and_delete_keeps_booking_history",
        difference="safer, no switch",
    ),
    _r("DIFF-e", "Booking details need room.view or ownership", "audit (e)", difference="safer, no switch"),
    _r(
        "DIFF-f",
        "Replacements counted in recur_max_instances (switch)",
        "audit (f)",
        FB + "test_f_replacements_do_not_count_against_recur_max_unless_switched",
        difference="CRBS default; recur_max_counts_replacements",
    ),
    _r(
        "DIFF-g",
        "Maintenance gating dashboard / lists / feeds (switch)",
        "audit (g)",
        FB + "test_g_maintenance_closes_bookings_but_not_the_dashboard_unless_switched",
        difference="CRBS default; maintenance_gates_lists",
    ),
    _r(
        "DIFF-i",
        "is_current computed from dates (switch)",
        "audit (i)",
        FB + "test_b3_new_active_term_keeps_its_flag_and_current_is_computed_from_dates",
        difference="CRBS default; manual_current_term",
    ),
    _r(
        "DIFF-j",
        "Export of ungrouped rooms (switch)",
        "audit (j)",
        FB + "test_b9_j_export_neutralises_formulas_and_follows_room_groups",
        difference="CRBS default; export_ungrouped_rooms",
    ),
    _r(
        "DIFF-ldap",
        "LDAP local fallback only when the directory is unreachable; ldap.ignore_cert default off",
        "audit security",
        FO + "test_ldap_rejection_does_not_fall_back_to_the_local_copy",
        FO + "test_every_new_setting_has_its_default_and_round_trips",
        difference="safer",
    ),
    _r(
        "DIFF-noesc",
        "No escalation by role editors (user decision 2026-10-08, stricter than CRBS)",
        "user decision",
        FO + "test_no_escalation_role_editors_cannot_grant_permissions_they_lack",
        FO + "test_setup_users_cannot_grant_or_take_over_administrator_without_setup_roles",
        ui=(E2E[14],),
        difference="stricter than CRBS, confirmed by the user",
    ),
    _r(
        "DIFF-changelog",
        '"What\'s new" reads the local CHANGELOG.md (no remote feed)',
        "audit",
        TA + "test_org_settings_translations_changelog_and_events",
        difference="no outbound call",
    ),
    # ---------------------------------------------------------------- later parts of Phase 18 (declared gaps)
    _r(
        "P18-LANG",
        "The 13 CRBS UI languages (cs, da, nl, en, fi, fr, de, it, pt, pt-BR, es, sv, cy) plus Turkish in "
        "the frontend and backend texts",
        "application/language/*",
        FO + "test_missing2_i18n_bundle_merges_overrides",
        gap="Phase 18 part 2: today TR + EN only (backend languages list, shipped e-mail strings, frontend message "
        "files being edited by other agents). Needs: the CRBS language files imported as message catalogues, the "
        "language list in app/services/bookings_i18n.py widened, frontend locale files + an e2e language switch",
    ),
    _r(
        "P18-LEGACY",
        "Upgrade a running classroombookings MySQL install (users with passwords, roles, ACLs, "
        "constraints, groups/fields, sessions/weeks/holidays, bookings and series) with a dry-run report",
        "Upgrade controller",
        IC + "test_import_crbs_fills_the_parity_tables",
        gap="Phase 18 part 3: needs the pod's --profile legacy CRBS with a real dump, a dry-run mode on "
        "POST /imports/crbs and a report diffing counts per table",
    ),
    _r(
        "P18-DIFF",
        "Side-by-side: legacy CRBS and SmartSched on the same data agree on grid states",
        "(gate)",
        gap="Phase 18 part 4: needs P18-LEGACY, a sampler of (date, room, user) and a CRBS grid scraper on the pod",
    ),
    # ---------------------------------------------------------------- CRBS screens (docs/CRBS_PARITY.md §5)
    _r(
        "S-01",
        "Setup wizard (organisation, time zone, administrator) and setup checklist",
        "install, setup/Dashboard",
        TA + "test_first_run_setup_wizard",
        FO + "test_missing6_installer_requirements_step",
        ui=(E2E[12],),
        screen=True,
    ),
    _r(
        "S-02",
        "Login: logo, login message, maintenance banner, username or e-mail, forgot password, forced change",
        "Login",
        TU + "test_csv_import_of_real_instructors",
        ui=(E2E[2], E2E[10], E2E[12]),
        screen=True,
        ui_gap="logo / login message / forgot-password link not mounted on the login page (ROADMAP 'Shell follow-ups')",
    ),
    _r(
        "S-03",
        "Bookings grid (day and room views, tabs, date picker, sessions, legend, multi-select)",
        "Bookings::index",
        TB + "test_published_timetable_and_other_bookings_block_a_slot",
        FB + "test_b7_grid_follows_group_and_room_positions",
        ui=(E2E[3], E2E[4], E2E[9]),
        screen=True,
    ),
    _r(
        "S-04",
        "Book a slot sheet (single / recurring, notes, department, user)",
        "SingleAgent views",
        TB + "test_published_timetable_and_other_bookings_block_a_slot",
        ui=(E2E[3], E2E[5]),
        screen=True,
    ),
    _r(
        "S-05",
        "Recurring preview table (book / skip / replace, limit warning)",
        "SingleAgent preview",
        TB + "test_recurring_series_skips_holidays_and_timetable_and_respects_limit",
        ui=(E2E[5],),
        screen=True,
    ),
    _r(
        "S-06",
        "Multi-booking wizard",
        "MultiAgent views",
        TB + "test_multi_booking_selection_and_atomic_create",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-07",
        "Booking details (room info, period, week, series link, user / notes per visibility)",
        "Bookings::view",
        TB + "test_show_names_setting_and_maintenance_mode",
        ui=(E2E[8],),
        screen=True,
    ),
    _r(
        "S-08",
        "Edit booking with scope picker",
        "Bookings::edit",
        TB + "test_edit_scopes_and_field_rights",
        ui=(E2E[4],),
        screen=True,
    ),
    _r(
        "S-09",
        "Cancel dialog (one / future / all, reason) and cancel many",
        "Bookings::cancel",
        TB + "test_cancel_one_future_all_and_owner_rules",
        ui=(E2E[6],),
        screen=True,
        ui_gap="cancel-many is not driven by an e2e step",
    ),
    _r(
        "S-10",
        "Staff dashboard (my upcoming, rooms I own, totals, limits)",
        "Dashboard",
        TB + "test_booking_for_another_user_notifies_and_shows_on_dashboard",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-11",
        "My bookings with filters and the calendar link",
        "(Dashboard lists)",
        TB + "test_recurring_series_skips_holidays_and_timetable_and_respects_limit",
        TE + "test_ics_feeds",
        ui=(E2E[6], E2E[7]),
        screen=True,
    ),
    _r(
        "S-12",
        "Profile (names, e-mail, extension, language, password, calendar token)",
        "Profile",
        TU + "test_search_profile_and_delete_keeps_booking_history",
        ui=(E2E[11],),
        screen=True,
    ),
    _r(
        "S-13",
        "Users (search, filters, add / edit, R/U/X limits, force change, reset code, delete)",
        "Users",
        TU + "test_search_profile_and_delete_keeps_booking_history",
        TR + "test_role_limits_and_user_constraints",
        ui=(E2E[1], E2E[12], E2E[14]),
        screen=True,
    ),
    _r(
        "S-14",
        "User import (CSV + defaults, results)",
        "Users::import",
        TU + "test_csv_import_of_real_instructors",
        ui=(E2E[14],),
        screen=True,
    ),
    _r(
        "S-15",
        "Roles (permission groups, the four limits)",
        "Roles",
        TR + "test_custom_role_permissions_are_enforced",
        ui=(E2E[14],),
        screen=True,
    ),
    _r(
        "S-16",
        "Departments",
        "Departments",
        TA + "test_departments_are_programmes",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-17",
        "Room groups, room booking settings, custom fields, room ACL, access checker",
        "setup/rooms/*",
        TA + "test_room_groups_order_fields_owner_and_photo",
        TB + "test_room_acl_by_department_and_access_checker",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-18",
        "Sessions: booking settings, per-group schedules, calendar of timetable weeks, holidays",
        "Sessions, Holidays, Room_schedules",
        TA + "test_schedules_periods_and_group_schedules",
        TB + "test_date_picker_shows_weeks_and_holidays_to_staff",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-19",
        "Schedules and periods (+ the 18 university periods)",
        "Schedules, Periods",
        TA + "test_schedules_periods_and_group_schedules",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-20",
        "Timetable weeks with colour picker",
        "Weeks",
        TB + "test_closed_dates_and_wrong_periods",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-21",
        "Organisation and general settings",
        "settings/Organisation, settings/General",
        TA + "test_org_settings_translations_changelog_and_events",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-22",
        "Authentication (LDAP) with test",
        "settings/Authentication",
        TU + "test_ldap_login_creates_updates_and_falls_back",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-23",
        "E-mail (SMTP) settings, test message and outbox",
        "(SmartSched)",
        TU + "test_reset_tokens_with_and_without_smtp",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-24",
        "Translation overrides",
        "setup/Language",
        TA + "test_org_settings_translations_changelog_and_events",
        screen=True,
        ui_gap=FRONTEND_UI_GAP,
    ),
    _r(
        "S-25",
        "Export bookings",
        "Export",
        TE + "test_csv_export_has_crbs_columns_and_turkish_text",
        ui=(E2E[7],),
        screen=True,
    ),
    _r(
        "S-26",
        "Conflicts after publishing (planners)",
        "(SmartSched)",
        TB + "test_unpublished_runs_do_not_block_but_activation_reports_conflicts",
        ui=(E2E[13],),
        screen=True,
    ),
    _r(
        "S-27",
        "Printable bookings page",
        "(CRBS print CSS)",
        FO + "test_missing5_grid_highlight_reaches_the_grid",
        ui=(E2E[9],),
        screen=True,
    ),
    _r(
        "S-28",
        "Room info popup",
        "Rooms::info",
        TA + "test_room_groups_order_fields_owner_and_photo",
        ui=(E2E[9],),
        screen=True,
    ),
    _r(
        "S-29",
        "Reset password page (one-time code)",
        "(SmartSched)",
        TU + "test_reset_tokens_with_and_without_smtp",
        ui=(E2E[12],),
        screen=True,
    ),
)

BY_ID: dict[str, Row] = {r.id: r for r in ROWS}
