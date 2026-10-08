import { describe, expect, it } from "vitest";
import type { RecurPlan } from "@/lib/api/crbs";
import { holidaysOnWeekday, initialPreview, instancesPayload, previewReducer, summarise, type PreviewState } from "./recurring-preview";

/* A 102 Thursday P3 in Bahar 2026: PSI 216 (timetable) in lecture weeks, one own booking, and 23 Nisan */
const plan = (max: number | null = null): RecurPlan => ({
  term_id: 1,
  room_id: 2,
  period_id: 3,
  weekday: 4,
  timetable_week_id: null,
  bookable_count: 3,
  max_instances: max,
  exceeds_by: 0,
  instances: [
    { date: "2026-04-09", term_week: 10, status: "free", actions: ["book", "do_not_book"] },
    { date: "2026-04-16", term_week: 11, status: "timetable", held: { kind: "timetable", room_id: 2, date: "2026-04-16", start_period: 3, end_period: 5, label: "PSI 216", id: 7 }, actions: ["do_not_book"] },
    { date: "2026-04-30", term_week: 13, status: "booked", held: { kind: "booking", room_id: 2, date: "2026-04-30", start_period: 3, end_period: 3, label: "", id: 9 }, actions: ["replace", "do_not_book"] },
    { date: "2026-05-07", term_week: 14, status: "free", actions: ["book", "do_not_book"] },
    { date: "2026-05-14", term_week: 15, status: "free", actions: ["book", "do_not_book"] },
  ],
});
const holidays = [{ date: "2026-04-23", name: "Ulusal Egemenlik ve Çocuk Bayramı" }];

const load = (max: number | null = null): PreviewState => previewReducer(initialPreview, { type: "load", plan: plan(max), holidays });

describe("recurring preview reducer", () => {
  it("defaults to the backend's choice: book free dates, skip taken ones", () => {
    const s = load();
    expect(s.choices).toEqual({ "2026-04-09": "book", "2026-04-16": "do_not_book", "2026-04-30": "do_not_book", "2026-05-07": "book", "2026-05-14": "book" });
    const sum = summarise(s);
    expect(sum).toMatchObject({ book: 3, replace: 0, skip: 2, holidays: 1, willCreate: 3, cut: 0 });
  });
  it("shows 23 Nisan as a skipped holiday row in date order", () => {
    const rows = summarise(load()).rows;
    expect(rows.map((r) => r.date)).toEqual(["2026-04-09", "2026-04-16", "2026-04-23", "2026-04-30", "2026-05-07", "2026-05-14"]);
    const hol = rows[2]!;
    expect(hol).toMatchObject({ kind: "holiday", action: null, heldLabel: "Ulusal Egemenlik ve Çocuk Bayramı" });
    expect(instancesPayload(load()).some((i) => i.date === "2026-04-23")).toBe(false);
  });
  it("only allows the actions the backend offers", () => {
    let s = load();
    s = previewReducer(s, { type: "set", date: "2026-04-16", action: "book" }); // timetable: refused
    expect(s.choices["2026-04-16"]).toBe("do_not_book");
    s = previewReducer(s, { type: "set", date: "2026-04-30", action: "replace" });
    expect(s.choices["2026-04-30"]).toBe("replace");
    expect(summarise(s)).toMatchObject({ book: 3, replace: 1, willCreate: 4 });
    s = previewReducer(s, { type: "set", date: "2026-05-07", action: "do_not_book" });
    expect(summarise(s).willCreate).toBe(3);
  });
  it("book all / skip all", () => {
    let s = previewReducer(load(), { type: "setAll", action: "do_not_book" });
    expect(summarise(s).willCreate).toBe(0);
    s = previewReducer(s, { type: "setAll", action: "book" });
    expect(summarise(s)).toMatchObject({ book: 3, replace: 0 }); // never turns a taken slot into "replace"
  });
  it("applies recur_max_instances in date order, like the backend", () => {
    let s = load(2);
    s = previewReducer(s, { type: "set", date: "2026-04-30", action: "replace" });
    const sum = summarise(s);
    expect(sum.maxInstances).toBe(2);
    expect(sum.rows.filter((r) => r.cut).map((r) => r.date)).toEqual(["2026-05-07", "2026-05-14"]);
    expect(sum).toMatchObject({ willCreate: 2, cut: 2 });
  });
  it("payload lists every instance with its action", () => {
    expect(instancesPayload(load())).toEqual([
      { date: "2026-04-09", action: "book" },
      { date: "2026-04-16", action: "do_not_book" },
      { date: "2026-04-30", action: "do_not_book" },
      { date: "2026-05-07", action: "book" },
      { date: "2026-05-14", action: "book" },
    ]);
    expect(previewReducer(load(), { type: "reset" })).toEqual(initialPreview);
  });
  it("finds holidays on the series weekday within the range", () => {
    const dates = [
      { date: "2026-04-22", weekday: 3, holiday: null },
      { date: "2026-04-23", weekday: 4, holiday: "Ulusal Egemenlik ve Çocuk Bayramı" },
      { date: "2026-05-01", weekday: 5, holiday: "Emek ve Dayanışma Günü" },
    ];
    expect(holidaysOnWeekday(dates, 4, "2026-02-19", "2026-06-25")).toEqual(holidays);
    expect(holidaysOnWeekday(dates, 4, "2026-04-24", "2026-06-25")).toEqual([]);
  });
});
