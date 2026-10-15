/**
 * AI intake policy (KVKK, review 2026-10-15 D7 / P19-A1): `GET /ai/policy` (planners) and `PUT /ai/policy`
 * (administrators), backend `app/ai/policy.py`. Two switches, both off by default: `intake_enabled` (the text
 * of uploaded files may be sent to the Claude API) and `vision_enabled` (page images too; needs intake). A
 * switch counts only with the administrator's KVKK sign-off record: turning one on needs `kvkk_ack`, every
 * change writes a new record and an `ai.policy` audit event. The council's `council_ai_enabled` setting is an
 * alias of the same policy, so the UI shows this one control only.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

export const AiSignoff = z.object({
  by: z.number().nullable().optional(),
  by_label: z.string().nullable().optional(),
  at: z.string(),
  features: z.array(z.string()).default([]),
  enabled: z.boolean().default(false),
  legal_basis: z.string().nullable().optional(),
  notice_version: z.string().nullable().optional(),
  acknowledged: z.boolean().optional(),
  reason: z.string().nullable().optional(),
});
export type AiSignoff = z.infer<typeof AiSignoff>;

export const AiPolicy = z.object({
  intake_enabled: z.boolean(),
  vision_enabled: z.boolean(),
  signoff: AiSignoff.nullable(),
  notice: z.object({ tr: z.string(), en: z.string() }),
  notice_version: z.string(),
  legal_basis: z.string(),
});
export type AiPolicy = z.infer<typeof AiPolicy>;

export interface AiPolicyIn {
  intake_enabled?: boolean;
  vision_enabled?: boolean;
  kvkk_ack?: boolean;
  reason?: string;
}

export const aiPolicyKey = ["ai", "policy"] as const;

export const aiPolicyApi = {
  get: () => request("/ai/policy", { schema: AiPolicy, silent: true }),
  put: (body: AiPolicyIn) => request("/ai/policy", { method: "PUT", body, schema: AiPolicy, silent: true }),
};

export const useAiPolicy = () => useQuery({ queryKey: aiPolicyKey, queryFn: aiPolicyApi.get, retry: false });

export function useSetAiPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: aiPolicyApi.put,
    onSuccess: (data) => {
      qc.setQueryData(aiPolicyKey, data);
      // GET /settings reports the alias council_ai_enabled from the same policy
      void qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}
