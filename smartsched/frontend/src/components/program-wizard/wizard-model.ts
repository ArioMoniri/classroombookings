/**
 * The program-from-scratch wizard as data (docs/design/v2/phase19-program-wizard.md, ROADMAP P19-F4): the draft,
 * the eight steps, TSV paste, course-code normalisation, weekly patterns from T/U/L, three levels of validation
 * (field · step · pre-check; only errors block), the live room fit, and the sync plan that autosaves the draft
 * through the catalog_admin endpoints. Pure functions, no React, no fetching: unit-tested.
 */
import type { Room } from "@/lib/api/schemas";

/* ------------------------------------------------------------------ steps */

export const STEPS = ["term", "program", "courses", "sections", "patterns", "constraints", "precheck", "generate"] as const;
export type Step = (typeof STEPS)[number];
export function parseStep(v: string | null | undefined): Step {
  return (STEPS as readonly string[]).includes(v ?? "") ? (v as Step) : "term";
}

export const LEVELS = ["associate", "bachelor", "masterThesis", "masterNonThesis", "phd"] as const;
export type Level = (typeof LEVELS)[number];
export const MODES = ["F2F", "ONLINE", "HYBRID"] as const;
export type Mode = (typeof MODES)[number];
export const TAGS = ["LAB", "PC", "AMPHI"] as const;

/* ------------------------------------------------------------------ draft */

export interface InstructorRef {
  /** null = a new person, created at the next save */
  id: number | null;
  name: string;
  title?: string | null;
}

export interface SectionDraft {
  key: string;
  id: number | null;
  label: string;
  enrolment: number | null;
  instructors: [InstructorRef | null, InstructorRef | null];
  meetingIds: number[];
}

export interface PatternDraft {
  /** theory split into consecutive blocks, e.g. [3] or [2, 1] */
  theoryBlocks: number[];
  /** weekly hours for a 0+0+0 course (seminars are often entered as 0 0 0; MBG 598, Bahar R182) */
  weeklyHours: number | null;
  days: number[];
  /** "HH:MM" of a period start */
  start: string;
  weeks: string;
}

export interface RoomNeed {
  capacity: number | null;
  tags: string[];
  building: string;
  preferred: string;
}

export interface CourseDraft {
  key: string;
  id: number | null;
  /** we created the catalogue row (only then the wizard may update it); false = an existing course reused */
  own: boolean;
  code: string;
  name: string;
  t: number | null;
  u: number | null;
  l: number | null;
  ects: number | null;
  year: number;
  mode: Mode;
  sections: SectionDraft[];
  pattern: PatternDraft;
  room: RoomNeed;
}

export interface RulesDraft {
  window: { enabled: boolean; earliest: number; latest: number; hard: boolean };
  sameRoom: boolean;
  ruleIds: number[];
}

export interface Draft {
  key: string;
  version: 1;
  termId: number | null;
  termCode: string | null;
  step: Step;
  program: {
    id: number | null;
    facultyId: number | null;
    facultyName: string;
    name: string;
    level: Level;
    evening: boolean;
    language: "tr" | "en" | "mixed";
    prefix: string;
    years: number;
  };
  courses: CourseDraft[];
  rules: RulesDraft;
  /** server-relevant hash per entity key at its last successful save */
  synced: Record<string, string>;
  savedAt: string | null;
  createdAt: string;
}

let seq = 0;
export function newKey(prefix: string): string {
  seq += 1;
  return `${prefix}-${Date.now().toString(36)}-${seq}`;
}

export function emptyPattern(): PatternDraft {
  return { theoryBlocks: [], weeklyHours: null, days: [1, 2, 3, 4, 5], start: "", weeks: "1-14" };
}

export function newSection(label = "1", enrolment: number | null = null): SectionDraft {
  return { key: newKey("s"), id: null, label, enrolment, instructors: [null, null], meetingIds: [] };
}

