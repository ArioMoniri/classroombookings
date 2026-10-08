import { describe, expect, it } from "vitest";
import { translate } from "@/lib/i18n";

// recording bug: "for 1 weeks" in the scope sentence. Counts go in as numbers; the messages pick the
// plural form with the language's CLDR rules and format the number (#) for the locale.
describe("studio plurals", () => {
  it("scope sentence: singular and plural in English", () => {
    expect(translate("en", "studio.scope.sentence", { n: 1, rooms: 1, weeks: 1 })).toBe("You are planning 1 class in 1 room for 1 week.");
    expect(translate("en", "studio.scope.sentence", { n: 1234, rooms: 61, weeks: 14 })).toBe("You are planning 1,234 classes in 61 rooms for 14 weeks.");
  });

  it("scope sentence in Turkish keeps the singular noun after a number and formats it", () => {
    expect(translate("tr", "studio.scope.sentence", { n: 1, rooms: 1, weeks: 1 })).toBe("1 hafta boyunca 1 derslikte 1 ders planlıyorsunuz.");
    expect(translate("tr", "studio.scope.sentence", { n: 1234, rooms: 61, weeks: 14 })).toBe("14 hafta boyunca 61 derslikte 1.234 ders planlıyorsunuz.");
  });

  it("second scope line and step status", () => {
    expect(translate("en", "studio.scope.line2", { out: "0", pinned: "2", holidays: 1 })).toBe("0 left out · 2 pinned · 1 week is a holiday");
    expect(translate("en", "studio.scope.line2", { out: "0", pinned: "2", holidays: 0 })).toBe("0 left out · 2 pinned · no holiday weeks");
    expect(translate("en", "studio.scope.line2", { out: "0", pinned: "2", holidays: 2 })).toBe("0 left out · 2 pinned · 2 weeks are holidays");
    expect(translate("tr", "studio.scope.line2", { out: "0", pinned: "2", holidays: 1 })).toBe("0 plan dışı · 2 sabit · 1 hafta tatil");
    expect(translate("en", "studio.stepStatus.weeks", { from: 3, to: 3, n: 1 })).toBe("W3 · 1 week");
    expect(translate("en", "studio.stepStatus.weeks", { from: 3, to: 6, n: 4 })).toBe("W3–6 · 4 weeks");
    expect(translate("tr", "studio.stepStatus.weeks", { from: 3, to: 3, n: 1 })).toBe("H3 · 1 hafta");
    expect(translate("en", "studio.stepStatus.term", { n: 1 })).toBe("Whole term · 1 week");
  });

  it("what-will-happen sentences", () => {
    expect(translate("en", "studio.summary.h.pinned", { n: 1 })).toBe("1 class is pinned and won't move.");
    expect(translate("en", "studio.summary.h.pinned", { n: 3 })).toBe("3 classes are pinned and won't move.");
    expect(translate("en", "studio.summary.h.out", { n: 1 })).toBe("1 is left out.");
    expect(translate("en", "studio.summary.h.rules", { must: 1, try: 2 })).toBe("It must follow 1 rule and will try to follow 2 preferences.");
    expect(translate("tr", "studio.summary.h.pinned", { n: 1 })).toBe("1 ders sabitlendi, yeri değişmeyecek.");
  });
});
