"use client";
/**
 * P19-T2 "Tercih ekle" (backend app/services/teacher_preferences.py, routes in app/api/v1/moderation.py; flow
 * docs/testing/flows/F-05 S03). An academician linked to an instructor record adds a room, building or time-window
 * wish for the classes they teach; it is stored switched off as a soft `TEACHER` rule, ranked below the
 * department's request, until a coordinator (planning.edit) accepts it or rejects it with a written reason.
 * Nothing is ever applied by itself. Errors are `detail: {code, message, message_tr}`.
 *
 * `?dry_run=1` previews a wish with every check of a real submit and the same `items[].text` / `effective`, storing
 * nothing; `GET /moderation/me/rooms` lists the bookable rooms the room picker offers (403 `not_linked` otherwise).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";
import { Pair, PrefStatus } from "./moderation";

export const WISH_KINDS = ["room_preference", "building_preference", "day_window"] as const;
export type WishKind = (typeof WISH_KINDS)[number];

const Ids = z.array(z.number()).default([]);

export const TeacherPref = z.object({
  id: z.number(),
  constraint_id: z.number(),
  term_id: z.number().nullable().default(null),
  status: PrefStatus,
  enabled: z.boolean().default(false),
  kind: z.string(),
  kind_label: Pair.default({ tr: "", en: "" }),
  submission: z.string().nullable().default(null),
  request_ids: Ids,
  labels: z.array(z.string()).default([]),
  instructor: z.object({ id: z.number().nullable().default(null), name: z.string().nullable().default(null) }).nullable().default(null),
  user_id: z.number().nullable().optional(),
  wish: z
    .object({
      room_ids: Ids.optional(),
      rooms: z.array(z.string()).optional(),
      buildings: z.array(z.string()).optional(),
      earliest: z.number().optional(),
      latest: z.number().optional(),
      days: z.array(z.number()).optional(),
    })
    .passthrough()
    .default({}),
  department: z.object({ room_ids: Ids.optional(), rooms: z.array(z.string()).optional(), buildings: z.array(z.string()).optional() }).passthrough().default({}),
  rank: z.string().default("below_department"),
  text: Pair.default({ tr: "", en: "" }),
  note: z.string().nullable().default(null),
  hardness: z.string().default("soft"),
  weight: z.number().default(1),
  submitted_at: z.string().nullable().default(null),
  decided_at: z.string().nullable().default(null),
  decided_by: z.number().nullable().default(null),
  reason: z.string().nullable().default(null),
  reason_code: z.string().nullable().default(null),
});
export type TeacherPref = z.infer<typeof TeacherPref>;

const Counts = z.object({ pending: z.number().default(0), accepted: z.number().default(0), rejected: z.number().default(0) });
export type PrefCounts = z.infer<typeof Counts>;

export const MinePrefs = z.object({
  linked: z.boolean(),
  instructor_id: z.number().nullable().default(null),
  term_id: z.number().nullable().default(null),
  counts: Counts.default({ pending: 0, accepted: 0, rejected: 0 }),
  total: z.number().default(0),
  items: z.array(TeacherPref).default([]),
});
export type MinePrefs = z.infer<typeof MinePrefs>;

export const SubmitOut = z.object({ submission: z.string(), status: z.string(), items: z.array(TeacherPref).default([]), effective: Pair });
export type SubmitOut = z.infer<typeof SubmitOut>;

/** `?dry_run=1`: the same answer as a submit, nothing stored (`submission` and item ids null, status "preview") */
export const PreviewItem = TeacherPref.extend({ id: z.number().nullable().default(null), constraint_id: z.number().nullable().default(null) });
export const PreviewOut = z.object({ dry_run: z.boolean().default(true), submission: z.string().nullable().default(null), status: z.string().default("preview"), items: z.array(PreviewItem).default([]), effective: Pair });
export type PreviewOut = z.infer<typeof PreviewOut>;

/** one bookable room of `GET /moderation/me/rooms` (code "C301", name "C 301", building letter + name; no notes) */
export const WishRoom = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string().nullable().default(null),
  capacity: z.number().nullable().default(null),
  building: z.string().nullable().default(null),
  building_name: z.string().nullable().default(null),
  tags: z.array(z.string()).default([]),
  bookable: z.boolean().default(true),
});
export type WishRoom = z.infer<typeof WishRoom>;
export const WishRooms = z.object({ items: z.array(WishRoom).default([]), count: z.number().default(0) });
export type WishRooms = z.infer<typeof WishRooms>;

export const TermPrefs = z.object({ term_id: z.number(), counts: Counts.default({ pending: 0, accepted: 0, rejected: 0 }), total: z.number().default(0), items: z.array(TeacherPref).default([]) });
export type TermPrefs = z.infer<typeof TermPrefs>;

