/** W3-SLOT: the administrator's slot display (booking.slot_display.*) as one pure model every booking surface reads. */
import { describe, expect, it } from "vitest";
import type { Grid, GridPeriod } from "@/lib/api/crbs";
import {
  DEFAULT_SLOT_DISPLAY,
  applySlotDisplay,
  blockCount,
  blockStarts,
  coverPeriods,
  defaultLens,
  defaultScope,
  defaultDisplay,
  lengthOptions,
  parseSlotDisplay,
  periodLabel,
  periodVisible,
  slotDisplayExtra,
  type SlotDisplay,
} from "./slot-display";

const P = (id: number, name: string, start: string, end: string, n = id): GridPeriod => ({ id, name, time_start: start, time_end: end, start_period: n, end_period: n, days: [1, 2, 3, 4, 5] });
const periods = [P(1, "P1", "08:30", "09:20"), P(2, "P2", "09:30", "10:20"), P(3, "P3", "10:30", "11:20"), P(4, "P4", "11:30", "12:20"), P(17, "P17", "21:10", "22:00")];
const sd = (patch: Partial<SlotDisplay> = {}): SlotDisplay => ({ ...DEFAULT_SLOT_DISPLAY, ...patch });
const time = (s: string) => s; // the booking formatter's identity for HH:MM

describe("parseSlotDisplay", () => {
  it("fills defaults and drops values a surface cannot draw (mirrors the backend sanitiser)", () => {
    expect(parseSlotDisplay(undefined)).toEqual(DEFAULT_SLOT_DISPLAY);
    expect(parseSlotDisplay({ unit: "hours", block_minutes: 45, label: "x", density: "huge", default_view: "month", min_length: 99, day_start: "25:00" })).toEqual({ ...DEFAULT_SLOT_DISPLAY, min_length: 8 });
    expect(parseSlotDisplay({ unit: "blocks", block_minutes: 15, label: "time", hidden_periods: ["P0", "p17"], hide_weekend: true, default_view: "week" })).toMatchObject({ unit: "blocks", block_minutes: 15, label: "time", hidden_periods: ["P0", "p17"], hide_weekend: true, default_view: "week" });
    expect(parseSlotDisplay({ day_start: "18:00", day_end: "09:00" })).toMatchObject({ day_start: null, day_end: null });
  });
});

describe("visible periods", () => {
  it("hides named periods case-insensitively and periods outside the day window (evening)", () => {
    expect(periods.filter((p) => periodVisible(p, sd({ hidden_periods: ["p2"] }))).map((p) => p.name)).toEqual(["P1", "P3", "P4", "P17"]);
    expect(periods.filter((p) => periodVisible(p, sd({ day_end: "18:00" }))).map((p) => p.name)).toEqual(["P1", "P2", "P3", "P4"]);
    expect(periods.filter((p) => periodVisible(p, sd({ day_start: "09:30" }))).map((p) => p.name)).toEqual(["P2", "P3", "P4", "P17"]);
  });

  it("applySlotDisplay filters a grid's periods, its slots and (hide_weekend) the weekend dates", () => {
    const grid = {
      display: "room",
      date: "2026-02-16",
      periods,
      dates: [{ date: "2026-02-16", weekday: 1, open: true }, { date: "2026-02-21", weekday: 6, open: true }, { date: "2026-02-22", weekday: 7, open: true }],
      slots: [
        { date: "2026-02-16", period_id: 1, room_id: 9, status: "available" },
        { date: "2026-02-16", period_id: 17, room_id: 9, status: "available" },
        { date: "2026-02-21", period_id: 1, room_id: 9, status: "available" },
      ],
    } as unknown as Grid;
    const out = applySlotDisplay(grid, sd({ day_end: "18:00", hide_weekend: true }));
    expect(out.periods.map((p) => p.id)).toEqual([1, 2, 3, 4]);
    expect(out.dates.map((d) => d.date)).toEqual(["2026-02-16"]);
    expect(out.slots).toHaveLength(1);
    // the default display is the very same object (memoised grids keep their identity)
    expect(applySlotDisplay(grid, DEFAULT_SLOT_DISPLAY)).toBe(grid);
  });
});

