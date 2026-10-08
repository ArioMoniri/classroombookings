import { describe, expect, it } from "vitest";
import {
  ADMIN_SECTIONS,
  adminSectionsFor,
  bookingCapabilities,
  canAccessRoute,
  canGrantRole,
  canManageAccount,
  hasAllPermissions,
  hasAnySetup,
  hasPermission,
  hasPlanning,
  isPrivilegedRole,
  missingPermissions,
  roleEditCheck,
  roleGrantCheck,
  routeRequirement,
} from "./permissions";

/* the seeded Teacher role, verbatim from CRBS data.sql (docs/CRBS_PARITY.md §1) */
const TEACHER = ["room.view", "book_single.create", "book_single.view_other_notes", "book_recur.view_other_notes"];
/* a custom role: a department secretary who manages users and holidays but cannot plan */
const SECRETARY = ["room.view", "book_single.create", "book_recur.create", "setup.users", "setup.sessions", "system.export_bookings"];

describe("hasPermission", () => {
  it("is any-of and treats null as 'any signed-in user'", () => {
    expect(hasPermission(TEACHER, "book_single.create")).toBe(true);
    expect(hasPermission(TEACHER, ["setup.users", "book_single.create"])).toBe(true);
    expect(hasPermission(TEACHER, ["setup.users", "setup.roles"])).toBe(false);
    expect(hasPermission(TEACHER, null)).toBe(true);
    expect(hasPermission(undefined, null)).toBe(true);
    expect(hasPermission([], [])).toBe(true);
  });
  it("denies while permissions are unknown", () => {
    expect(hasPermission(undefined, "room.view")).toBe(false);
    expect(hasPermission(null, ["room.view"])).toBe(false);
  });
  it("hasAll needs every permission", () => {
    expect(hasAllPermissions(SECRETARY, ["setup.users", "setup.sessions"])).toBe(true);
    expect(hasAllPermissions(SECRETARY, ["setup.users", "setup.roles"])).toBe(false);
    expect(hasAllPermissions(undefined, [])).toBe(true);
  });
});

describe("role-level capabilities, without assuming three roles", () => {
  it("a teacher books single slots only and sees no admin or planning screens", () => {
    const caps = bookingCapabilities(TEACHER);
    expect(caps.single).toBe(true);
    expect(caps.recurring).toBe(false);
    expect(caps.setUser.single).toBe(false);
    expect(caps.exportBookings).toBe(false);
    expect(hasAnySetup(TEACHER)).toBe(false);
    expect(hasPlanning(TEACHER)).toBe(false);
    expect(adminSectionsFor(TEACHER)).toEqual([]);
    expect(canAccessRoute(TEACHER, "/bookings")).toBe(true);
    expect(canAccessRoute(TEACHER, "/my-bookings")).toBe(true);
    expect(canAccessRoute(TEACHER, "/admin")).toBe(false);
    expect(canAccessRoute(TEACHER, "/admin/users")).toBe(false);
  });
  it("a custom role sees exactly the sections its permissions guard", () => {
    const ids = adminSectionsFor(SECRETARY).map((s) => s.id);
    expect(ids).toEqual(["users", "access", "sessions", "holidays"]);
    expect(canAccessRoute(SECRETARY, "/admin")).toBe(true);
    expect(canAccessRoute(SECRETARY, "/admin/holidays")).toBe(true);
    expect(canAccessRoute(SECRETARY, "/admin/roles")).toBe(false);
    expect(bookingCapabilities(SECRETARY)).toMatchObject({ recurring: true, exportBookings: true, bypassMaintenance: false });
  });
  it("the administrator holds every section", () => {
    const all = ADMIN_SECTIONS.flatMap((s) => s.permission);
    expect(adminSectionsFor(all)).toHaveLength(ADMIN_SECTIONS.length);
  });
  it("a planner without setup rights reaches only the booking conflicts screen", () => {
    const PLANNER = ["room.view", "book_single.create", "planning.view", "planning.edit"];
    expect(adminSectionsFor(PLANNER).map((s) => s.id)).toEqual(["conflicts"]);
    expect(canAccessRoute(PLANNER, "/admin/conflicts")).toBe(true);
    expect(canAccessRoute(PLANNER, "/admin")).toBe(false);
    expect(canAccessRoute(TEACHER, "/admin/conflicts")).toBe(false);
    expect(canAccessRoute(SECRETARY, "/admin/conflicts")).toBe(false);
  });
  it("unknown admin sub-routes still need some setup permission", () => {
    expect(routeRequirement("/admin/whatever")).not.toBeNull();
    expect(routeRequirement("/admin/rooms/12")).toEqual(["setup.rooms", "setup.rooms_acl"]);
    expect(routeRequirement("/timetable")).toBeNull(); // not this module's route
  });
});

describe("no escalation: grants and role edits need every permission involved", () => {
  const USERS_ONLY = ["setup.users", "room.view", "book_single.create"];
  const ROLES_TOO = ["setup.users", "setup.roles", "room.view", "book_single.create"];
  const teacher = { code: "TEACHER", permissions: ["room.view", "book_single.create"] };
  const planner = { code: "PLANNER", permissions: ["room.view", "book_single.create", "planning.edit", "planning.view"] };
  const custom = { code: null, permissions: ["setup.roles", "setup.users"] };
  it("recognises privileged roles", () => {
    expect(isPrivilegedRole({ code: "ADMIN" })).toBe(true);
    expect(isPrivilegedRole(custom)).toBe(true);
    expect(isPrivilegedRole(teacher)).toBe(false);
    expect(isPrivilegedRole(null)).toBe(false);
  });
  it("a role is grantable only when its permissions are a subset of the granter's, and names what is missing", () => {
    expect(roleGrantCheck(USERS_ONLY, teacher)).toEqual({ allowed: true, missing: [] });
    expect(roleGrantCheck(USERS_ONLY, planner)).toEqual({ allowed: false, missing: ["planning.edit", "planning.view"] });
    expect(roleGrantCheck(USERS_ONLY, custom)).toEqual({ allowed: false, missing: ["setup.roles"] });
    expect(canGrantRole(USERS_ONLY, { code: "ADMIN" })).toBe(false); // seeded code only: the privileged guard
    expect(canGrantRole(ROLES_TOO, custom)).toBe(true);
    expect(missingPermissions(["a"], ["c", "b", "a", "b"])).toEqual(["b", "c"]);
  });
  it("accounts follow their role; one's own account is always manageable", () => {
    expect(canManageAccount(USERS_ONLY, 7, { id: 3, role: "ADMIN" })).toBe(false);
    expect(canManageAccount(USERS_ONLY, 7, { id: 7, role: "ADMIN" })).toBe(true);
    expect(canManageAccount(USERS_ONLY, 7, { id: 4, role: "TEACHER", role_permissions: teacher.permissions })).toBe(true);
    expect(canManageAccount(USERS_ONLY, 7, { id: 5, role: "CUSTOM", role_permissions: planner.permissions })).toBe(false);
  });
  it("the role editor is read-only for roles beyond the editor's own permissions", () => {
    expect(roleEditCheck(ROLES_TOO, teacher).allowed).toBe(true);
    expect(roleEditCheck(ROLES_TOO, planner)).toEqual({ allowed: false, missing: ["planning.edit", "planning.view"] });
    expect(roleEditCheck(ROLES_TOO, null).allowed).toBe(true);
  });
});
