import type { Locale, MessageKey, Vars } from "@/lib/i18n";
import type { RuleTemplate, SourceRef, StudioMeta } from "@/lib/api/studio-schemas";
import type { TemplateField } from "@/lib/api/studio-schemas";
import { plainSentence, templateFor, tokens, type Params, type SentenceContext, type TemplateIssue, type Token } from "./rule-sentence";

type T = (key: MessageKey, vars?: Vars) => string;

export function ruleTokens(meta: StudioMeta | undefined, kind: string, params: Params, ctx: SentenceContext, showEmptyOptional = false): { template: RuleTemplate | undefined; tokens: Token[] | null } {
  const template = templateFor(kind, params, meta?.templates ?? []);
  return { template, tokens: template ? tokens(template, params, ctx, { showEmptyOptional }) : null };
}

export const FIELD_KEY: Record<string, MessageKey> = {
  applies_to: "studio.field.applies_to",
  building: "studio.field.building",
  buildings: "studio.field.buildings",
  days: "studio.field.days",
  latest: "studio.field.latest",
  earliest: "studio.field.earliest",
  tag: "studio.field.tag",
  rooms: "studio.field.rooms",
  room: "studio.field.room",
  course: "studio.field.course",
  courses: "studio.field.courses",
  from_date: "studio.field.from_date",
  periods: "studio.field.periods",
  weeks: "studio.field.weeks",
  unit: "studio.field.unit",
  n: "studio.field.n",
};

export function fieldLabel(field: TemplateField, t: T): string {
  return t(FIELD_KEY[field.name] ?? "studio.slot.value");
}

/** Plain messages for template validation issues: one "Still needed: a, b" line, then the others. */
export function issueMessages(issues: readonly TemplateIssue[], t: T, n: (v: number) => string = String): string[] {
  const missing = issues.filter((i) => i.code === "missing").map((i) => fieldLabel(i.field!, t));
  const out = missing.length ? [t("studio.builder.missing", { fields: missing.join(", ") })] : [];
  for (const i of issues) {
    if (i.code === "needOneTime") out.push(t("studio.builder.needOneTime"));
    else if (i.code === "timeOrder") out.push(t("studio.builder.timeOrder"));
    else if (i.code === "minItems") out.push(t("studio.builder.minItems", { n: n(i.n), field: fieldLabel(i.field, t) }));
    else if (i.code === "range") out.push(t("studio.builder.range", { field: fieldLabel(i.field, t), min: n(i.min), max: n(i.max) }));
  }
  return out;
}

export function catalogTitle(meta: StudioMeta | undefined, kind: string, locale: Locale): string {
  const c = meta?.catalog.find((x) => x.kind === kind);
  return c?.title[locale] ?? c?.title.en ?? kind;
}

/** Sentence used when no template matches: the catalogue title, plus the planner's own words. */
export function fallbackSentence(meta: StudioMeta | undefined, kind: string, nlText: string | null | undefined, locale: Locale): string {
  const title = catalogTitle(meta, kind, locale);
  return nlText ? `${title}: “${nlText}”` : title;
}

export function plainRuleText(meta: StudioMeta | undefined, kind: string, params: Params, nlText: string | null | undefined, ctx: SentenceContext): string {
  const r = ruleTokens(meta, kind, params, ctx);
  return r.tokens ? plainSentence(r.tokens) : fallbackSentence(meta, kind, nlText, ctx.locale);
}

/* ------------------------------------------------------------------ rule language */

const EN_WORDS = new Set(
  "the an and or for in on at no not after before class classes course courses room rooms keep every only must should never always week weeks building buildings put use same prefer please between exam exams lab labs morning mornings afternoon evening from to of with than closed all any day days monday tuesday wednesday thursday friday saturday sunday students hall halls"
    .split(" "),
);
const TR_EXACT = new Set("ve ile için her yok tut tüm hiç ya da veya bu şu".split(" "));
const TR_STEMS = "ders blok olsun olmasın sınıf hafta saat gün sabah akşam öğle sonra önce sadece yalnız asla kapalı açık pazartesi salı çarşamba perşembe cuma cumartesi pazar sınav laboratuvar amfi bütün kalsın yerleştir koyma kullan tercih aynı öğrenci bölüm".split(" ");