export function newCourse(over: Partial<CourseDraft> = {}): CourseDraft {
  return { key: newKey("c"), id: null, own: false, code: "", name: "", t: 0, u: 0, l: 0, ects: null, year: 1, mode: "F2F", sections: [newSection()], pattern: emptyPattern(), room: { capacity: null, tags: [], building: "", preferred: "" }, ...over };
}

export function newDraft(now = new Date().toISOString()): Draft {
  return {
    key: newKey("d"),
    version: 1,
    termId: null,
    termCode: null,
    step: "term",
    program: { id: null, facultyId: null, facultyName: "", name: "", level: "masterThesis", evening: false, language: "tr", prefix: "", years: 2 },
    courses: [],
    rules: { window: { enabled: true, earliest: 1, latest: 11, hard: false }, sameRoom: true, ruleIds: [] },
    synced: {},
    savedAt: null,
    createdAt: now,
  };
}

/* ------------------------------------------------------------------ course codes */

const TR_LETTERS = /[ÇĞİÖŞÜçğıöşü]/;

/** "mbg532" → "MBG 532" (info), "MBĞ 532" → error, "" → error. The backend's code-check is the final word. */
export function normalizeCode(raw: string): { code: string; info: boolean; error: "empty" | "turkish" | "shape" | null } {
  const v = raw.trim().replace(/\s+/g, " ");
  if (!v) return { code: "", info: false, error: "empty" };
  if (TR_LETTERS.test(v)) return { code: v, info: false, error: "turkish" };
  const m = /^([A-Za-z]{2,5})\s*-?\s*(\d{2,4}[A-Za-z]?)$/.exec(v);
  if (!m) return { code: v.toUpperCase(), info: false, error: "shape" };
  const code = `${m[1]!.toUpperCase()} ${m[2]!.toUpperCase()}`;
  return { code, info: code !== v, error: null };
}

/** "4,5" → 4.5; "" / "-" → null; "abc" → NaN (a field error) */
export function parseNumber(raw: string | number | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "number") return raw;
  const v = raw.trim().replace(/ /g, "");
  if (!v || v === "-" || v === "—") return null;
  const n = Number(v.replace(",", "."));
  return Number.isFinite(n) ? n : Number.NaN;
}

/* ------------------------------------------------------------------ TSV paste */

const HEADER_WORDS: Record<string, string> = { kod: "code", code: "code", ders: "code", "ders kodu": "code", ad: "name", "ders adı": "name", name: "name", adı: "name", t: "t", u: "u", l: "l", k: "credits", kredi: "credits", akts: "ects", ects: "ects", sınıf: "year", sinif: "year", year: "year" };
const DEFAULT_ORDER = ["code", "name", "t", "u", "l", "credits", "ects", "year"] as const;

export interface PastedRow {
  code: string;
  name: string;
  t: number | null;
  u: number | null;
  l: number | null;
  ects: number | null;
  year: number | null;
  line: number;
}

