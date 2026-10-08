import { describe, expect, it } from "vitest";
import type { Grid, GridSlot, RoomInfo } from "@/lib/api/crbs";
import {
  alternativesFromGrids,
  clampSpan,
  departmentColor,
  departmentTally,
  freeRun,
  freeSlotsByRoom,
  googleSubscribeUrl,
  nextFreeSlot,
  outlookSubscribeUrl,
  parseDepartmentLens,
  spanBetween,
  toggleRange,
  webcalUrl,
} from "./reserve-model";

const D = "2026-02-16";
const periods = [
  { id: 11, name: "P1", time_start: "08:30", time_end: "09:20", start_period: 1, end_period: 1, days: [1, 2, 3, 4, 5] },
  { id: 12, name: "P2", time_start: "09:30", time_end: "10:20", start_period: 2, end_period: 2, days: [1, 2, 3, 4, 5] },
  { id: 13, name: "P3", time_start: "10:30", time_end: "11:20", start_period: 3, end_period: 3, days: [1, 2, 3, 4, 5] },
  { id: 14, name: "P4", time_start: "11:30", time_end: "12:20", start_period: 4, end_period: 4, days: [1, 2, 3, 4, 5] },
];
const free = (room: number, period: number, date = D): GridSlot => ({ date, period_id: period, room_id: room, status: "available", allow_single: true, allow_recur: false });
const tt = (room: number, period: number, label = "FZT 132"): GridSlot => ({ date: D, period_id: period, room_id: room, status: "timetable", reason: "timetable", label });
const booked = (room: number, period: number, dept: number | null, name = "Psikoloji"): GridSlot => ({
  date: D,
  period_id: period,
  room_id: room,
  status: "booked",
  reason: "single",
  booking: { id: room * 100 + period, type: "single", status: "BOOKED", date: D, weekday: 1, period_id: period, start_period: 1, end_period: 1, room_id: room, room_name: "x", department_id: dept, department_name: dept ? name : null, user_hidden: false, notes_hidden: false, is_owner: false },
});

function grid(rooms: { id: number; name: string; capacity: number; group?: number }[], slots: GridSlot[], ps = periods): Grid {
  return {
    display: "day",
    term: { id: 1, code: "2026-BAHAR", name: "Bahar 2026", start: "2026-02-02", end: "2026-06-12" },
    date: D,
    room_group_id: rooms[0]?.group ?? null,
    dates: [{ date: D, weekday: 1, open: true }],
    periods: ps,
    rooms: rooms.map((r) => ({ id: r.id, name: r.name, code: r.name.replace(" ", ""), capacity: r.capacity, room_group_id: r.group ?? null })),
    slots,
    nav: {},
    limits: {},
    problems: [],
  };
}

// A 101: P1 P2 free, P3 timetable, P4 free; A 102: all free
const g = grid(
  [
    { id: 1, name: "A 101", capacity: 40 },
    { id: 2, name: "A 102", capacity: 90 },
  ],
  [free(1, 11), free(1, 12), tt(1, 13), free(1, 14), free(2, 11), free(2, 12), free(2, 13), free(2, 14)],
);
const at = (room: number, period: number) => g.slots.find((s) => s.room_id === room && s.period_id === period)!;

describe("spans of consecutive free periods", () => {
  it("spanBetween needs one room and date and every period in between free", () => {
    expect(spanBetween(g, at(1, 12), at(1, 11))!.map((s) => s.period_id)).toEqual([11, 12]);
    expect(spanBetween(g, at(1, 11), at(1, 14))).toBeNull(); // P3 is held by the timetable
    expect(spanBetween(g, at(1, 11), at(2, 12))).toBeNull(); // another room
    expect(spanBetween(g, at(2, 11), at(2, 14))!.length).toBe(4);
  });

  it("clampSpan stops a drag at the first period that cannot be booked", () => {
    expect(clampSpan(g, at(1, 11), at(1, 14)).map((s) => s.period_id)).toEqual([11, 12]);
    expect(clampSpan(g, at(1, 14), at(1, 11)).map((s) => s.period_id)).toEqual([14]);
    expect(clampSpan(g, at(2, 13), at(2, 11)).map((s) => s.period_id)).toEqual([11, 12, 13]);
    expect(clampSpan(g, at(1, 11), at(2, 12)).map((s) => s.period_id)).toEqual([11]);
  });

  it("freeRun finds the run around a slot; toggleRange keeps it contiguous and non-empty", () => {
    expect(freeRun(g, at(1, 12)).map((s) => s.period_id)).toEqual([11, 12]);
    expect(freeRun(g, at(1, 14)).map((s) => s.period_id)).toEqual([14]);
    expect(toggleRange({ lo: 1, hi: 1 }, 3)).toEqual({ lo: 1, hi: 3 });
    expect(toggleRange({ lo: 1, hi: 3 }, 0)).toEqual({ lo: 0, hi: 3 });
    expect(toggleRange({ lo: 1, hi: 3 }, 3)).toEqual({ lo: 1, hi: 2 });
    expect(toggleRange({ lo: 1, hi: 3 }, 1)).toEqual({ lo: 2, hi: 3 });
    expect(toggleRange({ lo: 1, hi: 3 }, 2)).toEqual({ lo: 1, hi: 2 });
    expect(toggleRange({ lo: 2, hi: 2 }, 2)).toEqual({ lo: 2, hi: 2 });
  });
});

