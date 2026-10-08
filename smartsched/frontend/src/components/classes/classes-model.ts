/**
 * All-classes query model (docs/design/v2/all-classes.md §6–§8): one filter AST produced by token search,
 * facet popovers and cell quick-facets; system views; facet counts against the other active filters;
 * group keys; saved-view state and its "modified" diff. Pure functions, unit-tested.
 */
import type { ClassRow, PlacementStatus } from "@/lib/api/classes";
import { PERIODS, parseClock, periodEndingAt, snapToPeriod } from "@/lib/time";
import { fold } from "@/components/timetable/model/filters";

export type Where = "placed" | "requested";

export interface ClassFilters {
  faculty: number[];
  program: number[];
  year: number[];
  instructor: string[];
  building: string[];
  buildingWhere: Where;
  room: string[];
  day: number[];
  dayWhere: Where;
  time: { from: number; to: number; mode: "overlap" | "within" } | null;
  mode: string[];
  status: string[];
  placement: PlacementStatus[];
  issue: "any" | "hard" | "soft" | null;
  changed: boolean | null;
  locked: boolean | null;
  text: string;
}

export const EMPTY: ClassFilters = {
  faculty: [],
  program: [],
  year: [],
  instructor: [],
  building: [],
  buildingWhere: "placed",
  room: [],
  day: [],
  dayWhere: "placed",
  time: null,
  mode: [],
  status: [],
  placement: [],
  issue: null,
  changed: null,
  locked: null,
  text: "",
};

/** The 13 filter fields of all-classes.md §7.1 (status covers request + placement). */
export const FILTER_FIELDS = ["faculty", "program", "year", "instructor", "building", "room", "day", "time", "mode", "status", "issue", "changed", "locked"] as const;
export type FilterField = (typeof FILTER_FIELDS)[number];

export function activeFields(f: ClassFilters): FilterField[] {
  const out: FilterField[] = [];
  if (f.faculty.length) out.push("faculty");
  if (f.program.length) out.push("program");
  if (f.year.length) out.push("year");
  if (f.instructor.length) out.push("instructor");
  if (f.building.length) out.push("building");
  if (f.room.length) out.push("room");
  if (f.day.length) out.push("day");
  if (f.time) out.push("time");
  if (f.mode.length) out.push("mode");
  if (f.status.length || f.placement.length) out.push("status");
  if (f.issue) out.push("issue");
  if (f.changed !== null) out.push("changed");
  if (f.locked !== null) out.push("locked");
  return out;
}

export function clearField(f: ClassFilters, field: FilterField): ClassFilters {
  switch (field) {
    case "status":
      return { ...f, status: [], placement: [] };
    case "time":
      return { ...f, time: null };
    case "issue":
      return { ...f, issue: null };
    case "changed":
      return { ...f, changed: null };
    case "locked":
      return { ...f, locked: null };
    default:
      return { ...f, [field]: [] };
  }
}

/* ------------------------------------------------------------------ row accessors */

export function rowDay(r: ClassRow, where: Where): number | null {
  return where === "placed" ? (r.placement?.day ?? null) : (r.req.day ?? null);
}

export function rowSpan(r: ClassRow, where: Where): [number, number] | null {
  if (where === "placed" && r.placement) return [r.placement.start_period, r.placement.end_period];
  if (r.req.start_period && r.req.end_period) return [r.req.start_period, r.req.end_period];
  return null;
}

export function rowRooms(r: ClassRow, where: Where): string[] {
  return where === "placed" ? (r.placement?.room_codes ?? []) : r.req.room_codes;
}

export function rowBuildings(r: ClassRow, where: Where): string[] {
  return [...new Set(rowRooms(r, where).map((c) => c.split(" ")[0].toUpperCase()))];
}

export function hasHard(r: ClassRow): boolean {
  return r.issues.some((i) => i.severity === "hard");
}

/* ------------------------------------------------------------------ filtering */

