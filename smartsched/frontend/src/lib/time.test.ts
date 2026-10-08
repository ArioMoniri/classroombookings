import { describe, expect, it } from "vitest";
import {
  PERIODS,
  dateForWeekDay,
  dayName,
  parseClock,
  periodEndingAt,
  periodRangeLabel,
  rangesOverlap,
  snapToPeriod,
  spanLength,
} from "./time";

describe("time grid", () => {
  it("defines 18 periods starting 08:30 and ending 22:50", () => {
    expect(PERIODS).toHaveLength(18);
    expect(PERIODS[0]).toEqual({ index: 1, start: "08:30", end: "09:10" });
    expect(PERIODS[11]).toEqual({ index: 12, start: "17:30", end: "18:00" });
    expect(PERIODS[17]).toEqual({ index: 18, start: "22:10", end: "22:50" });
  });

  it("parses dotted and colon clocks", () => {
    expect(parseClock("09.00")).toBe(540);
    expect(parseClock("13:30")).toBe(810);
    expect(parseClock(" 8:30 ")).toBe(510);
    expect(parseClock("Pazartesi")).toBeNull();
    expect(parseClock("25:00")).toBeNull();
  });

  it("snaps near-grid times with an exact flag", () => {
    expect(snapToPeriod("13:30")).toEqual({ index: 7, exact: true });
    expect(snapToPeriod("09:00")).toEqual({ index: 2, exact: false });
    expect(snapToPeriod("x")).toBeNull();
  });

  it("maps 13:30–16:00 to P7–P9 (DATA_ANALYSIS example)", () => {
    expect(snapToPeriod("13:30")?.index).toBe(7);
    expect(periodEndingAt("16:00")).toBe(9);
    expect(periodRangeLabel(7, 9)).toBe("13:30–15:50");
  });

  it("computes spans and overlaps", () => {
    expect(spanLength(3, 6)).toBe(4);
    expect(spanLength(6, 3)).toBe(0);
    expect(rangesOverlap(1, 3, 3, 5)).toBe(true);
    expect(rangesOverlap(1, 3, 4, 5)).toBe(false);
  });

  it("localises weekday names and derives dates", () => {
    expect(dayName(1, "en", "long")).toBe("Monday");
    expect(dayName(1, "tr", "long")).toBe("Pazartesi");
    expect(dateForWeekDay("2026-02-09", 3)).toBe("2026-02-11");
  });
});

describe("formatDate", () => {
  it("formats ISO dates in Turkish and tolerates weeks without a date (real Bahar 'Yaz Dönemi' sheet)", async () => {
    const { formatDate } = await import("./time");
    expect(formatDate("2026-02-16", "tr")).toBe("16 Şub");
    expect(formatDate("", "tr")).toBe("—");
    expect(formatDate(null, "en")).toBe("—");
  });
});
