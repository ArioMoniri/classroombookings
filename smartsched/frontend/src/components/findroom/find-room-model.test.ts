import { describe, expect, it } from "vitest";
import type { Grid } from "@/lib/api/crbs";
import { asRequestable, buildQuery, compactWeeks, emptyForm, formFromRecent, normaliseClock, parseWeeks, reserveSpan, slotsFor } from "./find-room-model";

describe("find a room form", () => {
  it("reads clock times the way planners type them", () => {
    expect(normaliseClock("10.10")).toBe("10:10");
    expect(normaliseClock("9:05")).toBe("09:05");
    expect(normaliseClock(" 1230 ")).toBe("12:30");
    expect(normaliseClock("25:00")).toBeNull();
  });
  it("weeks: ranges and lists", () => {
    expect(parseWeeks("3-5, 7")).toEqual([3, 4, 5, 7]);
    expect(parseWeeks("x")).toBeNull();
    expect(compactWeeks([7, 3, 4, 5])).toBe("3-5, 7");
  });
  it("Wednesday 10:10–12:30 for 90 people", () => {
    const f = { ...emptyForm("2026-02-18"), headcount: "90" };
    const out = buildQuery(f, 3);
    expect("query" in out && out.query).toMatchObject({ term_id: 3, date: "2026-02-18", start: "10:10", end: "12:30", headcount: 90, include_busy: false });
    expect(buildQuery({ ...f, end: "09:00" }, 3)).toEqual({ error: "order" });
  });
  it("a recent search goes back into the form", () => {
    const f = formFromRecent({ weekday: 3, weeks: [3, 4, 5], start: 3, end: 5, headcount: 40, text: "projeksiyon" }, emptyForm("2026-02-16"));
    expect(f).toMatchObject({ when: "weekday", weekday: 3, weeks: "3-5", time: "periods", startPeriod: 3, endPeriod: 5, headcount: "40", text: "projeksiyon" });
  });
});

const grid = {
  periods: [
    { id: 1, name: "1", time_start: "08:30", time_end: "09:20", start_period: 1, end_period: 1 },
    { id: 2, name: "2", time_start: "09:30", time_end: "10:20", start_period: 2, end_period: 2 },
  ],
  slots: [
    { date: "2026-02-18", period_id: 1, room_id: 5, status: "unavailable", reason: "permissions" },
    { date: "2026-02-18", period_id: 2, room_id: 5, status: "available", allow_single: true },
  ],
} as unknown as Grid;

describe("reserve target", () => {
  it("opens request-only periods for the sheet", () => {
    const g = asRequestable(grid, 5, "2026-02-18", 1, 2);
    expect(reserveSpan(slotsFor(g, 5, "2026-02-18", 1, 2))?.map((s) => s.period_id)).toEqual([1, 2]);
    expect(reserveSpan(slotsFor(grid, 5, "2026-02-18", 1, 2))?.map((s) => s.period_id)).toEqual([2]);
  });
});
