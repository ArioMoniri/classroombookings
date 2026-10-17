"use client";
/**
 * Welcome guide per role (WG-04…WG-08; docs/design/v3/welcome-guide.md §6.4, backend lane WG-B):
 *
 * - `GET /welcome`: the guide's state for the signed-in user (parts switched on, audiences, the one `show` the server
 *   decided, the sheet cards with admin overrides, the tour steps, the "Başlarken" checklist with server-side `done`,
 *   the eligible feature hints). The client only renders what `show` says; it never decides a trigger itself.
 * - `POST /welcome/events`: shown / snoozed / dismissed / started / step / completed / hidden / seen / item_done (204).
 * - `POST /welcome/restart`: Yardım › Turu yeniden başlat (sheet and tour back to `shown`, answers the GET payload).
 * - Admin (`setup.settings` or `planning.admin`): `GET/PUT /welcome/settings`, `GET/PUT /welcome/content/{audience}`
 *   (409 `stale`), `POST /welcome/content/{audience}/reshow`, `GET /welcome/stats?days=`.
 *
 * Every schema is lenient (defaults, `.catch`, `.nullish`): an older or newer backend answers without some fields
 * and the guide then shows only what exists. Copy is never in the payload: it comes from `welcome.*` message keys,
 * with the admin's `overrides` for the reader's locale on top.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

const s = { silent: true } as const;

/* ------------------------------------------------------------------------------------------- audiences */

/** Precedence for the primary audience (spec §5.9): admin > planner > viewer > dept_admin > approver > academician > staff. */
export const AUDIENCES = ["admin", "planner", "viewer", "dept_admin", "approver", "academician", "staff"] as const;
export type Audience = (typeof AUDIENCES)[number];
export const isAudience = (v: unknown): v is Audience => typeof v === "string" && (AUDIENCES as readonly string[]).includes(v);

/** The guide keys an event may carry (hints are `hint.<key>`). */
export const GUIDE_KEYS = ["sheet", "tour", "checklist"] as const;
export const EVENTS = ["shown", "snoozed", "dismissed", "started", "step", "completed", "hidden", "seen", "item_done"] as const;
export type WelcomeEventName = (typeof EVENTS)[number];

/* ------------------------------------------------------------------------------------------- schemas */

const Overrides = z.record(z.string(), z.string()).catch({});

export const SheetCard = z
  .object({
    key: z.string(),
    /** the audience whose copy the card uses (`approver` for an "Ayrıca" card); missing = the first matching one */
    audience: z.string().nullish(),
    href: z.string().nullish(),
    /** admin texts for the reader's locale: `title`, `body` */
    overrides: Overrides.nullish(),
  })
  .passthrough();
export type SheetCard = z.infer<typeof SheetCard>;

export const TourStep = z
  .object({
    anchor: z.string(),
    route: z.string().nullish(),
    interactive: z.boolean().nullish(),
    audience: z.string().nullish(),
  })
  .passthrough();
export type TourStep = z.infer<typeof TourStep>;

export const ChecklistItem = z
  .object({
    key: z.string(),
    href: z.string().nullish(),
    done: z.boolean().default(false),
    /** a view-only item ("Bitti olarak işaretle" allowed) */
    manual: z.boolean().default(false),
    audience: z.string().nullish(),
  })
  .passthrough();
export type ChecklistItem = z.infer<typeof ChecklistItem>;

export const HintEntry = z
  .object({
    /** `hint.quick_reserve` or `quick_reserve` */
    key: z.string(),
    route: z.string().nullish(),
    anchor: z.string().nullish(),
    overrides: Overrides.nullish(),
  })
  .passthrough();
export type HintEntry = z.infer<typeof HintEntry>;

const Show = z
  .object({
    kind: z.enum(["sheet", "delta", "hint"]).catch("sheet"),
    key: z.string().nullish(),
    /** delta: the new audiences only */
    audiences: z.array(z.string()).nullish(),
  })
  .passthrough();

const Enabled = z
  .object({
    sheet: z.boolean().default(true),
    tour: z.boolean().default(true),
    checklist: z.boolean().default(true),
    hints: z.boolean().default(true),
  })
  .catch({ sheet: true, tour: true, checklist: true, hints: true });

