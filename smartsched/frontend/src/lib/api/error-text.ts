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
