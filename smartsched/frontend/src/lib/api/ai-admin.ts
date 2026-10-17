"use client";
/**
 * W3-AI gateway administration (`app/api/v1/ai_admin.py`). Administrators with `planning.admin` or
 * `setup.settings`:
 * - `GET /ai/admin/providers` — one entry per provider: `keys` (`{set, masked}`; a key is never returned), `config`
 *   (`base_url` / `region` / `project_id`, `enabled`), `models` (synced, with `fetched_at`, `sync_error`),
 *   `last_test`, the KVKK `transfer` record and `transfer_ok`, `local` (a loopback / private base URL).
 * - `PUT /ai/admin/providers/{p}` `{api_key?, aws_access_key_id?, aws_secret_access_key?, clear?[], base_url?, region?,
 *   project_id?, enabled?, transfer?}` (422 `invalid_key | invalid_url | unknown_field | invalid_mechanism`).
 * - `POST /ai/admin/providers/{p}/sync` (409 `no_credentials`) → `{ok, fetched_at, models, error}`.
 * - `POST /ai/admin/providers/{p}/test {model?}` → `{ok, detail, model, at}` (a few-token real call, metered as `test`).
 * - `GET/PUT /ai/admin/routes` — `{default, features: {rules|chat|intake|vision|explain|booking_nl: Route|null}}`; the
 *   answer adds `effective` (the route each feature uses, with `source` feature/default/legacy and `caps`); 422
 *   `invalid_routes` with `errors[] {route, field, code, message_tr, message_en}` (`model_not_synced` …).
 * - `GET /ai/admin/usage?group=day|user|feature|model|provider|outcome&start&end&q` → `{rows}`;
 *   `GET /ai/admin/usage/summary` → `{org, by_feature, feature_labels}`; `GET /ai/admin/refusals`.
 * - `GET/PUT /ai/admin/limits`, `POST /ai/admin/limits/topup {tokens, cost_usd, reason}`.
 * - `GET/PUT /ai/admin/guardrails`, `POST /ai/admin/guardrails/check {text, feature, surface}` (dry run),
 *   `POST /ai/admin/redteam` (the shipped corpus through the guard).
 * Every signed-in user: `GET /ai/me/usage` (own usage, limits, banner `state`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

const s = { silent: true } as const;

export const AI_FEATURES = ["rules", "chat", "intake", "vision", "explain", "booking_nl"] as const;
export type AiFeature = (typeof AI_FEATURES)[number];
export const EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;

const KeyState = z.object({ set: z.boolean(), masked: z.string().nullish() });
export const SyncedModel = z.object({
  id: z.string(),
  display_name: z.string().nullish(),
  context_window: z.number().nullish(),
  max_output: z.number().nullish(),
  price_in: z.number().nullish(),
  price_out: z.number().nullish(),
  created_at: z.string().nullish(),
});
export type SyncedModel = z.infer<typeof SyncedModel>;
export const Transfer = z.object({
  region: z.string().nullish(),
  retention: z.string().nullish(),
  kvkk_mechanism: z.string().nullish(),
  contract_date: z.string().nullish(),
  notification_date: z.string().nullish(),
  note: z.string().nullish(),
  recorded_at: z.string().nullish(),
});
export type Transfer = z.infer<typeof Transfer>;
export const TestResult = z.object({ ok: z.boolean(), detail: z.string().default(""), model: z.string().nullish(), at: z.string().nullish() });
export type TestResult = z.infer<typeof TestResult>;
export const Provider = z.object({
  id: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  secrets: z.array(z.string()),
  config: z.record(z.string(), z.unknown()).default({}),
  config_fields: z.array(z.string()).default([]),
  keyless: z.boolean().default(false),
  default_base_url: z.string().nullish(),
  keys: z.record(z.string(), KeyState).default({}),
  has_credentials: z.boolean(),
  usable: z.boolean(),
  models: z.array(SyncedModel).default([]),
  fetched_at: z.string().nullish(),
  sync_error: z.string().nullish(),
  last_test: TestResult.partial().default({}),
  transfer: Transfer.default({}),
  transfer_ok: z.boolean(),
  local: z.boolean().default(false),
  // SSRF guard (docs/SECURITY.md R12): the OpenAI-compatible provider's opt-in for a local server, and its warning
  allow_local: z.boolean().default(false),
  warnings: z.array(z.object({ code: z.string(), message_tr: z.string(), message_en: z.string() })).default([]),
});
export type Provider = z.infer<typeof Provider>;
const ProviderList = z.object({ providers: z.array(Provider), kvkk_mechanisms: z.array(z.string()) });
export type ProviderList = z.infer<typeof ProviderList>;
export const SyncResult = z.object({ ok: z.boolean(), fetched_at: z.string().nullish(), models: z.array(SyncedModel), error: z.string().nullish() });

export const Route = z.object({
  provider: z.string(),
  model: z.string(),
  effort: z.string().nullish(),
  temperature: z.number().nullish(),
  max_tokens: z.number().nullish(),
  timeout_s: z.number().nullish(),
  max_tool_rounds: z.number().nullish(),
  fallback_provider: z.string().nullish(),
  fallback_model: z.string().nullish(),
});
export type Route = z.infer<typeof Route>;
const Effective = Route.extend({ source: z.string(), caps: z.record(z.string(), z.unknown()).default({}) });
export const Routes = z.object({
  default: Route.nullish(),
  features: z.record(z.string(), Route.nullish()).default({}),
  effective: z.record(z.string(), Effective),
  feature_list: z.array(z.object({ id: z.string(), label_tr: z.string(), label_en: z.string() })),
  efforts: z.array(z.string()),
  legacy_model: z.string(),
});
export type Routes = z.infer<typeof Routes>;
export interface RoutesIn {
  default?: Partial<Route> | null;
  features: Partial<Record<AiFeature, Partial<Route> | null>>;
}

export const UsageRow = z.object({
  key: z.union([z.string(), z.number()]).nullable(),
  calls: z.number(),
  tokens: z.number(),
  cost_usd: z.number().default(0),
  refused: z.number().default(0),
  input_tokens: z.number().optional(),
  output_tokens: z.number().optional(),
  cache_tokens: z.number().optional(),
  avg_latency_ms: z.number().optional(),
  label: z.string().nullish(),
  email: z.string().nullish(),
  role: z.string().nullish(),
  limits: z.object({ daily: z.number(), monthly: z.number() }).nullish(),
  features: z.record(z.string(), z.number()).optional(),
});
export type UsageRow = z.infer<typeof UsageRow>;
export const USAGE_GROUPS = ["day", "user", "feature", "model", "provider", "outcome"] as const;
export type UsageGroup = (typeof USAGE_GROUPS)[number];

export const OrgState = z.object({
  day_tokens: z.number(),
  month_tokens: z.number(),
  month_cost_usd: z.number(),
  month_calls: z.number(),
  budget_tokens: z.number(),
  budget_cost_usd: z.number(),
  pct: z.number().nullable(),
  state: z.string(),
  soft_pct: z.number(),
  month: z.string(),
});
export type OrgState = z.infer<typeof OrgState>;
const Summary = z.object({ org: OrgState, by_feature: z.array(UsageRow), feature_labels: z.record(z.string(), z.object({ tr: z.string(), en: z.string() })) });
export type Summary = z.infer<typeof Summary>;

export const Refusal = z.object({
  id: z.number(),
  at: z.string().nullish(),
  user_id: z.number().nullish(),
  user_label: z.string().nullish(),
  feature: z.string(),
  provider: z.string(),
  model: z.string(),
  outcome: z.string(),
  reason_code: z.string().nullish(),
  detail: z.string().nullish(),
  prompt_chars: z.number().nullish(),
});
export type Refusal = z.infer<typeof Refusal>;

const LimitPair = z.object({ daily: z.number().optional(), monthly: z.number().optional() });
export const Limits = z.object({
  org_monthly_tokens: z.number(),
  org_monthly_cost_usd: z.number(),
  user_daily_tokens: z.number(),
  user_monthly_tokens: z.number(),
  roles: z.record(z.string(), LimitPair).default({}),
  users: z.record(z.string(), LimitPair).default({}),
  soft_pct: z.number(),
  alert_recipients: z.array(z.number()).default([]),
  requests_per_minute: z.number(),
  max_concurrent: z.number(),
  topups: z.array(z.object({ month: z.string(), tokens: z.number().default(0), cost_usd: z.number().default(0), reason: z.string().nullish(), at: z.string().nullish() })).default([]),
  org: OrgState,
});
export type Limits = z.infer<typeof Limits>;
export type LimitsIn = Partial<Omit<Limits, "org" | "topups">>;

export const Guardrails = z.object({
  scope_check: z.boolean(),
  injection_check: z.boolean(),
  model_scope_check: z.boolean(),
  upload_neutralize: z.boolean(),
  output_check: z.boolean(),
  rate_limit: z.boolean(),
});
export type Guardrails = z.infer<typeof Guardrails>;
export const GUARD_SWITCHES = ["scope_check", "injection_check", "upload_neutralize", "output_check", "rate_limit", "model_scope_check"] as const;

export const GuardCheck = z.object({
  surface: z.string(),
  allowed: z.boolean(),
  result: z.enum(["allow", "refuse", "keep", "mark", "remove"]),
  reason_code: z.string().nullish(),
  rules: z.array(z.string()).default([]),
  message_tr: z.string().nullish(),
  message_en: z.string().nullish(),
  cleaned: z.string().nullish(),
});
export type GuardCheck = z.infer<typeof GuardCheck>;
export const RedTeam = z.object({
  total: z.object({ cases: z.number(), passed: z.number(), false_positives: z.number(), gate: z.boolean() }),
  by_category: z.record(z.string(), z.object({ cases: z.number(), passed: z.number(), false_positives: z.number() })),
  failed: z.array(z.record(z.string(), z.unknown())).default([]),
});
export type RedTeam = z.infer<typeof RedTeam>;

export const MyUsage = z.object({
  user_id: z.number(),
  day_tokens: z.number(),
  month_tokens: z.number(),
  day_calls: z.number().default(0),
  month_calls: z.number().default(0),
  daily_limit: z.number(),
  monthly_limit: z.number(),
  daily_pct: z.number().nullable(),
  monthly_pct: z.number().nullable(),
  pct: z.number().nullable(),
  state: z.string(),
  soft_pct: z.number(),
  org_state: z.string(),
  by_feature: z.array(UsageRow).default([]),
});
export type MyUsage = z.infer<typeof MyUsage>;

export const aiAdminApi = {
  providers: () => request("/ai/admin/providers", { schema: ProviderList, ...s }),
  saveProvider: (p: string, body: Record<string, unknown>) => request(`/ai/admin/providers/${p}`, { method: "PUT", body, schema: Provider, ...s }),
  sync: (p: string) => request(`/ai/admin/providers/${p}/sync`, { method: "POST", schema: SyncResult, ...s }),
  test: (p: string, model?: string) => request(`/ai/admin/providers/${p}/test`, { method: "POST", body: { model: model || null }, schema: TestResult, ...s }),
  routes: () => request("/ai/admin/routes", { schema: Routes, ...s }),
  saveRoutes: (body: RoutesIn) => request("/ai/admin/routes", { method: "PUT", body, schema: Routes, ...s }),
  usage: (group: UsageGroup, q?: { start?: string; end?: string; q?: string }) => request("/ai/admin/usage", { query: { group, ...q }, schema: z.object({ group: z.string(), rows: z.array(UsageRow) }), ...s }),
  summary: () => request("/ai/admin/usage/summary", { schema: Summary, ...s }),
  refusals: () => request("/ai/admin/refusals", { schema: z.object({ rows: z.array(Refusal) }), ...s }),
  limits: () => request("/ai/admin/limits", { schema: Limits, ...s }),
  saveLimits: (body: LimitsIn) => request("/ai/admin/limits", { method: "PUT", body, schema: Limits, ...s }),
  topup: (body: { tokens: number; cost_usd: number; reason: string }) => request("/ai/admin/limits/topup", { method: "POST", body, schema: Limits, ...s }),
  guardrails: () => request("/ai/admin/guardrails", { schema: Guardrails, ...s }),
  saveGuardrails: (body: Partial<Guardrails>) => request("/ai/admin/guardrails", { method: "PUT", body, schema: Guardrails, ...s }),
  check: (body: { text: string; feature: string; surface: "user" | "upload" }) => request("/ai/admin/guardrails/check", { method: "POST", body, schema: GuardCheck, ...s }),
  redteam: () => request("/ai/admin/redteam", { method: "POST", schema: RedTeam, ...s }),
  me: () => request("/ai/me/usage", { schema: MyUsage, ...s }),
};

export const aiKeys = {
  all: ["ai-admin"] as const,
  providers: ["ai-admin", "providers"] as const,
  routes: ["ai-admin", "routes"] as const,
  usage: (group: UsageGroup, q: Record<string, string | undefined>) => ["ai-admin", "usage", group, q] as const,
  summary: ["ai-admin", "summary"] as const,
  refusals: ["ai-admin", "refusals"] as const,
  limits: ["ai-admin", "limits"] as const,
  guardrails: ["ai-admin", "guardrails"] as const,
  me: ["ai-me"] as const,
};

export const useAiProviders = () => useQuery({ queryKey: aiKeys.providers, queryFn: aiAdminApi.providers });
export const useAiRoutes = () => useQuery({ queryKey: aiKeys.routes, queryFn: aiAdminApi.routes });
export const useAiUsage = (group: UsageGroup, q: { start?: string; end?: string; q?: string } = {}) =>
  useQuery({ queryKey: aiKeys.usage(group, q), queryFn: () => aiAdminApi.usage(group, q) });
export const useAiSummary = () => useQuery({ queryKey: aiKeys.summary, queryFn: aiAdminApi.summary });
export const useAiRefusals = () => useQuery({ queryKey: aiKeys.refusals, queryFn: aiAdminApi.refusals });
export const useAiLimits = () => useQuery({ queryKey: aiKeys.limits, queryFn: aiAdminApi.limits });
export const useAiGuardrails = () => useQuery({ queryKey: aiKeys.guardrails, queryFn: aiAdminApi.guardrails });
export const useMyAiUsage = (enabled = true) => useQuery({ queryKey: aiKeys.me, queryFn: aiAdminApi.me, enabled, staleTime: 30_000 });

/** Refetch everything of this screen after a write. Not awaited on purpose: the editors are keyed by the server
 * data and remount on the refetch, and a mutation's per-call `onSuccess` (the toast) is skipped once its component
 * has unmounted, so the call's own callbacks must run first. */
