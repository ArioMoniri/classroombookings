/**
 * Pure helpers of Yönetim › Yapay zekâ (docs/design/v3/ai-admin.md): number formats, meter states, provider status,
 * route drafts and their checks, the stacked daily chart's data, the per-user table order, reason / outcome labels.
 * No React here (vitest: ai-model.test.ts).
 */
import { HttpError } from "@/lib/api/client";
import type { AiErrorDetail, Provider, Route, RouteFeature, RoutesIn, SyncedModel, UsageRow } from "@/lib/api/ai-admin";
import { ROUTE_FEATURES } from "@/lib/api/ai-admin";

const TAG: Record<string, string> = { tr: "tr-TR", en: "en-GB" };
const tag = (locale: string) => TAG[locale] ?? "en-GB";

/** "2,41 Mn" / "2.41M"; full value for `title` / `aria-label` comes from {@link fullNumber}. */
export function compactTokens(n: number, locale: string): string {
  return new Intl.NumberFormat(tag(locale), { notation: "compact", maximumFractionDigits: 2 }).format(n);
}

export function fullNumber(n: number, locale: string): string {
  return new Intl.NumberFormat(tag(locale)).format(n);
}

export function usd(n: number, locale: string): string {
  return new Intl.NumberFormat(tag(locale), { style: "currency", currency: "USD", maximumFractionDigits: n < 1 ? 4 : 2 }).format(n);
}

export function pctText(pct: number | null | undefined, locale: string): string {
  if (pct == null) return "";
  const v = new Intl.NumberFormat(tag(locale), { maximumFractionDigits: 0 }).format(pct);
  return locale === "tr" ? `%${v}` : `${v}%`;
}

export type MeterState = "none" | "ok" | "near" | "at";

/** A meter against a limit: no limit → none; ≥ 100 → at; ≥ soft threshold → near. */
export function meterState(pct: number | null | undefined, soft: number): MeterState {
  if (pct == null) return "none";
  if (pct >= 100) return "at";
  if (pct >= soft) return "near";
  return "ok";
}

/** Fill colour of a meter (same-ramp track; warning at the threshold, danger at 100 %; the word always next to it). */
export function meterFill(state: MeterState): string {
  return state === "at" ? "var(--status-infeasible-fg)" : state === "near" ? "var(--status-warning-fg)" : "var(--seq-4)";
}

export function pctOf(used: number, limit: number): number | null {
  return limit > 0 ? Math.round((1000 * used) / limit) / 10 : null;
}

export type ProviderStatus = "ok" | "noKey" | "error" | "disabled" | "untested";

export function providerStatus(p: Provider): ProviderStatus {
  if (p.config.enabled === false && p.id !== "anthropic") return "disabled";
  if (!p.has_credentials) return "noKey";
  if (p.last_test?.ok === false || p.sync_error) return "error";
  if (p.last_test?.ok) return "ok";
  return "untested";
}

export function providerLabel(p: Pick<Provider, "label_tr" | "label_en">, locale: string): string {
  return locale === "tr" ? p.label_tr : p.label_en;
}

/** Providers a route may pick: usable ones with at least one synced model. */
export function routableProviders(providers: readonly Provider[]): Provider[] {
  return providers.filter((p) => p.usable && p.models.length > 0);
}

export function syncedIds(providers: readonly Provider[], providerId: string | null | undefined): string[] {
  return providers.find((p) => p.id === providerId)?.models.map((m) => m.id) ?? [];
}

export type RouteIssue = "providerUnusable" | "modelNotSynced" | "fallbackSame" | "fallbackIncomplete" | "transferMissing";

/** Problems the screen shows before saving (the backend re-checks every one). */
export function routeIssues(route: Partial<Route> | null | undefined, providers: readonly Provider[], feature?: string): RouteIssue[] {
  if (!route?.provider) return [];
  const out: RouteIssue[] = [];
  const p = providers.find((x) => x.id === route.provider);
  if (!p?.usable) out.push("providerUnusable");
  if (!route.model || !syncedIds(providers, route.provider).includes(route.model)) out.push("modelNotSynced");
  if (route.fallback_provider || route.fallback_model) {
    if (!route.fallback_provider || !route.fallback_model) out.push("fallbackIncomplete");
    else if (route.fallback_provider === route.provider && route.fallback_model === route.model) out.push("fallbackSame");
    else if (!syncedIds(providers, route.fallback_provider).includes(route.fallback_model)) out.push("modelNotSynced");
  }
  if (feature && feature !== "explain" && p && !p.transfer_ok) out.push("transferMissing");
  return [...new Set(out)];
}

