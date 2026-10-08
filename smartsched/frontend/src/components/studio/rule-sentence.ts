/**
 * Rule sentence model: turns a template sentence ("Keep {applies_to} in building {building} [on {days}]")
 * plus a rule's params into tokens (text and clickable slots), and reads/writes slot values back into
 * params. Pure and locale-aware; used by the rule card, the review tray, the builder and the tests.
 */
import type { Locale } from "@/lib/i18n";
import type { RuleTemplate, TemplateField } from "@/lib/api/studio-schemas";
import { harmoniseAfter } from "@/components/common/tr-suffix";
import { PERIODS } from "@/lib/time";
import { pairLang } from "@/lib/i18n";

export type Params = Record<string, unknown>;

/** Who a rule applies to. Mirrors the solver selectors (event_ids, programs, cohorts, match, instructors). */
export type AppliesTo =
  | { mode: "all" }
  | { mode: "programs"; programs: string[]; year: number | null }
  | { mode: "classes"; event_ids: number[] }
  | { mode: "other"; text: string };

export const SELECTOR_KEYS = ["event_ids", "cohort", "cohorts", "program", "programs", "match", "instructor", "instructors"] as const;

export interface SentenceContext {
  locale: Locale;
  roomCode: (id: number) => string;
  classLabel: (id: number) => string;
  /** every programme name in the term (for "only for X" = forbidden for everyone else) */
  programs: string[];
  dayName: (day: number) => string;
  tagLabel: (tag: string) => string;
  /** "all classes" / "3 classes" … */
  words: { allClasses: string; nClasses: (n: number) => string; year: (y: number) => string; choose: string; fromWeek: (w: number) => string; weeks: (w: string) => string };
}

export interface Slot {
  name: string;
  field: TemplateField;
  value: unknown;
  display: string;
  empty: boolean;
  optional: boolean;
}

export type Token = { kind: "text"; text: string } | { kind: "slot"; slot: Slot };

type Part = { kind: "text"; text: string } | { kind: "slot"; name: string } | { kind: "optional"; parts: Part[] };

/** "{a} x [y {b}]" → parts; brackets mark optional groups (no nesting). */
export function parseTemplate(sentence: string): Part[] {
  const out: Part[] = [];
  const re = /\[([^\]]*)\]|\{(\w+)\}|([^[{]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(sentence)) !== null) {
    if (m[1] !== undefined) out.push({ kind: "optional", parts: parseTemplate(m[1]) });
    else if (m[2] !== undefined) out.push({ kind: "slot", name: m[2] });
    else if (m[3] !== undefined) out.push({ kind: "text", text: m[3] });
  }
  return out;
}

const asNums = (v: unknown): number[] => (Array.isArray(v) ? v : v === undefined || v === null || v === "" ? [] : [v]).map(Number).filter((x) => Number.isFinite(x));
const asStrs = (v: unknown): string[] => (Array.isArray(v) ? v : v === undefined || v === null || v === "" ? [] : [v]).map(String);

export function compactRange(nums: number[]): string {
  const s = [...new Set(nums)].sort((a, b) => a - b);
  if (s.length === 0) return "";
  const parts: string[] = [];
  let start = s[0];
  let prev = s[0];
  for (const x of s.slice(1).concat([Number.NaN])) {
    if (x === prev + 1) {
      prev = x;
      continue;
    }
    parts.push(start === prev ? String(start) : `${start}–${prev}`);
    start = x;
    prev = x;
  }
  return parts.join(", ");
}

/* ------------------------------------------------------------------------- applies to */

export function readAppliesTo(params: Params): AppliesTo {
  const ids = asNums(params.event_ids);
  if (ids.length) return { mode: "classes", event_ids: ids };
  const cohorts = [...asStrs(params.cohort), ...asStrs(params.cohorts)];
  const programs = [...asStrs(params.program), ...asStrs(params.programs)];
  if (cohorts.length) {
    const parsed = cohorts.map((c) => /^PROG:(.+):Y(\d+)$/.exec(c)).filter((m): m is RegExpExecArray => m !== null);
    if (parsed.length === cohorts.length) {
      const years = [...new Set(parsed.map((m) => Number(m[2])))];
      return { mode: "programs", programs: [...new Set([...programs, ...parsed.map((m) => m[1])])], year: years.length === 1 ? years[0] : null };
    }
  }
  if (programs.length) return { mode: "programs", programs, year: null };
  const other = [...asStrs(params.match), ...asStrs(params.instructor), ...asStrs(params.instructors), ...cohorts];
  if (other.length) return { mode: "other", text: other.join(", ") };
  return { mode: "all" };
}

