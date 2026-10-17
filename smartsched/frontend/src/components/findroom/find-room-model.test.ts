import { describe, expect, it } from "vitest";
import type { Grid } from "@/lib/api/crbs";
import { altWhyQuery, asRequestable, buildingLabel, buildQuery, compactWeeks, emptyForm, formFromRecent, isFeatureMiss, isoDate, normaliseClock, ownRequestFor, parseWeeks, reserveSpan, slotsFor, whyQuery, wholeSpan } from "./find-room-model";

describe("T-R1-14 find-room results", () => {
  it("folds the near misses that lack the asked feature (find_room.py's 'free; missing:' reason)", () => {
    const near = (en: string) => ({ kind: "near_miss", reason: { tr: "", en } });
    expect(isFeatureMiss(near("A 101 free; missing: Bilgisayar laboratuvarı"))).toBe(true);
    expect(isFeatureMiss(near("B 207 free; 40 seats (5% short)"))).toBe(false);
    expect(isFeatureMiss({ kind: "time", reason: { tr: "", en: "free; missing: x" } })).toBe(false);
  });
  it("finds the own open request behind a 'Talebiniz bekliyor' row", () => {
    const reqs = [
      { id: 5, status: "PENDING", bookings: [{ room_id: 3, date: "2026-11-05", start_period: 6, end_period: 6 }] },
      { id: 6, status: "WITHDRAWN", bookings: [{ room_id: 3, date: "2026-11-05", start_period: 7, end_period: 7 }] },
    ] as never[];
    expect(ownRequestFor(3, ["2026-11-05"], 7, 8, reqs)).toBeNull();
    expect(ownRequestFor(3, ["2026-11-05"], 6, 7, reqs)).toBe(5);
    expect(ownRequestFor(4, ["2026-11-05"], 6, 7, reqs)).toBeNull();
  });
});

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
  it("T-R2-16: the building chip reads 'A Blok' in Turkish and 'Block A' in English, whatever the setup named it", () => {
    const tr = (_k: string, v: { b: string }) => `${v.b} Blok`;
    const en = (_k: string, v: { b: string }) => `Block ${v.b}`;
    expect(buildingLabel("A", tr)).toBe("A Blok");
    expect(buildingLabel("A Blok", tr)).toBe("A Blok");
    expect(buildingLabel("A Blok", en)).toBe("Block A");
    expect(buildingLabel("C", en)).toBe("Block C");
    expect(buildingLabel("Merkez Bina", en)).toBe("Merkez Bina");
  });
  it("T-R2-14: a stale result whose window is no longer free in full is refused, not trimmed", () => {
    const g = asRequestable(grid, 5, "2026-02-18", 1, 2);
    expect(wholeSpan(slotsFor(g, 5, "2026-02-18", 1, 2))?.map((s) => s.period_id)).toEqual([1, 2]);
    // period 1 is not reservable any more (taken meanwhile): no partial P2-only sheet
    expect(wholeSpan(slotsFor(grid, 5, "2026-02-18", 1, 2))).toBeNull();
    expect(wholeSpan([])).toBeNull();
  });
  it("opens request-only periods for the sheet", () => {
    const g = asRequestable(grid, 5, "2026-02-18", 1, 2);
    expect(reserveSpan(slotsFor(g, 5, "2026-02-18", 1, 2))?.map((s) => s.period_id)).toEqual([1, 2]);
    expect(reserveSpan(slotsFor(grid, 5, "2026-02-18", 1, 2))?.map((s) => s.period_id)).toEqual([2]);
  });
  it("GG.AA.YYYY dates (as the backend accepts them) become ISO; impossible dates are refused", () => {
    expect(isoDate("18.02.2026")).toBe("2026-02-18");
    expect(isoDate("5/3/2026")).toBe("2026-03-05");
    expect(isoDate("2026-02-18")).toBe("2026-02-18");
    expect(isoDate("31.02.2026")).toBeNull();
    expect(isoDate("yarın")).toBeNull();
    expect(emptyForm("18.02.2026").date).toBe("2026-02-18");
    const out = buildQuery({ ...emptyForm("2026-02-18"), date: "19.02.2026" }, 3);
    expect("query" in out && out.query.date).toBe("2026-02-19");
    expect(formFromRecent({ date: "20.02.2026", start: "10:10", end: "12:30" }, emptyForm("2026-02-18")).date).toBe("2026-02-20");
  });
  it("'Neden?' asks the verdict with the result's period_id on its free date, the rules only without one", () => {
    const slots = [{ date: "2026-02-18" }, { date: "2026-02-25" }];
    expect(whyQuery({ room_id: 4, per_date: null, period_id: 11 }, slots, 3)).toEqual({ room_id: 4, date: "2026-02-18", period_id: 11, term_id: 3 });
    expect(whyQuery({ room_id: 4, per_date: [{ date: "2026-02-18", status: "busy" }, { date: "2026-02-25", status: "free" }], period_id: 12 }, slots, 3).date).toBe("2026-02-25");
    expect(whyQuery({ room_id: 4, per_date: null, period_id: null }, slots).period_id).toBeNull();
    expect(whyQuery({ room_id: 4, per_date: null, period_id: 9 }, []).period_id).toBeNull();
    expect(altWhyQuery({ room_id: 5, dates: ["2026-02-19"], date: null, period_id: 21 }, 3)).toEqual({ room_id: 5, date: "2026-02-19", period_id: 21, term_id: 3 });
  });
});
