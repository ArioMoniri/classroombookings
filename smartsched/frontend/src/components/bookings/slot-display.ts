/**
 * W3-SLOT: how a slot is shown wherever bookings appear (docs/design/v3/slot-display.md): the grid, the free-slot
 * list, quick reserve (/reserve), and find-room / the kiosk once they read it. The administrator decides it; the
 * backend keeps it as `booking.slot_display.*` settings (app/services/settings_service.py SPECS) and hands every
 * signed-in user the sanitised values (`GET /bookings/slot-display`, also `slot_display` in `GET /bookings/context`).
 *
 * Bookings stay per period. "Blocks" is a way of *showing and choosing* time: a period's size follows its minutes and
 * is drawn as 15/30/60-minute blocks; a block start maps onto the period that contains it and a length in blocks covers
 * whole periods (`coverPeriods`). Pure and unit-tested (slot-display.test.ts); the hook is use-slot-display.ts.
 */
import type { Grid, GridPeriod } from "@/lib/api/crbs";

export type SlotUnit = "periods" | "blocks";
export type SlotLabelMode = "both" | "period" | "time";
export type PeriodNameMode = "schedule" | "ordinal";
export type TimeFormat = "range" | "start";
export type SlotDensity = "standard" | "compact" | "comfortable";
export type DesktopView = "grid_day" | "grid_room_week" | "free_slots" | "free_week" | "quick";
export type PhoneView = "free_slots" | "free_week" | "quick";

export interface SlotDisplay {
  unit: SlotUnit;
  block_minutes: 15 | 30 | 60;
  label: SlotLabelMode;
  period_name: PeriodNameMode;
  time_format: TimeFormat;
  density: SlotDensity;
  /** first / last visible period number (`start_period`); 0 = no limit */
  first_period: number;
  last_period: number;
  /** hide periods shorter than 35 minutes (transition slots) */
  hide_short: boolean;
  hide_weekend: boolean;
  /** null: the organisation's CRBS display type (Kuruluş › Rezervasyon) decides */
  default_view_desktop: DesktopView | null;
  default_view_phone: PhoneView;
  /** quick reserve lengths in the unit (periods or blocks): min_length … quick_span */
  min_length: number;
  quick_span: number;
}

export const SLOT_KEY_PREFIX = "booking.slot_display.";
export const BLOCK_MINUTES = [15, 30, 60] as const;
export const LENGTH_MAX = 8;
export const SHORT_MINUTES = 35;
export const DESKTOP_VIEWS: readonly DesktopView[] = ["grid_day", "grid_room_week", "free_slots", "free_week", "quick"];
export const PHONE_VIEWS: readonly PhoneView[] = ["free_slots", "free_week", "quick"];

export const DEFAULT_SLOT_DISPLAY: SlotDisplay = {
  unit: "periods",
  block_minutes: 30,
  label: "both",
  period_name: "schedule",
  time_format: "range",
  density: "standard",
  first_period: 0,
  last_period: 0,
  hide_short: false,
  hide_weekend: false,
  default_view_desktop: null,
  default_view_phone: "free_slots",
  min_length: 1,
  quick_span: 1,
};

const pick = <T extends string>(v: unknown, allowed: readonly T[], fallback: T): T => (typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : fallback);
const intIn = (v: unknown, lo: number, hi: number, fallback: number) => (typeof v === "number" && Number.isInteger(v) ? Math.max(lo, Math.min(hi, v)) : fallback);

