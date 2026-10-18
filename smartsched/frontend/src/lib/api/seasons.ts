"use client";
/**
 * AS-15 season calendar and profiles (backend app/api/v1/seasons.py, services/seasons.py; ADMIN only, 403 otherwise).
 *
 * - `GET /seasons/profiles`: built-ins (`standard`, `exam_week`, read-only, `id: null`) + stored versions, the weight
 *   keys, their defaults and the season / period-kind labels.
 * - `POST /seasons/profiles` (a draft, version 1), `PUT /seasons/profiles/{id}` (a draft is edited in place, an active
 *   profile gets a new draft version), `POST …/{id}/activate`, `POST …/{id}/revert` ("Geri al": the parent is active
 *   again), `DELETE …/{id}` (a draft is deleted, an active one retired).
 * - `GET /seasons/terms/{id}/periods`: the term's dated period segments plus admin segments (drafts come from imports
 *   and change nothing until approved: `PUT /seasons/segments/{id} {status: "active"}`).
 *
 * Errors carry `{code, message_tr, message_en}`; nothing here invents data.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";
import { serverMessage } from "./error-text";

const s = { silent: true } as const;

export const Pair = z.object({ tr: z.string().default(""), en: z.string().default("") });
export type Pair = z.infer<typeof Pair>;

export const ProfileStatus = z.enum(["draft", "active", "retired"]).catch("draft");
export type ProfileStatus = z.infer<typeof ProfileStatus>;

export const AppliesTo = z.object({ season: z.string(), period_kind: z.string() });
export type AppliesTo = z.infer<typeof AppliesTo>;

export const Profile = z.object({
  id: z.number().nullable(),
  key: z.string(),
  version: z.number(),
  name: Pair,
  name_tr: z.string().default(""),
  name_en: z.string().default(""),
  applies_to: z.array(AppliesTo).default([]),
  solver_weights: z.record(z.string(), z.number()).default({}),
  booking_overlays: z.array(z.record(z.string(), z.unknown())).default([]),
  peak_threshold_pct: z.number().default(85),
  status: ProfileStatus,
  builtin: z.boolean().default(false),
  origin: z.enum(["admin", "learned", "proposed", "builtin"]).catch("admin"),
  parent_id: z.number().nullable().default(null),
  approved_at: z.string().nullable().default(null),
  explanation: z.object({ tr: z.string().optional(), en: z.string().optional() }).catch({}).default({}),
  evidence: z.record(z.string(), z.unknown()).catch({}).default({}),
  source: z.string().default(""),
  weights_diff: z.array(z.object({ key: z.string(), default: z.number().nullable(), value: z.number() })).default([]),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type Profile = z.infer<typeof Profile>;

const Labelled = z.object({ key: z.string(), label: Pair });
export type Labelled = z.infer<typeof Labelled>;

export const ProfileList = z.object({
  profiles: z.array(Profile).default([]),
  weight_keys: z.array(z.string()).default([]),
  defaults: z.record(z.string(), z.number()).default({}),
  seasons: z.array(Labelled).default([]),
  period_kinds: z.array(Labelled).default([]),
});
export type ProfileList = z.infer<typeof ProfileList>;

export const Segment = z.object({
  id: z.number(),
  term_id: z.number(),
  kind: z.string(),
  kind_label: Pair.optional(),
  week_from: z.number().nullable().optional(),
  week_to: z.number().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  label: Pair.optional(),
  status: z.enum(["draft", "active"]).catch("draft"),
});
export type Segment = z.infer<typeof Segment>;

export const Period = z.object({
  kind: z.string(),
  kind_label: Pair.optional(),
  week_from: z.number().nullable().optional(),
  week_to: z.number().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  label: Pair.optional(),
  source: z.enum(["week", "holiday", "segment"]).catch("week"),
  status: z.enum(["draft", "active"]).catch("active"),
  segment_id: z.number().nullable().optional(),
});
export type Period = z.infer<typeof Period>;

export const TermPeriods = z.object({
  term_id: z.number(),
  term_code: z.string().nullable().optional(),
  season: Labelled.nullable().optional(),
  periods: z.array(Period).default([]),
  segments: z.array(Segment).default([]),
  empty: z.boolean().optional(),
  needs: Pair.nullable().optional(),
});
export type TermPeriods = z.infer<typeof TermPeriods>;

export interface ProfileIn {
  key?: string;
  name_tr: string;
  name_en: string;
  applies_to: AppliesTo[];
  solver_weights?: Record<string, number>;
  peak_threshold_pct?: number;
  explanation?: { tr: string; en: string };
}

export interface SegmentIn {
  kind: string;
  week_from: number;
  week_to: number;
  label_tr?: string;
  status?: "draft" | "active";
}

/** AS-14 `POST /learning/weights/propose {term_id}`: a draft "learned" profile from the term's manual edits, or `needs` */
export const WeightProposal = z.object({
  edits: z.number().catch(0).default(0),
  confidence: z.string().default("none"),
  needs: Pair.nullable().catch(null).optional(),
  proposal: z.object({ profile_id: z.number().nullable().optional(), key: z.string().optional(), version: z.number().optional() }).passthrough().nullable().catch(null).optional(),
});
export type WeightProposal = z.infer<typeof WeightProposal>;