export function matchesText(r: ClassRow, text: string): boolean {
  const q = fold(text);
  if (!q) return true;
  const hay = fold(`${r.course_code} ${r.section ?? ""} ${r.course_name ?? ""} ${r.program_name ?? ""} ${r.instructors.map((i) => i.name).join(" ")} ${(r.placement?.room_codes ?? []).join(" ")} ${r.definitive.room_codes.join(" ")} ${r.req.room_text ?? ""}`);
  return q.split(/\s+/).every((part) => hay.includes(part));
}

type Pred = (r: ClassRow) => boolean;

function predicates(f: ClassFilters, skip?: FilterField): Pred[] {
  const p: Pred[] = [];
  if (skip !== "faculty" && f.faculty.length) p.push((r) => f.faculty.includes(r.faculty_id ?? -1));
  if (skip !== "program" && f.program.length) p.push((r) => f.program.includes(r.program_id ?? -1));
  if (skip !== "year" && f.year.length) p.push((r) => r.class_years.some((y) => f.year.includes(y)));
  if (skip !== "instructor" && f.instructor.length) p.push((r) => r.instructors.some((i) => f.instructor.includes(fold(i.name))));
  if (skip !== "building" && f.building.length) p.push((r) => rowBuildings(r, f.buildingWhere).some((b) => f.building.includes(b)));
  if (skip !== "room" && f.room.length) p.push((r) => rowRooms(r, f.buildingWhere).some((c) => f.room.includes(fold(c))));
  if (skip !== "day" && f.day.length) p.push((r) => f.day.includes(rowDay(r, f.dayWhere) ?? -1));
  if (skip !== "time" && f.time) {
    const t = f.time;
    p.push((r) => {
      const s = rowSpan(r, f.dayWhere);
      if (!s) return false;
      return t.mode === "within" ? s[0] >= t.from && s[1] <= t.to : s[0] <= t.to && t.from <= s[1];
    });
  }
  if (skip !== "mode" && f.mode.length) p.push((r) => f.mode.includes(r.mode));
  if (skip !== "status") {
    if (f.status.length) p.push((r) => f.status.includes(r.req.status));
    if (f.placement.length) p.push((r) => f.placement.includes(r.placement_status));
  }
  if (skip !== "issue" && f.issue) p.push((r) => (f.issue === "any" ? r.issues.length > 0 : f.issue === "hard" ? hasHard(r) : r.issues.some((i) => i.severity === "soft")));
  if (skip !== "changed" && f.changed !== null) p.push((r) => (r.changed.length > 0) === f.changed);
  if (skip !== "locked" && f.locked !== null) p.push((r) => (r.placement?.locked ?? false) === f.locked);
  if (f.text.trim()) p.push((r) => matchesText(r, f.text));
  return p;
}

export function applyFilters(rows: readonly ClassRow[], f: ClassFilters, skip?: FilterField): ClassRow[] {
  const p = predicates(f, skip);
  return p.length ? rows.filter((r) => p.every((fn) => fn(r))) : [...rows];
}

/** Facet counts for one field against all *other* active filters ("Pazartesi 212 · Salı 198 …"). */
export function facetCounts(rows: readonly ClassRow[], f: ClassFilters, field: FilterField): Map<string, number> {
  const base = applyFilters(rows, f, field);
  const m = new Map<string, number>();
  const add = (k: string | number | null | undefined) => {
    if (k === null || k === undefined || k === "") return;
    const key = String(k);
    m.set(key, (m.get(key) ?? 0) + 1);
  };
  for (const r of base) {
    switch (field) {
      case "faculty":
        add(r.faculty_id);
        break;
      case "program":
        add(r.program_id);
        break;
      case "year":
        r.class_years.forEach(add);
        break;
      case "instructor":
        r.instructors.forEach((i) => add(fold(i.name)));
        break;
      case "building":
        rowBuildings(r, f.buildingWhere).forEach(add);
        break;
      case "room":
        rowRooms(r, f.buildingWhere).forEach((c) => add(fold(c)));
        break;
      case "day":
        add(rowDay(r, f.dayWhere));
        break;
      case "mode":
        add(r.mode);
        break;
      case "status":
        add(`req:${r.req.status}`);
        add(`pl:${r.placement_status}`);
        break;
      case "issue":
        add(r.issues.length ? (hasHard(r) ? "hard" : "soft") : "none");
        break;
      case "changed":
        add(r.changed.length ? "yes" : "no");
        break;
      case "locked":
        add(r.placement?.locked ? "yes" : "no");
        break;
      default:
    }
  }
  return m;
}