/** Lenient, the backend's rules: anything unknown becomes the default (an older backend answers 404 and every surface keeps today's look). */
export function parseSlotDisplay(raw: unknown): SlotDisplay {
  const r = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  let first = intIn(r.first_period, 0, 30, 0);
  let last = intIn(r.last_period, 0, 30, 0);
  if (first && last && first > last) first = last = 0;
  const block = Number(r.block_minutes);
  const min = intIn(r.min_length, 1, LENGTH_MAX, 1);
  return {
    unit: pick(r.unit, ["periods", "blocks"] as const, "periods"),
    block_minutes: (BLOCK_MINUTES as readonly number[]).includes(block) ? (block as 15 | 30 | 60) : 30,
    label: pick(r.label, ["both", "period", "time"] as const, "both"),
    period_name: pick(r.period_name, ["schedule", "ordinal"] as const, "schedule"),
    time_format: pick(r.time_format, ["range", "start"] as const, "range"),
    density: pick(r.density, ["standard", "compact", "comfortable"] as const, "standard"),
    first_period: first,
    last_period: last,
    hide_short: r.hide_short === true,
    hide_weekend: r.hide_weekend === true,
    default_view_desktop: typeof r.default_view_desktop === "string" && (DESKTOP_VIEWS as readonly string[]).includes(r.default_view_desktop) ? (r.default_view_desktop as DesktopView) : null,
    default_view_phone: pick(r.default_view_phone, PHONE_VIEWS, "free_slots"),
    min_length: min,
    quick_span: Math.max(min, intIn(r.quick_span, 1, LENGTH_MAX, 1)),
  };
}

/** minutes since midnight of "HH:MM" (or "HH:MM:SS") */
export function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

