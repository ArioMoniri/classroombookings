/**
 * Pure logic of the suggestion cards and the learning memory panel (docs/design/v2/phase19-suggestions.md):
 * confidence as word + 3-step meter, the evidence line ("2 dönemin 2'sinde" / "in 2 of 2 terms"), Bekleyen /
 * Geçmiş split, the typed confirmation word for "reset everything", and the undo window text. Unit-tested.
 */
import type { ResetRow, Suggestion } from "@/lib/api/learning";

export type Lang = "tr" | "en";

/** Yüksek ≥ 0.80 · Orta 0.60–0.79 · Düşük 0.50–0.59 (spec §4) → filled steps of the 3-step meter */
export function meterSteps(confidence: number): 0 | 1 | 2 | 3 {
  if (confidence >= 0.8) return 3;
  if (confidence >= 0.6) return 2;
  if (confidence >= 0.5) return 1;
  return 0;
}

export function levelCode(s: Pick<Suggestion, "level" | "confidence">): "high" | "medium" | "low" {
  if (s.level) return s.level.code;
  const st = meterSteps(s.confidence);
  return st === 3 ? "high" : st === 2 ? "medium" : "low";
}

/** the Turkish evidence count needs the 3rd-person possessive + locative: 2'sinde, 3'ünde, 4'ünde, 6'sında */
export function trOfTerms(seen: number, of: number): string {
  const tails: Record<number, string> = { 0: "ında", 1: "inde", 2: "sinde", 3: "ünde", 4: "ünde", 5: "inde", 6: "sında", 7: "sinde", 8: "inde", 9: "unda" };
  const last = seen % 10;
  const tens: Record<number, string> = { 10: "unda", 20: "sinde", 30: "unda", 40: "ında", 50: "sinde", 60: "ında", 70: "inde", 80: "inde", 90: "ında" };
  const tail = last === 0 && seen ? (tens[seen % 100] ?? "ünde") : (tails[last] ?? "inde");
  return `${of} dönemin ${seen}'${tail}`;
}

export function evidenceText(s: Pick<Suggestion, "support" | "evidence">, lang: Lang): string {
  const terms = s.evidence.terms ?? [];
  const seen = terms.filter((x) => x.pos > 0).length || s.support.seen_terms;
  const of = Math.max(terms.length, seen);
  if (of <= 1) return lang === "tr" ? `tek dönemde ${s.support.rows} kez` : `${s.support.rows} times in one term`;
  return lang === "tr" ? trOfTerms(seen, of) : `in ${seen} of ${of} terms`;
}

/** Bekleyen = open (never auto-applied); Geçmiş = decided or snoozed; hidden ones (explicit request wins, no
 *  classes this term, room unavailable) are not shown as cards */
export function splitSuggestions(list: readonly Suggestion[]): { pending: Suggestion[]; history: Suggestion[] } {
  const pending: Suggestion[] = [];
  const history: Suggestion[] = [];
  for (const s of list) {
    if (s.state === "open") pending.push(s);
    else if (s.state !== "hidden") history.push(s);
  }
  return { pending, history };
}

/** weights a learned preference may take (backend: 1..5, learned 5 < explicit 10, Q7) */
export const ACCEPT_WEIGHTS = { low: 2, normal: 5 } as const;

/* ------------------------------------------------------------------ memory reset */

const fold = (s: string) => s.trim().replace(/İ/g, "i").replace(/I/g, "ı").toLocaleLowerCase("tr-TR").replace(/ı/g, "i");

/** "Tümü" needs the typed word: SIFIRLA (tr) or RESET (en), either in either locale, Turkish-aware casefold */
export function typedConfirmOk(input: string): boolean {
  const v = fold(input);
  return v === fold("SIFIRLA") || v === fold("RESET");
}

export function reasonOk(reason: string): boolean {
  return reason.trim().length >= 3;
}

export type ResetStatus = "undoable" | "undone" | "purged" | "erased" | "expired";
export function resetStatus(r: ResetRow): ResetStatus {
  if (r.kind === "ERASURE") return "erased";
  if (r.undone_at) return "undone";
  if (r.purged_at) return "purged";
  return r.undoable ? "undoable" : "expired";
}
