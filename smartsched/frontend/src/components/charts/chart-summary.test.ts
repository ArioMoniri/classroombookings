import { describe, expect, it } from "vitest";
import { translate, type Locale, type MessageKey, type Vars } from "@/lib/i18n";
import { makeChartFormat } from "./chart-format";
import { chartSummary, peakOf, trendSentence } from "./chart-summary";

const tFor = (locale: Locale) => (key: MessageKey, vars?: Vars) => translate(locale, key, vars);

const days = [
  { label: "2026-10-12", value: 300_000 },
  { label: "2026-10-13", value: 410_000 },
  { label: "2026-10-14", value: 82_300 * 4 },
  { label: "2026-10-15", value: 160_000 },
];

describe("chart-summary", () => {
  it("tr: total, peak day and the unfinished day in one plain sentence", () => {
    const f = makeChartFormat("tr");
    const text = chartSummary({
      t: tFor("tr"),
      f,
      points: days,
      period: "30d",
      unit: "token",
      kind: "day",
      peakLabel: f.day,
      partial: true,
    });
    expect(text).toBe("Son 30 günde 1,2 milyon token; en yoğun gün 13 Eki (410 bin). Bugün henüz bitmedi.");
  });

  it("en: the same facts", () => {
    const f = makeChartFormat("en");
    const text = chartSummary({ t: tFor("en"), f, points: days, period: "30d", unit: "tokens", kind: "day", peakLabel: f.day });
    expect(text).toBe("In the last 30 days: 1.2 million tokens; busiest day Oct 13 (410 thousand).");
  });

  it("peak only (no period), with a custom value format, no stray spaces", () => {
    const f = makeChartFormat("tr");
    const text = chartSummary({
      t: tFor("tr"),
      f,
      points: [
        { label: "09:30", value: 0.5 },
        { label: "10:30", value: 0.86 },
        { label: "11:30", value: 0.7 },
      ],
      kind: "slot",
      total: false,
      formatValue: f.pct,
    });
    expect(text).toBe("En yoğun saat 10:30 (%86).");
  });

  it("weekly folding is said out loud", () => {
    const f = makeChartFormat("tr");
    const text = chartSummary({ t: tFor("tr"), f, points: days, period: "30d", kind: "week", weekly: true, peakLabel: f.day });
    expect(text.endsWith("Telefonda haftalık toplam gösteriliyor.")).toBe(true);
  });

  it("empty input gives an empty string (the card shows its empty state instead)", () => {
    expect(chartSummary({ t: tFor("tr"), f: makeChartFormat("tr"), points: [], kind: "day" })).toBe("");
  });

  it("peakOf picks the first maximum", () => {
    expect(peakOf([{ label: "a", value: 2 }, { label: "b", value: 5 }, { label: "c", value: 5 }])?.label).toBe("b");
  });

  it("trend: up, down, flat", () => {
    const f = makeChartFormat("tr");
    expect(trendSentence(tFor("tr"), f, 100, 125)).toBe("Önceki döneme göre %25 artış.");
    expect(trendSentence(tFor("tr"), f, 200, 150)).toBe("Önceki döneme göre %25 azalış.");
    expect(trendSentence(tFor("tr"), f, 100, 100.2)).toBe("Önceki döneme göre değişiklik yok.");
    expect(trendSentence(tFor("en"), makeChartFormat("en"), 100, 125)).toBe("Up 25% on the previous period.");
    expect(trendSentence(tFor("tr"), f, 0, 10)).toBe("");
  });
});
