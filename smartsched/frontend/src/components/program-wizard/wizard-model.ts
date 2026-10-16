/**
 * The program-from-scratch wizard as data (docs/design/v2/phase19-program-wizard.md; backend
 * app/services/program_drafts.py): the draft payload exactly as the server stores it (snake_case, list items
 * addressed by their `key`), the eight server steps, course-code normalisation, weekly patterns from T/U/L,
 * cohorts from Sınıf, and the autosave plan: `diffOps` turns two payloads into the smallest field ops for
 * `PATCH /program-drafts/{id} {ops, base_version}` and `applyOps` replays ops the same way the server does
 * (`program_drafts.apply_op`), so an edit made while a save is in flight is rebased onto the server's answer.
 * Pure functions, no React, no fetching: unit-tested.
 */
import { DRAFT_STEPS, type DraftIssue, type DraftOp, type DraftStep, type PasteRow, type StepState, type Validation } from "@/lib/api/program-drafts";

/* ------------------------------------------------------------------ steps */

export const STEPS = DRAFT_STEPS;
export type Step = DraftStep;
/** the old wizard's step names in saved links (`?step=term`), the same aliases the backend takes */
const ALIASES: Record<string, Step> = { term: "program", patterns: "rooms", precheck: "constraints" };
export function parseStep(v: string | null | undefined): Step {
  const s = ALIASES[v ?? ""] ?? v ?? "";
  return (STEPS as readonly string[]).includes(s) ? (s as Step) : "program";
}

export const LEVELS = ["associate", "bachelor", "masterThesis", "masterNonThesis", "phd"] as const;
export type Level = (typeof LEVELS)[number];
export const MODES = ["F2F", "ONLINE", "HYBRID", "UZEM"] as const;
export type Mode = (typeof MODES)[number];

/* ------------------------------------------------------------------ payload */

/** an existing person (`{id}`) or a new one created at the commit (`{name}`); names are display only for ids */
export interface InstructorRef {
  id?: number | null;
  name?: string;
  title?: string | null;
}

export interface SectionP {
  key: string;
  label: string;
  enrolment: number | null;
  /** first and second instructor, no holes (the server indexes the non-empty refs) */
  instructors: InstructorRef[];
  /** sections of the term taught together (joint teaching: one meeting, the bridge merges them) */
  joint_section_ids: number[];
  /** display cache of the linked sections ("MBG 014 §1 · Proteomiks · 75") keyed `id<section id>` (never digits
   * only: the server would read a digit segment as a list index), ignored by the server */
  joint_labels?: Record<string, { label: string; enrolment: number | null; periods: number | null }>;
}

export interface PatternP {
  theory_blocks: number[];
  weekly_hours: number | null;
  days: number[];
  start: string;
  weeks: string;
}

export interface RoomP {
  capacity: number | null;
  tags: string[];
  building: string;
  preferred: string;
}

export interface CourseP {
  key: string;
  /** an existing catalogue course reused as is (Var olan dersi ekle) */
  course_id: number | null;
  code: string;
  name: string;
  t: number | null;
  u: number | null;
  l: number | null;
  credits: number | null;
  ects: number | null;
  year: number;
  mode: Mode;
  compulsory: boolean;
  sections: SectionP[];
  pattern: PatternP;
  room: RoomP;
}

export interface CohortP {
  key: string;
  label: string;
  year: number;
  /** course keys that must not overlap */
  compulsory: string[];
  /** groups of course keys that may overlap within a group */
  elective_groups: string[][];
}

export interface ProgramP {
  faculty_id: number | null;
  faculty_name: string;
  name: string;
  level: Level;
  evening: boolean;
  language: "tr" | "en" | "mixed";
  prefix: string;
  years: number;
}

export interface Payload {
  program: ProgramP;
  courses: CourseP[];
  cohorts: CohortP[];
  rules: { window: { enabled: boolean; earliest: number; latest: number; hard: boolean }; same_room: boolean };
}

let seq = 0;
/** a stable list key: letters first and never all digits (the server reads a digit-only path segment as an index) */
export function newKey(prefix: string): string {
  seq += 1;
  return `${prefix}${Date.now().toString(36)}${seq.toString(36)}`;
}

export function emptyPattern(): PatternP {
  return { theory_blocks: [], weekly_hours: null, days: [1, 2, 3, 4, 5], start: "", weeks: "1-14" };
}

export function newSection(label = "1", enrolment: number | null = null): SectionP {
  return { key: newKey("s"), label, enrolment, instructors: [], joint_section_ids: [] };
}

