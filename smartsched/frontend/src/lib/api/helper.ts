"use client";
/**
 * The helper ("Yardımcı") API, HX-01 (docs/design/v3/helper.md; backend lanes HB-A / HB-B, `/api/v1/helper/**`).
 *
 * - `GET /helper/search?q=`: no AI. `pages` / `where` are `nav` cards ("Sayfalar ve ayarlar" / "Nerede?"), `data` are
 *   the palette's data hits through the person's own rights, `question` puts "Yardımcıya sor" first.
 * - `GET /helper/status`: the status chip (mode ai | index, why AI is off, local / cloud, the provider's name).
 * - `GET /helper/actions`: the actions this person may run (shortcuts are hidden for the others).
 * - `POST /helper/actions/{name}/card` `{args}`: a card with **no model call**; a write is only previewed (confirm /
 *   form / choice). `POST /helper/actions/confirm` / `undo` `{token}`: the card's button and "Geri al".
 * - `POST /helper/turn` `{text, lang, context?}`: one question, streamed as `text/event-stream` of server-built cards
 *   (components/helper/stream.ts). `context` (HB-D, HX-16) is the "Bu sayfa: …" chip: {@link TurnContext}.
 * - `GET /helper/actions/recent?limit=` (HB-D, HX-15): "Son işlemler", the person's own confirmed helper actions.
 * - `GET/PUT /helper/memory`, `GET/POST/DELETE /helper/notes`, `DELETE /helper/threads` (HB-21): Profil › Yardımcı.
 *
 * Cards are parsed with the zod generated from the server's JSON Schema (components/helper/schema.gen.ts). Errors
 * keep the project's shape `detail = {code, message_tr, message_en, card}`; {@link errorCard} reads the card.
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { HelperCard, NavCard, Txt } from "@/components/helper/schema.gen";
import { HttpError, request } from "./client";

const s = { silent: true } as const;

/* --------------------------------------------------------------------------------------------- schemas */

/** Keep the valid items of a list and drop the rest (one odd card never blanks the whole answer). */
const listOf = <T extends z.ZodType>(item: T) =>
  z.array(z.unknown()).catch([]).transform((xs) => xs.flatMap((x) => {
    const r = item.safeParse(x);
    return r.success ? [r.data as z.infer<T>] : [];
  }));

export const HelperStatus = z.object({
  mode: z.enum(["ai", "index"]).catch("index"),
  /** false: an administrator switched the helper off (`reason: disabled`) or off for all the person's audiences
   * (`audience_off`): hide the trigger's helper part and the sheet; the palette's page search stays */
  enabled: z.boolean().catch(true).default(true),
  /** why AI is off (`mode: index`): not_routed · provider_unusable · consent_missing · turn_unavailable · disabled ·
   * audience_off · index_mode */
  reason: z.string().nullish(),
  provider_kind: z.enum(["local", "cloud"]).nullish().catch(null),
  provider_label: Txt.nullish().catch(null),
  fallback_active: z.boolean().catch(false),
  message: Txt.nullish().catch(null),
});
export type HelperStatus = z.infer<typeof HelperStatus>;

export const DataHit = z.object({
  kind: z.string(),
  id: z.number(),
  label: z.string(),
  sub: Txt.nullish().catch(null),
  feature_id: z.string().nullish(),
});
export type DataHit = z.infer<typeof DataHit>;

export const HelperSearch = z.object({
  q: z.string().catch(""),
  question: z.boolean().catch(false),
  pages: listOf(NavCard),
  where: listOf(NavCard),
  data: z.record(z.string(), listOf(DataHit)).catch({}),
  skipped: z.array(z.object({ source: z.string(), reason: z.string() }).passthrough()).catch([]),
  timing_ms: z.number().nullish(),
});
export type HelperSearch = z.infer<typeof HelperSearch>;

export const HelperAction = z.object({
  name: z.string(),
  kind: z.enum(["read", "write"]).catch("read"),
  risk: z.string().catch("R0"),
  card: z.string().catch("answer"),
  summary: Txt.nullish().catch(null),
});
export type HelperAction = z.infer<typeof HelperAction>;

export const HelperMemory = z.object({
  institution_enabled: z.boolean().catch(false),
  enabled: z.boolean().catch(false),
  notes: z.number().catch(0),
  max_notes: z.number().catch(20),
  max_chars: z.number().catch(200),
  retention_days: z.number().catch(180),
  history_days: z.number().catch(30),
});
export type HelperMemory = z.infer<typeof HelperMemory>;