/** Excel copies rows as TSV: detect a header row (Kod / Ad / T / U / L / K / AKTS / Sınıf), skip empty lines */
export function parseTsv(text: string): { columns: string[]; rows: PastedRow[]; ignored: number[] } {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const ignored: number[] = [];
  let columns: string[] = [...DEFAULT_ORDER];
  const rows: PastedRow[] = [];
  lines.forEach((line, i) => {
    if (!line.trim()) {
      if (i < lines.length - 1) ignored.push(i + 1);
      return;
    }
    const cells = line.split("\t").map((c) => c.trim());
    const asHeader = cells.map((c) => HEADER_WORDS[c.toLocaleLowerCase("tr-TR")]);
    if (rows.length === 0 && asHeader.filter(Boolean).length >= 2) {
      columns = asHeader.map((h, j) => h ?? `skip${j}`);
      ignored.push(i + 1);
      return;
    }
    const get = (k: string) => {
      const j = columns.indexOf(k);
      return j >= 0 ? (cells[j] ?? "") : "";
    };
    if (!get("code")) {
      ignored.push(i + 1);
      return;
    }
    const num = (k: string) => {
      const v = parseNumber(get(k));
      return v === null || Number.isNaN(v) ? null : v;
    };
    rows.push({ code: get("code"), name: get("name"), t: num("t"), u: num("u"), l: num("l"), ects: num("ects"), year: num("year"), line: i + 1 });
  });
  return { columns, rows, ignored };
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

export function courseHours(c: Pick<CourseDraft, "t" | "u" | "l">): number {
  return (c.t ?? 0) + (c.u ?? 0) + (c.l ?? 0);
}

/** the pattern's weekly periods: the theory split + one block each for U and L, or the seminar's weekly hours */
export function patternHours(c: Pick<CourseDraft, "t" | "u" | "l" | "pattern">): number {
  if (!courseHours(c)) return c.pattern.weeklyHours ?? 0;
  const theory = c.pattern.theoryBlocks.length ? c.pattern.theoryBlocks.reduce((a, b) => a + b, 0) : (c.t ?? 0);
  return theory + (c.u ?? 0) + (c.l ?? 0);
}

/** the body of `POST /sections/{id}/pattern` (app/services/patterns.py) */
export function patternBody(c: CourseDraft, enrolment: number | null) {
  const zero = !courseHours(c);
  const theory = zero ? (c.pattern.weeklyHours ?? 0) : (c.t ?? 0);
  const room: Record<string, unknown> = {};
  if (c.room.tags.length) room.tags = c.room.tags;
  if (c.room.building) room.building = c.room.building;
  if (c.room.preferred) room.preferred_room = c.room.preferred;
  const cap = c.room.capacity ?? enrolment;
  if (cap) room.capacity = cap;
  return {
    theory,
    practice: zero ? 0 : (c.u ?? 0),
    lab: zero ? 0 : (c.l ?? 0),
    ...(c.pattern.theoryBlocks.length && !zero ? { block_size: c.pattern.theoryBlocks } : {}),
    days: c.pattern.days,
    start: c.pattern.start,
    weeks: c.pattern.weeks || "1-14",
    ...(Object.keys(room).length ? { room_needs: room } : {}),
    replace: true,
  };
}

/* ------------------------------------------------------------------ rooms */

export function neededCapacity(c: CourseDraft): number {
  return c.room.capacity ?? Math.max(0, ...c.sections.map((s) => s.enrolment ?? 0));
}

/** bookable rooms that seat `capacity` and carry every tag, smallest first (the live "Sığan odalar" line) */
export function fittingRooms(rooms: readonly Room[], capacity: number, tags: readonly string[], building = ""): Room[] {
  return rooms
    .filter((r) => r.is_bookable && r.capacity >= capacity && tags.every((t) => (r.tags as string[]).includes(t)) && (!building || r.building_code === building))
    .sort((a, b) => a.capacity - b.capacity || a.display_name.localeCompare(b.display_name, "tr", { numeric: true }));
}

/* ------------------------------------------------------------------ validation */

export type Level3 = "error" | "warning" | "info";
export interface Issue {
  step: Step;
  level: Level3;
  /** message key under programWizard.v.* */
  code: string;
  vars?: Record<string, string | number>;
  /** the field it belongs to (`courses.<key>.code`), for the error summary links */
  path?: string;
}

const fmtRooms = (rs: readonly Room[]) => rs.slice(0, 4).map((r) => `${r.display_name} (${r.capacity})`).join(", ");

export function validate(d: Draft, rooms: readonly Room[] | null = null): Issue[] {
  const out: Issue[] = [];
  const add = (step: Step, level: Level3, code: string, vars?: Issue["vars"], path?: string) => out.push({ step, level, code, vars, path });
  if (!d.termId) add("term", "error", "noTerm", undefined, "termId");
  const p = d.program;
  if (!p.name.trim()) add("program", "error", "noName", undefined, "program.name");
  if (!p.facultyId && !p.facultyName.trim()) add("program", "error", "noFaculty", undefined, "program.faculty");
  if (p.prefix && !/^[A-Z]{2,4}$/.test(p.prefix)) add("program", "error", TR_LETTERS.test(p.prefix) ? "prefixTurkish" : "prefixShape", { prefix: p.prefix }, "program.prefix");
  if (!d.courses.length) add("courses", "error", "noCourses", undefined, "courses");
  const seen = new Map<string, string>();
  const ectsByYear = new Map<number, number>();
  for (const c of d.courses) {
    const code = normalizeCode(c.code);
    const path = `courses.${c.key}`;
    if (code.error) add("courses", "error", `code_${code.error}`, { code: c.code || "—" }, `${path}.code`);
    else if (seen.has(code.code)) add("courses", "error", "duplicate", { code: code.code }, `${path}.code`);
    else seen.set(code.code, c.key);
    if (!c.name.trim()) add("courses", "warning", "noCourseName", { code: code.code || "—" }, `${path}.name`);
    if ([c.t, c.u, c.l, c.ects].some((v) => v !== null && (Number.isNaN(v) || v < 0))) add("courses", "error", "badNumber", { code: code.code }, `${path}.t`);
    if (!courseHours(c)) add("courses", "warning", "zeroHours", { code: code.code }, `${path}.t`);
    ectsByYear.set(c.year, (ectsByYear.get(c.year) ?? 0) + (c.ects && !Number.isNaN(c.ects) ? c.ects : 0));

    // sections + instructors
    if (!c.sections.length) add("sections", "error", "noSections", { code: code.code }, `${path}.sections`);
    for (const s of c.sections) {
      if ((s.enrolment ?? 0) <= 0 && c.mode !== "ONLINE") add("sections", "error", "noStudents", { code: code.code, section: s.label }, `${path}.${s.key}.enrolment`);
      if (!s.instructors[0] && c.mode === "F2F") add("sections", "warning", "noInstructor", { code: code.code, section: s.label }, `${path}.${s.key}.instructor`);
    }

    // patterns + rooms
    const hours = courseHours(c);
    if (!hours && !c.pattern.weeklyHours) add("patterns", "error", "needWeeklyHours", { code: code.code }, `${path}.weekly`);
    if (hours && c.pattern.theoryBlocks.length && patternHours(c) !== hours) add("patterns", "error", "patternTotal", { code: code.code, hours, placed: patternHours(c) }, `${path}.pattern`);
    if (!c.pattern.start) add("patterns", "error", "noStart", { code: code.code }, `${path}.start`);
    if (!c.pattern.days.length) add("patterns", "error", "noDays", { code: code.code }, `${path}.days`);
    if (rooms && c.mode !== "ONLINE") {
      const cap = neededCapacity(c);
      const tags = c.room.tags;
      const fit = fittingRooms(rooms, cap, tags, c.room.building);
      if (!fit.length) add("patterns", "error", tags.includes("LAB") ? "noLabRoom" : "noRoom", { code: code.code, n: cap }, `${path}.room`);
      else {
        add("patterns", "info", "fits", { code: code.code, n: cap, rooms: fmtRooms(fit), count: fit.length });
        if (fit[0]!.capacity === cap && fit.length <= 4) add("patterns", "warning", "exactFit", { code: code.code, room: fit[0]!.display_name, n: cap }, `${path}.room`);
      }
      if (c.room.preferred) {
        const pr = rooms.find((r) => r.display_name.replace(/\s+/g, "").toUpperCase() === c.room.preferred.replace(/\s+/g, "").toUpperCase());
        if (!pr || !pr.is_bookable) add("patterns", "warning", "preferredUnknown", { code: code.code, room: c.room.preferred }, `${path}.preferred`);
        else if (pr.capacity < cap) add("patterns", "warning", "preferredSmall", { code: code.code, room: pr.display_name, seats: pr.capacity, n: cap }, `${path}.preferred`);
      }
    }
  }
  for (const [year, ects] of ectsByYear) if (ects > 30) add("courses", "warning", "ectsHigh", { year, ects });
  if (d.rules.window.enabled && d.rules.window.earliest > d.rules.window.latest) add("constraints", "error", "windowOrder");
  return out;
}

export interface StepStatus {
  step: Step;
  errors: number;
  warnings: number;
  /** – = nothing entered yet */
  empty: boolean;
}

export function stepStatus(d: Draft, issues: readonly Issue[]): StepStatus[] {
  const empty: Record<Step, boolean> = {
    term: !d.termId,
    program: !d.program.name.trim(),
    courses: d.courses.length === 0,
    sections: d.courses.length === 0,
    patterns: d.courses.every((c) => !c.pattern.start),
    constraints: false,
    precheck: false,
    generate: false,
  };
  return STEPS.map((step) => ({
    step,
    errors: issues.filter((i) => i.step === step && i.level === "error").length,
    warnings: issues.filter((i) => i.step === step && i.level === "warning").length,
    empty: empty[step],
  }));
}

/** only errors block the final write; warnings never do */
export function canGenerate(issues: readonly Issue[]): boolean {
  return !issues.some((i) => i.level === "error");
}

export function summary(d: Draft) {
  const sections = d.courses.reduce((n, c) => n + c.sections.length, 0);
  const people = new Set(d.courses.flatMap((c) => c.sections.flatMap((s) => s.instructors.filter(Boolean).map((i) => (i!.id ? `#${i!.id}` : i!.name)))));
  const fresh = new Set(d.courses.flatMap((c) => c.sections.flatMap((s) => s.instructors.filter((i) => i && !i.id).map((i) => i!.name))));
  return {
    courses: d.courses.length,
    ects: d.courses.reduce((n, c) => n + (c.ects && !Number.isNaN(c.ects) ? c.ects : 0), 0),
    sections,
    people: people.size,
    newPeople: fresh.size,
    weeklyHours: d.courses.reduce((n, c) => n + patternHours(c), 0),
    meetings: d.courses.reduce((n, c) => n + c.sections.reduce((k, s) => k + s.meetingIds.length, 0), 0),
  };
}

export function meetingIds(d: Draft): number[] {
  return d.courses.flatMap((c) => c.sections.flatMap((s) => s.meetingIds));
}

/* ------------------------------------------------------------------ autosave plan */

export type SyncOp =
  | { kind: "faculty" }
  | { kind: "program" }
  | { kind: "course"; course: string }
  | { kind: "instructor"; course: string; section: string; slot: 0 | 1 }
  | { kind: "section"; course: string; section: string }
  | { kind: "pattern"; course: string; section: string }
  | { kind: "rules" };

const h = (v: unknown) => JSON.stringify(v);
export const hashes = {
  program: (d: Draft) => h([d.program.name.trim(), d.program.facultyId, d.program.evening, d.program.level, d.program.language]),
  course: (c: CourseDraft) => h([normalizeCode(c.code).code, c.name.trim(), c.t, c.u, c.l, c.ects]),
  section: (d: Draft, c: CourseDraft, s: SectionDraft) => h([d.termId, d.program.id, c.id, s.label, c.year, s.enrolment, c.mode, s.instructors.map((i) => (i ? (i.id ?? `new:${i.name}`) : null))]),
  pattern: (c: CourseDraft, s: SectionDraft) => h([c.t, c.u, c.l, c.pattern, c.room, s.enrolment, s.id]),
  rules: (d: Draft) => h([d.rules.window, d.rules.sameRoom, meetingIds(d)]),
};

/**
 * What the next save writes, in dependency order: the faculty, the programme, the courses (field-valid only),
 * new instructors, the sections, the weekly patterns (which create the meeting requests), then the rules
 * targeted at those meetings. An entity is written when its hash differs from its last save.
 */
export function planSync(d: Draft): SyncOp[] {
  const ops: SyncOp[] = [];
  if (!d.termId) return ops;
  const p = d.program;
  if (!p.facultyId && p.facultyName.trim()) ops.push({ kind: "faculty" });
  if (p.name.trim() && (p.facultyId || p.facultyName.trim()) && (!p.id || d.synced.program !== hashes.program(d))) ops.push({ kind: "program" });
  const codes = new Map<string, number>();
  for (const c of d.courses) {
    const nc = normalizeCode(c.code);
    if (nc.error) continue;
    codes.set(nc.code, (codes.get(nc.code) ?? 0) + 1);
  }
  for (const c of d.courses) {
    const nc = normalizeCode(c.code);
    const valid = !nc.error && codes.get(nc.code) === 1 && ![c.t, c.u, c.l, c.ects].some((v) => v !== null && Number.isNaN(v));
    if (!valid) continue;
    if (!c.id || (c.own && d.synced[c.key] !== hashes.course(c))) ops.push({ kind: "course", course: c.key });
    for (const s of c.sections) {
      s.instructors.forEach((i, slot) => {
        if (i && i.id === null && i.name.trim().length >= 2) ops.push({ kind: "instructor", course: c.key, section: s.key, slot: slot as 0 | 1 });
      });
      if ((s.enrolment ?? 0) > 0 || c.mode === "ONLINE") {
        if (!s.id || d.synced[s.key] !== hashes.section(d, c, s)) ops.push({ kind: "section", course: c.key, section: s.key });
        const hours = courseHours(c);
        const patternOk = c.pattern.start && c.pattern.days.length && (hours ? !c.pattern.theoryBlocks.length || patternHours(c) === hours : (c.pattern.weeklyHours ?? 0) > 0);
        if (patternOk && d.synced[`${s.key}:pattern`] !== hashes.pattern(c, s)) ops.push({ kind: "pattern", course: c.key, section: s.key });
      }
    }
  }
  if (meetingIds(d).length && d.synced.rules !== hashes.rules(d)) ops.push({ kind: "rules" });
  return ops;
}

/* ------------------------------------------------------------------ the worked example */

/**
 * Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (Fen Bilimleri Enstitüsü), 2026-GÜZ, rebuilt by hand (spec §4;
 * real Bahar rows 182–199). The joint totals that drive the room size are the Bahar ones where known
 * (MBG 598 + MBG 408 / 416 / 698 = 120; MBG 532 + MBG 012 = 80); the others are this YL program alone.
 */
export const MBG_TSV = [
  "Kod\tAd\tT\tU\tL\tK\tAKTS\tSınıf",
  "MBG 598\tSeminer\t0\t0\t0\t0\t9\t1",
  "MBG532\tEpigenetik\t3\t0\t0\t3\t9\t1",
  "MBG 534\tProteomiks\t3\t0\t0\t3\t9\t1",
  "MBG 546\tGenetik ve Genomiks\t3\t0\t0\t3\t9\t1",
  "MBG 502\tİleri Moleküler Genetik\t3\t0\t0\t3\t9\t1",
  "MBG 541\tGen Mühendisliği ve Biyoteknoloji\t3\t0\t0\t3\t9\t1",
  "MBG 549\tKanser İmmünolojisi\t3\t0\t0\t3\t9\t1",
].join("\n");

export const MBG_ENROLMENT: Record<string, number> = { "MBG 598": 120, "MBG 532": 80, "MBG 534": 15, "MBG 546": 15, "MBG 502": 12, "MBG 541": 15, "MBG 549": 15 };

export function coursesFromPaste(rows: readonly PastedRow[], enrolment: Record<string, number> = {}): CourseDraft[] {
  return rows.map((r) => {
    const nc = normalizeCode(r.code);
    const code = nc.error ? r.code : nc.code;
    const hours = (r.t ?? 0) + (r.u ?? 0) + (r.l ?? 0);
    return newCourse({
      code,
      name: r.name,
      t: r.t ?? 0,
      u: r.u ?? 0,
      l: r.l ?? 0,
      ects: r.ects,
      year: r.year && r.year > 0 ? r.year : 1,
      sections: [newSection("1", enrolment[code] ?? null)],
      pattern: { ...emptyPattern(), theoryBlocks: r.t ? [r.t] : [], weeklyHours: hours ? null : 1 },
    });
  });
}
