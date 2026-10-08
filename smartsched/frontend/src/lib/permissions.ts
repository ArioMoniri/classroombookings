"use client";
/**
 * Permission helpers over `GET /auth/me` → `permissions[]` (CRBS 2.15 model, docs/CRBS_PARITY.md §1).
 *
 * Never branch on the role code: roles are permission sets an administrator edits (custom roles exist, and
 * `users.role` is `CUSTOM` / `NONE` for them). Room-specific rights (ACL entries on a room or room group)
 * are only known per slot from the booking grid (`allow_single` / `allow_recur`), so the helpers here
 * answer the role-level question, exactly like CRBS `has_permission(p)` without a room id.
 */
import { useCrbsMe } from "@/lib/api/crbs";
import type { MessageKey } from "@/lib/i18n";

export type PermissionName = string;
/** one permission, an any-of list, or `null` = any signed-in user */
export type PermissionRequirement = PermissionName | readonly PermissionName[] | null | undefined;

export const SETUP_PERMISSIONS = [
  "setup.authentication",
  "setup.departments",
  "setup.roles",
  "setup.rooms",
  "setup.rooms_acl",
  "setup.schedules",
  "setup.sessions",
  "setup.settings",
  "setup.timetable_weeks",
  "setup.users",
] as const;

export const PLANNING_PERMISSIONS = ["planning.view", "planning.edit", "planning.admin"] as const;

/** `true` when `perms` satisfies the requirement (any-of; `null` / `undefined` = no requirement). */
export function hasPermission(perms: readonly string[] | undefined | null, need: PermissionRequirement): boolean {
  if (need === null || need === undefined) return true;
  if (!perms) return false;
  const list = typeof need === "string" ? [need] : need;
  if (list.length === 0) return true;
  return list.some((p) => perms.includes(p));
}

/** `true` when every listed permission is held. */
export function hasAllPermissions(perms: readonly string[] | undefined | null, need: readonly string[]): boolean {
  if (!perms) return need.length === 0;
  return need.every((p) => perms.includes(p));
}

export function hasAnySetup(perms: readonly string[] | undefined | null): boolean {
  return hasPermission(perms, SETUP_PERMISSIONS);
}

export function hasPlanning(perms: readonly string[] | undefined | null): boolean {
  return hasPermission(perms, PLANNING_PERMISSIONS);
}

/** Role-level booking capabilities (CRBS checks without a room). Per-room rights come from the grid. */
export interface BookingCapabilities {
  single: boolean;
  recurring: boolean;
  setUser: { single: boolean; recurring: boolean };
  setDepartment: { single: boolean; recurring: boolean };
  editOthers: boolean;
  cancelOthers: boolean;
  exportBookings: boolean;
  bypassMaintenance: boolean;
  viewAllSessions: boolean;
}

export function bookingCapabilities(perms: readonly string[] | undefined | null): BookingCapabilities {
  const p = (name: string) => hasPermission(perms, name);
  return {
    single: p("book_single.create"),
    recurring: p("book_recur.create"),
    setUser: { single: p("book_single.set_user"), recurring: p("book_recur.set_user") },
    setDepartment: { single: p("book_single.set_department"), recurring: p("book_recur.set_department") },
    editOthers: hasPermission(perms, ["book_single.edit_other_booking", "book_recur.edit_other_booking"]),
    cancelOthers: hasPermission(perms, ["book_single.cancel_other_booking", "book_recur.cancel_other_booking"]),
    exportBookings: p("system.export_bookings"),
    bypassMaintenance: p("system.bypass_maintenance_mode"),
    viewAllSessions: p("system.view_all_sessions"),
  };
}

/* ------------------------------------------------------------------ no escalation (role grants) */