export const HelperNote = z.object({
  id: z.number(),
  text: z.string(),
  source: z.string().nullish(),
  created_at: z.string().nullish(),
  last_used_at: z.string().nullish(),
  expires_at: z.string().nullish(),
});
export type HelperNote = z.infer<typeof HelperNote>;

/**
 * HB-D §3 `GET /helper/actions/recent`: one of the person's own confirmed helper actions, newest first. The label is
 * already worded by the server (TR and EN, database values only); `undo_token` is there only while `undoable`.
 */
export const RecentAction = z.object({
  id: z.number(),
  action: z.string(),
  kind: z.string().nullish(),
  entity_id: z.number().nullish(),
  feature_id: z.string().nullish(),
  label: Txt,
  /** naive UTC ("2026-02-16T08:01:12") */
  at: z.string(),
  status: z.enum(["done", "undone"]).catch("done"),
  undoable: z.boolean().catch(false),
  undo_token: z.string().nullish(),
  undo_expires_at: z.string().nullish(),
});
export type RecentAction = z.infer<typeof RecentAction>;

/**
 * HB-D §2 `POST /helper/turn` `context`: the page the person is on ("Bu sayfa: …" chip), never page text. The server
 * answers 422 before the stream for any other shape, so the client parses it with the same rules first.
 */
export const TurnContext = z.strictObject({
  route: z.string().min(1).max(200),
  entity_kind: z.enum(["room", "booking", "approval_request"]).optional(),
  entity_id: z.number().int().min(1).optional(),
});
export type TurnContext = z.infer<typeof TurnContext>;

export const DeletedOut = z.object({ notes: z.number().catch(0), threads: z.number().catch(0) }).passthrough();
/** HB-21 `DELETE /helper/threads`: the counts deleted and the notes kept. */
export const ThreadsDeletedOut = z.object({ threads: z.number().catch(0), messages: z.number().catch(0), notes_kept: z.number().catch(0) }).passthrough();

/* ---------------------------------------------------------------------------------------------- errors */

export interface HelperRefusal {
  status: number;
  code: string;
  tr: string | null;
  en: string | null;
  /** the card the helper shows for it (`limit` / `refusal` / `error`, or a fresh `confirm` / `form` on 409 changed) */
  card: HelperCard | null;
  /** 409 `conflict`: free rooms for the same slot (`find_room.alternatives_for`, ≤ 3) */
  alternatives: HelperAlternative[];
}

export interface HelperAlternative {
  room_id: number;
  name: string;
  capacity: number | null;
  status: string;
}

const Alternative = z.object({ room_id: z.number().int().positive(), name: z.string().optional(), code: z.string().optional(), capacity: z.number().nullish(), status: z.string().optional() });

function alternativesOf(raw: unknown): HelperAlternative[] {
  if (!Array.isArray(raw)) return [];
  const out: HelperAlternative[] = [];
  for (const x of raw.slice(0, 3)) {
    const a = Alternative.safeParse(x);
    if (a.success) out.push({ room_id: a.data.room_id, name: a.data.name || a.data.code || String(a.data.room_id), capacity: a.data.capacity ?? null, status: a.data.status ?? "free" });
  }
  return out;
}

/**
 * Read an API error of the helper routes (`detail = {code, message_tr, message_en, card, alternatives}`). The API
 * client keeps an object `detail` as the whole body (`{detail: {...}}`, HB18-F03), so that wrapper is unwrapped.
 */
export function helperRefusal(err: unknown): HelperRefusal {
  const status = err instanceof HttpError ? err.status : 0;
  let d = err instanceof HttpError && err.detail && typeof err.detail === "object" ? (err.detail as Record<string, unknown>) : {};
  if (typeof d.code !== "string" && d.detail && typeof d.detail === "object" && !Array.isArray(d.detail)) d = d.detail as Record<string, unknown>;
  const parsed = HelperCard.safeParse(d.card);
  return {
    status,
    code: typeof d.code === "string" ? d.code : status === 0 ? "network" : "error",
    tr: typeof d.message_tr === "string" ? d.message_tr : null,
    en: typeof d.message_en === "string" ? d.message_en : null,
    card: parsed.success ? parsed.data : null,
    alternatives: alternativesOf(d.alternatives),
  };
}

/** Only the card of a helper error (or null). */
export const errorCard = (err: unknown): HelperCard | null => helperRefusal(err).card;

/* --------------------------------------------------------------------------------------------- requests */

export type ActionArgs = Record<string, string | number | boolean | null>;

