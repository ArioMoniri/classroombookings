import { describe, expect, it } from "vitest";
import { translate, type MessageKey } from "@/lib/i18n";
import { isTintOnlyRoute } from "./blur-budget";
import { breadcrumbs } from "./breadcrumbs";

const tr = (key: MessageKey) => translate("tr", key);
const en = (key: MessageKey) => translate("en", key);
const labels = (path: string, t: (key: MessageKey) => string) => breadcrumbs(path, t).map((c) => c.label);

describe("breadcrumbs", () => {
  it("localises /admin/* with the admin navigation labels", () => {
    expect(labels("/admin/conflicts", tr)).toEqual(["Kurulum", "Rezervasyon çakışmaları"]);
    expect(labels("/admin/conflicts", en)).toEqual(["Setup", "Booking conflicts"]);
    expect(labels("/admin/authentication", en)).toEqual(["Setup", "Sign-in (LDAP)"]);
    expect(labels("/admin/weeks", tr)).toEqual(["Kurulum", "Ders haftaları"]);
  });

  it("tells /rooms (planning) from /admin/rooms (room setup) by the full path", () => {
    expect(labels("/rooms", en)).toEqual([translate("en", "nav.rooms")]);
    expect(labels("/admin/rooms", en)).toEqual(["Setup", translate("en", "crbs.admin.rooms.title")]);
  });

  it("labels the CRBS pages and the planning pages, ids as #n", () => {
    expect(labels("/my-bookings", tr)).toEqual(["Rezervasyonlarım"]);
    expect(labels("/profile", en)).toEqual(["Profile"]);
    expect(labels("/runs/12", en)).toEqual([translate("en", "nav.runs"), "#12"]);
    expect(labels("/classes", tr)).toEqual([translate("tr", "glass.shell.classes")]);
  });

  it("marks only the last crumb current and links every level", () => {
    const crumbs = breadcrumbs("/admin/users", en);
    expect(crumbs.map((c) => [c.href, c.current])).toEqual([
      ["/admin", false],
      ["/admin/users", true],
    ]);
  });
});

describe("tint-only shell chrome", () => {
  it("applies on the calendar and the all-classes page only", () => {
    expect(isTintOnlyRoute("/timetable")).toBe(true);
    expect(isTintOnlyRoute("/classes")).toBe(true);
    expect(isTintOnlyRoute("/classes/exams")).toBe(true);
    expect(isTintOnlyRoute("/timetables")).toBe(false);
    expect(isTintOnlyRoute("/dashboard")).toBe(false);
    expect(isTintOnlyRoute("/admin/rooms")).toBe(false);
    expect(isTintOnlyRoute(null)).toBe(false);
  });
});
