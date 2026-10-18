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
 * - `POST /helper/turn` `{text, lang}`: one question, streamed as `text/event-stream` of server-built cards
 *   (components/helper/stream.ts).
 * - `GET/PUT /helper/memory`, `GET/POST/DELETE /helper/notes`: Profil › Yardımcı.
 *
 * Cards are parsed with the zod generated from the server's JSON Schema (components/helper/schema.gen.ts). Errors
 * keep the project's shape `detail = {code, message_tr, message_en, card}`; {@link errorCard} reads the card.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

export const DeletedOut = z.object({ notes: z.number().catch(0), threads: z.number().catch(0) }).passthrough();

/* ---------------------------------------------------------------------------------------------- errors */

export interface HelperRefusal {
  status: number;
  code: string;
  tr: string | null;
  en: string | null;
  /** the card the helper shows for it (`limit` / `refusal` / `error`, or a fresh `confirm` / `form` on 409 changed) */
  card: HelperCard | null;
}

/** Read an API error of the helper routes (`detail = {code, message_tr, message_en, card}`). */
export function helperRefusal(err: unknown): HelperRefusal {
  const status = err instanceof HttpError ? err.status : 0;
  const d = err instanceof HttpError && err.detail && typeof err.detail === "object" ? (err.detail as Record<string, unknown>) : {};
  const parsed = HelperCard.safeParse(d.card);
  return {
    status,
    code: typeof d.code === "string" ? d.code : status === 0 ? "network" : "error",
    tr: typeof d.message_tr === "string" ? d.message_tr : null,
    en: typeof d.message_en === "string" ? d.message_en : null,
    card: parsed.success ? parsed.data : null,
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
  /** 👍 / 👎 on a turn (`run_started.turn_id`) */
  feedback: (body: { turn_id: string; thumb: "up" | "down"; reason?: string; note?: string }) => request("/helper/feedback", { ...s, method: "POST", body }),
  /** what deflection counts: `nav_click` ("Sayfayı aç"), `form_open`, `cancel` ("Vazgeç" on a confirm card) */
  event: (body: { kind: "nav_click" | "form_open" | "cancel"; turn_id?: string; feature_id?: string; action?: string }) =>
    request<void>("/helper/events", { ...s, method: "POST", body }),
  status: () => request("/helper/status", { ...s, schema: HelperStatus }),
  actions: () => request("/helper/actions", { ...s, schema: listOf(HelperAction) }),
  card: (name: string, args: ActionArgs) => request(`/helper/actions/${encodeURIComponent(name)}/card`, { ...s, method: "POST", body: { args }, schema: HelperCard }),
  confirm: (token: string) => request("/helper/actions/confirm", { ...s, method: "POST", body: { token }, schema: HelperCard }),
  undo: (token: string) => request("/helper/actions/undo", { ...s, method: "POST", body: { token }, schema: HelperCard }),
  memory: () => request("/helper/memory", { ...s, schema: HelperMemory }),
  setMemory: (enabled: boolean) => request("/helper/memory", { ...s, method: "PUT", body: { enabled }, schema: HelperMemory }),
  notes: () => request("/helper/notes", { ...s, schema: z.array(HelperNote) }),
  addNote: (text: string, source: "user_button" | "user_confirmed") => request("/helper/notes", { ...s, method: "POST", body: { text, source }, schema: HelperNote }),
  deleteNote: (id: number) => request<void>(`/helper/notes/${id}`, { ...s, method: "DELETE" }),
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
  return useMutation({ mutationFn: helperApi.setMemory, onSuccess: (data) => qc.setQueryData(helperKeys.memory, data) });
}
export function useAddHelperNote() {
  const done = useMemoryInvalidate();
  return useMutation({ mutationFn: ({ text, source }: { text: string; source: "user_button" | "user_confirmed" }) => helperApi.addNote(text, source), onSuccess: done });
}
export function useDeleteHelperNote() {
  const done = useMemoryInvalidate();
  return useMutation({ mutationFn: helperApi.deleteNote, onSuccess: done });
}
export function useDeleteAllHelperNotes() {
  const done = useMemoryInvalidate();
  return useMutation({ mutationFn: ({ history }: { history: boolean }) => helperApi.deleteAll(history), onSuccess: done });
}