export const helperApi = {
  search: (q: string, termId?: number | null, signal?: AbortSignal, final = false) =>
    request("/helper/search", { ...s, query: { q, limit: 6, term_id: termId ?? undefined, final: final ? "true" : undefined }, schema: HelperSearch, signal }),
  /** the person submitted the search (Enter / picked a "Nerede?" row): one `query` event server-side */
  searchFinal: (q: string) => request("/helper/search", { ...s, query: { q, limit: 1, final: "true" } }).then(() => undefined),
  /** thumbs up / down on a turn (`run_started.turn_id`) */
  feedback: (body: { turn_id: string; thumb: "up" | "down"; reason?: string; note?: string }) => request("/helper/feedback", { ...s, method: "POST", body }),
  /** what deflection counts: `nav_click` ("Sayfayı aç"), `form_open`, `cancel` ("Vazgeç" on a confirm card) */
  event: (body: { kind: "nav_click" | "form_open" | "cancel"; turn_id?: string; feature_id?: string; action?: string }) =>
    request<void>("/helper/events", { ...s, method: "POST", body }),
  status: () => request("/helper/status", { ...s, schema: HelperStatus }),
  actions: () => request("/helper/actions", { ...s, schema: listOf(HelperAction) }),
  card: (name: string, args: ActionArgs) => request(`/helper/actions/${encodeURIComponent(name)}/card`, { ...s, method: "POST", body: { args }, schema: HelperCard }),
  confirm: (token: string) => request("/helper/actions/confirm", { ...s, method: "POST", body: { token }, schema: HelperCard }),
  undo: (token: string) => request("/helper/actions/undo", { ...s, method: "POST", body: { token }, schema: HelperCard }),
  /** HB-D: "Son işlemler" (1..20) */
  recent: (limit = 5) => request("/helper/actions/recent", { ...s, query: { limit }, schema: listOf(RecentAction) }),
  memory: () => request("/helper/memory", { ...s, schema: HelperMemory }),
  setMemory: (enabled: boolean) => request("/helper/memory", { ...s, method: "PUT", body: { enabled }, schema: HelperMemory }),
  notes: () => request("/helper/notes", { ...s, schema: z.array(HelperNote) }),
  addNote: (text: string, source: "user_button" | "user_confirmed") => request("/helper/notes", { ...s, method: "POST", body: { text, source }, schema: HelperNote }),
  deleteNote: (id: number) => request<void>(`/helper/notes/${id}`, { ...s, method: "DELETE" }),
  /** HB-21: the conversation history only; the notes stay (HX-18 M7), while {@link helperCaps}.threadsDelete is on. */
  deleteThreads: () => request("/helper/threads", { ...s, method: "DELETE", schema: ThreadsDeletedOut }),
  deleteAll: (history: boolean) => request("/helper/notes", { ...s, method: "DELETE", query: { history: history ? "true" : undefined }, schema: DeletedOut }),
};

/* ------------------------------------------------------------------------------------------------ hooks */

export const helperKeys = {
  all: ["helper"] as const,
  status: ["helper", "status"] as const,
  actions: ["helper", "actions"] as const,
  search: (q: string, termId?: number | null) => ["helper", "search", q, termId ?? null] as const,
  memory: ["helper", "memory"] as const,
  notes: ["helper", "notes"] as const,
  recent: ["helper", "recent"] as const,
};

export const useHelperStatus = (enabled = true) => useQuery({ queryKey: helperKeys.status, queryFn: helperApi.status, enabled, staleTime: 60_000, retry: false });
export const useHelperActions = (enabled = true) => useQuery({ queryKey: helperKeys.actions, queryFn: helperApi.actions, enabled, staleTime: 5 * 60_000, retry: false });

/** `GET /helper/search` for 2+ characters (the palette debounces the text first). */
export function useHelperSearch(q: string, termId?: number | null, enabled = true) {
  const text = q.trim();
  return useQuery({
    queryKey: helperKeys.search(text, termId),
    queryFn: ({ signal }) => helperApi.search(text, termId, signal),
    enabled: enabled && text.length >= 2,
    staleTime: 30_000,
    retry: false,
  });
}

/** "Son işlemler" (HX-15): the palette shows 3 of them, the sheet 5; one cache. */
export const RECENT_LIMIT = 5;
export const useHelperRecent = (enabled = true) =>
  useQuery({ queryKey: helperKeys.recent, queryFn: () => helperApi.recent(RECENT_LIMIT), enabled, staleTime: 30_000, retry: false });

/**
 * After a helper write was confirmed or undone (the card's button, "Geri al" in a card or in "Son işlemler"):
 * "Son işlemler" again, and for a note (`remember_note`, HX-17) Profil › Yardımcı's notes and memory count.
 */
