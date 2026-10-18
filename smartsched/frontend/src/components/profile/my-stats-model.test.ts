import { describe, expect, it } from "vitest";
import { translate, type MessageKey, type Vars } from "@/lib/i18n";
import { loadRows, myTiles, quotaSentence, timetableDayHref } from "./my-stats-model";

const t = (k: MessageKey, v?: Vars) => translate("tr", k, v);

describe("CH-11 my statistics (tiles + quota)", () => {
  it("three tiles: active, this term, open requests", () => {
    const tiles = myTiles({ totals: { active: 3, session: 12, all: 40 } }, 2);
    expect(tiles).toEqual([
      { key: "active", value: 3 },
      { key: "term", value: 12 },
      { key: "open", value: 2 },
    ]);
  });

  it("quota: used out of the limit (periods when the server counts them); nothing without a limit", () => {
    expect(quotaSentence({ totals: { active: 3, session: 0, all: 0 }, limits: { max_active_bookings: 5 } }, t)).toBe("3 / 5 aktif rezervasyon hakkı kullanıldı");
    expect(quotaSentence({ totals: { active: 2, active_periods: 4, session: 0, all: 0 }, limits: { max_active_bookings: 5 } }, t)).toBe("4 / 5 aktif rezervasyon hakkı kullanıldı");
    expect(quotaSentence({ totals: { active: 3, session: 0, all: 0 }, limits: { max_active_bookings: null } }, t)).toBeNull();
  });
});

describe("CH-11 weekly teaching load (academician)", () => {
  it("Monday to Friday always, the weekend only when it has classes; 0 reads 'ders yok'", () => {
    const rows = loadRows({ days: [{ day: 1, periods: 4, minutes: 200 }, { day: 3, periods: 6, minutes: 300 }, { day: 6, periods: 2, minutes: 100 }] }, "tr", t);
    expect(rows.map((r) => r.day)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(rows.map((r) => r.label)).toEqual(["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"]);
    expect(rows.map((r) => r.display)).toEqual(["4 ders saati", "ders yok", "6 ders saati", "ders yok", "ders yok", "2 ders saati"]);
  });

  it("each row links to that day of the timetable for the linked instructor", () => {
    expect(timetableDayHref(3, 41, 12)).toBe("/timetable?lens=day&day=3&subject=instructor%3A41&run=12");
    expect(timetableDayHref(1, 41, null)).toBe("/timetable?lens=day&day=1&subject=instructor%3A41");
  });
});