function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: aiKeys.all });
  };
}

export function useSaveProvider() {
  const done = useInvalidate();
  return useMutation({ mutationFn: ({ p, body }: { p: string; body: Record<string, unknown> }) => aiAdminApi.saveProvider(p, body), onSuccess: done });
}
export function useSyncProvider() {
  const done = useInvalidate();
  return useMutation({ mutationFn: (p: string) => aiAdminApi.sync(p), onSuccess: done });
}
export function useTestProvider() {
  const done = useInvalidate();
  return useMutation({ mutationFn: ({ p, model }: { p: string; model?: string }) => aiAdminApi.test(p, model), onSuccess: done });
}
export function useSaveRoutes() {
  const done = useInvalidate();
  return useMutation({ mutationFn: aiAdminApi.saveRoutes, onSuccess: done });
}
export function useSaveLimits() {
  const done = useInvalidate();
  return useMutation({ mutationFn: aiAdminApi.saveLimits, onSuccess: done });
}
export function useTopup() {
  const done = useInvalidate();
  return useMutation({ mutationFn: aiAdminApi.topup, onSuccess: done });
}
export function useSaveGuardrails() {
  const done = useInvalidate();
  return useMutation({ mutationFn: aiAdminApi.saveGuardrails, onSuccess: done });
}
export const useGuardCheck = () => useMutation({ mutationFn: aiAdminApi.check });
export const useRedTeam = () => useMutation({ mutationFn: aiAdminApi.redteam });

/** `{code, message_tr, message_en, errors?}` of an AI admin 4xx (or null). */
export interface AiErrorDetail {
  code?: string;
  message_tr?: string;
  message_en?: string;
  errors?: { route?: string; field?: string; code?: string; message_tr?: string; message_en?: string }[];
}
