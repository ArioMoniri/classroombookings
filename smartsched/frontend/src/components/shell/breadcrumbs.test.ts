import { describe, expect, it } from "vitest";
import { translate, type MessageKey } from "@/lib/i18n";
import { isTintOnlyRoute } from "./blur-budget";
import { breadcrumbs } from "./breadcrumbs";

const tr = (key: MessageKey, vars?: Record<string, string | number>) => translate("tr", key, vars);
const en = (key: MessageKey, vars?: Record<string, string | number>) => translate("en", key, vars);
const labels = (path: string, t: (key: MessageKey) => string) => breadcrumbs(path, t).map((c) => c.label);

describe("breadcrumbs", () => {
  it("localises /admin/* with the admin navigation labels", () => {
    expect(labels("/admin/conflicts", tr)).toEqual(["Kurulum", "Rezervasyon çakışmaları"]);
    expect(labels("/admin/conflicts", en)).toEqual(["Setup", "Booking conflicts"]);
    expect(labels("/admin/authentication", en)).toEqual(["Setup", "Sign-in (LDAP)"]);
    expect(labels("/admin/weeks", tr)).toEqual(["Kurulum", "Ders haftaları"]);
  });

  it("names the wave-2 conflict resolver under the bookings; the run id folds into it (no raw '#3', T-R1-08)", () => {
    expect(labels("/bookings/conflicts/3", tr)).toEqual(["Rezervasyonlar", "Rezervasyon çakışmalarını çöz"]);
    const crumbs = breadcrumbs("/bookings/conflicts/3", tr);
    expect(crumbs.at(-1)).toEqual({ href: "/bookings/conflicts/3", label: "Rezervasyon çakışmalarını çöz", current: true });
  });

    it("tells /rooms (planning) from /admin/rooms (room setup) by the full path", () => {
    expect(labels("/rooms", en)).toEqual([translate("en", "nav.rooms")]);
    expect(labels("/admin/rooms", en)).toEqual(["Setup", translate("en", "crbs.admin.rooms.title")]);
  });

  it("labels the CRBS pages and the planning pages; a run reads like its page title ('Çalıştırma #12', never a bare id)", () => {
    expect(labels("/my-bookings", tr)).toEqual(["Rezervasyonlarım"]);
    expect(labels("/profile", en)).toEqual(["Profile"]);
    expect(labels("/runs/12", en)).toEqual([translate("en", "nav.runs"), "Run #12"]);
    expect(labels("/runs/12", tr)).toEqual([translate("tr", "nav.runs"), "Çalıştırma #12"]);
    expect(labels("/rooms/7", tr)).toEqual([translate("tr", "nav.rooms"), "Derslik"]);
    expect(labels("/classes", tr)).toEqual([translate("tr", "glass.shell.classes")]);
  });

  describe("moderation sub-pages never print a route word or an internal id (T-R1-08, R1-A-11)", () => {
    it("another person: Moderasyon / Kişiler / Kişi", () => {
      expect(labels("/moderation/people/157", tr)).toEqual(["Moderasyon", "Kişiler", "Kişi"]);
      expect(labels("/moderation/people/157", en)).toEqual(["Moderation", "People", "Person"]);
      for (const c of breadcrumbs("/moderation/people/157", tr)) expect(c.label).not.toMatch(/people|#/);
    });
    it("the academician's own id: Taleplerim / Geçmişim, linking back to /moderation/me", () => {
      const crumbs = breadcrumbs("/moderation/people/157", tr, { ownPersonId: 157 });
      expect(crumbs).toEqual([
        { href: "/moderation/me", label: "Taleplerim", current: false },
        { href: "/moderation/people/157", label: "Geçmişim", current: true },
      ]);
      // another person's page stays the console trail even for a linked academician
      expect(labels("/moderation/people/158", tr)).toEqual(["Moderasyon", "Kişiler", "Kişi"]);
    });
    it("the re-solve preview: Moderasyon / Yeniden çözüm önizlemesi, the run id folded in", () => {
      expect(labels("/moderation/recreate/15", tr)).toEqual(["Moderasyon", "Yeniden çözüm önizlemesi"]);
      expect(breadcrumbs("/moderation/recreate/15", en).at(-1)).toMatchObject({ href: "/moderation/recreate/15", current: true, label: "Re-solve preview" });
      for (const c of breadcrumbs("/moderation/recreate/15", tr)) expect(c.label).not.toMatch(/recreate|#/);
    });
    it("Taleplerim and the learning memory read like their titles; a wizard draft folds into 'Yeni program'", () => {
      expect(labels("/moderation/me", tr)).toEqual(["Moderasyon", "Taleplerim"]);
      expect(labels("/moderation/learning", tr)).toEqual(["Moderasyon", translate("tr", "learning.memory.title")]);
      expect(labels("/programs/new/0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b", tr)).toEqual([translate("tr", "programWizard.nav")]);
    });
    it("an unlabelled route word folds into its parent; a 404 path with no parent is shown as typed", () => {
      expect(labels("/admin/unknown-thing", tr)).toEqual(["Kurulum"]);
      expect(labels("/yok-boyle-sayfa", tr)).toEqual(["yok-boyle-sayfa"]);
    });
  });

  it("names the analytics, exams and comparison pages and their parents in both languages", () => {
    expect(labels("/analytics/heatmap", tr)).toEqual(["Analiz", "Doluluk ısı haritası"]);
    expect(labels("/analytics/heatmap", en)).toEqual(["Analytics", "Utilisation heatmap"]);
    expect(labels("/analytics", en)).toEqual(["Analytics"]);
    expect(labels("/exams/invigilation", tr)).toEqual(["Sınavlar", "Gözetmen ataması"]);
    expect(labels("/exams/invigilation", en)).toEqual(["Exams", "Invigilator assignment"]);
    expect(labels("/exams", tr)).toEqual(["Sınavlar"]);
    expect(labels("/runs/compare", tr)).toEqual([translate("tr", "nav.runs"), "Senaryo karşılaştırma"]);
    expect(labels("/runs/compare", en)).toEqual([translate("en", "nav.runs"), "Scenario comparison"]);
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
