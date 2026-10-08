/**
 * Calendar view state ↔ URL (calendar.md §4): every view is linkable.
 * /timetable?run=42&lens=board|week|day|month|term|agenda&board=day|strip&week=7&day=3
 *           &subject=room:12|instructor:45|cohort:118-2|section:991&compare=41&density=standard&zoom=3&sel=8812
 */
import type { Density } from "./geometry";
import { DEFAULT_ZOOM, clampZoom } from "./geometry";

export const LENSES = ["board", "week", "day", "month", "term", "agenda"] as const;
export type Lens = (typeof LENSES)[number];
export type BoardMode = "day" | "strip";
export type SubjectKind = "room" | "instructor" | "cohort" | "section";
export interface Subject {
  kind: SubjectKind;
  id: string;
}

export interface ViewState {
  run: number | null;
  lens: Lens;
  board: BoardMode;
  week: number | null;
  day: number;
  subject: Subject | null;
  compare: number | null;
  density: Density;
  zoom: number;
  sel: number | null;
}

/** Keyboard letters (Google Calendar style, Latin letters present on Turkish Q and F layouts). */
export const LENS_KEYS: Record<string, Lens> = { b: "board", w: "week", d: "day", m: "month", y: "term", a: "agenda" };

/** Order used for the lens-switch travel direction (motion.md §3.2: Board ← → Agenda). */
export function lensDirection(from: Lens, to: Lens): -1 | 0 | 1 {
  const a = LENSES.indexOf(from);
  const b = LENSES.indexOf(to);
  return a === b ? 0 : b > a ? 1 : -1;
}

/** Turkish-aware key → lens ("Y" for term/year), ignoring modifiers. */
export function lensForKey(key: string): Lens | null {
  const k = key.replace("İ", "i").toLocaleLowerCase("tr-TR").replace("ı", "i");
  return LENS_KEYS[k] ?? null;
}

const num = (v: string | null): number | null => {
  if (v === null || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export function parseSubject(v: string | null): Subject | null {
  if (!v) return null;
  const m = /^(room|instructor|cohort|section):(.+)$/.exec(v);
  return m ? { kind: m[1] as SubjectKind, id: m[2] } : null;
}

export function parseViewState(params: URLSearchParams, defaults: Partial<ViewState> = {}): ViewState {
  const lens = params.get("lens");
  const density = params.get("density");
  return {
    run: num(params.get("run")) ?? defaults.run ?? null,
    lens: (LENSES as readonly string[]).includes(lens ?? "") ? (lens as Lens) : (defaults.lens ?? "board"),
    board: params.get("board") === "strip" ? "strip" : (defaults.board ?? "day"),
    week: num(params.get("week")) ?? defaults.week ?? null,
    day: Math.min(7, Math.max(1, num(params.get("day")) ?? defaults.day ?? 1)),
    subject: parseSubject(params.get("subject")) ?? defaults.subject ?? null,
    compare: num(params.get("compare")) ?? defaults.compare ?? null,
    density: density === "compact" || density === "comfortable" || density === "standard" ? density : (defaults.density ?? "standard"),
    zoom: clampZoom(num(params.get("zoom")) ?? defaults.zoom ?? DEFAULT_ZOOM),
    sel: num(params.get("sel")) ?? null,
  };
}

/** Serialise only what differs from the defaults so links stay short. */
export function serializeViewState(s: ViewState, base?: URLSearchParams): URLSearchParams {
  const p = new URLSearchParams(base);
  const set = (k: string, v: string | null) => (v === null ? p.delete(k) : p.set(k, v));
  set("run", s.run !== null ? String(s.run) : null);
  set("lens", s.lens !== "board" ? s.lens : null);
  set("board", s.board === "strip" ? "strip" : null);
  set("week", s.week !== null ? String(s.week) : null);
  set("day", String(s.day));
  set("subject", s.subject ? `${s.subject.kind}:${s.subject.id}` : null);
  set("compare", s.compare !== null ? String(s.compare) : null);
  set("density", s.density !== "standard" ? s.density : null);
  set("zoom", s.zoom !== DEFAULT_ZOOM ? String(s.zoom) : null);
  set("sel", s.sel !== null ? String(s.sel) : null);
  return p;
}

/** The week a run covers that is closest to `preferred` (planner usability M1: never open an empty week). */
export function weekInRun(runWeeks: readonly number[], allWeeks: readonly number[], preferred: number | null): number {
  const pool = runWeeks.length ? runWeeks : allWeeks;
  if (!pool.length) return preferred ?? 1;
  if (preferred !== null && pool.includes(preferred)) return preferred;
  const target = preferred ?? pool[0];
  return [...pool].sort((a, b) => Math.abs(a - target) - Math.abs(b - target) || a - b)[0];
}