export function newCourse(over: Partial<CourseP> = {}): CourseP {
  return { key: newKey("c"), course_id: null, code: "", name: "", t: 0, u: 0, l: 0, credits: null, ects: null, year: 1, mode: "F2F", compulsory: true, sections: [newSection()], pattern: emptyPattern(), room: { capacity: null, tags: [], building: "", preferred: "" }, ...over };
}

export function newPayload(): Payload {
  return {
    program: { faculty_id: null, faculty_name: "", name: "", level: "masterThesis", evening: false, language: "tr", prefix: "", years: 2 },
    courses: [],
    cohorts: [],
    rules: { window: { enabled: true, earliest: 1, latest: 11, hard: false }, same_room: true },
  };
}

const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const numOrNull = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : typeof v === "string" && v.trim() && Number.isFinite(Number(v.replace(",", "."))) ? Number(v.replace(",", ".")) : null);
const str = (v: unknown, d = ""): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : d);
const pick = (o: Record<string, unknown>, snake: string, camel: string): unknown => (snake in o ? o[snake] : o[camel]);

/**
 * The stored payload with every default filled in. Drafts written by an older client or by hand may use the
 * wizard's camelCase keys (the backend accepts both); the wizard always writes snake_case back.
 */
export function readPayload(raw: unknown): Payload {
  const base = newPayload();
  const r = obj(raw);
  const p = obj(r.program);
  const level = str(p.level, base.program.level);
  const program: ProgramP = {
    faculty_id: numOrNull(pick(p, "faculty_id", "facultyId")),
    faculty_name: str(pick(p, "faculty_name", "facultyName")),
    name: str(p.name),
    level: (LEVELS as readonly string[]).includes(level) ? (level as Level) : base.program.level,
    evening: Boolean(p.evening),
    language: (["tr", "en", "mixed"] as const).find((x) => x === p.language) ?? "tr",
    prefix: str(p.prefix),
    years: numOrNull(p.years) ?? base.program.years,
  };
  const courses: CourseP[] = arr(r.courses).map((c0, i) => {
    const c = obj(c0);
    const pat = obj(c.pattern);
    const room = obj(c.room);
    const mode = str(c.mode, "F2F");
    return {
      key: str(c.key) || `c${i}x`,
      course_id: numOrNull(pick(c, "course_id", "courseId")),
      code: str(c.code),
      name: str(c.name),
      t: numOrNull(c.t),
      u: numOrNull(c.u),
      l: numOrNull(c.l),
      credits: numOrNull(c.credits),
      ects: numOrNull(c.ects),
      year: numOrNull(c.year) ?? 1,
      mode: (MODES as readonly string[]).includes(mode) ? (mode as Mode) : "F2F",
      compulsory: c.compulsory === undefined ? true : Boolean(c.compulsory),
      sections: arr(c.sections).map((s0, j) => {
        const s = obj(s0);
        const labels = obj(pick(s, "joint_labels", "jointLabels"));
        return {
          key: str(s.key) || `s${i}x${j}`,
          label: str(s.label, String(j + 1)),
          enrolment: numOrNull(s.enrolment),
          instructors: arr(s.instructors).filter(Boolean).map((x) => {
            const o = obj(x);
            return { id: numOrNull(o.id), name: str(o.name) || undefined, title: typeof o.title === "string" ? o.title : null };
          }),
          joint_section_ids: arr(pick(s, "joint_section_ids", "jointSectionIds")).map(numOrNull).filter((x): x is number => x !== null),
          ...(Object.keys(labels).length ? { joint_labels: labels as SectionP["joint_labels"] } : {}),
        };
      }),
      pattern: {
        theory_blocks: arr(pick(pat, "theory_blocks", "theoryBlocks")).map(numOrNull).filter((x): x is number => x !== null && x > 0),
        weekly_hours: numOrNull(pick(pat, "weekly_hours", "weeklyHours")),
        days: arr(pat.days).map(numOrNull).filter((x): x is number => x !== null),
        start: str(pat.start),
        weeks: str(pat.weeks, "1-14"),
      },
      room: { capacity: numOrNull(room.capacity), tags: arr(room.tags).map((x) => str(x)).filter(Boolean), building: str(room.building), preferred: str(room.preferred) },
    };
  });
  const cohorts: CohortP[] = arr(r.cohorts).map((x0, i) => {
    const x = obj(x0);
    return {
      key: str(x.key) || `y${i}x`,
      label: str(x.label),
      year: numOrNull(x.year) ?? 1,
      compulsory: arr(x.compulsory).map((k) => str(k)).filter(Boolean),
      elective_groups: arr(pick(x, "elective_groups", "electiveGroups")).map((g) => arr(g).map((k) => str(k)).filter(Boolean)),
    };
  });
  const rules = obj(r.rules);
  const w = obj(rules.window);
  return {
    program,
    courses,
    cohorts,
    rules: {
      window: { enabled: w.enabled === undefined ? true : Boolean(w.enabled), earliest: numOrNull(w.earliest) ?? 1, latest: numOrNull(w.latest) ?? 11, hard: Boolean(w.hard) },
      same_room: pick(rules, "same_room", "sameRoom") === undefined ? true : Boolean(pick(rules, "same_room", "sameRoom")),
    },
  };
}

