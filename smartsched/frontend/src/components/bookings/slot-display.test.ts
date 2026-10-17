/** W3-SLOT: the administrator's slot display (booking.slot_display.*) as one pure model every booking surface reads. */
import { describe, expect, it } from "vitest";
import type { Grid, GridPeriod } from "@/lib/api/crbs";
import {
  DEFAULT_SLOT_DISPLAY,
  applySlotDisplay,
  blockCount,
  blockStarts,
  coverPeriods,
  hiddenPeriodCount,
  lengthOptions,
  openingView,
  parseSlotDisplay,
  periodHeight,
  periodVisible,
  periodWidth,
  slotDisplayExtra,
  slotLabel,
  type SlotDisplay,
} from "./slot-display";

const P = (id: number, name: string, start: string, end: string, n = id): GridPeriod => ({ id, name, time_start: start, time_end: end, start_period: n, end_period: n, days: [1, 2, 3, 4, 5] });
const periods = [P(1, "P1", "08:30", "09:20"), P(2, "P2", "09:30", "10:20"), P(3, "P3", "10:30", "11:20"), P(4, "", "11:30", "12:20"), P(12, "P12", "17:30", "18:00"), P(17, "P17", "21:10", "22:00")];
const sd = (patch: Partial<SlotDisplay> = {}): SlotDisplay => ({ ...DEFAULT_SLOT_DISPLAY, ...patch });
const f = { time: (s: string) => s, ordinal: (n: number) => `${n}. ders` };

describe("parseSlotDisplay", () => {
  it("fills defaults and drops values a surface cannot draw (mirrors the backend sanitiser)", () => {
    expect(parseSlotDisplay(undefined)).toEqual(DEFAULT_SLOT_DISPLAY);
    expect(parseSlotDisplay({ unit: "hours", block_minutes: 45, label: "x", density: "huge", default_view_desktop: "month", default_view_phone: "grid_day", min_length: 99, first_period: 9, last_period: 2 })).toEqual({ ...DEFAULT_SLOT_DISPLAY, min_length: 8, quick_span: 8 });
    expect(parseSlotDisplay({ unit: "blocks", block_minutes: 15, label: "time", time_format: "start", period_name: "ordinal", hide_weekend: true, default_view_desktop: "free_week", default_view_phone: "quick", quick_span: 3 })).toMatchObject({ unit: "blocks", block_minutes: 15, label: "time", time_format: "start", period_name: "ordinal", hide_weekend: true, default_view_desktop: "free_week", default_view_phone: "quick", quick_span: 3 });
  });
});

describe("visible periods (a display filter, never a permission)", () => {
  it("first / last period and short transition slots", () => {
    expect(periods.filter((p) => periodVisible(p, sd({ last_period: 11 }))).map((p) => p.id)).toEqual([1, 2, 3, 4]);
    expect(periods.filter((p) => periodVisible(p, sd({ first_period: 3 }))).map((p) => p.id)).toEqual([3, 4, 12, 17]);
    expect(periods.filter((p) => periodVisible(p, sd({ hide_short: true }))).map((p) => p.id)).toEqual([1, 2, 3, 4, 17]);
    expect(hiddenPeriodCount(periods, sd({ last_period: 11 }))).toBe(2);
  });

  it("applySlotDisplay filters periods, slots and (week grids) the weekend; reveal shows everything", () => {
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
    const out = applySlotDisplay(grid, sd({ last_period: 11, hide_weekend: true }));
    expect(out.periods.map((p) => p.id)).toEqual([1, 2, 3, 4]);
    expect(out.dates.map((d) => d.date)).toEqual(["2026-02-16"]);
    expect(out.slots).toHaveLength(1);
    expect(applySlotDisplay(grid, sd({ last_period: 11 }), true)).toBe(grid);
    // the default display is the very same object (memoised grids keep their identity)
    expect(applySlotDisplay(grid, DEFAULT_SLOT_DISPLAY)).toBe(grid);
  });
});

