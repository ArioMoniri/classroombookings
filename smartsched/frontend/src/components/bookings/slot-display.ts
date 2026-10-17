/**
 * W3-SLOT: how a slot is shown wherever bookings appear (the grid, the free-slot list, quick reserve, find-room and
 * the kiosk once they read it). The administrator decides it in Ayarlar › Rezervasyon › Görünüm; the backend keeps it
 * as `booking.slot_display.*` settings (app/services/settings_service.py SPECS) and hands every signed-in user the
 * sanitised values (`GET /bookings/slot-display`, also `slot_display` in `GET /bookings/context`).
 *
 * Bookings stay per period. "Blocks" (15/30/60 min) is a way of *showing and choosing* time: a block start maps onto
 * the period that contains it and a length in blocks covers whole periods (`coverPeriods`). Pure and unit-tested
 * (slot-display.test.ts); the hook is use-slot-display.ts.
 */
import type { Grid, GridPeriod } from "@/lib/api/crbs";

export type SlotUnit = "periods" | "blocks";
export type SlotLabelMode = "both" | "name" | "time";
export type SlotDensity = "comfortable" | "compact";
export type SlotView = "day" | "room" | "week";

export interface SlotDisplay {
  unit: SlotUnit;
  block_minutes: 15 | 30 | 60;
  label: SlotLabelMode;
  density: SlotDensity;
  /** null: the organisation's CRBS display type (Kuruluş › Rezervasyon) decides */
  default_view: SlotView | null;
  /** "HH:MM" window; periods outside are hidden (null = the whole day) */
  day_start: string | null;
  day_end: string | null;
  hide_weekend: boolean;
  /** period names never shown, matched case-insensitively */
  hidden_periods: string[];
  /** the shortest booking the simple surfaces offer, in the unit (periods or blocks), 1..8 */
  min_length: number;
}

export const SLOT_KEY_PREFIX = "booking.slot_display.";
export const BLOCK_MINUTES = [15, 30, 60] as const;
export const MIN_LENGTH_MAX = 8;

export const DEFAULT_SLOT_DISPLAY: SlotDisplay = {
  unit: "periods",
  block_minutes: 30,
  label: "both",
  density: "comfortable",
  default_view: null,
  day_start: null,
  day_end: null,
  hide_weekend: false,
  hidden_periods: [],
  min_length: 1,
};

const pick = <T extends string>(v: unknown, allowed: readonly T[], fallback: T): T => (typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : fallback);

