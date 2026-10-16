import { describe, expect, it } from "vitest";
import { doorsFor, homeFor, normalizeProfileSsoError, normalizeSsoError, parseWelcomeFlag, readSignInParams, retryMinutes, safeNext, safeRef, startUrl, welcomePath } from "./signin-model";

const auth = (over: Partial<{ ms: boolean; local: boolean; self: boolean }> = {}) => ({
  microsoft: { enabled: over.ms ?? true, self_signup: over.self ?? true },
  local_enabled: over.local ?? true,
});

describe("safeNext (sign-in.md §4.2, §15 #19)", () => {
  it.each(["/timetable", "/bookings?week=3", "/admin/users"])("keeps the same-origin path %s", (p) => expect(safeNext(p)).toBe(p));
  it.each(["//evil.example", "https://evil.example/x", "/\\evil", "timetable", "", "/x\u0000y", "/login", "/login?next=/x", "/login/sso?ticket=1"])("drops %j", (p) => expect(safeNext(p)).toBeNull());
  it("drops overlong paths", () => expect(safeNext(`/${"a".repeat(300)}`)).toBeNull());
});

describe("error codes (§6.3, §15 #15/#16)", () => {
  it.each(["tenant", "cancelled", "failed", "unavailable", "signup_closed", "invite_expired", "invite_invalid", "invite_mismatch"])("keeps %s", (c) => expect(normalizeSsoError(c)).toBe(c));
  it("renders unknown codes as failed (no enumeration)", () => {
    expect(normalizeSsoError("nonsense")).toBe("failed");
    expect(normalizeSsoError("disabled")).toBe("failed");
    expect(normalizeSsoError("")).toBeNull();
    expect(normalizeSsoError(null)).toBeNull();
  });
  it("profile codes add already_linked and fold the rest into failed", () => {
    expect(normalizeProfileSsoError("already_linked")).toBe("already_linked");
    expect(normalizeProfileSsoError("invite_mismatch")).toBe("failed");
  });
  it("accepts short support codes only", () => {
    expect(safeRef("7F3A-21C")).toBe("7F3A-21C");
    expect(safeRef("S-123")).toBe("S-123");
    expect(safeRef("<script>")).toBeNull();
    expect(safeRef("x".repeat(40))).toBeNull();
  });
});

describe("readSignInParams", () => {
  it("reads the whole contract from URLSearchParams or a Next searchParams object", () => {
    const sp = new URLSearchParams("next=/timetable&reason=expired&error=invite_mismatch&ref=S-9&invite=tok_123456789&method=local&invited_masked=ay•••@uni.edu.tr&signed_in=ba•••@uni.edu.tr");
    const a = readSignInParams(sp);
    expect(a).toEqual({ next: "/timetable", reason: "expired", error: "invite_mismatch", ref: "S-9", invite: "tok_123456789", methodLocal: true, invitedMasked: "ay•••@uni.edu.tr", signedIn: "ba•••@uni.edu.tr" });
    expect(readSignInParams({ next: ["/a", "/b"], reason: "bogus" })).toMatchObject({ next: "/a", reason: null, error: null, invite: null, methodLocal: false });
  });
});

describe("startUrl (§4.2, §15 #1/#17/#21)", () => {
  it("defaults to the backend start route and carries next, invite, prompt and login_hint", () => {
    expect(startUrl()).toBe("/api/v1/auth/sso/entra/start");
    expect(startUrl({ next: "/timetable" })).toBe("/api/v1/auth/sso/entra/start?next=%2Ftimetable");
    const u = new URL(startUrl({ next: "/x", invite: "t0kenvalue", prompt: "select_account", loginHint: "ayse@uni.edu.tr" }), "http://h");
    expect(u.searchParams.get("invite")).toBe("t0kenvalue");
    expect(u.searchParams.get("prompt")).toBe("select_account");
    expect(u.searchParams.get("login_hint")).toBe("ayse@uni.edu.tr");
  });
  it("never uses an off-site base from the backend", () => {
    expect(startUrl({ base: "https://evil.example/start" })).toBe("/api/v1/auth/sso/entra/start");
    expect(startUrl({ base: "/api/v1/auth/sso/entra/start" })).toBe("/api/v1/auth/sso/entra/start");
  });
});

describe("doorsFor (§4.3, §6.5, §12)", () => {
  const base = { reachable: true, params: { methodLocal: false }, invite: null, lastMethodLocal: false };
  it("Microsoft on: button + closed disclosure, secondary submit", () => {
    expect(doorsFor({ ...base, auth: auth() })).toMatchObject({ microsoft: true, disclosure: true, formOpenInitially: false, formPrimary: false, resetLink: true, selfSignup: true });
  });
  it("Microsoft off: open primary form, no disclosure, no sign-up hint", () => {
    expect(doorsFor({ ...base, auth: auth({ ms: false }) })).toMatchObject({ microsoft: false, disclosure: false, formOpenInitially: true, formPrimary: true, selfSignup: false });
  });
  it("local sign-in hidden for everyone: only ?method=local opens the door (break-glass)", () => {
    expect(doorsFor({ ...base, auth: auth({ local: false }) })).toMatchObject({ disclosure: false, resetLink: false });
    expect(doorsFor({ ...base, auth: auth({ local: false }), params: { methodLocal: true } })).toMatchObject({ disclosure: true, formOpenInitially: true, resetLink: false });
  });
  it("a valid invite hides door 2", () => {
    const invite = { state: "valid" as const, token: "t", inviter: "F", role: "R", masked: "a@b", loginHint: "a@b", daysLeft: 3 };
    expect(doorsFor({ ...base, auth: auth(), invite })).toMatchObject({ microsoft: true, disclosure: false });
  });
  it("remembers the password door", () => {
    expect(doorsFor({ ...base, auth: auth(), lastMethodLocal: true }).formOpenInitially).toBe(true);
  });
  it("self sign-up off drops hint 2", () => {
    expect(doorsFor({ ...base, auth: auth({ self: false }) }).selfSignup).toBe(false);
  });
  it("backend unreachable: door 2 open, no Microsoft, offline", () => {
    expect(doorsFor({ ...base, reachable: false, auth: null })).toMatchObject({ microsoft: false, formOpenInitially: true, formPrimary: true, offline: true });
  });
});

describe("small helpers", () => {
  it("homeFor: planners the dashboard, others bookings", () => {
    expect(homeFor(["planning.view"])).toBe("/dashboard");
    expect(homeFor(["book_single.create"])).toBe("/bookings");
  });
  it("retryMinutes rounds Retry-After seconds up", () => {
    expect(retryMinutes("61")).toBe(2);
    expect(retryMinutes("10")).toBe(1);
    expect(retryMinutes(null)).toBe(5);
  });
  it("welcome flag round trip", () => {
    expect(parseWelcomeFlag(JSON.stringify({ kind: "invited", inviter: "Fatih Demir", next: "//evil" }))).toEqual({ kind: "invited", inviter: "Fatih Demir", next: null });
    expect(parseWelcomeFlag("{bad")).toBeNull();
    expect(parseWelcomeFlag(JSON.stringify({ kind: "admin" }))).toBeNull();
    expect(welcomePath("bound")).toBe("/welcome?bound=1");
  });
});