/**
 * Mirrors the backend (`bookings_perms.may_grant_role` / `may_manage_user`, `roles._no_escalation`; user
 * decision 2026-10-08): nobody grants a role, manages an account, or creates, edits or deletes a role unless
 * they hold every permission involved; a privileged role (Administrator, or any role holding setup.roles)
 * also needs setup.roles. Administrator holds everything and is unaffected. The backend decides; this only
 * disables what would be refused and names what is missing.
 */
export const GRANT_GUARD = "setup.roles";

export interface RoleLike {
  code?: string | null;
  /** known to people who can list roles (setup.roles); otherwise only the seeded code is known */
  permissions?: readonly string[] | null;
}

export function isPrivilegedRole(role: RoleLike | null | undefined): boolean {
  if (!role) return false;
  return role.code === "ADMIN" || !!role.permissions?.includes(GRANT_GUARD);
}

/** Names in `need` that `perms` does not hold, sorted (the backend lists them in the same order). */
export function missingPermissions(perms: readonly string[] | undefined | null, need: readonly string[] | Iterable<string>): string[] {
  const held = new Set(perms ?? []);
  return [...new Set(need)].filter((p) => !held.has(p)).sort();
}

export interface GrantCheck {
  allowed: boolean;
  missing: string[];
}

/** May `perms` give `role` to someone? Unknown permission sets are only checked for the privileged guard. */
export function roleGrantCheck(perms: readonly string[] | undefined | null, role: RoleLike | null | undefined): GrantCheck {
  if (!role) return { allowed: true, missing: [] };
  const need = [...(role.permissions ?? [])];
  if (isPrivilegedRole(role)) need.push(GRANT_GUARD);
  const missing = missingPermissions(perms, need);
  return { allowed: missing.length === 0, missing };
}

export function canGrantRole(perms: readonly string[] | undefined | null, role: RoleLike | null | undefined): boolean {
  return roleGrantCheck(perms, role).allowed;
}

/** Edit, reset, delete or change the limits of `target` (own account always; `target.role` is the user row's code). */
export function canManageAccount(
  perms: readonly string[] | undefined | null,
  meId: number | undefined,
  target: { id: number; role?: string | null; role_permissions?: readonly string[] | null },
): boolean {
  if (meId !== undefined && target.id === meId) return true;
  return canGrantRole(perms, { code: target.role, permissions: target.role_permissions });
}

/** Role editor: a role whose permissions exceed the editor's own is read-only and cannot be deleted. */
export function roleEditCheck(perms: readonly string[] | undefined | null, role: RoleLike | null | undefined): GrantCheck {
  const missing = missingPermissions(perms, role?.permissions ?? []);
  return { allowed: missing.length === 0, missing };
}

/* --------------------------------------------------------------------------------- admin sections */

export type AdminSectionId =
  | "users"
  | "roles"
  | "departments"
  | "rooms"
  | "access"
  | "sessions"
  | "holidays"
  | "schedules"
  | "weeks"
  | "conflicts"
  | "settings"
  | "authentication"
  | "email";

export interface AdminSection {
  id: AdminSectionId;
  href: `/admin/${string}`;
  labelKey: MessageKey;
  descriptionKey: MessageKey;
  permission: readonly PermissionName[];
  /** CRBS setup menu group, for the /admin index */
  group: "people" | "rooms" | "calendar" | "organisation";
}