export const seasonsApi = {
  proposeWeights: (termId: number) => request("/learning/weights/propose", { method: "POST", body: { term_id: termId }, schema: WeightProposal, ...s }),
  profiles: () => request("/seasons/profiles", { schema: ProfileList, ...s }),
  create: (body: ProfileIn) => request("/seasons/profiles", { method: "POST", body, schema: Profile, ...s }),
  update: (id: number, body: Partial<ProfileIn>) => request(`/seasons/profiles/${id}`, { method: "PUT", body, schema: Profile, ...s }),
  activate: (id: number) => request(`/seasons/profiles/${id}/activate`, { method: "POST", schema: Profile, ...s }),
  revert: (id: number) => request(`/seasons/profiles/${id}/revert`, { method: "POST", schema: Profile, ...s }),
  remove: (id: number) => request(`/seasons/profiles/${id}`, { method: "DELETE", ...s }),
  periods: (termId: number) => request(`/seasons/terms/${termId}/periods`, { schema: TermPeriods, ...s }),
  createSegment: (termId: number, body: SegmentIn) => request(`/seasons/terms/${termId}/segments`, { method: "POST", body, schema: Segment, ...s }),
  updateSegment: (id: number, body: { status: "active" | "draft" }) => request(`/seasons/segments/${id}`, { method: "PUT", body, schema: Segment, ...s }),
  removeSegment: (id: number) => request(`/seasons/segments/${id}`, { method: "DELETE", ...s }),
};

export const seasonKeys = {
  all: ["seasons"] as const,
  profiles: ["seasons", "profiles"] as const,
  periods: (termId: number | null) => ["seasons", "periods", termId] as const,
};

const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && [401, 403, 404, 422].includes(e.status)) && n < 2;

export function useProfiles(enabled = true) {
  return useQuery({ queryKey: seasonKeys.profiles, queryFn: seasonsApi.profiles, enabled, retry: noRetry });
}

export function useTermPeriods(termId: number | null) {
  return useQuery({ queryKey: seasonKeys.periods(termId), queryFn: () => seasonsApi.periods(termId ?? 0), enabled: termId !== null, retry: noRetry });
}

export function useProfileActions() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: seasonKeys.all });
  return {
    propose: useMutation({ mutationFn: (termId: number) => seasonsApi.proposeWeights(termId), onSuccess: done }),
    create: useMutation({ mutationFn: (body: ProfileIn) => seasonsApi.create(body), onSuccess: done }),
    update: useMutation({ mutationFn: (v: { id: number; body: Partial<ProfileIn> }) => seasonsApi.update(v.id, v.body), onSuccess: done }),
    activate: useMutation({ mutationFn: (id: number) => seasonsApi.activate(id), onSuccess: done }),
    revert: useMutation({ mutationFn: (id: number) => seasonsApi.revert(id), onSuccess: done }),
    remove: useMutation({ mutationFn: (id: number) => seasonsApi.remove(id), onSuccess: done }),
    createSegment: useMutation({ mutationFn: (v: { termId: number; body: SegmentIn }) => seasonsApi.createSegment(v.termId, v.body), onSuccess: done }),
    approveSegment: useMutation({ mutationFn: (id: number) => seasonsApi.updateSegment(id, { status: "active" }), onSuccess: done }),
    removeSegment: useMutation({ mutationFn: (id: number) => seasonsApi.removeSegment(id), onSuccess: done }),
  };
}

/** the server's own sentence (`message_tr` / `message_en`), else the transport message */
export function apiText(e: unknown, locale: string): string {
  return serverMessage(e, locale) ?? (e instanceof Error ? e.message : String(e));
}