export const WelcomeState = z
  .object({
    enabled: Enabled.default({ sheet: true, tour: true, checklist: true, hints: true }),
    audiences: z.array(z.string()).default([]),
    primary: z.string().nullish(),
    show: Show.nullish(),
    department: z.string().nullish(),
    first_name: z.string().nullish(),
    sheet: z
      .object({
        cards: z.array(SheetCard).default([]),
        updated: z.boolean().default(false),
        /** admin texts for the sheet title / lead (reader's locale) */
        overrides: Overrides.nullish(),
      })
      .passthrough()
      .default({ cards: [], updated: false }),
    tour: z.object({ steps: z.array(TourStep).default([]) }).passthrough().default({ steps: [] }),
    checklist: z
      .object({
        items: z.array(ChecklistItem).default([]),
        done: z.number().nullish(),
        total: z.number().nullish(),
        hidden: z.boolean().default(false),
      })
      .passthrough()
      .default({ items: [], hidden: false }),
    hints: z.array(HintEntry).default([]),
    content_version: z.number().nullish(),
  })
  .passthrough();
export type WelcomeState = z.infer<typeof WelcomeState>;

export interface WelcomeEvent {
  guide_key: string;
  event: WelcomeEventName;
  step?: number;
  item?: string;
  audience?: string;
}

/* ------------------------------------------------------------------------------------------- admin */

export const PARTS = ["enabled", "sheet", "tour", "checklist", "hints", "hints_for_all"] as const;
export type Part = (typeof PARTS)[number];

export const WelcomeSettings = z
  .object({
    enabled: z.boolean().default(true),
    sheet: z.boolean().default(true),
    tour: z.boolean().default(true),
    checklist: z.boolean().default(true),
    hints: z.boolean().default(true),
    hints_for_all: z.boolean().default(false),
    min_cohort: z.number().default(5),
  })
  .passthrough();
export type WelcomeSettings = z.infer<typeof WelcomeSettings>;

const ContentField = z
  .object({
    field: z.string(),
    locale: z.string(),
    text: z.string(),
    version: z.number().nullish(),
    updated_by: z.string().nullish(),
    updated_at: z.string().nullish(),
  })
  .passthrough();

/**
 * `GET /welcome/content/{audience}`: the overrides that exist, `version` for the optimistic check, the last editor.
 * The backend may answer a flat list (`fields`) or a nested map (`texts: {tr: {title: …}}`); both normalise here.
 */
export const WelcomeContent = z
  .object({
    audience: z.string(),
    version: z.number().default(0),
    fields: z.array(ContentField).nullish(),
    texts: z.record(z.string(), z.record(z.string(), z.string())).nullish(),
    updated_by: z.string().nullish(),
    updated_at: z.string().nullish(),
    content_version: z.number().nullish(),
  })
  .passthrough()
  .transform((c) => {
    const texts: Record<string, Record<string, string>> = { tr: {}, en: {} };
    for (const [loc, map] of Object.entries(c.texts ?? {})) texts[loc] = { ...(texts[loc] ?? {}), ...map };
    let last: { by?: string | null; at?: string | null } = { by: c.updated_by, at: c.updated_at };
    for (const f of c.fields ?? []) {
      (texts[f.locale] ??= {})[f.field] = f.text;
      if (f.updated_at && (!last.at || f.updated_at > last.at)) last = { by: f.updated_by, at: f.updated_at };
    }
    return { audience: c.audience, version: c.version, texts, updatedBy: last.by ?? null, updatedAt: last.at ?? null, contentVersion: c.content_version ?? null };
  });
export type WelcomeContent = z.infer<typeof WelcomeContent>;

const StatRow = z
  .object({
    audience: z.string(),
    small_group: z.boolean().default(false),
    people: z.number().nullish(),
    shown: z.number().nullish(),
    tour_completed_pct: z.number().nullish(),
    checklist_80_pct: z.number().nullish(),
    dismissed_pct: z.number().nullish(),
    median_days_to_first_booking: z.number().nullish(),
  })
  .passthrough();
export type StatRow = z.infer<typeof StatRow>;

