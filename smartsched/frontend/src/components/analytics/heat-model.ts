/**
 * Pure helpers of the utilisation heatmaps: cell lookup, column headers (weekday or exam date), the overview and
 * room drill-down rows, the URL state and the instructor matrix scaling.
 */
import type { GroupBy, HeatCell, HeatColumn, HeatCount, InstructorHeatmap, RoomHeatmap } from "@/lib/api/analytics";
import { GROUP_BY } from "@/lib/api/analytics";
import type { CountLike } from "./heat-scale";

export const cellKey = (col: string, period: number) => `${col}|${period}`;

export function indexCells(cells: readonly HeatCell[]): Map<string, HeatCell> {
  const m = new Map<string, HeatCell>();
  for (const c of cells) m.set(cellKey(c.col, c.period), c);
  return m;
}

/** a weekday column → "Pzt"; an exam date column → "Çar" + "13.05" */
export function columnHeader(col: HeatColumn, locale: string): { label: string; sub?: string; text: string } {
  const loc = locale.startsWith("tr") ? "tr-TR" : "en-GB";
  const ref = new Date(Date.UTC(2024, 0, col.day)); // 2024-01-01 is a Monday: day 1..7 → Mon..Sun
  const short = new Intl.DateTimeFormat(loc, { weekday: "short", timeZone: "UTC" }).format(ref);
  const long = new Intl.DateTimeFormat(loc, { weekday: "long", timeZone: "UTC" }).format(ref);
  if (col.date) {
    const d = new Date(`${col.date}T00:00:00Z`);
    const [, mm, dd] = col.date.split("-");
    const dm = loc === "tr-TR" ? `${dd}.${mm}` : new Intl.DateTimeFormat(loc, { day: "2-digit", month: "2-digit", timeZone: "UTC" }).format(d);
    const full = new Intl.DateTimeFormat(loc, { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(d);
    return { label: short, sub: dm, text: full };
  }
  return { label: short, text: long };
}

export type Source = "live" | "run";
export type Scope = "week" | "term";
export type HeatTab = "rooms" | "instructors";

export interface HeatUrlState {
  tab: HeatTab;
  source: Source;
  run: number | null;
  group: GroupBy;
  scope: Scope;
  week: number | null;
  bookings: boolean;
  blocks: boolean;
  /** the drilled-down group key ("" = all rooms) */
  g: string;
}

const int = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null);

export function readHeatUrl(p: URLSearchParams): HeatUrlState {
  const run = int(p.get("run"));
  const group = p.get("group");
  return {
    tab: p.get("tab") === "instructors" ? "instructors" : "rooms",
    source: p.get("source") === "run" && run !== null ? "run" : "live",
    run,
    group: (GROUP_BY as readonly string[]).includes(group ?? "") ? (group as GroupBy) : "building",
    scope: p.get("scope") === "term" ? "term" : "week",
    week: int(p.get("week")),
    bookings: p.get("bookings") !== "0",
    blocks: p.get("blocks") !== "0",
    g: p.get("g") ?? "",
  };
}

export interface OverviewRow {
  key: string;
  label: { tr: string; en: string };
  rooms: number;
  roomId: number | null;
  byCol: Map<string, HeatCount>;
  total: HeatCount;
}

/** "Tümü" (every room) first, then one row per group, each with its per-column totals */
export function overviewRows(data: RoomHeatmap): OverviewRow[] {
  const all: OverviewRow = {
    key: "",
    label: { tr: "Tüm derslikler", en: "All rooms" },
    rooms: data.overall.rooms,
    roomId: null,
    byCol: new Map(data.overall.by_col.map((c) => [c.col, c])),
    total: data.overall.total,
  };
  const rows = data.rows.map((r) => ({
    key: r.key,
    label: r.label,
    rooms: r.rooms,
    roomId: data.group_by === "room" && r.room_ids.length === 1 ? r.room_ids[0]! : null,
    byCol: new Map(r.by_col.map((c) => [c.col, c])),
    total: r.total,
  }));
  return [all, ...rows];
}

/** the cells of the drilled-down group (or of all rooms) */
export function detailCells(data: RoomHeatmap, g: string): Map<string, HeatCell> {
  const row = g ? data.rows.find((r) => r.key === g) : undefined;
  return indexCells(row ? row.cells : data.overall.cells);
}

/** instructors teaching in a slot, coloured relative to the busiest slot (100 = the busiest) */
export function instructorMatrix(data: InstructorHeatmap): { cell: (day: number, period: number) => (CountLike & { count: number }) | undefined; max: number } {
  const m = new Map<string, { instructors: number; pct: number }>();
  let max = 0;
  for (const x of data.matrix) {
    m.set(`${x.day}|${x.period}`, x);
    max = Math.max(max, x.instructors);
  }
  return {
    max,
    cell: (day, period) => {
      const x = m.get(`${day}|${period}`);
      if (!x) return undefined;
      return { occupied: x.instructors, blocked: 0, capacity: Math.max(1, data.instructors_total), pct: max ? (x.instructors / max) * 100 : 0, count: x.instructors };
    },
  };
}

/** a person's own week: share of the weeks in scope they teach in a slot (1 = every week) */
export function personMatrix(cells: InstructorHeatmap["rows"][number]["cells"]): (day: number, period: number) => CountLike | undefined {
  const m = new Map(cells.map((c) => [`${c.day}|${c.period}`, c]));
  return (day, period) => {
    const c = m.get(`${day}|${period}`);
    return { occupied: c ? 1 : 0, blocked: 0, capacity: 1, pct: c ? c.share * 100 : 0 };
  };
}