describe("one label rule (slot-display.md §5)", () => {
  const p3 = periods[2]!;
  it("period, time or both; the accessible text is always complete", () => {
    expect(slotLabel(p3, sd({ label: "period" }), f)).toEqual({ primary: "P3", secondary: null, inline: "P3", a11y: "P3, 10:30–11:20" });
    expect(slotLabel(p3, sd({ label: "time" }), f)).toEqual({ primary: "10:30–11:20", secondary: null, inline: "10:30–11:20", a11y: "10:30–11:20, P3" });
    expect(slotLabel(p3, sd(), f)).toEqual({ primary: "P3", secondary: "10:30–11:20", inline: "P3 · 10:30–11:20", a11y: "P3, 10:30–11:20" });
    expect(slotLabel(p3, sd({ time_format: "start" }), f).inline).toBe("P3 · 10:30");
    expect(slotLabel(p3, sd({ time_format: "start", label: "time" }), f).a11y).toBe("10:30–11:20, P3");
  });
  it("ordinal names, and a period without a name falls back to its number", () => {
    expect(slotLabel(p3, sd({ period_name: "ordinal" }), f).primary).toBe("3. ders");
    expect(slotLabel(periods[3]!, sd(), f).primary).toBe("4. ders");
  });
});

describe("blocks mapped onto periods", () => {
  it("counts blocks, sizes in proportion to minutes, lists block starts inside the periods", () => {
    expect(blockCount(periods[0]!, 30)).toBe(2); // 50 min
    expect(blockCount(periods[0]!, 15)).toBe(4);
    expect(blockCount(periods[0]!, 60)).toBe(1);
    expect(periodWidth(periods[0]!, sd())).toBe(78);
    expect(periodWidth(periods[0]!, sd({ density: "compact" }))).toBe(64);
    expect(periodWidth(periods[0]!, sd({ unit: "blocks" }))).toBe(70); // 50 min × 1.4
    expect(periodHeight(periods[4]!, sd({ unit: "blocks" }))).toBe(42); // 30 min × 1.4: visibly shorter than 70
    expect(periodHeight(periods[0]!, sd({ density: "comfortable" }))).toBe(56);
    const starts = blockStarts(periods.slice(0, 2), sd({ unit: "blocks", block_minutes: 30 }));
    expect(starts.map((s) => s.time)).toEqual(["08:30", "09:00", "09:30", "10:00"]);
    expect(starts.map((s) => s.periodId)).toEqual([1, 1, 2, 2]);
  });

  it("covers [start, start + minutes) with whole periods, or null past the day / in a gap", () => {
    expect(coverPeriods(periods, "09:00", 60)?.map((p) => p.id)).toEqual([1, 2]);
    expect(coverPeriods(periods, "10:30", 30)?.map((p) => p.id)).toEqual([3]);
    expect(coverPeriods(periods, "12:00", 120)).toBeNull(); // 12:20 → 17:30 is a gap
    expect(coverPeriods(periods, "07:00", 30)).toBeNull();
  });
});

describe("quick reserve lengths", () => {
  it("min_length … quick_span, within what is left of the day", () => {
    expect(lengthOptions(sd(), 6)).toEqual([1]);
    expect(lengthOptions(sd({ quick_span: 3 }), 6)).toEqual([1, 2, 3]);
    expect(lengthOptions(sd({ min_length: 2, quick_span: 4 }), 3)).toEqual([2, 3]);
    expect(lengthOptions(sd({ min_length: 3, quick_span: 3 }), 2)).toEqual([]);
  });
});

describe("opening view", () => {
  it("unset desktop follows the organisation's display type; the phone set has no multi-room grid", () => {
    expect(openingView(sd(), false, "room")).toEqual({ display: "room", lens: "grid", scope: "day", quick: false });
    expect(openingView(sd({ default_view_desktop: "grid_day" }), false, "room").display).toBe("day");
    expect(openingView(sd({ default_view_desktop: "free_week" }), false, "day")).toMatchObject({ lens: "free", scope: "week" });
    expect(openingView(sd(), true, "day")).toMatchObject({ lens: "free", scope: "day" });
    expect(openingView(sd({ default_view_phone: "quick" }), true, "day").quick).toBe(true);
  });
});

describe("saving", () => {
  it("writes every key under booking.slot_display.* (null clears to the default)", () => {
    const extra = slotDisplayExtra(sd({ unit: "blocks" }));
    expect(Object.keys(extra)).toHaveLength(14);
    expect(extra["booking.slot_display.unit"]).toBe("blocks");
    expect(extra["booking.slot_display.default_view_desktop"]).toBe("");
    expect(extra["booking.slot_display.hide_weekend"]).toBe(false);
  });
});