describe("labels", () => {
  it("name, time or both, as the administrator chose", () => {
    expect(periodLabel(periods[2]!, sd({ label: "name" }), time)).toEqual({ title: "P3", sub: null, text: "P3" });
    expect(periodLabel(periods[2]!, sd({ label: "time" }), time)).toEqual({ title: "10:30–11:20", sub: null, text: "10:30–11:20" });
    expect(periodLabel(periods[2]!, sd(), time)).toEqual({ title: "P3", sub: "10:30–11:20", text: "P3 · 10:30–11:20" });
  });
});

describe("blocks mapped onto periods", () => {
  it("counts the blocks a period spans and lists block starts inside the visible periods", () => {
    expect(blockCount(periods[0]!, 30)).toBe(2); // 50 min
    expect(blockCount(periods[0]!, 15)).toBe(4);
    expect(blockCount(periods[0]!, 60)).toBe(1);
    const starts = blockStarts(periods.slice(0, 2), sd({ unit: "blocks", block_minutes: 30 }));
    expect(starts.map((s) => s.time)).toEqual(["08:30", "09:00", "09:30", "10:00"]);
    expect(starts.map((s) => s.periodId)).toEqual([1, 1, 2, 2]);
  });

  it("covers [start, start + minutes) with whole periods, or null when it runs into a gap past the day", () => {
    expect(coverPeriods(periods, "09:00", 60)?.map((p) => p.name)).toEqual(["P1", "P2"]);
    expect(coverPeriods(periods, "10:30", 30)?.map((p) => p.name)).toEqual(["P3"]);
    expect(coverPeriods(periods, "12:00", 120)).toBeNull(); // P4 ends 12:20, nothing until 21:10
    expect(coverPeriods(periods, "07:00", 30)).toBeNull();
  });
});

describe("lengths", () => {
  it("start at the administrator's minimum and stay within what is left of the day", () => {
    expect(lengthOptions(sd(), 6)).toEqual([1, 2, 3, 4]);
    expect(lengthOptions(sd({ min_length: 2 }), 3)).toEqual([2, 3]);
    expect(lengthOptions(sd({ min_length: 3 }), 2)).toEqual([]);
  });
});

describe("default view", () => {
  it("unset follows the organisation's display type; week means the free-slot week", () => {
    expect(defaultDisplay(sd(), "room")).toBe("room");
    expect(defaultDisplay(sd({ default_view: "day" }), "room")).toBe("day");
    expect(defaultDisplay(sd({ default_view: "week" }), "room")).toBe("day");
    expect(defaultLens(sd({ default_view: "week" }), false)).toBe("free");
    expect(defaultLens(sd(), false)).toBe("grid");
    expect(defaultLens(sd(), true)).toBe("free");
    expect(defaultScope(sd({ default_view: "week" }))).toBe("week");
    expect(defaultScope(sd())).toBe("day");
  });
});

describe("saving", () => {
  it("writes every key under booking.slot_display.* (empty clears to the default)", () => {
    expect(slotDisplayExtra(sd({ unit: "blocks", hidden_periods: ["P0", "P18"], day_start: null, default_view: null }))).toEqual({
      "booking.slot_display.unit": "blocks",
      "booking.slot_display.block_minutes": 30,
      "booking.slot_display.label": "both",
      "booking.slot_display.density": "comfortable",
      "booking.slot_display.default_view": "",
      "booking.slot_display.day_start": "",
      "booking.slot_display.day_end": "",
      "booking.slot_display.hide_weekend": false,
      "booking.slot_display.hidden_periods": "P0, P18",
      "booking.slot_display.min_length": 1,
    });
  });
});