export const DecideOut = z.object({
  decision: z.enum(["accept", "reject"]),
  status: PrefStatus,
  decided_ids: Ids,
  notified: z.boolean().default(false),
  items: z.array(TeacherPref).default([]),
  effective: Pair.nullable().default(null),
});
export type DecideOut = z.infer<typeof DecideOut>;

/** the body of `POST /moderation/me/preferences` (the fields of the chosen kind only) */
export interface WishIn {
  kind: WishKind;
  request_ids: number[];
  room_ids?: number[];
  rooms?: string[];
  buildings?: string[];
  earliest?: number;
  latest?: number;
  days?: number[];
  note?: string;
}

export interface DecideIn {
  decision: "accept" | "reject";
  reason?: string;
  reason_code?: string;
  with_submission: boolean;
}

export const prefsApi = {
  mine: (termId?: number | null) => request(`/moderation/me/preferences`, { query: { term_id: termId ?? undefined }, schema: MinePrefs, silent: true }),
  submit: (body: WishIn) => request(`/moderation/me/preferences`, { method: "POST", body, schema: SubmitOut, silent: true }),
  preview: (body: WishIn) => request(`/moderation/me/preferences`, { method: "POST", query: { dry_run: 1 }, body, schema: PreviewOut, silent: true }),
  rooms: () => request(`/moderation/me/rooms`, { schema: WishRooms, silent: true }),
  withdraw: (id: number) => request(`/moderation/me/preferences/${id}`, { method: "DELETE", silent: true }),
  term: (termId: number, status = "all") => request(`/terms/${termId}/moderation/teacher-preferences`, { query: { status }, schema: TermPrefs, silent: true }),
  decide: (id: number, body: DecideIn) => request(`/moderation/preferences/${id}/decide`, { method: "POST", body, schema: DecideOut, silent: true }),
};

export const pk = {
  mine: (termId: number | null) => ["moderation", "my-prefs", termId] as const,
  term: (termId: number | null) => ["moderation", "teacher-prefs", termId] as const,
  preview: (body: WishIn | null) => ["moderation", "wish-preview", body ? JSON.stringify(body) : null] as const,
  rooms: ["moderation", "me-rooms"] as const,
};

const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && [401, 403, 404, 409, 422].includes(e.status)) && n < 2;

export function useMyPreferences(termId: number | null, enabled = true) {
  return useQuery({ queryKey: pk.mine(termId), queryFn: () => prefsApi.mine(termId), enabled, retry: noRetry, staleTime: 15_000 });
}
export function useTermTeacherPreferences(termId: number | null, enabled = true) {
  return useQuery({ queryKey: pk.term(termId), queryFn: () => prefsApi.term(termId ?? 0), enabled: enabled && termId !== null, retry: noRetry, staleTime: 15_000 });
}

/**
 * The server's own preview of a wish (`?dry_run=1`) for a body the sheet already accepts; `null` asks nothing. A
 * refusal is the error (same codes as a submit). Under ["moderation"], so a submit marks it stale.
 */
export function useWishPreview(body: WishIn | null) {
  return useQuery({ queryKey: pk.preview(body), queryFn: () => prefsApi.preview(body!), enabled: body !== null, retry: false, staleTime: 15_000, gcTime: 60_000 });
}

/** the room picker's rooms; a 403 `not_linked` (or any error) leaves the typed-code path */
export function useWishRooms(enabled = true) {
  return useQuery({ queryKey: pk.rooms, queryFn: prefsApi.rooms, enabled, retry: noRetry, staleTime: 5 * 60_000 });
}

/** every moderation read (people badges, matchings, Tercihler, /moderation/me counts) changes with a wish */
export function useSubmitWish() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: prefsApi.submit, onSuccess: () => qc.invalidateQueries({ queryKey: ["moderation"] }) });
}
export function useWithdrawWish() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: prefsApi.withdraw, onSuccess: () => qc.invalidateQueries({ queryKey: ["moderation"] }) });
}
export function useDecideWish() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (v: { id: number; body: DecideIn }) => prefsApi.decide(v.id, v.body), onSuccess: () => qc.invalidateQueries({ queryKey: ["moderation"] }) });
}

/** `{code, message, message_tr, ...}` of a refusal, or null when the error is not one */
export function wishError(e: unknown): { status: number; code: string; message: string; message_tr: string; request_ids: number[] } | null {
  if (!(e instanceof HttpError)) return null;
  const raw = e.detail as unknown;
  const body = raw && typeof raw === "object" && "detail" in (raw as Record<string, unknown>) ? (raw as Record<string, unknown>).detail : raw;
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const b = body as Record<string, unknown>;
  if (typeof b.code !== "string") return null;
  return {
    status: e.status,
    code: b.code,
    message: typeof b.message === "string" ? b.message : e.message,
    message_tr: typeof b.message_tr === "string" ? b.message_tr : "",
    request_ids: Array.isArray(b.request_ids) ? b.request_ids.filter((x): x is number => typeof x === "number") : [],
  };
}