/* ------------------------------------------------------------------ autosave ops */

type Json = unknown;
const isObj = (v: Json): v is Record<string, Json> => !!v && typeof v === "object" && !Array.isArray(v);
const keyed = (v: Json): v is { key: string }[] => Array.isArray(v) && v.length > 0 && v.every((x) => isObj(x) && typeof x.key === "string" && x.key !== "" && !/^\d+$/.test(x.key) && !x.key.includes("."));
const sameKeys = (a: { key: string }[], b: { key: string }[]) => a.length === b.length && a.every((x, i) => x.key === b[i]!.key);

export function deepEqual(a: Json, b: Json): boolean {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => deepEqual(x, b[i]));
  if (isObj(a) && isObj(b)) {
    const ka = Object.keys(a).filter((k) => a[k] !== undefined);
    const kb = Object.keys(b).filter((k) => b[k] !== undefined);
    return ka.length === kb.length && ka.every((k) => deepEqual(a[k], b[k]));
  }
  return false;
}

/**
 * The smallest field ops from `base` to `next`: objects key by key, keyed lists (courses, sections, cohorts)
 * item by item while the keys and their order are the same, anything else (a reordered or resized list, a
 * scalar, `days`, `instructors`) as one `set` of the whole value. A field set by someone else later keeps
 * theirs unless we touch it too (the server merges per path, last write wins).
 */
export function diffOps(base: Json, next: Json, path = ""): DraftOp[] {
  if (deepEqual(base, next)) return [];
  const at = (k: string) => (path ? `${path}.${k}` : k);
  if (isObj(base) && isObj(next)) {
    const out: DraftOp[] = [];
    for (const k of Object.keys(next)) {
      if (next[k] === undefined) continue;
      if (!(k in base) || base[k] === undefined) out.push({ path: at(k), value: next[k], op: "set" });
      else out.push(...diffOps(base[k], next[k], at(k)));
    }
    for (const k of Object.keys(base)) if (base[k] !== undefined && (!(k in next) || next[k] === undefined)) out.push({ path: at(k), op: "remove" });
    return out;
  }
  if (path && keyed(base) && keyed(next) && sameKeys(base, next)) {
    return next.flatMap((item, i) => diffOps(base[i], item, at(item.key)));
  }
  return path ? [{ path, value: next, op: "set" }] : [];
}

function stepInto(node: Json, seg: string): { cont: Record<string, Json> | Json[]; key: string | number } {
  if (Array.isArray(node)) {
    if (seg === "-") return { cont: node, key: node.length };
    if (/^\d+$/.test(seg)) return { cont: node, key: Number(seg) };
    const i = node.findIndex((x) => isObj(x) && String(x.key) === seg);
    if (i < 0) throw new Error(`no list item with key ${seg}`);
    return { cont: node, key: i };
  }
  if (isObj(node)) return { cont: node, key: seg };
  throw new Error(`cannot descend at ${seg}`);
}

/** `program_drafts.apply_op` in TypeScript: set / remove one dot path in place (list items by index, key or `-`) */
export function applyOp(payload: Record<string, Json>, op: DraftOp): void {
  const segs = op.path.split(/[./]/).filter(Boolean);
  if (!segs.length) throw new Error("empty path");
  let node: Json = payload;
  segs.slice(0, -1).forEach((seg, i) => {
    const { cont, key } = stepInto(node, seg);
    if (Array.isArray(cont)) {
      node = cont[key as number];
    } else {
      const k = key as string;
      if (cont[k] === undefined || cont[k] === null) cont[k] = /^\d+$/.test(segs[i + 1]!) || segs[i + 1] === "-" ? [] : {};
      node = cont[k];
    }
  });
  const { cont, key } = stepInto(node, segs[segs.length - 1]!);
  if (Array.isArray(cont)) {
    const i = key as number;
    if (op.op === "remove") cont.splice(i, 1);
    else if (i >= cont.length) cont.push(op.value);
    else cont[i] = op.value;
  } else if (op.op === "remove") {
    delete cont[key as string];
  } else {
    cont[key as string] = op.value;
  }
}

