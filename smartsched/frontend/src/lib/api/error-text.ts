/**
 * Planner-facing text of an API refusal (round-1 R1-M-02 / R1-S-06): a 409 is only "someone else changed it"
 * when the server says the record is stale; every other refusal (scope reduction, a run that is not finished, a
 * forced hard-rule break, an empty plan, ...) is shown in the server's own words (`message_tr` / `message_en`, or
 * `{tr, en}`), never as a concurrency conflict.
 */
import { HttpError } from "./client";

const rec = (v: unknown): Record<string, unknown> | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null);

/** The structured body of a refusal: FastAPI wraps a dict detail as `{detail: {...}}`. */
export function refusalBody(e: unknown): Record<string, unknown> | null {
  if (!(e instanceof HttpError)) return null;
  const d = rec(e.detail);
  return rec(d?.detail) ?? d;
}

/** The refusal's machine code (`scope_reduction`, `forced_breaks`, `capacity`, `empty_plan` ...), if any. */
export function refusalCode(e: unknown): string | null {
  const b = refusalBody(e);
  return typeof b?.code === "string" ? b.code : null;
}

const STALE_CODES = new Set(["stale", "version_conflict", "changed", "conflict", "plan_stale", "draft_changed"]);
const STALE_TEXT = /changed since|stale|version|başka biri|değişti/i;

/** True only for the "the record changed meanwhile" family of 409s. */
export function isStaleConflict(e: unknown): boolean {
  if (!(e instanceof HttpError) || e.status !== 409) return false;
  const code = refusalCode(e);
  if (code) return STALE_CODES.has(code);
  const b = refusalBody(e);
  const msg = typeof b?.message === "string" ? b.message : typeof e.detail === "string" ? e.detail : rec(e.detail) && typeof rec(e.detail)?.detail === "string" ? String(rec(e.detail)?.detail) : "";
  return !msg || STALE_TEXT.test(msg);
}

/**
 * The server's own sentence in the planner's language, or null when it gave none. `strict` (the global toast in
 * Turkish): only a Turkish sentence is returned, never the backend's English detail (usability m1).
 */
export function serverMessage(e: unknown, locale: string, strict = false): string | null {
  const b = refusalBody(e);
  const tr = b?.message_tr ?? b?.tr;
  if (strict && locale === "tr") return typeof tr === "string" && tr.trim() ? tr : null;
  if (b) {
    const en = b.message_en ?? b.en ?? b.message;
    const pick = locale === "tr" ? (tr ?? en) : (en ?? tr);
    if (typeof pick === "string" && pick.trim()) return pick;
    const issues = Array.isArray(b.issues) ? b.issues.map(String).filter(Boolean) : [];
    if (issues.length) return issues.slice(0, 3).join(" · ");
  }
  if (e instanceof HttpError) {
    const d = rec(e.detail);
    if (typeof d?.detail === "string") return d.detail;
    if (typeof e.detail === "string") return e.detail;
  }
  return null;
}

/* ------------------------------------------------------------------ validation issues (round-1 R1-M-17, T-R1-31) */

/** One refused field of a 422 (FastAPI `detail[]`) or a coded refusal, in the reader's language. */
export interface ValidationIssue {
  /** the body field (`url`, `tenant_id`), or null when the server named none */
  field: string | null;
  /** what the person reads: `ctx.message_tr` in Turkish, else the English sentence without pydantic's prefix */
  text: string;
  /** the server's English sentence and code, for an expandable "technical detail" part */
  detail: string | null;
  code: string | null;
}

const PYDANTIC_PREFIX = /^(?:Value error|Assertion failed|Type error),\s*/i;

/** `"Value error, URL too long"` → `"URL too long"`. */
export function stripPydanticPrefix(msg: string): string {
  return msg.replace(PYDANTIC_PREFIX, "").trim();
}

/** pydantic's own error types (a missing field, a too-long string) in Turkish; anything else keeps the server's text. */
const PYDANTIC_TR: Record<string, string> = {
  missing: "Bu alan zorunlu.",
  string_too_long: "Değer çok uzun.",
  string_too_short: "Değer çok kısa.",
  int_parsing: "Bir tam sayı girin.",
  int_type: "Bir tam sayı girin.",
  float_parsing: "Bir sayı girin.",
  greater_than_equal: "Değer çok küçük.",
  less_than_equal: "Değer çok büyük.",
  too_short: "En az bir öğe seçin.",
  too_long: "Çok fazla öğe seçildi.",
  bool_parsing: "Evet ya da hayır bekleniyor.",
  enum: "Listedeki seçeneklerden birini seçin.",
  literal_error: "Listedeki seçeneklerden birini seçin.",
  json_invalid: "Gönderilen veri okunamadı.",
  value_error: "Girilen değer kabul edilmedi.",
};

const fieldOf = (loc: unknown): string | null => {
  if (!Array.isArray(loc)) return null;
  const parts = loc.filter((x) => typeof x === "string" && x !== "body" && x !== "query" && x !== "path") as string[];
  return parts.length ? parts[parts.length - 1]! : null;
};

/** The refused fields of a 422 (empty for any other refusal). */
export function validationIssues(e: unknown, locale: string): ValidationIssue[] {
  if (!(e instanceof HttpError)) return [];
  const d = rec(e.detail);
  const list = Array.isArray(e.detail) ? e.detail : Array.isArray(d?.detail) ? d.detail : null;
  if (!list) return [];
  return list.flatMap((item): ValidationIssue[] => {
    const it = rec(item);
    if (!it) return [];
    const ctx = rec(it.ctx);
    const msg = typeof it.msg === "string" ? stripPydanticPrefix(it.msg) : "";
    const type = typeof it.type === "string" ? it.type : null;
    const code = typeof ctx?.code === "string" ? ctx.code : type;
    const en = typeof ctx?.message_en === "string" && ctx.message_en.trim() ? ctx.message_en : msg;
    const tr = typeof ctx?.message_tr === "string" && ctx.message_tr.trim() ? ctx.message_tr : type ? PYDANTIC_TR[type] : undefined;
    const text = locale === "tr" ? (tr ?? en) : en || tr || "";
    if (!text) return [];
    return [{ field: fieldOf(it.loc), text, detail: en && en !== text ? en : null, code }];
  });
}

/**
 * The text a form shows for a refused request: the server's coded sentence (`serverMessage`), else the refused
 * fields' sentences, else null. Never pydantic's `Value error,` prefix.
 */
export function problemText(e: unknown, locale: string): string | null {
  const issues = validationIssues(e, locale);
  if (issues.length) return [...new Set(issues.map((i) => i.text))].join(" · ");
  const said = serverMessage(e, locale);
  return said ? stripPydanticPrefix(said) : null;
}

/** The English sentences behind `problemText`, when they differ from what was shown (the "technical detail"). */
export function problemDetail(e: unknown, locale: string): string | null {
  const parts = validationIssues(e, locale)
    .map((i) => i.detail)
    .filter((x): x is string => !!x);
  if (parts.length) return [...new Set(parts)].join(" · ");
  const b = refusalBody(e);
  const en = typeof b?.message_en === "string" ? b.message_en : typeof b?.message === "string" ? b.message : null;
  return locale === "tr" && en && en !== problemText(e, locale) ? en : null;
}
