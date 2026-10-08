import type { Locale, MessageKey, Vars } from "@/lib/i18n";
import type { RuleTemplate, SourceRef, StudioMeta } from "@/lib/api/studio-schemas";
import { plainSentence, templateFor, tokens, type Params, type SentenceContext, type Token } from "./rule-sentence";

type T = (key: MessageKey, vars?: Vars) => string;

export function ruleTokens(meta: StudioMeta | undefined, kind: string, params: Params, ctx: SentenceContext, showEmptyOptional = false): { template: RuleTemplate | undefined; tokens: Token[] | null } {
  const template = templateFor(kind, params, meta?.templates ?? []);
  return { template, tokens: template ? tokens(template, params, ctx, { showEmptyOptional }) : null };
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