/* ------------------------------------------------------------------ token search (TR + EN aliases) */

const DAY_TOKENS: Record<string, number> = { pzt: 1, pazartesi: 1, mon: 1, sal: 2, sali: 2, tue: 2, car: 3, carsamba: 3, wed: 3, per: 4, persembe: 4, thu: 4, cum: 5, cuma: 5, fri: 5, cmt: 6, cumartesi: 6, sat: 6, paz: 7, pazar: 7, sun: 7 };
const KEYS: Record<string, string> = {
  fak: "faculty", fac: "faculty", fakulte: "faculty",
  prog: "program", program: "program",
  sinif: "year", year: "year",
  hoca: "instructor", instr: "instructor",
  bina: "building", bldg: "building",
  oda: "room", room: "room",
  gun: "day", day: "day",
  saat: "time", time: "time",
  mod: "mode", mode: "mode",
  durum: "status", status: "status",
};
const FLAGS: Record<string, (f: ClassFilters) => ClassFilters> = {
  yerlesmedi: (f) => ({ ...f, placement: [...new Set([...f.placement, "unplaced" as const])] }),
  unplaced: (f) => ({ ...f, placement: [...new Set([...f.placement, "unplaced" as const])] }),
  sorunlu: (f) => ({ ...f, issue: "any" }),
  issues: (f) => ({ ...f, issue: "any" }),
  degisti: (f) => ({ ...f, changed: true }),
  changed: (f) => ({ ...f, changed: true }),
  kilitli: (f) => ({ ...f, locked: true }),
  locked: (f) => ({ ...f, locked: true }),
};

export interface TokenContext {
  faculties: { id: number; name: string }[];
  programs: { id: number; name: string }[];
  modes: string[];
}

/** Parse "fak:ecz gün:pzt saat:13:30-17:30 yerleşmedi kaya" → filters patch + remaining free text. */
export function parseTokens(input: string, base: ClassFilters, ctx: TokenContext): { filters: ClassFilters; rest: string; consumed: string[] } {
  let f = { ...base };
  const rest: string[] = [];
  const consumed: string[] = [];
  for (const raw of input.split(/\s+/).filter(Boolean)) {
    const tok = fold(raw);
    const m = /^([a-z]+):(.+)$/.exec(tok.replace(/\.(?=\d)/g, ":"));
    const flag = FLAGS[tok];
    if (flag) {
      f = flag(f);
      consumed.push(raw);
      continue;
    }
    const key = m ? KEYS[m[1]] : undefined;
    if (!m || !key) {
      rest.push(raw);
      continue;
    }
    const value = m[2];
    let ok = true;
    switch (key) {
      case "faculty": {
        const ids = ctx.faculties.filter((x) => fold(x.name).includes(value)).map((x) => x.id);
        ok = ids.length > 0;
        f = { ...f, faculty: [...new Set([...f.faculty, ...ids])] };
        break;
      }
      case "program": {
        const ids = ctx.programs.filter((x) => fold(x.name).includes(value)).map((x) => x.id);
        ok = ids.length > 0;
        f = { ...f, program: [...new Set([...f.program, ...ids])] };
        break;
      }
      case "year": {
        const ys = value.split(/[,-]/).map(Number).filter((n) => Number.isInteger(n) && n >= 0 && n <= 6);
        ok = ys.length > 0;
        f = { ...f, year: [...new Set([...f.year, ...ys])] };
        break;
      }
      case "instructor":
        f = { ...f, instructor: [...new Set([...f.instructor, value])] };
        break;
      case "building":
        f = { ...f, building: [...new Set([...f.building, ...value.split(",").map((b) => b.toUpperCase())])] };
        break;
      case "room":
        f = { ...f, room: [...new Set([...f.room, value])] };
        break;
      case "day": {
        const ds = value.split(",").map((d) => DAY_TOKENS[d]).filter((d): d is number => !!d);
        ok = ds.length > 0;
        f = { ...f, day: [...new Set([...f.day, ...ds])] };
        break;
      }
      case "time": {
        const span = parseTimeWindow(value);
        ok = span !== null;
        if (span) f = { ...f, time: { ...span, mode: "overlap" } };
        break;
      }
      case "mode": {
        const ms = ctx.modes.filter((x) => fold(x).startsWith(value));
        ok = ms.length > 0;
        f = { ...f, mode: [...new Set([...f.mode, ...ms])] };
        break;
      }
      case "status": {
        const map: Record<string, PlacementStatus> = { yerlesti: "placed", placed: "placed", kismi: "partial", partial: "partial", yerlesmedi: "unplaced", unplaced: "unplaced", cakisma: "conflict", conflict: "conflict" };
        const s = map[value];
        ok = !!s;
        if (s) f = { ...f, placement: [...new Set([...f.placement, s])] };
        break;
      }
      default:
        ok = false;
    }
    if (ok) consumed.push(raw);
    else rest.push(raw);
  }
  return { filters: { ...f, text: rest.join(" ") }, rest: rest.join(" "), consumed };
}

