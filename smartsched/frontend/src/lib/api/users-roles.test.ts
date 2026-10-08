import { describe, expect, it } from "vitest";
import { responseSchemas } from "./endpoints";
import { User } from "./schemas";

// GET /users on the e2e backend after bookings.spec.ts created its accounts (trimmed): CRBS-parity roles and a
// username-only account. One TEACHER used to fail the whole list, which emptied Settings → Users.
const users = [
  { id: 1, email: "admin@smartsched.local", username: null, full_name: "Administrator", role: "ADMIN", is_active: true },
  { id: 3, email: "e2e.hoca@uni.edu.tr", username: "e2e.hoca", full_name: "Elif Şahin", role: "TEACHER", is_active: true },
  { id: 4, email: "e2e.rolyon@uni.edu.tr", username: "e2e.rolyon", full_name: null, role: "CUSTOM", is_active: true },
  { id: 6, email: null, username: "kutuphane", full_name: "Kütüphane", role: "NONE", is_active: true },
];

describe("users and /auth/me with the backend's roles", () => {
  it("parses every role the backend has (ADMIN, PLANNER, VIEWER, TEACHER, CUSTOM, NONE) and username-only accounts", () => {
    const out = responseSchemas.users.parse(users);
    expect(out.map((u) => u.role)).toEqual(["ADMIN", "TEACHER", "CUSTOM", "NONE"]);
    expect(out[3].email).toBeNull();
  });

  it("parses a teacher's /auth/me", () => {
    expect(User.parse({ id: 3, email: "e2e.hoca@uni.edu.tr", full_name: "Elif Şahin", role: "TEACHER", permissions: ["book_single.create"] }).role).toBe("TEACHER");
  });
});