export function hhmm(total: number): string {
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export const duration = (p: Pick<GridPeriod, "time_start" | "time_end">) => minutes(p.time_end) - minutes(p.time_start);

type PeriodLike = Pick<GridPeriod, "id" | "name" | "time_start" | "time_end" | "start_period">;

/** A display filter, never a permission (slot-display.md §3): hidden periods still show in My bookings. */
export function periodVisible(p: PeriodLike, sd: SlotDisplay): boolean {
  if (sd.first_period && p.start_period < sd.first_period) return false;
  if (sd.last_period && p.start_period > sd.last_period) return false;
  if (sd.hide_short && duration(p) < SHORT_MINUTES) return false;
  return true;
}

export function isWeekend(date: string): boolean {
  const d = new Date(`${date}T12:00:00`).getDay();
  return d === 0 || d === 6;
}

/** Does the display hide anything at all (periods or the weekend)? */
export function filters(sd: SlotDisplay): boolean {
  return !!(sd.first_period || sd.last_period || sd.hide_short || sd.hide_weekend);
}

/**
 * The grid as the administrator wants it shown: hidden periods and (hide_weekend, week grids) Saturday and Sunday
 * removed, with their slots. Returns the same object when nothing changes (memoised children keep their identity).
 * `reveal` (the "+N gizli saat" chip) shows everything for the session.
 */
export function applySlotDisplay(grid: Grid, sd: SlotDisplay, reveal = false): Grid {
  if (reveal || !filters(sd)) return grid;
  const periods = grid.periods.filter((p) => periodVisible(p, sd));
  // a day grid keeps its one date even on a weekend (the user navigated there on purpose)
  const dates = sd.hide_weekend && grid.display !== "day" ? grid.dates.filter((d) => !isWeekend(d.date)) : grid.dates;
  if (periods.length === grid.periods.length && dates.length === grid.dates.length) return grid;
  const keepP = new Set(periods.map((p) => p.id));
  const keepD = new Set(dates.map((d) => d.date));
  return { ...grid, periods, dates, slots: grid.slots.filter((s) => keepP.has(s.period_id) && keepD.has(s.date)) };
}

export function hiddenPeriodCount(periods: readonly PeriodLike[], sd: SlotDisplay): number {
  return periods.filter((p) => !periodVisible(p, sd)).length;
}

/* -------------------------------------------------------------------------------- one label rule (§5) */

export interface SlotText {
  primary: string;
  secondary: string | null;
  /** one line: "3. ders · 10:10" */
  inline: string;
  /** always complete: the period and the full time range, whatever is visible (visible text first, WCAG 2.5.3) */
  a11y: string;
}

export interface LabelFormat {
  /** HH:MM for the locale */
  time: (hhmm: string) => string;
  /** "3. ders" / "Period 3" */
  ordinal: (n: number) => string;
}

export function periodName(p: PeriodLike, sd: SlotDisplay, f: LabelFormat): string {
  const ordinal = f.ordinal(p.start_period);
  return sd.period_name === "ordinal" ? ordinal : p.name.trim() || ordinal;
}

export function slotLabel(p: PeriodLike, sd: SlotDisplay, f: LabelFormat): SlotText {
  const range = `${f.time(p.time_start)}–${f.time(p.time_end)}`;
  const time = sd.time_format === "start" ? f.time(p.time_start) : range;
  const name = periodName(p, sd, f);
  if (sd.label === "period") return { primary: name, secondary: null, inline: name, a11y: `${name}, ${range}` };
  if (sd.label === "time") return { primary: time, secondary: null, inline: time, a11y: `${range}, ${name}` };
  return { primary: name, secondary: time, inline: `${name} · ${time}`, a11y: `${name}, ${range}` };
}

/* ----------------------------------------------------------------------- blocks mapped onto periods */

/** How many blocks of `size` minutes a period spans (at least 1). */
export function blockCount(p: Pick<GridPeriod, "time_start" | "time_end">, size: number): number {
  return Math.max(1, Math.ceil(duration(p) / size));
}

/** px per minute of a period's size in "blocks" mode, by density (slot-display.md §6: 1.1 / 1.4 / 1.8) */
export const PX_PER_MIN: Record<SlotDensity, number> = { compact: 1.1, standard: 1.4, comfortable: 1.8 };

/** A period column's width: equal (78 / 64 compact / 92 comfortable), or proportional to its minutes. */
export function periodWidth(p: Pick<GridPeriod, "time_start" | "time_end">, sd: SlotDisplay): number {
  if (sd.unit === "blocks") return Math.max(sd.density === "compact" ? 44 : 56, Math.round(duration(p) * PX_PER_MIN[sd.density]));
  return sd.density === "compact" ? 64 : sd.density === "comfortable" ? 92 : 78;
}

/** A period row's height (px) on a fine pointer; touch never goes below 44 (the caller clamps with CSS). */
export function periodHeight(p: Pick<GridPeriod, "time_start" | "time_end">, sd: SlotDisplay): number {
  if (sd.unit === "blocks") return Math.max(32, Math.round(duration(p) * PX_PER_MIN[sd.density]));
  return sd.density === "compact" ? 32 : sd.density === "comfortable" ? 56 : 44;
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
 * between two periods still counts as consecutive), or null when the start is in no period or the span runs past them.
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

/** Quick reserve length choices in the unit: min_length … quick_span, never more than `available`. */
export function lengthOptions(sd: SlotDisplay, available: number): number[] {
  const out: number[] = [];
  for (let n = sd.min_length; n <= Math.min(available, Math.max(sd.min_length, sd.quick_span)); n++) out.push(n);
  return out;
}

/* ----------------------------------------------------------------------------------------- default view */

export interface OpeningView {
  display: "day" | "room";
  lens: "grid" | "free";
  scope: "day" | "week";
  /** the administrator chose quick reserve as the landing view */
  quick: boolean;
}

/** What /bookings opens on without URL parameters: the phone set never holds a multi-room grid (MOBILE M-08). */
export function openingView(sd: SlotDisplay, phone: boolean, org: "day" | "room" | undefined): OpeningView {
  const view: DesktopView | null = phone ? sd.default_view_phone : sd.default_view_desktop;
  switch (view) {
    case "grid_day":
      return { display: "day", lens: "grid", scope: "day", quick: false };
    case "grid_room_week":
      return { display: "room", lens: "grid", scope: "day", quick: false };
    case "free_slots":
      return { display: "day", lens: "free", scope: "day", quick: false };
    case "free_week":
      return { display: "day", lens: "free", scope: "week", quick: false };
    case "quick":
      return { display: "day", lens: phone ? "free" : "grid", scope: "day", quick: true };
    default:
      return { display: org ?? "day", lens: phone ? "free" : "grid", scope: "day", quick: false };
  }
}

/* ----------------------------------------------------------------------------------------------- saving */

/** PUT /settings `extra` for the whole display (an empty string resets a key to its default). */
export function slotDisplayExtra(sd: SlotDisplay): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(sd) as [keyof SlotDisplay, SlotDisplay[keyof SlotDisplay]][]) out[`${SLOT_KEY_PREFIX}${k}`] = v ?? "";
  return out;
}