const ROUTE_FIELDS = ["provider", "model", "effort", "temperature", "max_tokens", "timeout_s", "max_tool_rounds", "fallback_provider", "fallback_model"] as const;

function cleanRoute(r: Partial<Route> | null | undefined): Partial<Route> | null {
  if (!r?.provider || !r.model) return null;
  const out: Record<string, unknown> = {};
  for (const k of ROUTE_FIELDS) {
    const v = r[k];
    if (v !== null && v !== undefined && v !== "") out[k] = v;
  }
  return out as Partial<Route>;
}

/** Draft (default + per feature, `null` = follow the default) → the `PUT /ai/admin/routes` body. */
export function routesBody(def: Partial<Route> | null, features: Partial<Record<RouteFeature, Partial<Route> | null>>): RoutesIn {
  const out: RoutesIn = { default: cleanRoute(def), features: {} };
  for (const f of ROUTE_FEATURES) {
    const r = cleanRoute(features[f]);
    if (r) out.features[f] = r;
  }
  return out;
}

/** Fixed categorical order of the stacked chart (colour follows the feature, never its rank). */
export const CHART_SERIES = ["chat", "rules", "intake", "explain", "vision", "other"] as const;
export type ChartSeries = (typeof CHART_SERIES)[number];
export const SERIES_COLOR: Record<ChartSeries, string> = {
  chat: "var(--cat-1)",
  rules: "var(--cat-2)",
  intake: "var(--cat-3)",
  explain: "var(--cat-4)",
  vision: "var(--cat-5)",
  other: "var(--label-3)",
};

export function seriesOf(feature: string): ChartSeries {
  return (CHART_SERIES as readonly string[]).includes(feature) ? (feature as ChartSeries) : "other";
}

export type DayPoint = { day: string; label: string; total: number } & Record<ChartSeries, number>;

/** `GET /ai/admin/usage?group=day` rows → one point per day with every series (0 when absent). */
export function dayChartData(rows: readonly UsageRow[], locale: string, lastDays?: number): DayPoint[] {
  const fmt = new Intl.DateTimeFormat(tag(locale), { day: "numeric", month: "short", timeZone: "UTC" });
  const points = rows.map((r) => {
    const day = String(r.key ?? "");
    const p = { day, label: day ? fmt.format(new Date(`${day}T00:00:00Z`)) : "", total: r.tokens } as DayPoint;
    for (const sname of CHART_SERIES) p[sname] = 0;
    for (const [feature, n] of Object.entries(r.features ?? {})) p[seriesOf(feature)] += n;
    return p;
  });
  return lastDays ? points.slice(-lastDays) : points;
}

/** Series that carry any value in the range (the legend lists only these, in the fixed order). */
export function activeSeries(points: readonly DayPoint[]): ChartSeries[] {
  return CHART_SERIES.filter((sname) => points.some((p) => p[sname] > 0));
}

/** The share of a user's monthly (else daily) limit used this period; null without a limit. */
export function userPct(row: UsageRow): number | null {
  const lim = row.limits;
  if (!lim) return null;
  if (lim.monthly > 0) return pctOf(row.tokens, lim.monthly);
  if (lim.daily > 0) return pctOf(row.tokens, lim.daily);
  return null;
}

/** Users table: search on name / e-mail, sorted by share of limit (then tokens), descending. */
export function sortUsers(rows: readonly UsageRow[], q: string): UsageRow[] {
  const needle = q.trim().toLocaleLowerCase("tr");
  const filtered = needle ? rows.filter((r) => `${r.label ?? ""} ${r.email ?? ""}`.toLocaleLowerCase("tr").includes(needle)) : [...rows];
  return filtered.sort((a, b) => (userPct(b) ?? -1) - (userPct(a) ?? -1) || b.tokens - a.tokens);
}

/** Known reason codes have their own label key (`aiAdmin.reason.<code>`); others show the code's family. */
export const REASONS = [
  "out_of_scope_code",
  "out_of_scope_translation",
  "out_of_scope_writing",
  "out_of_scope_general",
  "input_too_long",
  "code_like_input",
  "prompt_injection_override",
  "prompt_injection_roleplay",
  "prompt_injection_exfiltration",
  "prompt_injection_tool_smuggling",
  "prompt_injection_encoded",
  "prompt_injection_addressed",
  "model_scope_check",
  "rate_limited",
  "too_many_concurrent",
  "tool_rounds_exceeded",
  "output_unexpected_tool",
  "output_invalid_json",
  "ai_limit_reached",
  "ai_budget_exceeded",
  "ai_transfer_basis_missing",
  "provider_error",
  "provider_refusal",
  "provider_unsupported",
] as const;
export type Reason = (typeof REASONS)[number];