export function invalidateAfterHelperWrite(qc: QueryClient, action: string | null | undefined): void {
  void qc.invalidateQueries({ queryKey: helperKeys.recent });
  if (action === "remember_note") {
    void qc.invalidateQueries({ queryKey: helperKeys.notes });
    void qc.invalidateQueries({ queryKey: helperKeys.memory });
  }
}

export const useHelperMemory = (enabled = true) => useQuery({ queryKey: helperKeys.memory, queryFn: helperApi.memory, enabled, retry: false });
export const useHelperNotes = (enabled = true) => useQuery({ queryKey: helperKeys.notes, queryFn: helperApi.notes, enabled, retry: false });

function useMemoryInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: helperKeys.memory });
    void qc.invalidateQueries({ queryKey: helperKeys.notes });
  };
}

export function useSetHelperMemory() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (enabled: boolean) => helperApi.setMemory(enabled), onSuccess: (data) => qc.setQueryData(helperKeys.memory, data) });
}
export function useAddHelperNote() {
  const done = useMemoryInvalidate();
  return useMutation({ mutationFn: ({ text, source }: { text: string; source: "user_button" | "user_confirmed" }) => helperApi.addNote(text, source), onSuccess: done });
}
export function useDeleteHelperNote() {
  const done = useMemoryInvalidate();
  return useMutation({ mutationFn: (id: number) => helperApi.deleteNote(id), onSuccess: done });
}
/**
 * What this client relies on from the server. `threadsDelete`: HB-21's threads-only `DELETE /helper/threads` (on since
 * HB-D shipped it, 2026-10-18). Off, "Geçmişi sil" falls back to `DELETE /helper/notes?history=true` and its button
 * and dialog say that the notes go too (HX-18 M7). A plain object so the tests can switch it.
 */
export const helperCaps = { threadsDelete: true };

export function useDeleteHelperThreads() {
  const done = useMemoryInvalidate();
  return useMutation({ mutationFn: () => helperApi.deleteThreads(), onSuccess: done });
}
export function useDeleteAllHelperNotes() {
  const done = useMemoryInvalidate();
  return useMutation({ mutationFn: ({ history }: { history: boolean }) => helperApi.deleteAll(history), onSuccess: done });
}

/** Fire-and-forget telemetry (never blocks or fails the person's action). */
export function trackHelper(body: Parameters<typeof helperApi.event>[0]): void {
  void helperApi.event(body).catch(() => undefined);
}

/* ------------------------------------------------------------------------- /admin/ai › Yardımcı (HB-14 / HB-15) */

const Label = Txt.catch({ tr: "", en: "" });

export const HelperAdminSettings = z.object({
  enabled: z.boolean().catch(true),
  mode: z.enum(["ai", "index"]).catch("ai"),
  audiences: z.record(z.string(), z.boolean()).catch({}),
  actions: z.record(z.string(), z.object({ enabled: z.boolean().catch(true), audiences: z.array(z.string()).nullish().catch(null) }).passthrough()).catch({}),
  memory: z.object({ enabled: z.boolean().catch(true), retention_days: z.number().catch(180) }).passthrough().catch({ enabled: true, retention_days: 180 }),
  history_days: z.number().catch(30),
  feedback_notes: z.boolean().catch(true),
  guard: z.object({ scope: z.string().catch("normal") }).passthrough().catch({ scope: "normal" }),
});
export type HelperAdminSettings = z.infer<typeof HelperAdminSettings>;

export const HelperAdmin = z.object({
  settings: HelperAdminSettings,
  version: z.string().nullish(),
  effective: z.object({ mode: z.enum(["ai", "index"]).catch("index"), reason: z.string().nullish(), message: Txt.nullish().catch(null) }).passthrough().nullish(),
  catalog: z
    .object({
      audiences: z.array(z.object({ id: z.string(), label: Label })).catch([]),
      actions: z.array(z.object({ name: z.string(), kind: z.string().catch("read"), risk: z.string().catch("R0"), summary: Label, risk_label: Label })).catch([]),
      scopes: z.array(z.object({ id: z.string(), label: Label, hint: Txt.nullish().catch(null) })).catch([]),
    })
    .catch({ audiences: [], actions: [], scopes: [] }),
});
export type HelperAdmin = z.infer<typeof HelperAdmin>;

export interface HelperAdminPatch {
  version?: string | null;
  enabled?: boolean;
  mode?: "ai" | "index";
  audiences?: Record<string, boolean>;
  actions?: Record<string, { enabled?: boolean; audiences?: string[] | null }>;
  memory?: { enabled?: boolean; retention_days?: number };
  history_days?: number;
  feedback_notes?: boolean;
  guard?: { scope?: string };
}