export function applyOps<T>(payload: T, ops: readonly DraftOp[]): T {
  const copy = structuredClone(payload) as Record<string, Json>;
  for (const op of ops) {
    try {
      applyOp(copy, op);
    } catch {
      // the item was removed by someone else: our edit of it has nothing left to land on
    }
  }
  return copy as T;
}

/* ------------------------------------------------------------------ course codes and numbers */

const TR_LETTERS = /[ÇĞİÖŞÜçğıöşü]/;

/** "mbg532" → "MBG 532" (info), "MBĞ 532" → error, "" → error. The backend's validation is the final word. */
export function normalizeCode(raw: string): { code: string; info: boolean; error: "empty" | "turkish" | "shape" | null } {
  const v = raw.trim().replace(/\s+/g, " ");
  if (!v) return { code: "", info: false, error: "empty" };
  if (TR_LETTERS.test(v)) return { code: v, info: false, error: "turkish" };
  const m = /^([A-Za-z]{2,5})\s*-?\s*(\d{2,4}[A-Za-z]?)$/.exec(v);
  if (!m) return { code: v.toUpperCase(), info: false, error: "shape" };
  const code = `${m[1]!.toUpperCase()} ${m[2]!.toUpperCase()}`;
  return { code, info: code !== v, error: null };
}

/** "4,5" → 4.5; "" / "-" → null; "abc" → NaN (the server reports the field) */
export function parseNumber(raw: string | number | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "number") return raw;
  const v = raw.trim().replace(/ /g, "");
  if (!v || v === "-" || v === "—") return null;
  const n = Number(v.replace(",", "."));
  return Number.isFinite(n) ? n : Number.NaN;
}

/** pasted rows (`POST /program-drafts/{id}/paste` preview) → course rows; codes are kept as the server fixed them */
export function coursesFromPaste(rows: readonly PasteRow[]): CourseP[] {
  return rows.map((r) => {
    const hours = (r.t ?? 0) + (r.u ?? 0) + (r.l ?? 0);
    return newCourse({
      code: r.code,
      name: r.name,
      t: r.t ?? 0,
      u: r.u ?? 0,
      l: r.l ?? 0,
      credits: r.credits,
      ects: r.ects,
      year: r.year && r.year > 0 ? Math.round(r.year) : 1,
      sections: [newSection("1", r.enrolment ?? null)],
      pattern: { ...emptyPattern(), theory_blocks: r.t ? [r.t] : [], weekly_hours: hours ? null : 1 },
    });
  });
}

/** the codes of `rows` that the draft (or an earlier pasted row) already has: "MBG 951 iki kez listelenmiş" */
export function pasteDuplicates(existing: readonly CourseP[], rows: readonly PasteRow[]): Set<number> {
  const seen = new Set(existing.map((c) => normalizeCode(c.code).code).filter(Boolean));
  const dup = new Set<number>();
  for (const r of rows) {
    const code = normalizeCode(r.code).code || r.code;
    if (seen.has(code)) dup.add(r.line);
    seen.add(code);
  }
  return dup;
}

/* ------------------------------------------------------------------ weekly patterns */

/** the theory splits offered for T hours (spec §4.6: T3 → "3 saat tek blok" · "2 + 1" · "1 + 1 + 1") */
export function patternOptions(hours: number): number[][] {
  if (hours <= 0) return [];
  if (hours === 1) return [[1]];
  const out: number[][] = [[hours]];
  if (hours >= 3) out.push([hours - 1, 1]);
  if (hours === 4) out.push([2, 2]);
  if (hours >= 2 && hours <= 4) out.push(Array.from({ length: hours }, () => 1));
  return out.filter((o, i) => out.findIndex((x) => x.join("+") === o.join("+")) === i);
}

export function courseHours(c: Pick<CourseP, "t" | "u" | "l">): number {
  const v = (x: number | null) => (x === null || Number.isNaN(x) || x < 0 ? 0 : x);
  return v(c.t) + v(c.u) + v(c.l);
}

