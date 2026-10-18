import { describe, expect, it } from "vitest";
import { isoWeekday, lowConfidence, peakHit, Peaks, showRange, type PeakCell } from "./adaptive";

const cell = (day: number, period: number, peak: boolean): PeakCell => ({ day, period, group: "*", value: peak ? 92 : 40, lo80: 30, hi80: 95, n_weeks: 12, rooms: 40, peak });

describe("forecast ranges (AS-21)", () => {
  it("shows a calibrated range, with düşük güven while confidence is low", () => {
    const low = { lo80: 10, hi80: 18, confidence: "low" as const, method: "seasonal_naive" };
    expect(showRange(low)).toBe(true);
    expect(lowConfidence(low)).toBe(true);
    const medium = { ...low, confidence: "medium" as const };
    expect(showRange(medium)).toBe(true);
    expect(lowConfidence(medium)).toBe(false);
  });

  it("never shows a range for computed requests counts or an empty answer", () => {
    expect(showRange({ lo80: 12, hi80: 12, confidence: "high", method: "requests" })).toBe(false);
    expect(showRange({ lo80: 10, hi80: 14, confidence: "high", method: "requests" })).toBe(false);
    expect(lowConfidence({ confidence: "low", method: "requests" })).toBe(false);
    expect(showRange({ lo80: 1, hi80: 3, confidence: "none", method: "none" })).toBe(false);
    expect(showRange({ lo80: null, hi80: null, confidence: "low" })).toBe(false);
  });
});

describe("peak chip", () => {
  const day = [1, 2, 3, 4, 5, 6, 7, 8].map((p) => cell(3, p, p === 4 || p === 5));

  it("marks a Wednesday P4 search and offers the nearest off-peak span of the same day", () => {
    const hit = peakHit(day, 3, 4, 4);
    expect(hit.hits.map((c) => c.period)).toEqual([4]);
    expect(hit.alternative).toEqual({ start: 3, end: 3 });
    expect(peakHit(day, 3, 4, 5).alternative).toEqual({ start: 2, end: 3 });
  });

  it("says nothing off peak or on another day", () => {
    expect(peakHit(day, 3, 2, 2)).toEqual({ hits: [], alternative: null });
    expect(peakHit(day, 1, 4, 4).hits).toEqual([]);
  });

  it("reads ISO weekdays of calendar dates", () => {
    expect(isoWeekday("2026-10-21")).toBe(3);
    expect(isoWeekday("2026-10-25")).toBe(7);
  });
});

describe("Peaks schema", () => {
  it("parses an empty install's answer (none + needs) without throwing", () => {
    const out = Peaks.parse({ term_id: null, term_code: null, cells: [], peaks: [], confidence: "none", needs: { tr: "Yayımlanmış program yok", en: "No published timetable" } });
    expect(out.confidence).toBe("none");
    expect(out.needs?.tr).toMatch(/Yayımlanmış/);
  });
});