/** Language of a planner's own sentence (EN/TR word scores; Turkish letters count a little). Null if unclear. */
export function detectTextLang(text: string): "en" | "tr" | null {
  const words = text.replace(/İ/g, "i").replace(/I/g, "i").toLowerCase().match(/[a-zçğıöşü]+/g) ?? [];
  let en = 0;
  let tr = 0;
  for (const w of words) {
    if (EN_WORDS.has(w)) en += 1;
    else if (TR_EXACT.has(w) || TR_STEMS.some((s) => w.startsWith(s))) tr += 1;
    else if (/[çğıöşü]/.test(w)) tr += 0.5;
  }
  if (en === tr) return null;
  return en > tr ? "en" : "tr";
}

/** Rules the planner wrote in their own words (AI parse, an uploaded row, a planning-file note): their text is
 * the original and is kept as written. Builder, policy and quick-create rules are structured: their text is
 * rebuilt from the params in the UI language. */
export function isFreeTextRule(rule: { source: string; nl_text?: string | null }): boolean {
  return ["AI", "UPLOAD", "FILE"].includes(rule.source) && Boolean(rule.nl_text?.trim());
}

export interface RuleDisplay {
  template: RuleTemplate | undefined;
  tokens: Token[] | null;
  /** sentence when no template matches */
  fallback: string;
  /** the planner's original words (free-text rules only) */
  nlText: string | null;
  /** language of `nlText` when it differs from the UI language ("written in EN") */
  writtenIn: "en" | "tr" | null;
}

export function ruleDisplay(rule: { kind: string; params: Params; nl_text?: string | null; source: string }, meta: StudioMeta | undefined, ctx: SentenceContext, params: Params = rule.params): RuleDisplay {
  const { template, tokens: toks } = ruleTokens(meta, rule.kind, params, ctx);
  const free = isFreeTextRule(rule);
  const nlText = free ? (rule.nl_text ?? null) : null;
  const fallback = toks ? fallbackSentence(meta, rule.kind, null, ctx.locale) : free ? catalogTitle(meta, rule.kind, ctx.locale) : fallbackSentence(meta, rule.kind, rule.nl_text, ctx.locale);
  const lang = nlText ? detectTextLang(nlText) : null;
  return { template, tokens: toks, fallback, nlText, writtenIn: lang && lang !== ctx.locale ? lang : null };
}

export function allowedHardness(meta: StudioMeta | undefined, kind: string): ("hard" | "soft")[] {
  const c = meta?.catalog.find((x) => x.kind === kind);
  const list = (c?.allowed_hardness ?? ["hard", "soft"]).filter((h): h is "hard" | "soft" => h === "hard" || h === "soft");
  return list.length ? list : ["hard", "soft"];
}

/** "from Eczacılık_talepler.xlsx · Sayfa1 · row 12", "copied from term #3", … */
export function provenanceText(ref: SourceRef | null | undefined, t: T): string | null {
  if (!ref) return null;
  const copied = ref.copied_from as { term_id?: number; run_id?: number | null } | undefined;
  if (copied) return copied.run_id ? t("studio.provenance.copiedRun", { id: copied.run_id }) : t("studio.provenance.copiedTerm", { id: copied.term_id ?? "?" });
  const file = typeof ref.file === "string" ? ref.file : null;
  if (!file) return null;
  const where = ref.row !== undefined ? t("studio.provenance.row", { n: String(ref.row) }) : ref.page !== undefined ? t("studio.provenance.page", { n: String(ref.page) }) : ref.paragraph !== undefined ? t("studio.provenance.paragraph", { n: String(ref.paragraph) }) : ref.line !== undefined ? t("studio.provenance.line", { n: String(ref.line) }) : "";
  return t("studio.provenance.from", { where: [file, typeof ref.sheet === "string" ? ref.sheet : null, where].filter(Boolean).join(" · ") });
}

export function confidenceLevel(c: number): "high" | "medium" | "low" {
  return c >= 0.8 ? "high" : c >= 0.6 ? "medium" : "low";
}