/** "HH:MM" or null (also the backend's rule). */
export function clock(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const m = /^(\d{1,2}):(\d{2})$/.exec(v.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  return h <= 23 && min <= 59 ? `${String(h).padStart(2, "0")}:${m[2]}` : null;
}

/** Lenient: anything unknown becomes the default (an older backend answers 404 and every surface keeps today's look). */
export function parseSlotDisplay(raw: unknown): SlotDisplay {
  const r = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  let start = clock(r.day_start);
  let end = clock(r.day_end);
  if (start && end && start >= end) start = end = null;
  const block = Number(r.block_minutes);
  const len = Number(r.min_length);
  const hidden = Array.isArray(r.hidden_periods) ? r.hidden_periods.filter((x): x is string => typeof x === "string" && !!x.trim()).map((x) => x.trim()) : [];
  return {
    unit: pick(r.unit, ["periods", "blocks"] as const, "periods"),
    block_minutes: (BLOCK_MINUTES as readonly number[]).includes(block) ? (block as 15 | 30 | 60) : 30,
    label: pick(r.label, ["both", "name", "time"] as const, "both"),
    density: pick(r.density, ["comfortable", "compact"] as const, "comfortable"),
    default_view: r.default_view === "day" || r.default_view === "room" || r.default_view === "week" ? r.default_view : null,
    day_start: start,
    day_end: end,
    hide_weekend: r.hide_weekend === true,
    hidden_periods: hidden,
    min_length: Number.isInteger(len) && len >= 1 ? Math.min(MIN_LENGTH_MAX, len) : 1,
  };
}

export function isDefaultDisplay(sd: SlotDisplay): boolean {
  return JSON.stringify(sd) === JSON.stringify(DEFAULT_SLOT_DISPLAY);
}

/** minutes since midnight of "HH:MM" (or "HH:MM:SS") */
export function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

export function hhmm(total: number): string {
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

type PeriodLike = Pick<GridPeriod, "id" | "name" | "time_start" | "time_end">;

export function periodVisible(p: PeriodLike, sd: SlotDisplay): boolean {
  const name = p.name.trim().toLocaleLowerCase("tr");
  if (sd.hidden_periods.some((h) => h.toLocaleLowerCase("tr") === name)) return false;
  if (sd.day_start && minutes(p.time_start) < minutes(sd.day_start)) return false;
  if (sd.day_end && minutes(p.time_end) > minutes(sd.day_end)) return false;
  return true;
}

export function isWeekend(date: string): boolean {
  const d = new Date(`${date}T12:00:00`).getDay();
  return d === 0 || d === 6;
}

/**
 * The grid as the administrator wants it shown: hidden / out-of-window periods and (hide_weekend) Saturday and
 * Sunday removed, with their slots. Returns the same object when nothing changes (memoised children keep identity).
 */
export function applySlotDisplay(grid: Grid, sd: SlotDisplay): Grid {
  const periods = grid.periods.filter((p) => periodVisible(p, sd));
  const dates = sd.hide_weekend ? grid.dates.filter((d) => !isWeekend(d.date)) : grid.dates;
  if (periods.length === grid.periods.length && dates.length === grid.dates.length) return grid;
  const keepP = new Set(periods.map((p) => p.id));
  const keepD = new Set(dates.map((d) => d.date));
  // a day grid keeps its one date even on a weekend (the user navigated there on purpose)
  const dayGrid = grid.display === "day";
  return {
    ...grid,
    periods,
    dates: dayGrid ? grid.dates : dates,
    slots: grid.slots.filter((s) => keepP.has(s.period_id) && (dayGrid || keepD.has(s.date))),
  };
}

export interface PeriodText {
  title: string;
  sub: string | null;
  /** one line (chips, accessible names) */
  text: string;
}

/** A period's label: "P3", "10:30–11:20" or both (title + sub), as chosen. `time` formats HH:MM for the locale. */
export function periodLabel(p: PeriodLike, sd: SlotDisplay, time: (hhmm: string) => string): PeriodText {
  const range = `${time(p.time_start)}–${time(p.time_end)}`;
  if (sd.label === "name") return { title: p.name, sub: null, text: p.name };
  if (sd.label === "time") return { title: range, sub: null, text: range };
  return { title: p.name, sub: range, text: `${p.name} · ${range}` };
}

/** How many blocks of `size` minutes a period spans (at least 1). */
export function blockCount(p: Pick<GridPeriod, "time_start" | "time_end">, size: number): number {
  return Math.max(1, Math.ceil((minutes(p.time_end) - minutes(p.time_start)) / size));
}

export interface BlockStart {
  /** HH:MM */
  time: string;
  /** the period the block falls in (what gets booked) */
  periodId: number;
}

/** Block starts inside the given (visible) periods, in time order. */
export function blockStarts(periods: readonly PeriodLike[], sd: SlotDisplay): BlockStart[] {
  const out: BlockStart[] = [];
  for (const p of [...periods].sort((a, b) => minutes(a.time_start) - minutes(b.time_start))) {
    for (let t = minutes(p.time_start); t < minutes(p.time_end); t += sd.block_minutes) out.push({ time: hhmm(t), periodId: p.id });
  }
  return out;
}

/**
 * The whole periods that cover [start, start + length): consecutive in time order (a break of up to 20 minutes
 * between two periods is still "consecutive"), or null when the start is in no period or the span runs past them.
 */
export function coverPeriods<T extends PeriodLike>(periods: readonly T[], start: string, length: number): T[] | null {
  const sorted = [...periods].sort((a, b) => minutes(a.time_start) - minutes(b.time_start));
  const s = minutes(start);
  const end = s + length;
  const i = sorted.findIndex((p) => minutes(p.time_start) <= s && s < minutes(p.time_end));
  if (i < 0) return null;
  const out: T[] = [sorted[i]!];
  let reach = minutes(sorted[i]!.time_end);
  for (let k = i + 1; reach < end; k++) {
    const next = sorted[k];
    if (!next || minutes(next.time_start) - reach > 20) return null;
    out.push(next);
    reach = minutes(next.time_end);
  }
  return out;
}

/** Length choices in the unit: from the minimum, at most four, never more than `available`. */
export function lengthOptions(sd: SlotDisplay, available: number): number[] {
  const out: number[] = [];
  for (let n = sd.min_length; n <= Math.min(available, sd.min_length + 3); n++) out.push(n);
  return out;
}

/* ----------------------------------------------------------------------------------------- default view */

export function defaultDisplay(sd: SlotDisplay, org: "day" | "room" | undefined): "day" | "room" {
  if (sd.default_view === "room") return "room";
  if (sd.default_view === "day" || sd.default_view === "week") return "day";
  return org ?? "day";
}

export function defaultLens(sd: SlotDisplay, phone: boolean): "grid" | "free" {
  return phone || sd.default_view === "week" ? "free" : "grid";
}

export function defaultScope(sd: SlotDisplay): "day" | "week" {
  return sd.default_view === "week" ? "week" : "day";
}

/* ----------------------------------------------------------------------------------------------- saving */

/** PUT /settings `extra` for the whole display (an empty string resets a key to its default). */
export function slotDisplayExtra(sd: SlotDisplay): Record<string, string | number | boolean> {
  const k = (name: keyof SlotDisplay) => `${SLOT_KEY_PREFIX}${name}`;
  return {
    [k("unit")]: sd.unit,
    [k("block_minutes")]: sd.block_minutes,
    [k("label")]: sd.label,
    [k("density")]: sd.density,
    [k("default_view")]: sd.default_view ?? "",
    [k("day_start")]: sd.day_start ?? "",
    [k("day_end")]: sd.day_end ?? "",
    [k("hide_weekend")]: sd.hide_weekend,
    [k("hidden_periods")]: sd.hidden_periods.join(", "),
    [k("min_length")]: sd.min_length,
  };
}
