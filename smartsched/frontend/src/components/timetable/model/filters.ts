/**
 * Sidebar filters (calendar.md §5.2) applied to rooms (columns/rows) and events (chips), plus the
 * Turkish-aware search fold shared with /classes (İ/ı, diacritics, spaces: "phar240" finds "PHAR 240").
 */
import type { IndexRoom } from "@/lib/api/calendar";
import type { CalEvent } from "./index-model";

export type StatusFilter = "conflict" | "warning" | "locked" | "partial" | "preoccupied" | "booking";

export interface CalendarFilters {
  buildings: string[];
  slots: number[];
  tags: string[];
  status: StatusFilter[];
  minCap: number;
  query: string;
  /** Day timeline "Şu an boş" */
  freeNow: boolean;
}

export const EMPTY_FILTERS: CalendarFilters = { buildings: [], slots: [], tags: [], status: [], minCap: 0, query: "", freeNow: false };

export const CAPACITY_BUCKETS = [30, 40, 58, 64, 72, 96, 120, 156] as const;

/** Turkish casefold + diacritic fold + no spaces. */
export function fold(text: string | null | undefined): string {
  return (text ?? "")
    .replace(/İ/g, "i")
    .replace(/I/g, "ı")
    .toLocaleLowerCase("tr-TR")
    .replace(/ı/g, "i")
    .replace(/ş/g, "s")
    .replace(/ğ/g, "g")
    .replace(/ç/g, "c")
    .replace(/ö/g, "o")
    .replace(/ü/g, "u")
    .replace(/â/g, "a")
    .replace(/î/g, "i")
    .replace(/û/g, "u")
    .replace(/\s+/g, "");
}

export function activeFilterCount(f: CalendarFilters): number {
  return f.buildings.length + f.slots.length + f.tags.length + f.status.length + (f.minCap > 0 ? 1 : 0) + (f.query.trim() ? 1 : 0) + (f.freeNow ? 1 : 0);
}

export function roomPasses(f: CalendarFilters, r: IndexRoom): boolean {
  if (f.buildings.length && !f.buildings.includes(r.building)) return false;
  if (f.tags.length && !f.tags.some((t) => r.tags.includes(t))) return false;
  if (f.minCap > 0 && r.capacity < f.minCap) return false;
  return true;
}

export function eventPasses(f: CalendarFilters, e: CalEvent): boolean {
  if (f.slots.length && !f.slots.includes(e.a.slot)) return false;
  if (f.status.length) {
    const s = new Set<StatusFilter>();
    if (e.conflict) s.add("conflict");
    if (e.warning) s.add("warning");
    if (e.a.locked) s.add("locked");
    if (!f.status.some((x) => s.has(x))) return false;
  }
  const q = fold(f.query);
  if (q) {
    const hay = fold(`${e.a.label} ${e.a.code ?? ""} ${e.a.name ?? ""} ${e.a.prog ?? ""} ${e.a.instr.join(" ")}`);
    if (!hay.includes(q)) return false;
  }
  return true;
}

/** Does a query look like a room code ("A 204", "a204")? Then it filters rooms instead of chips. */
export function queryMatchesRoom(query: string, r: IndexRoom): boolean {
  const q = fold(query);
  return q.length > 0 && (fold(r.name) === q || fold(r.code) === q);
}
