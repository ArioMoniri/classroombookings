import { describe, expect, it } from "vitest";
import type { UserIdentityStatus } from "@/lib/api/identity";
import { breakGlassMissing, cleanInviteEmail, identityCounts, invitesByUser, matchesIdentity, methodView, selfSignupRecent, statusView } from "./users-admin-identity-model";

const NOW = Date.parse("2026-10-16T10:00:00Z");
const s = (over: Partial<UserIdentityStatus> = {}): UserIdentityStatus => ({ status: "none", auth_methods: ["local"], invite: null, binding_pending: false, self_signup_at: null, break_glass: false, instructor_id: null, ...over });
const inv = (kind: string, expires: string) => ({ id: 1, kind, expires_at: expires, invited_by: 9 });

describe("statusView (sign-in.md §13 Durum)", () => {
  it("active, invited with days left, binding, expired, disabled", () => {
    expect(statusView(s({ status: "linked", auth_methods: ["microsoft"] }), true, NOW)).toMatchObject({ tone: "feasible", word: "active" });
    expect(statusView(s({ status: "invited", invite: inv("invite", "2026-11-12T09:00:00Z") }), true, NOW)).toMatchObject({ tone: "pending", word: "invited", daysLeft: 27 });
    expect(statusView(s({ status: "binding", invite: inv("bind", "2026-10-20T10:00:00Z") }), true, NOW)).toMatchObject({ tone: "pending", word: "binding", daysLeft: 4 });
    expect(statusView(s({ status: "invite_expired", invite: inv("invite", "2026-10-02T10:00:00Z") }), true, NOW)).toMatchObject({ tone: "warning", word: "inviteExpired", expiredAt: "2026-10-02T10:00:00Z" });
    expect(statusView(s({ status: "linked" }), false, NOW)).toMatchObject({ tone: "neutral", word: "disabled" });
    expect(statusView(undefined, true, NOW).word).toBe("active");
  });
});

describe("methodView (Giriş yöntemi)", () => {
  it.each([
    [s({ status: "linked", auth_methods: ["microsoft"] }), "microsoft"],
    [s({ status: "invited", auth_methods: [], invite: inv("invite", "2026-11-01T00:00:00Z") }), "microsoftInvite"],
    [s({ status: "binding", invite: inv("bind", "2026-11-01T00:00:00Z") }), "binding"],
    [s({ auth_methods: ["ldap"] }), "ldap"],
    [s(), "local"],
  ] as const)("%#", (st, want) => expect(methodView(st)).toBe(want));
});

describe("filters and counts", () => {
  const map = {
    "1": s({ status: "invited", invite: inv("invite", "2026-11-12T09:00:00Z") }),
    "2": s({ status: "linked", auth_methods: ["microsoft"], self_signup_at: "2026-10-14T08:00:00Z" }),
    "3": s({ status: "linked", auth_methods: ["microsoft"], self_signup_at: "2026-09-01T08:00:00Z" }),
    "4": s({ break_glass: true }),
  };
  it("counts pending invites and self sign-ups of the last 7 days", () => {
    expect(identityCounts(map, NOW)).toEqual({ invited: 1, selfRecent: 1 });
    expect(selfSignupRecent(map["3"], NOW)).toBe(false);
  });
  it("chip and method filters", () => {
    expect(matchesIdentity(map["1"], "invited", "", "local", NOW)).toBe(true);
    expect(matchesIdentity(map["2"], "invited", "", "local", NOW)).toBe(false);
    expect(matchesIdentity(map["2"], "self", "", "local", NOW)).toBe(true);
    expect(matchesIdentity(map["4"], "all", "microsoft", "local", NOW)).toBe(false);
    expect(matchesIdentity(map["4"], "all", "local", "local", NOW)).toBe(true);
  });
});

describe("breakGlassMissing", () => {
  const on = { microsoft: { enabled: true }, local_enabled: false };
  it("warns only when Microsoft is on, password sign-in is off and no break-glass admin exists", () => {
    expect(breakGlassMissing(on, { "1": s() })).toBe(true);
    expect(breakGlassMissing(on, { "1": s({ break_glass: true }) })).toBe(false);
    expect(breakGlassMissing({ ...on, local_enabled: true }, { "1": s() })).toBe(false);
    expect(breakGlassMissing({ microsoft: { enabled: false }, local_enabled: false }, { "1": s() })).toBe(false);
  });
});

describe("invite helpers", () => {
  it("keeps the newest invite per user", () => {
    const m = invitesByUser([
      { id: 1, user_id: 5, email: "a@b.c", kind: "invite", status: "invited", created_at: "", expires_at: "", link: null },
      { id: 3, user_id: 5, email: "a@b.c", kind: "invite", status: "invited", created_at: "", expires_at: "", link: "x" },
    ]);
    expect(m.get(5)?.id).toBe(3);
  });
  it("lower-cases, validates and flags another domain without blocking", () => {
    expect(cleanInviteEmail("  Ayse.Yilmaz@ORNEK.edu.tr ", "ornek.edu.tr")).toEqual({ email: "ayse.yilmaz@ornek.edu.tr", valid: true, domainMismatch: false });
    expect(cleanInviteEmail("ayse@gmail.com", "ornek.edu.tr").domainMismatch).toBe(true);
    expect(cleanInviteEmail("ayse@mf.ornek.edu.tr", "@ornek.edu.tr").domainMismatch).toBe(false);
    expect(cleanInviteEmail("not-an-address", "ornek.edu.tr").valid).toBe(false);
  });
});