describe("free slots lens", () => {
  it("groups reservable slots by room into runs and leaves periods that are over out", () => {
    const rooms = freeSlotsByRoom([g]);
    expect(rooms.map((r) => [r.room.name, r.count])).toEqual([
      ["A 101", 3],
      ["A 102", 4],
    ]);
    expect(rooms[0]!.days[0]!.runs.map((r) => r.map((s) => s.period_id))).toEqual([[11, 12], [14]]);
    const later = freeSlotsByRoom([g], { now: { date: D, time: "10:00" } });
    expect(later[0]!.days[0]!.runs.map((r) => r.map((s) => s.period_id))).toEqual([[12], [14]]);
    expect(freeSlotsByRoom([g], { firstRooms: new Set([2]) })[0]!.room.name).toBe("A 102");
  });

  it("drops rooms with nothing to book and slots the user may not book", () => {
    const g2 = grid([{ id: 3, name: "B 201", capacity: 30 }], [{ ...free(3, 11), allow_single: false }, { ...free(3, 12), status: "unavailable", reason: "limit" }]);
    expect(freeSlotsByRoom([g2])).toEqual([]);
  });

  it("nextFreeSlot is the first reservable period from now", () => {
    expect(nextFreeSlot(g, 1)!.period_id).toBe(11);
    expect(nextFreeSlot(g, 1, { date: D, time: "09:25" })!.period_id).toBe(12);
    expect(nextFreeSlot(g, 1, { date: D, time: "10:25" })!.period_id).toBe(14);
    expect(nextFreeSlot(g, 1, { date: D, time: "13:00" })).toBeNull();
  });
});

describe("other available rooms (client-side)", () => {
  const info = (id: number, tags: string[]): RoomInfo => ({ id, code: "", name: "", tags, fields: [] });
  const infos = new Map([
    [1, info(1, [])],
    [2, info(2, ["PC"])],
    [3, info(3, ["PC", "LAB"])],
  ]);
  // another room group with its own schedule: same solver periods, other period ids
  const other = grid(
    [{ id: 3, name: "C 301", capacity: 60, group: 2 }],
    [free(3, 21), free(3, 22)],
    periods.slice(0, 2).map((p) => ({ ...p, id: p.id + 10 })),
  );

  it("lists rooms free for every asked period, best fit first, across room groups", () => {
    const alts = alternativesFromGrids([g, other], { date: D, periods: [periods[0]!, periods[1]!], excludeRoomId: 1, minSeats: 50, tags: [] }, infos);
    expect(alts.map((a) => [a.room.name, a.spare])).toEqual([
      ["C 301", 10],
      ["A 102", 40],
    ]);
    expect(alts[0]!.slots.map((s) => s.period_id)).toEqual([21, 22]);
  });

  it("filters by tags and skips rooms busy in any asked period", () => {
    const alts = alternativesFromGrids([g, other], { date: D, periods: [periods[0]!], minSeats: 0, tags: ["lab"] }, infos);
    expect(alts.map((a) => a.room.name)).toEqual(["C 301"]);
    expect(alternativesFromGrids([g], { date: D, periods: [periods[2]!], minSeats: 0, tags: [] }, infos).map((a) => a.room.name)).toEqual(["A 102"]);
  });
});

describe("departments and calendar links", () => {
  it("colours are stable per department and the tally puts mine first", () => {
    expect(departmentColor(1)).toBe("var(--cat-1)");
    expect(departmentColor(9)).toBe("var(--cat-1)");
    expect(departmentColor(null)).toBeNull();
    const dg = grid([{ id: 1, name: "A 101", capacity: 40 }], [booked(1, 11, 5, "Psikoloji"), booked(1, 12, 7, "Hukuk"), booked(1, 13, 7, "Hukuk"), booked(1, 14, null)]);
    expect(departmentTally(dg, null).map((d) => [d.name, d.count])).toEqual([
      ["Hukuk", 2],
      ["Psikoloji", 1],
    ]);
    expect(departmentTally(dg, 5)[0]!.name).toBe("Psikoloji");
    expect(parseDepartmentLens("all")).toBe("all");
    expect(parseDepartmentLens("12")).toBe(12);
    expect(parseDepartmentLens("x")).toBeNull();
  });

  it("builds webcal, Google and Outlook subscribe links", () => {
    const url = "https://uni.edu.tr/api/v1/ics/abc/user.ics";
    expect(webcalUrl(url)).toBe("webcal://uni.edu.tr/api/v1/ics/abc/user.ics");
    expect(googleSubscribeUrl(url)).toBe("https://calendar.google.com/calendar/r?cid=webcal%3A%2F%2Funi.edu.tr%2Fapi%2Fv1%2Fics%2Fabc%2Fuser.ics");
    expect(outlookSubscribeUrl(url, "SmartSched")).toBe("https://outlook.live.com/calendar/0/addfromweb?url=https%3A%2F%2Funi.edu.tr%2Fapi%2Fv1%2Fics%2Fabc%2Fuser.ics&name=SmartSched");
    expect(outlookSubscribeUrl(url, "x", true)).toMatch(/^https:\/\/outlook\.office\.com\//);
  });
});