/** Writes a selector into params, replacing every previous selector key. */
export function writeAppliesTo(params: Params, value: AppliesTo): Params {
  const next: Params = { ...params };
  for (const k of SELECTOR_KEYS) delete next[k];
  if (value.mode === "classes" && value.event_ids.length) next.event_ids = [...value.event_ids];
  if (value.mode === "programs" && value.programs.length) {
    if (value.year) next.cohorts = value.programs.map((p) => `PROG:${p}:Y${value.year}`);
    else next.programs = [...value.programs];
  }
  if (value.mode === "other" && value.text.trim()) next.match = value.text.trim();
  return next;
}

export function appliesToDisplay(v: AppliesTo, ctx: SentenceContext): string {
  switch (v.mode) {
    case "all":
      return ctx.words.allClasses;
    case "programs": {
      const names = v.programs.length > 2 ? `${v.programs.slice(0, 2).join(", ")} +${v.programs.length - 2}` : v.programs.join(", ");
      return v.year ? `${names} ${ctx.words.year(v.year)}` : names;
    }
    case "classes":
      return v.event_ids.length === 1 ? ctx.classLabel(v.event_ids[0]) : ctx.words.nClasses(v.event_ids.length);
    case "other":
      return v.text;
  }
}

/** "TIP rooms only for Tıp" is stored as forbidden_tags for every *other* programme. */
export function othersComplement(params: Params, ctx: SentenceContext): string[] {
  const a = readAppliesTo(params);
  if (a.mode !== "programs") return [];
  const stored = new Set(a.programs);
  return ctx.programs.filter((p) => !stored.has(p));
}

/* ------------------------------------------------------------------- field read/write */

export function readField(field: TemplateField, params: Params, ctx: SentenceContext): unknown {
  switch (field.type) {
    case "applies_to":
      return readAppliesTo(params);
    case "applies_to_others":
      return othersComplement(params, ctx);
    case "building": {
      const b = params[field.param] ?? asStrs(params.buildings)[0];
      return typeof b === "string" && b ? b : null;
    }
    case "buildings":
    case "tag":
      return asStrs(params[field.param]);
    case "days":
    case "periods":
    case "rooms":
    case "courses":
    case "weeks":
    case "date":
      return asNums(params[field.param]);
    case "room":
    case "period":
    case "number": {
      const v = params[field.param];
      return v === undefined || v === null || v === "" ? null : Number(v);
    }
    default:
      return params[field.param] ?? null;
  }
}

export function writeField(field: TemplateField, params: Params, value: unknown, ctx: SentenceContext): Params {
  if (field.type === "applies_to") return writeAppliesTo(params, value as AppliesTo);
  if (field.type === "applies_to_others") {
    const allowed = new Set(asStrs(value));
    const others = ctx.programs.filter((p) => !allowed.has(p));
    return writeAppliesTo(params, allowed.size ? { mode: "programs", programs: others, year: null } : { mode: "all" });
  }
  const next: Params = { ...params };
  const empty = value === null || value === undefined || (Array.isArray(value) && value.length === 0) || value === "";
  if (empty) delete next[field.param];
  else next[field.param] = value;
  if (field.type === "building") delete next.buildings;
  return next;
}

export function isEmptyValue(field: TemplateField, value: unknown): boolean {
  if (field.type === "applies_to") return false; // "all classes" is a valid choice
  if (value === null || value === undefined || value === "") return true;
  return Array.isArray(value) && value.length === 0;
}

export function displayValue(field: TemplateField, value: unknown, ctx: SentenceContext): string {
  if (isEmptyValue(field, value)) return ctx.words.choose;
  switch (field.type) {
    case "applies_to":
      return appliesToDisplay(value as AppliesTo, ctx);
    case "applies_to_others": {
      const list = asStrs(value);
      return list.length > 2 ? `${list.slice(0, 2).join(", ")} +${list.length - 2}` : list.join(", ");
    }
    case "building":
      return String(value).toLocaleUpperCase(ctx.locale === "tr" ? "tr-TR" : "en-US");
    case "buildings":
      return asStrs(value).map((b) => b.toLocaleUpperCase(ctx.locale === "tr" ? "tr-TR" : "en-US")).join(ctx.locale === "tr" ? " ve " : " and ");
    case "tag":
      return asStrs(value).map(ctx.tagLabel).join(", ");
    case "days":
      return asNums(value).map(ctx.dayName).join(", ");
    case "period": {
      const p = PERIODS[Number(value) - 1];
      if (!p) return `P${String(value)}`;
      return field.name === "earliest" ? p.start : p.end;
    }
    case "periods": {
      const ps = asNums(value).sort((a, b) => a - b);
      const a = PERIODS[ps[0] - 1];
      const b = PERIODS[ps[ps.length - 1] - 1];
      return a && b ? `P${ps[0]}–P${ps[ps.length - 1]} (${a.start}–${b.end})` : compactRange(ps);
    }
    case "rooms":
      return asNums(value).map(ctx.roomCode).join(", ");
    case "room":
      return ctx.roomCode(Number(value));
    case "courses": {
      const ids = asNums(value);
      return ids.length <= 2 ? ids.map(ctx.classLabel).join(", ") : ctx.words.nClasses(ids.length);
    }
    case "date": {
      const ws = asNums(value);
      return ws.length ? ctx.words.fromWeek(Math.min(...ws)) : ctx.words.choose;
    }
    case "weeks":
      return ctx.words.weeks(compactRange(asNums(value)));
    default:
      return String(value);
  }
}

