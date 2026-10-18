"use client";
/**
 * AS-13 / RF-07 learning versions, calibration drafts and per-habit controls (backend app/api/v1/learning.py,
 * services/learning_versions.py).
 *
 * - `POST /learning/refresh {term_id}` (planning.edit): re-extract and record a new learning version ("Öğrenmeyi yenile").
 * - `GET /learning/versions?term_id=` (planning.view) and `POST /learning/versions/{id}/revert` (planning.admin): the
 *   term stays on the restored version until the next manual refresh (`pinned_version_id`).
 * - `GET /learning/calibration` + `POST /learning/calibration/apply` (planning.admin): "Ayar önerileri".
 * - `GET /learning/priors?term_id=` (planning.view): every active learned habit; `PUT /learning/priors/{id}/habit`
 *   (planning.admin) disables, corrects or tunes one (`state: null` clears it).
 * - `GET / PUT /learning/settings` (planning.admin): the nightly refresh switch.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";

const s = { silent: true } as const;
const Pair = z.object({ tr: z.string().default(""), en: z.string().default("") });

export const VersionDiffItem = z.object({ scope: z.string(), attribute: z.string(), value: z.string(), value_label: z.union([Pair, z.string()]).nullable().catch(null).optional() }).passthrough();

export const LearningVersion = z.object({
  id: z.number(),
  number: z.number(),
  trigger: z.string(),
  trigger_label: Pair.optional(),
  created_at: z.string().nullable(),
  observations: z.number().default(0),
  priors: z.number().default(0),
  suggestible: z.number().default(0),
  checksum: z.string().default(""),
  diff: z
    .object({
      new: z.array(VersionDiffItem).catch([]).default([]),
      dropped: z.array(VersionDiffItem).catch([]).default([]),
      changed: z.array(VersionDiffItem).catch([]).default([]),
      counts: z.object({ new: z.number().default(0), dropped: z.number().default(0), changed: z.number().default(0) }).catch({ new: 0, dropped: 0, changed: 0 }),
    })
    .nullable()
    .catch(null),
  restored_from: z.number().nullable().default(null),
});
export type LearningVersion = z.infer<typeof LearningVersion>;

export const VersionList = z.object({
  versions: z.array(LearningVersion).default([]),
  pinned_version_id: z.number().nullable().default(null),
  nightly_refresh: z.boolean().default(false),
  needs: Pair.nullable().catch(null).optional(),
});
export type VersionList = z.infer<typeof VersionList>;

export const Calibration = z.object({
  proposals: z
    .array(z.object({ attribute: z.string(), band: z.string(), min_confidence: z.number(), current: z.number().nullable().catch(null), explanation: Pair }))
    .catch([])
    .default([]),
  applied: z.record(z.string(), z.number()).catch({}).default({}),
  confidence: z.string().default("none"),
  needs: Pair.nullable().catch(null).optional(),
});
export type Calibration = z.infer<typeof Calibration>;

export const HabitState = z.enum(["disabled", "corrected", "tuned"]);
export type HabitState = z.infer<typeof HabitState>;
export const HabitOverride = z.object({ state: HabitState, reason: z.string().nullable().optional(), weight: z.number().optional(), to: z.string().optional() }).passthrough();
export type HabitOverride = z.infer<typeof HabitOverride>;

export const Prior = z.object({
  id: z.number(),
  subject: z.object({ type: z.string(), id: z.union([z.string(), z.number()]), label: z.string() }),
  attribute: z.string(),
  value: z.string(),
  value_label: z.union([Pair, z.string()]).nullable().catch(null).optional(),
  confidence: z.number().default(0),
  suggestible: z.boolean().default(false),
  explanation: Pair.optional(),
  evidence: z.object({ habit: HabitOverride.nullable().catch(null).optional() }).passthrough().catch({}).default({}),
});
export type Prior = z.infer<typeof Prior>;

export interface HabitIn {
  state: HabitState | null;
  reason?: string;
  value?: string;
  weight?: number;
}

export const learningVersionsApi = {
  refresh: (termId: number) => request("/learning/refresh", { method: "POST", body: { term_id: termId }, schema: z.object({ version: LearningVersion.nullable().catch(null).optional() }).passthrough(), ...s }),
  versions: (termId: number) => request("/learning/versions", { query: { term_id: termId }, schema: VersionList, ...s }),
  revert: (id: number) => request(`/learning/versions/${id}/revert`, { method: "POST", schema: z.object({ identical: z.boolean().default(false), version: LearningVersion.nullable().catch(null).optional() }).passthrough(), ...s }),
  calibration: () => request("/learning/calibration", { schema: Calibration, ...s }),
  applyCalibration: (attribute: string, min: number | null) => request("/learning/calibration/apply", { method: "POST", body: { attribute, min_confidence: min }, ...s }),
  priors: (termId: number) => request("/learning/priors", { query: { term_id: termId }, schema: z.array(Prior), ...s }),
  setHabit: (priorId: number, body: HabitIn) => request(`/learning/priors/${priorId}/habit`, { method: "PUT", body, ...s }),
  settings: () => request("/learning/settings", { schema: z.object({ nightly_refresh: z.boolean().default(false) }).passthrough(), ...s }),
  putSettings: (nightly: boolean) => request("/learning/settings", { method: "PUT", body: { nightly_refresh: nightly }, ...s }),
};

const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && [401, 403, 404, 422].includes(e.status)) && n < 2;

export const lvKeys = {
  versions: (termId: number | null) => ["learning", "versions", termId] as const,
  calibration: ["learning", "calibration"] as const,
  priors: (termId: number | null) => ["learning", "priors", termId] as const,
  settings: ["learning", "settings"] as const,
};

export function useLearningVersions(termId: number | null, enabled = true) {
  return useQuery({ queryKey: lvKeys.versions(termId), queryFn: () => learningVersionsApi.versions(termId ?? 0), enabled: enabled && termId !== null, retry: noRetry });
}
export function useCalibration(enabled = true) {
  return useQuery({ queryKey: lvKeys.calibration, queryFn: learningVersionsApi.calibration, enabled, retry: noRetry });
}
export function usePriors(termId: number | null, enabled = true) {
  return useQuery({ queryKey: lvKeys.priors(termId), queryFn: () => learningVersionsApi.priors(termId ?? 0), enabled: enabled && termId !== null, retry: noRetry });
}
export function useLearningSettings(enabled = true) {
  return useQuery({ queryKey: lvKeys.settings, queryFn: learningVersionsApi.settings, enabled, retry: noRetry });
}

/** every write refreshes the whole learning cache (summary, suggestions, versions, priors) */
export function useLearningVersionActions() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["learning"] });
  return {
    refresh: useMutation({ mutationFn: (termId: number) => learningVersionsApi.refresh(termId), onSuccess: done }),
    revert: useMutation({ mutationFn: (id: number) => learningVersionsApi.revert(id), onSuccess: done }),
    apply: useMutation({ mutationFn: (v: { attribute: string; min: number | null }) => learningVersionsApi.applyCalibration(v.attribute, v.min), onSuccess: done }),
    habit: useMutation({ mutationFn: (v: { id: number; body: HabitIn }) => learningVersionsApi.setHabit(v.id, v.body), onSuccess: done }),
    nightly: useMutation({ mutationFn: (on: boolean) => learningVersionsApi.putSettings(on), onSuccess: done }),
  };
}
