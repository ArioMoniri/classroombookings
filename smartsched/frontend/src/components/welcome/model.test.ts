/** WG-04 / WG-05 / WG-06 rules: cards per audience (max 5, "Ayrıca"), steps (≤ 5), checklist (server wins, ≤ 5 visible), copy helpers. */
import { describe, expect, it } from "vitest";
import { isExcludedRoute } from "./content";
import { badPlaceholders, buildChecklist, buildSheet, buildSteps, fillPlaceholders, firstNameOf, MAX_STEPS } from "./model";
import { makeState } from "./test-helpers";

describe("buildSheet", () => {
  it("academician: the four academician cards, no 'Ayrıca'", () => {
    const m = buildSheet(makeState())!;
    expect(m.primary).toBe("academician");
    expect(m.cards.map((c) => c.key)).toEqual(["quick_reserve", "my_requests", "my_bookings", "calendar"]);
    expect(m.cards.some((c) => c.also)).toBe(false);
  });

  it("staff who approves: 4 staff cards + the approver 'Ayrıca' card = 5", () => {
    const m = buildSheet(makeState({ audiences: ["staff", "approver"], primary: null }))!;
    expect(m.primary).toBe("staff");
    expect(m.cards).toHaveLength(5);
    expect(m.cards.filter((c) => c.also).map((c) => c.key)).toEqual(["approvals"]);
  });

  it("precedence picks admin over planner; never more than 5 cards with several secondaries", () => {
    const m = buildSheet(makeState({ audiences: ["staff", "planner", "admin", "approver", "dept_admin"], primary: null }))!;
    expect(m.primary).toBe("admin");
    expect(m.cards.length).toBeLessThanOrEqual(5);
    expect(m.cards.filter((c) => !c.also).length).toBeGreaterThanOrEqual(1);
  });

  it("delta: only the new audience's cards", () => {
    const m = buildSheet(makeState({ audiences: ["staff", "approver"], primary: "staff", show: { kind: "delta", audiences: ["approver"] } }))!;
    expect(m.kind).toBe("delta");
    expect(m.cards.map((c) => `${c.audience}:${c.key}`)).toEqual(["approver:approvals"]);
  });

  it("server cards win and carry the admin's overrides", () => {
    const m = buildSheet(makeState({ sheet: { cards: [{ key: "my_bookings", overrides: { title: "Benim salonlarım" } }], updated: true } }))!;
    expect(m.cards).toHaveLength(1);
    expect(m.cards[0]!.overrides.title).toBe("Benim salonlarım");
    expect(m.updated).toBe(true);
  });

  it("no known audience: no sheet", () => {
    expect(buildSheet(makeState({ audiences: ["kiosk"], primary: null }))).toBeNull();
  });
});

describe("buildSteps", () => {
  it("academician: the five spec steps, reserve-when is interactive on /reserve", () => {
    const s = buildSteps(makeState());
    expect(s.map((x) => x.anchor)).toEqual(["nav-reserve", "reserve-when", "nav-my-bookings", "nav-my-requests", "user-menu"]);
    expect(s[1]).toMatchObject({ route: "/reserve", interactive: true });
  });

  it("the approver's steps appear after the grant and the tour stays at 5 or fewer", () => {
    const s = buildSteps(makeState({ audiences: ["staff", "approver"], primary: "staff" }));
    expect(s.length).toBeLessThanOrEqual(MAX_STEPS);
    expect(s.map((x) => x.anchor)).toEqual(expect.arrayContaining(["nav-approvals", "approvals-row-actions"]));
  });

  it("every audience's tour has 5 steps or fewer", () => {
    for (const a of ["academician", "staff", "approver", "dept_admin", "viewer", "planner", "admin"]) {
      expect(buildSteps(makeState({ audiences: [a], primary: a })).length).toBeLessThanOrEqual(5);
    }
  });
});

describe("buildChecklist", () => {
  it("the server's done wins, counts and the next item", () => {
    const m = buildChecklist(makeState({ checklist: { items: [{ key: "profile", done: true }, { key: "first_booking", done: false }, { key: "requests_seen", done: false, manual: true }], hidden: false } }))!;
    expect(m.done).toBe(1);
    expect(m.total).toBe(3);
    expect(m.next?.key).toBe("first_booking");
    expect(m.items.find((i) => i.key === "requests_seen")?.manual).toBe(true);
    expect(m.items.find((i) => i.key === "first_booking")?.href).toBe("/reserve");
  });

  it("at most 5 rows are visible, open items first", () => {
    const items = ["org_ready", "rooms_added", "users_invited", "mail_ready", "welcome_reviewed", "first_decision"].map((key, i) => ({ key, done: i === 0 }));
    const m = buildChecklist(makeState({ audiences: ["admin", "approver"], primary: "admin", checklist: { items, hidden: false } }))!;
    expect(m.total).toBe(6);
    expect(m.visible).toHaveLength(5);
    expect(m.visible.every((i) => !i.done)).toBe(true);
  });

  it("falls back to the catalog when the server sends no items", () => {
    const m = buildChecklist(makeState())!;
    expect(m.items.map((i) => i.key)).toEqual(["profile", "first_booking", "channel", "calendar", "requests_seen"]);
  });
});

describe("copy helpers", () => {
  it("fills {ad} / {name} and {bölüm} / {department}", () => {
    expect(fillPlaceholders("Merhaba {ad}, {bölüm}", { name: "Ayşe", department: "Psikoloji" })).toBe("Merhaba Ayşe, Psikoloji");
    expect(fillPlaceholders("Hi {name} ({department})", { name: "Ayşe", department: "Psychology" })).toBe("Hi Ayşe (Psychology)");
  });
  it("rejects other placeholders", () => {
    expect(badPlaceholders("Merhaba {ad} {soyad}")).toEqual(["soyad"]);
    expect(badPlaceholders("{bölüm} · {department}")).toEqual([]);
  });
  it("first name skips titles and initials", () => {
    expect(firstNameOf(undefined, "Dr. A. Tekin")).toBe("Tekin");
    expect(firstNameOf(undefined, "Doç. Dr. Ayşe Tekin")).toBe("Ayşe");
    expect(firstNameOf(makeState({ first_name: "Fatih" }), "x")).toBe("Fatih");
  });
  it("excluded routes never call the API", () => {
    for (const p of ["/setup", "/login", "/welcome", "/reset-password", "/public/rooms/1"]) expect(isExcludedRoute(p, null)).toBe(true);
    expect(isExcludedRoute("/bookings", new URLSearchParams("kiosk=1"))).toBe(true);
    expect(isExcludedRoute("/bookings", new URLSearchParams("embed=1"))).toBe(true);
    expect(isExcludedRoute("/reserve", new URLSearchParams())).toBe(false);
  });
});
