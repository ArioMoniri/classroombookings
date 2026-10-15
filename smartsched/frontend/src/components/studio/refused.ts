/**
 * The backend's AI source policy (`app/ai/elicit.py` `enforce_source_policy`) marks proposals it may not make —
 * untargeted rules, soft structural rules from a model source — as `rejected` with the reasons. They used to be
 * filtered out of the tray silently; they are now listed as "planner decision needed" notes with the reason.
 */
import type { ProposedConstraint } from "@/lib/api/schemas";
import type { Unparsed } from "@/lib/api/studio-schemas";

export function splitRefused(proposals: readonly ProposedConstraint[]): { usable: ProposedConstraint[]; refused: ProposedConstraint[] } {
  return { usable: proposals.filter((p) => p.status !== "rejected"), refused: proposals.filter((p) => p.status === "rejected") };
}

export function refusedAsDecisions(refused: readonly ProposedConstraint[]): Unparsed[] {
  return refused.map((p) => ({ text: p.nl_text || p.title || p.kind, reason: p.issues.join("; "), source_ref: p.source_ref ?? null, decision: true }));
}
