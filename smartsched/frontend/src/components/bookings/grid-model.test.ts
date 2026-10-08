import { describe, expect, it } from "vitest";
import type { Grid, GridSlot } from "@/lib/api/crbs";
import { crosshairCss, hiddenDays, isSelectable, layoutGrid, moveFocus, parseSlotKey, slotKey, slotText, slotTone } from "./grid-model";

const booking = (over: Partial<NonNullable<GridSlot["booking"]>> = {}): NonNullable<GridSlot["booking"]> => ({
  id: 7,
  type: "single",
  status: "BOOKED",
  date: "2026-02-16",
  weekday: 1,
  period_id: 1,
  start_period: 1,
  end_period: 1,
  room_id: 1,
  room_name: "A 101",
  user_hidden: false,
  notes_hidden: false,
  is_owner: false,
  ...over,
});

function grid(display: "day" | "room"): Grid {
  const periods = [
    { id: 1, name: "P1", time_start: "08:30", time_end: "09:10", start_period: 1, end_period: 1, days: [1, 2, 3, 4, 5] },
    { id: 4, name: "P4", time_start: "11:00", time_end: "11:40", start_period: 4, end_period: 4, days: [1, 2, 3, 4, 5] },
  ];
  const rooms = display === "day" ? [{ id: 1, name: "A 101", code: "A101" }, { id: 2, name: "A 102", code: "A102" }] : [{ id: 1, name: "A 101", code: "A101" }];
  const dates =
    display === "day"
      ? [{ date: "2026-02-16", weekday: 1, open: true }]
      : ["2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-21", "2026-02-22"].map((date, i) => ({ date, weekday: i + 1, open: i < 5 }));
  const slots: GridSlot[] = [];
  for (const d of dates) for (const p of periods) for (const r of rooms) slots.push({ date: d.date, period_id: p.id, room_id: r.id, status: "available", allow_single: true, allow_recur: false });
  return { display, term: { id: 1, code: "2026-BAHAR", name: "2026-BAHAR", start: "2026-02-02", end: "2026-06-28" }, date: "2026-02-16", dates, periods, rooms, slots, nav: {}, limits: {}, problems: [] };
}

describe("grid orientation (CRBS displaytype × d_columns)", () => {
  it("day view: rooms down, periods across — or the other way round", () => {
    const a = layoutGrid(grid("day"), "periods");
    expect(a.rows.map((r) => r.key)).toEqual(["r1", "r2"]);
    expect(a.cols.map((c) => c.key)).toEqual(["p1", "p4"]);
    expect(a.slot(a.rows[1]!, a.cols[1]!)).toMatchObject({ room_id: 2, period_id: 4, date: "2026-02-16" });
    const b = layoutGrid(grid("day"), "rooms");
    expect(b.rows.map((r) => r.key)).toEqual(["p1", "p4"]);
    expect(b.cols.map((c) => c.key)).toEqual(["r1", "r2"]);
    expect(b.slot(b.rows[1]!, b.cols[0]!)).toMatchObject({ room_id: 1, period_id: 4 });
  });
  it("room view: days down, periods across — or periods down, days across", () => {
    const a = layoutGrid(grid("room"), "periods");
    expect(a.rows[0]!.kind).toBe("date");
    expect(a.cols.map((c) => c.key)).toEqual(["p1", "p4"]);
    expect(a.slot(a.rows[3]!, a.cols[0]!)).toMatchObject({ date: "2026-02-19", room_id: 1, period_id: 1 });
    const b = layoutGrid(grid("room"), "days");
    expect(b.rows.map((r) => r.key)).toEqual(["p1", "p4"]);
    expect(b.cols[0]!.kind).toBe("date");
  });
  it("week view hides days without periods and days outside the session (CRBS Context rules)", () => {
    const g = grid("room");
    expect([...hiddenDays(g)]).toEqual(["2026-02-21", "2026-02-22"]);
    expect(layoutGrid(g, "periods").rows.map((r) => r.key)).toEqual(["2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20"]);
    const early = { ...g, term: { ...g.term, start: "2026-02-18" } };
    expect([...hiddenDays(early)].sort()).toEqual(["2026-02-16", "2026-02-17", "2026-02-21", "2026-02-22"]);
    const withHoliday = { ...g, dates: g.dates.map((d) => (d.date === "2026-02-21" ? { ...d, reason: "holiday", holiday: "Bayram" } : d)) };
    expect(hiddenDays(withHoliday).has("2026-02-21")).toBe(false); // holidays stay visible as holidays
    expect(hiddenDays(grid("day")).size).toBe(0);
  });
});