/** "13:30-17:30", "13.30-17.30", "17:30-" (after 17:30) → period window. */
export function parseTimeWindow(value: string): { from: number; to: number } | null {
  const [a, b] = value.split("-");
  const from = a ? snapToPeriod(a.replace(".", ":"))?.index : 1;
  const to = b ? periodEndingAt(b.replace(".", ":")) : PERIODS.length;
  if (!from || !to || parseClock((a ?? "08:30").replace(".", ":")) === null) return null;
  return { from, to: Math.max(from, to) };
}

/* ------------------------------------------------------------------ system views */

export type SystemView = "all" | "unplaced" | "issues" | "changed" | "evening" | "tip" | "noRoom" | "review";
export const SYSTEM_VIEWS: SystemView[] = ["all", "unplaced", "issues", "changed", "evening", "tip", "noRoom", "review"];

export function systemPredicate(v: SystemView, tipRooms: ReadonlySet<string>): (r: ClassRow) => boolean {
  switch (v) {
    case "unplaced":
      return (r) => r.placement_status === "unplaced";
    case "issues":
      return (r) => r.issues.length > 0;
    case "changed":
      return (r) => r.changed.length > 0;
    case "evening":
      return (r) => r.is_evening || (rowSpan(r, "placed")?.[0] ?? 0) >= 13;
    case "tip":
      return (r) => (r.placement?.room_codes ?? []).some((c) => tipRooms.has(c));
    case "noRoom":
      return (r) => r.placement_status === "no_room_needed";
    case "review":
      return (r) => r.req.status === "NEEDS_REVIEW";
    default:
      return () => true;
  }
}

/* ------------------------------------------------------------------ view state (saved views) */

export type Density = "compact" | "standard" | "comfortable";
export interface ViewState {
  system: SystemView;
  filters: ClassFilters;
  sort: { id: string; desc: boolean }[];
  group: string | null;
  subgroup: string | null;
  collapsed: string[];
  columns: string[];
  density: Density;
}

export const DEFAULT_COLUMNS = ["select", "status", "course", "program", "year", "instructor", "students", "reqRoom", "definitive", "placement", "fit", "issues", "lock", "changed"];
export const ALL_COLUMNS = ["select", "status", "course", "faculty", "program", "year", "instructor", "students", "mode", "reqTime", "weeks", "reqRoom", "definitive", "placement", "fit", "issues", "lock", "changed", "reqStatus", "source", "notes"];

export function defaultView(system: SystemView = "all"): ViewState {
  return { system, filters: EMPTY, sort: [], group: system === "unplaced" || system === "issues" ? null : "faculty", subgroup: null, collapsed: [], columns: DEFAULT_COLUMNS, density: "standard" };
}