/** The CRBS setup menu (`Menu_model::setup_menu`), one entry per screen, with the permission that guards it. */
export const ADMIN_SECTIONS: readonly AdminSection[] = [
  { id: "users", href: "/admin/users", labelKey: "crbs.admin.users.title", descriptionKey: "crbs.admin.users.lead", permission: ["setup.users"], group: "people" },
  { id: "roles", href: "/admin/roles", labelKey: "crbs.admin.roles.title", descriptionKey: "crbs.admin.roles.lead", permission: ["setup.roles"], group: "people" },
  { id: "departments", href: "/admin/departments", labelKey: "crbs.admin.departments.title", descriptionKey: "crbs.admin.departments.lead", permission: ["setup.departments"], group: "people" },
  { id: "rooms", href: "/admin/rooms", labelKey: "crbs.admin.rooms.title", descriptionKey: "crbs.admin.rooms.lead", permission: ["setup.rooms", "setup.rooms_acl"], group: "rooms" },
  { id: "access", href: "/admin/access", labelKey: "crbs.admin.access.title", descriptionKey: "crbs.admin.access.lead", permission: ["setup.rooms_acl", "setup.users"], group: "rooms" },
  { id: "sessions", href: "/admin/sessions", labelKey: "crbs.admin.sessions.title", descriptionKey: "crbs.admin.sessions.lead", permission: ["setup.sessions"], group: "calendar" },
  { id: "holidays", href: "/admin/holidays", labelKey: "crbs.admin.holidays.title", descriptionKey: "crbs.admin.holidays.lead", permission: ["setup.sessions"], group: "calendar" },
  { id: "schedules", href: "/admin/schedules", labelKey: "crbs.admin.schedules.title", descriptionKey: "crbs.admin.schedules.lead", permission: ["setup.schedules"], group: "calendar" },
  { id: "weeks", href: "/admin/weeks", labelKey: "crbs.admin.weeks.title", descriptionKey: "crbs.admin.weeks.lead", permission: ["setup.timetable_weeks"], group: "calendar" },
  // planners: bookings the newly published timetable overlaps (GET /bookings/conflicts, planning.view)
  { id: "conflicts", href: "/admin/conflicts", labelKey: "crbs.admin.conflicts.title", descriptionKey: "crbs.admin.conflicts.lead", permission: ["planning.view"], group: "calendar" },
  { id: "settings", href: "/admin/settings", labelKey: "crbs.admin.settings.title", descriptionKey: "crbs.admin.settings.lead", permission: ["setup.settings"], group: "organisation" },
  { id: "authentication", href: "/admin/authentication", labelKey: "crbs.admin.ldap.title", descriptionKey: "crbs.admin.ldap.lead", permission: ["setup.authentication"], group: "organisation" },
  { id: "email", href: "/admin/email", labelKey: "crbs.admin.email.title", descriptionKey: "crbs.admin.email.lead", permission: ["setup.settings"], group: "organisation" },
];

export function adminSectionsFor(perms: readonly string[] | undefined | null): AdminSection[] {
  return ADMIN_SECTIONS.filter((s) => hasPermission(perms, s.permission));
}

/** Route → requirement for the pages this module owns (`null` = any signed-in user). */
export function routeRequirement(pathname: string): PermissionRequirement {
  if (pathname === "/bookings" || pathname.startsWith("/bookings/") || pathname === "/my-bookings") return null;
  if (pathname === "/admin") return SETUP_PERMISSIONS;
  const section = ADMIN_SECTIONS.find((s) => pathname === s.href || pathname.startsWith(`${s.href}/`));
  if (section) return section.permission;
  if (pathname.startsWith("/admin/")) return SETUP_PERMISSIONS;
  return null;
}

export function canAccessRoute(perms: readonly string[] | undefined | null, pathname: string): boolean {
  return hasPermission(perms, routeRequirement(pathname));
}

/* -------------------------------------------------------------------------------------------- hook */

export interface PermissionsState {
  loading: boolean;
  perms: readonly string[] | undefined;
  can: (need: PermissionRequirement) => boolean;
  canAll: (need: readonly string[]) => boolean;
  userId: number | undefined;
  departmentId: number | null | undefined;
}

export function usePermissions(): PermissionsState {
  const me = useCrbsMe();
  const perms = me.data?.permissions;
  return {
    loading: me.isLoading,
    perms,
    can: (need) => hasPermission(perms, need),
    canAll: (need) => hasAllPermissions(perms, need),
    userId: me.data?.id,
    departmentId: me.data?.department_id,
  };
}