/** the pattern's weekly periods: the theory split + one block each for U and L, or the seminar's weekly hours */
export function patternHours(c: Pick<CourseP, "t" | "u" | "l" | "pattern">): number {
  if (!courseHours(c)) return c.pattern.weekly_hours ?? 0;
  const theory = c.pattern.theory_blocks.length ? c.pattern.theory_blocks.reduce((a, b) => a + b, 0) : (c.t ?? 0);
  return theory + (c.u ?? 0) + (c.l ?? 0);
}

export const jointKey = (id: number) => `id${id}`;

/** "Ortak toplam": this section's students plus every linked section's (drives the room size) */
export function jointTotal(s: SectionP): number {
  const own = s.enrolment ?? 0;
  return own + s.joint_section_ids.reduce((n, id) => n + (s.joint_labels?.[jointKey(id)]?.enrolment ?? 0), 0);
}

/** the seats a course needs: the override, else the biggest section's joint total */
export function neededCapacity(c: CourseP): number {
  return c.room.capacity ?? Math.max(0, ...c.sections.map(jointTotal));
}

/* ------------------------------------------------------------------ cohorts */

/** cohorts pre-built from Sınıf (spec §4.5): "<prefix> 1. sınıf" with the compulsory courses of that year */
export function cohortsFromYears(p: Payload, label: (year: number) => string): CohortP[] {
  const years = [...new Set(p.courses.map((c) => c.year))].sort((a, b) => a - b);
  return years.map((year) => {
    const of = p.courses.filter((c) => c.year === year);
    const electives = of.filter((c) => !c.compulsory).map((c) => c.key);
    const prev = p.cohorts.find((x) => x.year === year);
    return {
      key: prev?.key ?? newKey("y"),
      label: prev?.label || label(year),
      year,
      compulsory: of.filter((c) => c.compulsory).map((c) => c.key),
      elective_groups: electives.length ? [electives] : [],
    };
  });
}

/** "MBG 1. sınıf" / "MBG year 1" */
export function newCohortLabel(prefix: string, year: number, lang: "tr" | "en"): string {
  const head = prefix.trim();
  return lang === "tr" ? `${head ? `${head} ` : ""}${year}. sınıf` : `${head ? `${head} ` : ""}year ${year}`;
}

/** compulsory courses in no cohort (the server warns `not_in_cohort` once cohorts exist) */
export function uncohorted(p: Payload): CourseP[] {
  if (!p.cohorts.length) return [];
  const inAny = new Set(p.cohorts.flatMap((c) => [...c.compulsory, ...c.elective_groups.flat()]));
  return p.courses.filter((c) => c.compulsory && !inAny.has(c.key));
}

/* ------------------------------------------------------------------ validation (server issues) */

export function issuesAt(v: Validation | null | undefined, path: string): DraftIssue[] {
  return (v?.issues ?? []).filter((i) => i.path === path);
}
/** the issues of a field and of everything below it (`courses.c1` → its sections, pattern, room) */
export function issuesUnder(v: Validation | null | undefined, path: string): DraftIssue[] {
  return (v?.issues ?? []).filter((i) => i.path === path || i.path.startsWith(`${path}.`));
}
export function hasError(v: Validation | null | undefined, path: string): boolean {
  return issuesAt(v, path).some((i) => i.level === "error");
}
export function stepState(v: Validation | null | undefined, step: Step): StepState | undefined {
  return v?.steps.find((s) => s.step === step);
}
/** the first error of a step that names a field (Devam with errors focuses it) */
export function firstErrorPath(v: Validation | null | undefined, step: Step): string | null {
  return (v?.issues ?? []).find((i) => i.step === step && i.level === "error" && i.path)?.path ?? null;
}

/** the commit summary (spec §4.8 confirm): what the commit writes */
export function commitCounts(p: Payload) {
  const sections = p.courses.reduce((n, c) => n + c.sections.length, 0);
  const meetings = p.courses.reduce((n, c) => n + c.sections.length * Math.max(1, c.pattern.theory_blocks.length + ((c.u ?? 0) > 0 ? 1 : 0) + ((c.l ?? 0) > 0 ? 1 : 0)), 0);
  const rules = (p.rules.window.enabled ? 1 : 0) + (p.rules.same_room ? 1 : 0);
  return { courses: p.courses.length, sections, cohorts: p.cohorts.length, meetings, rules };
}

/** issue text in the UI language (the server sends TR + EN) */
export function issueText(i: Pick<DraftIssue, "text">, lang: "tr" | "en"): string {
  return i.text[lang] || i.text.tr || i.text.en;
}
