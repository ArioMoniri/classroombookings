/**
 * The term's relaxation policy (backend `app/api/v1/terms.py`): `GET /terms/{id}/relaxation-policy` →
 * `{policy, source: term | default}`; `PUT` `{policy}` (administrators; `null` clears the setting) writes the settings
 * key `term.<id>.relaxation_policy`, audited as `term.relaxation_policy`.
 */
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

export const TermRelaxationPolicy = z.object({
  term_id: z.number(),
  policy: z.enum(["lock_first", "most_classes_first"]),
  source: z.enum(["term", "default"]),
  default: z.string().default("lock_first"),
  options: z.array(z.string()).default([]),
  /** the stored value was not a policy name; runs use the default */
  stored_invalid: z.boolean().default(false),
});
export type TermRelaxationPolicy = z.infer<typeof TermRelaxationPolicy>;

export const termPolicyKey = (termId: number) => ["term-relaxation-policy", termId] as const;

export const relaxationApi = {
  get: (termId: number) => request(`/terms/${termId}/relaxation-policy`, { schema: TermRelaxationPolicy, silent: true }),
  put: (termId: number, policy: TermRelaxationPolicy["policy"] | null) =>
    request(`/terms/${termId}/relaxation-policy`, { method: "PUT", body: { policy }, schema: TermRelaxationPolicy, silent: true }),
};

export function useTermRelaxationPolicy(termId: number | null | undefined, enabled = true) {
  return useQuery({ queryKey: termPolicyKey(termId ?? 0), queryFn: () => relaxationApi.get(termId ?? 0), enabled: enabled && !!termId, staleTime: 30_000 });
}