describe("slot states and labels follow the viewer's permissions", () => {
  const labels = { booked: "Rezerve", mine: "Siz" };
  it("another person's booking shows their name only when the backend sent it (show names / view_other_users)", () => {
    const visible: GridSlot = { date: "2026-02-16", period_id: 1, room_id: 1, status: "booked", reason: "single", booking: booking({ user_name: "Ayşe Yılmaz", notes: "Tez savunması" }) };
    expect(slotText(visible, labels)).toEqual({ primary: "Ayşe Yılmaz", secondary: "Tez savunması" });
    const hidden: GridSlot = { ...visible, booking: booking({ user_name: null, user_hidden: true, notes: null, notes_hidden: true }) };
    expect(slotText(hidden, labels)).toEqual({ primary: "Rezerve", secondary: null });
    const mine: GridSlot = { ...visible, booking: booking({ is_owner: true, user_name: "Ayşe Yılmaz", notes: null, department_name: "Fizyoterapi" }) };
    expect(slotText(mine, labels)).toEqual({ primary: "Siz", secondary: "Fizyoterapi" });
    expect(slotTone(mine)).toBe("booked-mine");
    expect(slotTone({ ...visible, reason: "recurring" })).toBe("booked-recurring");
  });
  it("timetable, holiday and closed slots", () => {
    const tt: GridSlot = { date: "2026-02-16", period_id: 4, room_id: 1, status: "timetable", reason: "timetable", label: "FZT 132" };
    expect(slotText(tt, labels).primary).toBe("FZT 132");
    expect(slotTone(tt)).toBe("timetable");
    expect(isSelectable(tt)).toBe(false);
    const hol: GridSlot = { date: "2026-04-23", period_id: 1, room_id: 1, status: "unavailable", reason: "holiday", label: "Ulusal Egemenlik ve Çocuk Bayramı" };
    expect(slotTone(hol)).toBe("holiday");
    expect(slotText(hol, labels).primary).toBe("Ulusal Egemenlik ve Çocuk Bayramı");
    const noRights: GridSlot = { date: "2026-02-16", period_id: 1, room_id: 1, status: "available", allow_single: false, allow_recur: false };
    expect(isSelectable(noRights)).toBe(false);
    expect(slotTone(noRights)).toBe("unavailable");
  });
  it("slot keys round-trip; keyboard focus is clamped", () => {
    const k = slotKey({ date: "2026-02-16", period_id: 4, room_id: 12 });
    expect(parseSlotKey(k)).toEqual({ date: "2026-02-16", period_id: 4, room_id: 12 });
    expect(moveFocus({ r: 0, c: 0 }, "ArrowLeft", { rows: 3, cols: 18 })).toEqual({ r: 0, c: 0 });
    expect(moveFocus({ r: 2, c: 5 }, "End", { rows: 3, cols: 18 })).toEqual({ r: 2, c: 17 });
    expect(moveFocus({ r: 2, c: 5 }, "ArrowDown", { rows: 3, cols: 18 })).toEqual({ r: 2, c: 5 });
    expect(moveFocus({ r: 0, c: 0 }, "x", { rows: 3, cols: 18 })).toBeNull();
  });
  it("grid highlight (CRBS grid_highlight) tints one row and one column of free slots", () => {
    expect(crosshairCss("g1", null)).toBe("");
    const css = crosshairCss("g1", { r: 2, c: 5 });
    expect(css).toContain('[data-grid-scope="g1"] tr[data-r="2"] > td > button[data-tone="available"]');
    expect(css).toContain('td[data-c="5"] > button[data-tone="available"]');
  });
});