/* ---------------------------------------------------------------------------- tokens */

export function tokens(template: RuleTemplate, params: Params, ctx: SentenceContext, opts: { showEmptyOptional?: boolean } = {}): Token[] {
  const sentence = template.sentence[pairLang(ctx.locale)] || template.sentence.en;
  const fields = new Map(template.fields.map((f) => [f.name, f]));
  const slotOf = (name: string, optional: boolean): Slot | null => {
    const field = fields.get(name);
    if (!field) return null;
    const value = readField(field, params, ctx);
    return { name, field, value, display: displayValue(field, value, ctx), empty: isEmptyValue(field, value), optional };
  };
  const out: Token[] = [];
  const walk = (parts: Part[], optional: boolean) => {
    for (const p of parts) {
      if (p.kind === "text") out.push({ kind: "text", text: p.text });
      else if (p.kind === "slot") {
        const s = slotOf(p.name, optional);
        if (s) out.push({ kind: "slot", slot: s });
        else out.push({ kind: "text", text: `{${p.name}}` });
      } else {
        const inner = p.parts.filter((x): x is { kind: "slot"; name: string } => x.kind === "slot").map((x) => slotOf(x.name, true));
        const filled = inner.some((s) => s && !s.empty);
        if (filled || opts.showEmptyOptional) walk(p.parts, true);
      }
    }
  };
  walk(parseTemplate(sentence), false);
  // Turkish suffix harmony after a filled slot: "{date}'den itibaren" + "4. hafta" → "4. haftadan itibaren",
  // "{latest}'den sonra" + "17:30" → "17:30'dan sonra" (usability m2)
  if (ctx.locale === "tr") {
    for (let i = 1; i < out.length; i++) {
      const prev = out[i - 1];
      const cur = out[i];
      if (prev?.kind === "slot" && !prev.slot.empty && cur?.kind === "text") out[i] = { kind: "text", text: harmoniseAfter(prev.slot.display, cur.text) };
    }
  }
  // tidy whitespace between tokens
  return out.filter((t) => t.kind === "slot" || t.text.length > 0);
}

export function plainSentence(toks: Token[]): string {
  return toks.map((t) => (t.kind === "text" ? t.text : t.slot.display)).join("").replace(/\s+/g, " ").trim();
}

/** The template that best describes a stored rule (kind + which params are set). */
export function templateFor(kind: string, params: Params, templates: readonly RuleTemplate[]): RuleTemplate | undefined {
  const same = templates.filter((t) => t.kind === kind);
  if (same.length <= 1) return same[0];
  const scored = same.map((t) => ({ t, score: t.fields.filter((f) => f.param !== "selector" && params[f.param] !== undefined).length }));
  scored.sort((a, b) => b.score - a.score);
  return scored[0]?.t;
}

/** Template defaults (e.g. needs_lab → required_tags ["PC"], no_small_in_big → unit 10). */
export function defaultParams(template: RuleTemplate): Params {
  const out: Params = {};
  for (const f of template.fields) if (f.default !== undefined && f.param !== "selector") out[f.param] = f.default;
  return out;
}

/** Required fields that are still empty (builder validation). */
export function missingRequired(template: RuleTemplate, params: Params, ctx: SentenceContext): TemplateField[] {
  return template.fields.filter((f) => f.required && isEmptyValue(f, readField(f, params, ctx)));
}

/** Weight ↔ Low / Normal / High (2 / 5 / 8 from GET /studio/meta). */
export type Importance = "low" | "normal" | "high" | "custom";
export interface WeightScale {
  low: number;
  normal: number;
  high: number;
}
export const DEFAULT_SCALE: WeightScale = { low: 2, normal: 5, high: 8 };
export function importanceOf(weight: number, scale: WeightScale = DEFAULT_SCALE): Importance {
  if (weight === scale.low) return "low";
  if (weight === scale.normal) return "normal";
  if (weight === scale.high) return "high";
  return "custom";
}
