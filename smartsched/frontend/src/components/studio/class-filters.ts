/**
 * Class list filters (Step 2). The whole term's class list is fetched once (≤ 2 000 rows) and filtered
 * client-side so filters and search feel instant; the predicates mirror the backend's
 * `studio_classes._match` (faculty, programme, year, day, building, mode, changed, quick chips).
 */
import type { ClassRow } from "@/lib/api/studio-schemas";

export type QuickFilter = "needsRoom" | "changed" | "pinned" | "leftOut" | "needsReview" | "evening" | "noDayTime";
export const QUICK_FILTERS: readonly QuickFilter[] = ["needsRoom", "changed", "pinned", "leftOut", "needsReview", "evening", "noDayTime"];

export interface ClassFilters {
  q: string;
  faculty: number | null;
  program: number | null;
  year: number | null;
  day: number | null;
  building: string | null;
  mode: string | null;
  changed: boolean;
  quick: QuickFilter | null;
  /** classes matched by a rule (`?rule=<id>` from a rule card's "applies to N classes") */
  ruleId: number | null;
}

export const EMPTY_FILTERS: ClassFilters = { q: "", faculty: null, program: null, year: null, day: null, building: null, mode: null, changed: false, quick: null, ruleId: null };

/** Draft state the server row may not reflect yet (local edits are autosaved a moment later). */
export interface RowState {
  excluded: ReadonlySet<number>;
  pinned: ReadonlySet<number>;
}

const FOLD: Record<string, string> = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u", â: "a", î: "i", û: "u" };

/** Turkish-aware, diacritic-insensitive search key (İ/ı, Ç → c …), like the backend's `fold`. */
export function fold(text: string | null | undefined): string {
  const lower = String(text ?? "").toLocaleLowerCase("tr-TR");
  const mapped = lower.replace(/[çğıöşüâîû]/g, (ch) => FOLD[ch] ?? ch);
  return mapped.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ");
}

export function haystack(r: ClassRow): string {
  return fold([r.course_code, r.course_name, r.section_label ? `§${r.section_label}` : "", r.program_name, r.faculty_name, ...r.instructors, ...r.requested_room_codes, ...r.definitive_room_codes].join(" "));
}

export function isIncluded(r: ClassRow, s: RowState): boolean {
  return !s.excluded.has(r.id);
}
export function isPinned(r: ClassRow, s: RowState): boolean {
  return s.pinned.has(r.id);
}
export function hasDayTime(r: ClassRow): boolean {
  return r.start_period !== null && r.end_period !== null && (r.day !== null || r.days.length > 0 || r.flexible_day);
}

export function matchesQuick(r: ClassRow, quick: QuickFilter, s: RowState): boolean {
  switch (quick) {
    case "needsRoom":
      return r.needs_room;
    case "changed":
      return r.changed_fields.length > 0;
    case "pinned":
      return isPinned(r, s);
    case "leftOut":
      return !isIncluded(r, s);
    case "needsReview":
      return r.status === "NEEDS_REVIEW";
    case "evening":
      return r.is_evening;
    case "noDayTime":
      return r.needs_room && !hasDayTime(r);
  }
}

export function buildingOf(r: ClassRow): string[] {
  const letters = new Set<string>();
  if (r.requested_building) letters.add(r.requested_building.toLocaleUpperCase("tr-TR").slice(0, 1));
  for (const c of [...r.requested_room_codes, ...r.definitive_room_codes]) if (c) letters.add(c.toLocaleUpperCase("tr-TR").slice(0, 1));
  return [...letters];
}

export function matches(r: ClassRow, f: ClassFilters, s: RowState, hay?: string): boolean {
  if (f.faculty !== null && r.faculty_id !== f.faculty) return false;
  if (f.program !== null && r.program_id !== f.program) return false;
  if (f.year !== null && !(r.class_years.length ? r.class_years : [r.class_year]).includes(f.year)) return false;
  if (f.day !== null && r.day !== f.day && !r.days.includes(f.day)) return false;
  if (f.building !== null && !buildingOf(r).includes(f.building)) return false;
  if (f.mode !== null && (r.mode ?? "").toUpperCase() !== f.mode.toUpperCase()) return false;
  if (f.changed && r.changed_fields.length === 0) return false;
  if (f.ruleId !== null && !r.rule_ids.includes(f.ruleId)) return false;
  if (f.quick !== null && !matchesQuick(r, f.quick, s)) return false;
  const q = fold(f.q).trim();
  if (q) {
    const h = hay ?? haystack(r);
    if (!q.split(" ").every((part) => h.includes(part))) return false;
  }
  return true;
}

export function filterClasses(rows: readonly ClassRow[], f: ClassFilters, s: RowState): ClassRow[] {
  const hasQuery = fold(f.q).trim().length > 0;
  return rows.filter((r) => matches(r, f, s, hasQuery ? haystack(r) : undefined));
}

export function quickCounts(rows: readonly ClassRow[], s: RowState): Record<QuickFilter, number> {
  const out = Object.fromEntries(QUICK_FILTERS.map((q) => [q, 0])) as Record<QuickFilter, number>;
  for (const r of rows) for (const q of QUICK_FILTERS) if (matchesQuick(r, q, s)) out[q]++;
  return out;
}

export function activeFilterCount(f: ClassFilters): number {
  return [f.q.trim() ? 1 : 0, f.faculty, f.program, f.year, f.day, f.building, f.mode, f.changed ? 1 : null, f.quick, f.ruleId].filter((v) => v !== null && v !== 0).length;
}

/** Options for the filter selects, derived from the rows (only values that exist). */
export function filterOptions(rows: readonly ClassRow[]) {
  const faculties = new Map<number, string>();
  const programs = new Map<number, { name: string; faculty: number | null }>();
  const years = new Set<number>();
  const modes = new Set<string>();
  const buildings = new Set<string>();
  for (const r of rows) {
    if (r.faculty_id !== null) faculties.set(r.faculty_id, r.faculty_name ?? `#${r.faculty_id}`);
    if (r.program_id !== null) programs.set(r.program_id, { name: r.program_name ?? `#${r.program_id}`, faculty: r.faculty_id });
    for (const y of r.class_years.length ? r.class_years : r.class_year !== null ? [r.class_year] : []) years.add(y);
    if (r.mode) modes.add(r.mode);
    for (const b of buildingOf(r)) buildings.add(b);
  }
  const byName = <T extends { name: string }>(a: T, b: T) => a.name.localeCompare(b.name, "tr");
  return {
    faculties: [...faculties.entries()].map(([id, name]) => ({ id, name })).sort(byName),
    programs: [...programs.entries()].map(([id, v]) => ({ id, ...v })).sort(byName),
    years: [...years].sort((a, b) => a - b),
    modes: [...modes].sort(),
    buildings: [...buildings].sort(),
  };
}
