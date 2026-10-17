import { describe, expect, it } from "vitest";
import type { BookingOut } from "@/lib/api/crbs";
import { groupBookings } from "./my-bookings-model";

const b = (id: number, p: number, extra: Partial<BookingOut> = {}): BookingOut => ({
  id,
  type: "single",
  status: "BOOKED",
  date: "2026-11-05",
  weekday: 4,
  period_id: p,
  period_name: `P${p}`,
  time_start: `${12 + p}:30`,
  time_end: `${13 + p}:00`,
  start_period: p,
  end_period: p,
  room_id: 3,
  room_name: "C 303",
  user_hidden: false,
  notes_hidden: false,
  is_owner: true,
  ...extra,
});

describe("T-R2-13 my-bookings rows", () => {
  it("one row for the periods of one submission, in period order, with the span label", () => {
    const rows = groupBookings([b(12, 8, { group_id: 4 }), b(11, 7, { group_id: 4 }), b(20, 3, { group_id: null, date: "2026-11-12" })]);
    expect(rows.map((r) => [r.id, r.ids, r.periodLabel])).toEqual([
      [11, [11, 12], "P7–P8"],
      [20, [20], "P3"],
    ]);
    expect(rows[0]!.first.time_start).toBe("19:30");
    expect(rows[0]!.last.time_end).toBe("21:00");
  });
  it("a cancelled period leaves the span: it is its own row with its own status", () => {
    const rows = groupBookings([b(11, 7, { group_id: 4 }), b(12, 8, { group_id: 4, status: "CANCELLED" })]);
    expect(rows.map((r) => [r.periodLabel, r.first.status])).toEqual([
      ["P7", "BOOKED"],
      ["P8", "CANCELLED"],
    ]);
  });
  it("another day or room of the same submission, and series instances, stay apart", () => {
    const rows = groupBookings([b(1, 7, { group_id: 4 }), b(2, 8, { group_id: 4, date: "2026-11-12" }), b(3, 9, { group_id: 4, room_id: 5 }), b(4, 10, { group_id: 4, type: "recurring", series_id: 9 })]);
    expect(rows).toHaveLength(4);
  });
});
