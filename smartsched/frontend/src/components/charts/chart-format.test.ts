import { describe, expect, it } from "vitest";
import { CHART_TIME_ZONE, makeChartFormat } from "./chart-format";

describe("chart-format (tr-TR Intl, Europe/Istanbul)", () => {
  const tr = makeChartFormat("tr");
  const en = makeChartFormat("en");

  it("formats numbers, percentages and compact values the Turkish way", () => {
    expect(tr.num(82300)).toBe("82.300");
    expect(tr.num(82.25)).toBe("82,3");
    expect(tr.pct(0.86)).toBe("%86");
    expect(tr.compact(82300)).toBe("82\u00a0B");
    expect(tr.compact(1_200_000)).toBe("1,2\u00a0Mn");
    expect(tr.compactLong(1_200_000)).toBe("1,2 milyon");
    expect(tr.compactLong(82300)).toBe("82 bin");
  });

  it("formats the same values in English", () => {
    expect(en.num(82300)).toBe("82,300");
    expect(en.pct(0.86)).toBe("86%");
    expect(en.compact(1_200_000)).toBe("1.2M");
  });

  it("reads an ISO day as that calendar day in Istanbul", () => {
    expect(CHART_TIME_ZONE).toBe("Europe/Istanbul");
    expect(tr.day("2026-10-14")).toBe("14 Eki");
    expect(tr.dayLong("2026-10-14")).toBe("14 Ekim Çarşamba");
    expect(tr.weekday("2026-10-14")).toBe("Çar");
    expect(en.dayLong("2026-10-14")).toBe("Wednesday, October 14");
    // 23:30 UTC on the 13th is already the 14th in Istanbul (UTC+3)
    expect(tr.isoDay(new Date("2026-10-13T23:30:00Z"))).toBe("2026-10-14");
  });

  it("prints 24-hour times in both languages", () => {
    const d = new Date("2026-10-17T16:42:00Z");
    expect(tr.time(d)).toBe("19:42");
    expect(en.time(d)).toBe("19:42");
  });

  it("says how long ago, relative to now", () => {
    const now = new Date("2026-10-17T18:00:00Z");
    expect(tr.ago(new Date("2026-10-17T16:00:00Z"), now)).toBe("2 saat önce");
    expect(en.ago(new Date("2026-10-17T17:55:00Z"), now)).toBe("5 minutes ago");
  });
});
