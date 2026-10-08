/**
 * Booking grid model (CRBS `components/bookings/Grid`): the backend sends flat slots; the page lays them
 * out on two axes chosen by the display type and the org's "columns" setting:
 *
 * | display | columns   | rows    | columns |
 * |---------|-----------|---------|---------|
 * | day     | periods   | rooms   | periods |
 * | day     | rooms     | periods | rooms   |
 * | room    | periods   | days    | periods |
 * | room    | days      | periods | days    |
 */
import type { Grid, GridPeriod, GridRoom, GridSlot, DateInfo } from "@/lib/api/crbs";

export type AxisKind = "room" | "period" | "date";

export interface AxisItem {
  kind: AxisKind;
  key: string;
  room?: GridRoom;
  period?: GridPeriod;
  date?: DateInfo;
}

export interface GridLayout {
  rows: AxisItem[];
  cols: AxisItem[];
  slot: (row: AxisItem, col: AxisItem) => GridSlot | undefined;
}

export function slotKey(s: { date: string; period_id: number; room_id: number }): string {
  return `${s.date}|${s.period_id}|${s.room_id}`;
}

export function parseSlotKey(key: string): { date: string; period_id: number; room_id: number } {
  const [date = "", p = "0", r = "0"] = key.split("|");
  return { date, period_id: Number(p), room_id: Number(r) };
}

/**
 * Days a week view should not list (CRBS `Context` / `Dates_model`): outside the session, or with no period
 * running that weekday. Holidays stay visible (they are shown as holidays).
 */
export function hiddenDays(grid: Grid): Set<string> {
  const out = new Set<string>();
  if (grid.display !== "room") return out;
  for (const d of grid.dates) {
    if (d.date < grid.term.start || d.date > grid.term.end || d.reason === "date_range") {
      out.add(d.date);
      continue;
    }
    const runs = grid.periods.some((p) => !p.days || p.days.includes(d.weekday));
    if (!runs && d.reason !== "holiday") out.add(d.date);
  }
  return out;
}

export function layoutGrid(grid: Grid, columns: "periods" | "rooms" | "days"): GridLayout {
  const index = new Map<string, GridSlot>();
  for (const s of grid.slots) index.set(slotKey(s), s);
  const hidden = hiddenDays(grid);
  const rooms: AxisItem[] = grid.rooms.map((r) => ({ kind: "room", key: `r${r.id}`, room: r }));
  const periods: AxisItem[] = grid.periods.map((p) => ({ kind: "period", key: `p${p.id}`, period: p }));
  const dates: AxisItem[] = grid.dates.filter((d) => !hidden.has(d.date)).map((d) => ({ kind: "date", key: d.date, date: d }));
  const onlyRoom = grid.rooms[0];
  let rows: AxisItem[];
  let cols: AxisItem[];
  if (grid.display === "day") {
    [rows, cols] = columns === "rooms" ? [periods, rooms] : [rooms, periods];
  } else {
    [rows, cols] = columns === "days" ? [periods, dates] : [dates, periods];
  }
  const pick = (a: AxisItem, b: AxisItem) => {
    const items = [a, b];
    const room = items.find((x) => x.kind === "room")?.room ?? onlyRoom;
    const period = items.find((x) => x.kind === "period")?.period;
    const date = items.find((x) => x.kind === "date")?.date?.date ?? grid.date;
    if (!room || !period) return undefined;
    return index.get(slotKey({ date, period_id: period.id, room_id: room.id }));
  };
  return { rows, cols, slot: pick };
}

export function isSelectable(slot: GridSlot | undefined): boolean {
  return !!slot && slot.status === "available" && !!(slot.allow_single || slot.allow_recur);
}

export type SlotTone = "available" | "booked-single" | "booked-recurring" | "booked-mine" | "timetable" | "holiday" | "unavailable";

export function slotTone(slot: GridSlot | undefined): SlotTone {
  if (!slot) return "unavailable";
  if (slot.status === "available") return isSelectable(slot) ? "available" : "unavailable";
  if (slot.status === "booked") {
    if (slot.booking?.is_owner) return "booked-mine";
    return slot.reason === "recurring" ? "booked-recurring" : "booked-single";
  }
  if (slot.status === "timetable") return "timetable";
  return slot.reason === "holiday" ? "holiday" : "unavailable";
}

export interface SlotText {
  /** main line: who / what holds it */
  primary: string | null;
  /** second line: notes or department */
  secondary: string | null;
}

/**
 * What a slot says, following the viewer's permissions and the "show names" setting: the backend already
 * blanks `user_name` / `notes` when the viewer may not see them (`user_hidden`, `notes_hidden`), so the
 * label falls back to a neutral "Booked" instead of a name.
 */
export function slotText(slot: GridSlot | undefined, labels: { booked: string; mine: string }): SlotText {
  if (!slot) return { primary: null, secondary: null };
  if (slot.status === "booked" && slot.booking) {
    const b = slot.booking;
    const who = b.is_owner ? labels.mine : b.user_name || labels.booked;
    const secondary = b.notes || b.department_name || null;
    return { primary: who, secondary };
  }
  if (slot.status === "timetable") return { primary: slot.label ?? null, secondary: null };
  if (slot.status === "unavailable" && slot.reason === "holiday") return { primary: slot.label ?? null, secondary: null };
  return { primary: null, secondary: null };
}

/** Keyboard navigation inside the grid (roving focus): next cell coordinates, clamped. */
export function moveFocus(pos: { r: number; c: number }, key: string, size: { rows: number; cols: number }): { r: number; c: number } | null {
  const clamp = (v: number, max: number) => Math.max(0, Math.min(max - 1, v));
  switch (key) {
    case "ArrowRight":
      return { r: pos.r, c: clamp(pos.c + 1, size.cols) };
    case "ArrowLeft":
      return { r: pos.r, c: clamp(pos.c - 1, size.cols) };
    case "ArrowDown":
      return { r: clamp(pos.r + 1, size.rows), c: pos.c };
    case "ArrowUp":
      return { r: clamp(pos.r - 1, size.rows), c: pos.c };
    case "Home":
      return { r: pos.r, c: 0 };
    case "End":
      return { r: pos.r, c: size.cols - 1 };
    default:
      return null;
  }
}

/** CRBS `grid_highlight`: CSS that tints the row and column under the pointer (one rule, no per-cell state). */
export function crosshairCss(scope: string, pos: { r: number; c: number } | null): string {
  if (!pos) return "";
  const tint = "box-shadow: inset 0 0 0 999px color-mix(in oklab, var(--status-warning-solid) 16%, transparent);";
  return `[data-grid-scope="${scope}"] tr[data-r="${pos.r}"] > td > button[data-tone="available"], [data-grid-scope="${scope}"] td[data-c="${pos.c}"] > button[data-tone="available"] { ${tint} }`;
}