export const HelperSummary = z.object({
  days: z.number().catch(7),
  tiles: z.array(z.object({ id: z.string(), tr: z.string(), en: z.string() })).catch([]),
  misses: z.array(z.object({ query: z.string(), users: z.number(), count: z.number() })).catch([]),
  k_min: z.number().catch(5),
});
export type HelperSummary = z.infer<typeof HelperSummary>;

/* ------------------------------------------------------------------- faculty quotas (HB-10 / HB-11, `/ai/faculty`) */

export const FacultyUsage = z.object({
  /** `share_of_allowance` (HB-21): 0..1 of the allowance used (the larger of the token and cost shares), null without one */
  faculty: z.object({ id: z.number(), name: z.string(), share_of_allowance: z.number().nullish().catch(null) }).nullish(),
  faculties: z.array(z.object({ id: z.number(), name: z.string() })).catch([]),
  month: z.string().nullish(),
  allocation: z.object({ monthly_tokens: z.number().nullish(), monthly_cost_usd: z.number().nullish() }).passthrough().nullish().catch(null),
  totals: z.object({ tokens: z.number().catch(0), cost_usd: z.number().catch(0), calls: z.number().catch(0) }).catch({ tokens: 0, cost_usd: 0, calls: 0 }),
  by_department: z
    .array(
      z.object({
        id: z.number(),
        name: z.string(),
        tokens: z.number().catch(0),
        calls: z.number().catch(0),
        allocation: z.object({ monthly_tokens: z.number().nullish(), monthly_cost_usd: z.number().nullish() }).passthrough().nullish().catch(null),
        share_of_allowance: z.number().nullish().catch(null),
      }),
    )
    .catch([]),
  by_feature: z.array(z.object({ feature: z.string(), label_tr: z.string().nullish(), label_en: z.string().nullish(), tokens: z.number().catch(0) }).passthrough()).catch([]),
  trend: z.array(z.object({ day: z.string(), tokens: z.number().catch(0) })).catch([]),
  show_people: z.boolean().catch(false),
  people: z.array(z.object({ label: z.string(), department: z.string().nullish(), tokens: z.number().catch(0) })).nullish().catch(null),
});
export type FacultyUsage = z.infer<typeof FacultyUsage>;

export const helperAdminApi = {
  get: () => request("/ai/admin/helper", { ...s, schema: HelperAdmin }),
  put: (patch: HelperAdminPatch) => request("/ai/admin/helper", { ...s, method: "PUT", body: patch, schema: HelperAdmin }),
  summary: (days = 7) => request("/ai/admin/helper/summary", { ...s, query: { days }, schema: HelperSummary }),
  facultyUsage: (facultyId?: number | null) => request("/ai/faculty/usage", { ...s, query: { faculty_id: facultyId ?? undefined }, schema: FacultyUsage }),
  facultyAllocations: (facultyId: number, departments: Record<string, { monthly_tokens: number | null; monthly_cost_usd?: number | null }>) =>
    request("/ai/faculty/allocations", { ...s, method: "PUT", body: { faculty_id: facultyId, departments } }),
};

export const helperAdminKeys = {
  settings: ["helper", "admin"] as const,
  summary: (days: number) => ["helper", "admin", "summary", days] as const,
  faculty: (id: number | null) => ["helper", "faculty", id] as const,
};

export const useHelperAdmin = (enabled = true) => useQuery({ queryKey: helperAdminKeys.settings, queryFn: helperAdminApi.get, enabled, retry: false });
export const useHelperSummary = (days = 7, enabled = true) => useQuery({ queryKey: helperAdminKeys.summary(days), queryFn: () => helperAdminApi.summary(days), enabled, retry: false });
export const useFacultyUsage = (facultyId: number | null, enabled = true) =>
  useQuery({ queryKey: helperAdminKeys.faculty(facultyId), queryFn: () => helperAdminApi.facultyUsage(facultyId), enabled, retry: false });

export function useSaveHelperAdmin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: HelperAdminPatch) => helperAdminApi.put(patch),
    onSuccess: (data) => {
      qc.setQueryData(helperAdminKeys.settings, data);
      void qc.invalidateQueries({ queryKey: helperKeys.status });
      void qc.invalidateQueries({ queryKey: helperKeys.actions });
    },
  });
}

export function useSaveFacultyAllocations() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ facultyId, departments }: { facultyId: number; departments: Record<string, { monthly_tokens: number | null }> }) => helperAdminApi.facultyAllocations(facultyId, departments),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["helper", "faculty"] }),
  });
}