export function reasonOf(code: string | null | undefined): Reason | "other" {
  return code && (REASONS as readonly string[]).includes(code) ? (code as Reason) : "other";
}

export const OUTCOMES = ["ok", "refused_by_guardrail", "provider_error", "limit_reached"] as const;
export type Outcome = (typeof OUTCOMES)[number];
export function outcomeOf(o: string): Outcome {
  return (OUTCOMES as readonly string[]).includes(o) ? (o as Outcome) : "provider_error";
}

/** The backend's `{code, message_tr, message_en, errors}` from a failed request. */
export function errorDetail(e: unknown): AiErrorDetail | null {
  if (!(e instanceof HttpError)) return null;
  const d = e.detail as unknown;
  return d && typeof d === "object" ? (d as AiErrorDetail) : null;
}

export function errorMessage(e: unknown, locale: string, fallback: string): string {
  const d = errorDetail(e);
  const text = locale === "tr" ? d?.message_tr : d?.message_en;
  if (text) return text;
  return e instanceof HttpError && e.message && !/^\d{3}\b/.test(e.message) ? e.message : fallback;
}

/** The day the daily / monthly limit resets (Europe/Istanbul): tomorrow, or the 1st of next month. */
export function resetDate(kind: "day" | "month", locale: string, now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Istanbul", year: "numeric", month: "2-digit", day: "2-digit" }).format(now).split("-").map(Number);
  const [y, m, d] = parts as [number, number, number];
  const next = kind === "day" ? new Date(Date.UTC(y, m - 1, d + 1)) : new Date(Date.UTC(y, m, 1));
  return new Intl.DateTimeFormat(tag(locale), { day: "numeric", month: "long", timeZone: "UTC" }).format(next);
}

/** `Number(input)` for limit fields: empty → 0 (no limit), negative / NaN → null (invalid). */
export function parseLimit(raw: string): number | null {
  const t = raw.trim().replace(/[.\s]/g, "");
  if (!t) return 0;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : null;
}

/* ------------------------------------------------------------------ voice (VO-07) */

export type SpeechKind = "stt" | "tts";

/** A synced model that can do `kind`: its synced modalities when the backend sent them, else its id
 *  (`*transcribe*`, `whisper*` for speech-to-text; `*tts*` for read-aloud). */
export function isSpeechModel(m: Pick<SyncedModel, "id" | "modalities">, kind: SpeechKind = "stt"): boolean {
  if (m.modalities?.length) return m.modalities.includes(kind);
  return kind === "stt" ? /transcribe|whisper/i.test(m.id) : /(^|[-_])tts([-_]|$)/i.test(m.id);
}

/** Whether a provider says it can do `kind` (providers from a backend without capabilities: judged by models). */
export function providerCan(p: Pick<Provider, "capabilities" | "models">, kind: SpeechKind = "stt"): boolean {
  if (p.capabilities?.length) return p.capabilities.includes(kind);
  return (p.models ?? []).some((m) => isSpeechModel(m, kind));
}

/** The providers a speech route may use, each with only its speech-capable models. */
export function speechProviders(providers: readonly Provider[], kind: SpeechKind = "stt"): Provider[] {
  return providers.filter((p) => providerCan(p, kind)).map((p) => ({ ...p, models: p.models.filter((m) => isSpeechModel(m, kind)) }));
}

/** The first speech-capable synced model of a provider (what its voice test transcribes with). */
export function firstSpeechModel(p: Provider, kind: SpeechKind = "stt"): string | null {
  if (!providerCan(p, kind)) return null;
  return p.models.find((m) => isSpeechModel(m, kind))?.id ?? null;
}

/** Seconds (the backend's unit) ⇄ whole minutes (what the screen shows); empty → undefined. */
export function minutesOf(seconds: number | undefined): string {
  return seconds === undefined ? "" : String(Math.round(seconds / 60));
}
export function secondsOf(minutes: string): number | null | undefined {
  if (!minutes.trim()) return undefined;
  const n = parseLimit(minutes);
  return n === null ? null : n * 60;
}

/** Audio minutes per day from `GET /ai/admin/usage?group=day` rows (rows without audio are left out). */
export function audioDays(rows: readonly UsageRow[], locale: string): { day: string; label: string; minutes: number }[] {
  const fmt = new Intl.DateTimeFormat(tag(locale), { day: "numeric", month: "short", timeZone: "UTC" });
  return rows
    .filter((r) => (r.audio_minutes ?? 0) > 0)
    .map((r) => {
      const day = String(r.key ?? "");
      return { day, label: day ? fmt.format(new Date(`${day}T00:00:00Z`)) : "", minutes: Math.round((r.audio_minutes ?? 0) * 10) / 10 };
    });
}