/** `GET /welcome/stats?days=`: a list, or a map audience → row. Rows under k = 5 carry `small_group` and no numbers. */
export const WelcomeStats = z
  .union([
    z.object({ days: z.number().nullish(), min_cohort: z.number().nullish(), audiences: z.array(StatRow) }).passthrough(),
    z.object({ days: z.number().nullish(), min_cohort: z.number().nullish(), audiences: z.record(z.string(), StatRow.omit({ audience: true }).passthrough()) }).passthrough(),
    z.array(StatRow),
  ])
  .transform((v) => {
    if (Array.isArray(v)) return { days: null, rows: v };
    const rows = Array.isArray(v.audiences) ? v.audiences : Object.entries(v.audiences).map(([audience, r]) => StatRow.parse({ ...r, audience }));
    return { days: v.days ?? null, rows };
  });
export type WelcomeStats = z.infer<typeof WelcomeStats>;

/* ------------------------------------------------------------------------------------------- calls */

export const welcomeApi = {
  get: (query: { first_route?: string; route?: string } = {}) => request("/welcome", { query, schema: WelcomeState, ...s }),
  event: (body: WelcomeEvent) => request<void>("/welcome/events", { method: "POST", body, ...s }),
  restart: () => request("/welcome/restart", { method: "POST", schema: WelcomeState, ...s }),
  settings: () => request("/welcome/settings", { schema: WelcomeSettings, ...s }),
  saveSettings: (body: Partial<WelcomeSettings>) => request("/welcome/settings", { method: "PUT", body, schema: WelcomeSettings, ...s }),
  content: (audience: string) => request(`/welcome/content/${audience}`, { schema: WelcomeContent, ...s }),
  saveContent: (audience: string, body: { version: number; texts: Record<string, Record<string, string>>; reshow?: boolean }) =>
    request(`/welcome/content/${audience}`, { method: "PUT", body, schema: WelcomeContent, ...s }),
  reshow: (audience: string) => request<unknown>(`/welcome/content/${audience}/reshow`, { method: "POST", ...s }),
  stats: (days: number) => request("/welcome/stats", { query: { days }, schema: WelcomeStats, ...s }),
};

export const welcomeKeys = {
  all: ["welcome"] as const,
  state: ["welcome", "state"] as const,
  settings: ["welcome", "settings"] as const,
  content: (audience: string) => ["welcome", "content", audience] as const,
  stats: (days: number) => ["welcome", "stats", days] as const,
};

/* ------------------------------------------------------------------------------------------- hooks */

/** The guide state. `enabled: false` on excluded routes (no call at all: spec §15 check 5). */
export function useWelcome(opts: { enabled: boolean; firstRoute?: string; route?: string }) {
  return useQuery({
    queryKey: welcomeKeys.state,
    queryFn: () => welcomeApi.get({ first_route: opts.firstRoute, route: opts.route }),
    enabled: opts.enabled,
    staleTime: 60_000,
    retry: false,
  });
}

/** Events are fire-and-forget for the UI; the state refetches so `done` / `show` follow the server. */
export function useWelcomeEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (e: WelcomeEvent) => welcomeApi.event(e),
    onSettled: () => qc.invalidateQueries({ queryKey: welcomeKeys.state }),
  });
}

export function useWelcomeRestart() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => welcomeApi.restart(),
    onSuccess: (data) => qc.setQueryData(welcomeKeys.state, data),
  });
}

export function useWelcomeSettings(enabled = true) {
  return useQuery({ queryKey: welcomeKeys.settings, queryFn: () => welcomeApi.settings(), enabled, retry: false });
}

export function useSaveWelcomeSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<WelcomeSettings>) => welcomeApi.saveSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(welcomeKeys.settings, data);
      void qc.invalidateQueries({ queryKey: welcomeKeys.state });
    },
  });
}

export function useWelcomeContent(audience: string, enabled = true) {
  return useQuery({ queryKey: welcomeKeys.content(audience), queryFn: () => welcomeApi.content(audience), enabled, retry: false });
}

export function useSaveWelcomeContent(audience: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { version: number; texts: Record<string, Record<string, string>>; reshow: boolean }) => {
      const saved = await welcomeApi.saveContent(audience, { version: body.version, texts: body.texts });
      if (body.reshow) await welcomeApi.reshow(audience);
      return saved;
    },
    onSuccess: (data) => {
      qc.setQueryData(welcomeKeys.content(audience), data);
      void qc.invalidateQueries({ queryKey: welcomeKeys.state });
    },
  });
}

export function useWelcomeStats(days: number, enabled = true) {
  return useQuery({ queryKey: welcomeKeys.stats(days), queryFn: () => welcomeApi.stats(days), enabled, retry: false });
}
