/** W3-SLOT quick reserve (docs/design/v3/quick-reserve.md): the pure model behind /reserve. */
import { describe, expect, it } from "vitest";
import type { DateInfo, Grid, GridPeriod, GridSlot } from "@/lib/api/crbs";
import type { FindRow } from "@/lib/api/wave1";
import { DEFAULT_SLOT_DISPLAY, type SlotDisplay } from "@/components/bookings/slot-display";
import { dayChips, defaultSlot, findQuery, lengthChoices, rankRooms, roomAction, slotOptions, spanFor } from "./quick-reserve-model";

const D = "2026-02-16"; // Monday
const P = (id: number, start: string, end: string, n = id): GridPeriod => ({ id, name: `P${n}`, time_start: start, time_end: end, start_period: n, end_period: n, days: [1, 2, 3, 4, 5] });
const periods = [P(1, "08:30", "09:20"), P(2, "09:30", "10:20"), P(3, "10:30", "11:20"), P(4, "11:30", "12:20"), P(17, "21:10", "22:00")];
const free = (p: number, room = 1): GridSlot => ({ date: D, period_id: p, room_id: room, status: "available", allow_single: true });
const taken = (p: number, room = 1): GridSlot => ({ date: D, period_id: p, room_id: room, status: "timetable", reason: "timetable", label: "MAT" });
const grid = (slots: GridSlot[]): Grid => ({ display: "day", term: { id: 1, code: "B", name: "Bahar", start: "2026-02-02", end: "2026-06-12" }, date: D, dates: [{ date: D, weekday: 1, open: true }], periods, rooms: [{ id: 1, name: "A 101", code: "A101" }, { id: 2, name: "A 102", code: "A102" }], slots, nav: {}, limits: {}, problems: [] });
const sd = (patch: Partial<SlotDisplay> = {}): SlotDisplay => ({ ...DEFAULT_SLOT_DISPLAY, ...patch });

describe("day chips", () => {
  it("today, tomorrow, then school days; closed days stay (disabled, with the reason); weekends that are closed are left out", () => {
    const dates: DateInfo[] = [
      { date: "2026-02-16", weekday: 1, open: true },
      { date: "2026-02-17", weekday: 2, open: true },
      { date: "2026-02-18", weekday: 3, open: false, holiday: "Kandil" },
      { date: "2026-02-19", weekday: 4, open: false, reason: "range_max" },
      { date: "2026-02-20", weekday: 5, open: true },
      { date: "2026-02-21", weekday: 6, open: false },
      { date: "2026-02-22", weekday: 7, open: false },
      { date: "2026-02-23", weekday: 1, open: true },
    ];
    const chips = dayChips(dates, D, 7);
    expect(chips.map((c) => c.date)).toEqual(["2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23"]);
    expect(chips.map((c) => c.kind)).toEqual(["today", "tomorrow", "day", "day", "day", "day"]);
    expect(chips[2]).toMatchObject({ closed: true, holiday: "Kandil" });
    expect(chips[3]).toMatchObject({ closed: true, holiday: null });
  });
});

describe("slot options", () => {
  const g = grid([free(1), taken(1, 2), taken(2), taken(2, 2), free(3), free(3, 2), free(4), free(17)]);
  it("periods: one option per visible period; started ones are left out; Dolu when no room is free", () => {
    const opts = slotOptions(g, sd(), { date: D, time: "08:40" }, true);
    expect(opts.map((o) => o.key)).toEqual(["p2", "p3", "p4", "p17"]);
    expect(opts.find((o) => o.key === "p2")!.full).toBe(true);
    expect(opts.find((o) => o.key === "p3")!.full).toBe(false);
    expect(slotOptions(g, sd({ last_period: 11 }), undefined, true).map((o) => o.key)).toEqual(["p1", "p2", "p3", "p4"]);
  });
  it("without every room in the grid (room groups) 'Dolu' is not claimed", () => {
    expect(slotOptions(g, sd(), undefined, false).every((o) => !o.full)).toBe(true);
  });
  it("blocks: one option per block start, mapped onto its period", () => {
    const opts = slotOptions(g, sd({ unit: "blocks", block_minutes: 30, last_period: 2 }), { date: D, time: "08:40" }, true);
    expect(opts.map((o) => o.time)).toEqual(["09:00", "09:30", "10:00"]);
    expect(opts.map((o) => o.periodId)).toEqual([1, 2, 2]);
  });
  it("the default is the first option that is not full", () => {
    const opts = slotOptions(g, sd(), { date: D, time: "08:40" }, true);
    expect(defaultSlot(opts)?.key).toBe("p3");
    expect(defaultSlot([])).toBeNull();
  });
});

describe("length and span", () => {
  const g = grid([]);
  it("periods: consecutive visible periods from the start; lengths within the admin's range", () => {
    const visible = g.periods;
    const p3 = slotOptions(g, sd(), undefined, false).find((o) => o.key === "p3")!;
    expect(spanFor(visible, p3, 2, sd())?.map((p) => p.id)).toEqual([3, 4]);
    expect(lengthChoices(visible, p3, sd({ quick_span: 4 }))).toEqual([1, 2]); // P3, P4; P17 is hours later
    expect(lengthChoices(visible, p3, sd())).toEqual([1]);
  });
  it("blocks: the minutes cover whole periods", () => {
    const s = sd({ unit: "blocks", block_minutes: 30, quick_span: 4 });
    const opt = slotOptions(g, s, undefined, false).find((o) => o.time === "09:00")!;
    expect(spanFor(g.periods, opt, 2, s)?.map((p) => p.id)).toEqual([1, 2]); // 09:00-10:00 → P1 + P2
    expect(lengthChoices(g.periods, opt, s)).toEqual([1, 2, 3, 4]);
  });
});

describe("find query", () => {
  it("one date, the span's grid periods, only bookable rooms, no flex", () => {
    const span = [periods[2]!, periods[3]!];
    expect(findQuery({ date: D, termId: 1, span, headcount: 30, features: [5] })).toEqual({
      term_id: 1,
      date: D,
      start: 3,
      duration_periods: 2,
      headcount: 30,
      features: [{ field: 5 }],
      include_busy: false,
      include_requestable: true,
      flex: { periods: 0 },
      limit: 60,
    });
  });
});

describe("ranking", () => {
  const row = (code: string, extra: Partial<FindRow>): FindRow => ({ room_id: Number(code.replace(/\D/g, "")), code, name: code, building: null, capacity: 40, exam_capacity: 0, tags: [], features: [], status: "free", action: "book", start_period: 3, end_period: 3, reason: null, fit: { waste_pct: 0, score: 1 }, reasons: [], busy_with: null, free_dates: 1, open_dates: 1, per_date: null, period_ids: [3], period_id: 3, ...extra }) as FindRow;
  it("bookable rows only; server score first, then recently used, direct before request, smaller room, code", () => {
    const rows = [
      row("B201", { fit: { waste_pct: 0, score: 0.5 } }),
      row("A103", { action: "request", status: "requestable" }),
      row("A102", { capacity: 60 }),
      row("A101", { capacity: 60 }),
      row("A104", {}),
      row("C301", { status: "busy", action: "none" }),
      row("A105", { status: "mine_pending", action: "none" }),
    ];
    const ranked = rankRooms(rows, new Set([102]));
    expect(ranked.map((r) => r.code)).toEqual(["A102", "A104", "A101", "A103", "A105", "B201"]);
    expect(roomAction(ranked[3]!)).toBe("request");
    expect(roomAction(ranked[4]!)).toBe("mine");
    expect(roomAction(ranked[0]!)).toBe("book");
  });
});