/** Stable comparison for the "Görünüm değişti" bar (order of keys does not matter). */
export function sameView(a: ViewState, b: ViewState): boolean {
  return stable(a) === stable(b);
}

function stable(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stable).join(",")}]`;
  if (v && typeof v === "object") return `{${Object.keys(v as Record<string, unknown>).sort().map((k) => `${k}:${stable((v as Record<string, unknown>)[k])}`).join(",")}}`;
  return JSON.stringify(v);
}

/** Saved state from the server may be partial or older: merge onto the defaults. */
export function normalizeView(state: Partial<ViewState> | Record<string, unknown> | null | undefined): ViewState {
  const s = (state ?? {}) as Partial<ViewState>;
  const base = defaultView(s.system ?? "all");
  return {
    ...base,
    ...s,
    filters: { ...EMPTY, ...(s.filters ?? {}) },
    columns: Array.isArray(s.columns) && s.columns.length ? s.columns.filter((c) => ALL_COLUMNS.includes(c)) : base.columns,
    sort: Array.isArray(s.sort) ? s.sort : [],
    collapsed: Array.isArray(s.collapsed) ? s.collapsed : [],
  };
}

/* ------------------------------------------------------------------ grouping */

export function groupKey(r: ClassRow, by: string): { key: string; label: string; order: string } {
  switch (by) {
    case "faculty":
      return { key: `f${r.faculty_id ?? 0}`, label: r.faculty_name ?? "—", order: r.faculty_name ?? "~" };
    case "program":
      return { key: `p${r.program_id ?? 0}`, label: r.program_name ?? "—", order: r.program_name ?? "~" };
    case "day": {
      const d = rowDay(r, "placed") ?? rowDay(r, "requested");
      return { key: `d${d ?? 0}`, label: d ? String(d) : "—", order: String(d ?? 9) };
    }
    case "room": {
      const c = r.placement?.room_codes[0] ?? "—";
      return { key: `r${c}`, label: c, order: c };
    }
    case "building": {
      const b = rowBuildings(r, "placed")[0] ?? "—";
      return { key: `b${b}`, label: b, order: b };
    }
    case "status": {
      const order = ["conflict", "unplaced", "partial", "placed", "no_run", "no_room_needed"].indexOf(r.placement_status);
      return { key: `s${r.placement_status}`, label: r.placement_status, order: String(order) };
    }
    case "instructor": {
      const n = r.instructors[0]?.name ?? "—";
      return { key: `i${n}`, label: n, order: n };
    }
    case "year": {
      const y = r.class_years[0] ?? 0;
      return { key: `y${y}`, label: String(y || "—"), order: String(y || 9) };
    }
    default:
      return { key: "all", label: "", order: "" };
  }
}

/** Group aggregates: count, Σ students, % placed, issue count (all-classes.md §8.1). */
export function aggregate(rows: readonly ClassRow[]): { n: number; students: number; placedPct: number; issues: number } {
  const needs = rows.filter((r) => r.placement_status !== "no_room_needed" && r.placement_status !== "no_run");
  const placed = needs.filter((r) => r.placement_status === "placed" || r.placement_status === "partial" || r.placement_status === "conflict").length;
  return {
    n: rows.length,
    students: rows.reduce((s, r) => s + (r.enrolment ?? 0), 0),
    placedPct: needs.length ? Math.round((placed / needs.length) * 100) : 100,
    issues: rows.filter((r) => r.issues.length > 0).length,
  };
}

/** Parse a pasted Excel column (one value per line) for a numeric field. */
export function parsePastedColumn(text: string): (number | null)[] {
  return text
    .replace(/\r/g, "")
    .split("\n")
    .filter((line, i, all) => !(i === all.length - 1 && line === ""))
    .map((line) => {
      const v = line.split("\t")[0].trim().replace(/\./g, "").replace(",", ".");
      if (v === "") return null;
      const n = Number(v);
      return Number.isFinite(n) ? Math.round(n) : null;
    });
}
