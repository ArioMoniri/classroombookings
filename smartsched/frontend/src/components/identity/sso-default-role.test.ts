import { describe, expect, it } from "vitest";
import { defaultRoleEligible } from "./sso-settings";

// T-R1-35 (round-1 R1-M-25): the self sign-up role picker offers only roles the server accepts
describe("SSO default role", () => {
  it("refuses administrative and planning-editing roles like the server", () => {
    expect(
      defaultRoleEligible({
        code: "TEACHER",
        permissions: ["room.view", "book_single.create"],
      }),
    ).toBe(true);
    expect(
      defaultRoleEligible({
        code: "VIEWER",
        permissions: ["planning.view", "room.view"],
      }),
    ).toBe(true);
    expect(defaultRoleEligible({ code: "ADMIN", permissions: [] })).toBe(false);
    expect(
      defaultRoleEligible({
        code: "PLANNER",
        permissions: ["planning.view", "planning.edit"],
      }),
    ).toBe(false);
    expect(
      defaultRoleEligible({
        code: null,
        permissions: ["setup.users", "setup.roles", "room.view"],
      }),
    ).toBe(false);
    expect(
      defaultRoleEligible({
        code: null,
        permissions: ["planning.admin"],
      }),
    ).toBe(false);
  });
});
