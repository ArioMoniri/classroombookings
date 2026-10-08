import { describe, expect, it } from "vitest";
import type { BookingConflict } from "@/lib/api/crbs";
import { groupConflicts, periodSpan, summariseConflicts } from "./conflicts-model";

const held = (over: Partial<BookingConflict["held"]>): BookingConflict["held"] => ({
  kind: "timetable",
  room_id: 1,
  date: "2026-03-02",
  start_period: 3,
  end_period: 4,
  label: "FIZ101",
  id: 10,
  run_id: 7,
  series_id: null,
  ...over,
});

const ROOMS: Record<number, string> = { 1: "FZT 132", 2: "A 101" };
const label = (id: number) => ROOMS[id] ?? String(id);

describe("groupConflicts", () => {
  it("collapses (booking, holder) pairs into one row per booking and drops repeated holders", () => {
    const rows = groupConflicts(
      [
        { booking_id: 5, room_id: 1, date: "2026-03-02", held: held({ id: 10, start_period: 4, end_period: 4, label: "MAT201" }) },
        { booking_id: 5, room_id: 1, date: "2026-03-02", held: held({ id: 11, start_period: 3, end_period: 3, label: "FIZ101" }) },
        { booking_id: 5, room_id: 1, date: "2026-03-02", held: held({ id: 11, start_period: 3, end_period: 3, label: "FIZ101" }) },
      ],
      label,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].holders.map((h) => h.label)).toEqual(["FIZ101", "MAT201"]);
  });

  it("orders rows by date, then room label (Turkish collation), then booking id", () => {
    const rows = groupConflicts(
      [
        { booking_id: 9, room_id: 1, date: "2026-03-03", held: held({ id: 1 }) },
        { booking_id: 8, room_id: 1, date: "2026-03-02", held: held({ id: 2 }) },
        { booking_id: 7, room_id: 2, date: "2026-03-02", held: held({ id: 3, room_id: 2, kind: "block", label: "Bakım" }) },
      ],
      label,
    );
    expect(rows.map((r) => r.bookingId)).toEqual([7, 8, 9]);
    expect(summariseConflicts(rows)).toEqual({ bookings: 3, rooms: 2, days: 2 });
  });

  it("is empty for no conflicts", () => {
    expect(groupConflicts([])).toEqual([]);
    expect(summariseConflicts([])).toEqual({ bookings: 0, rooms: 0, days: 0 });
  });
});

describe("periodSpan", () => {
  it("shows one slot or a range", () => {
    expect(periodSpan({ start_period: 4, end_period: 4 })).toBe("4");
    expect(periodSpan({ start_period: 3, end_period: 5 })).toBe("3–5");
  });
});
