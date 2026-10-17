/**
 * Tour definitions per audience live in ../content (STEPS, ≤ 5 each) and are combined by ../model `buildSteps`.
 * This module turns a resolved step into its copy (`welcome.tour.step.<anchor>.*`) and holds the step-level fallbacks:
 * the approvals step points at the page heading with "Şu an bekleyen talep yok…" when the inbox is empty.
 */
import type { MessageKey } from "@/lib/i18n";
import { stepKey } from "../content";
import type { ResolvedStep } from "../model";

/** steps whose anchor may be missing for a good reason: show them on the page heading with `bodyEmpty` */
export const HEADING_FALLBACK = new Set(["approvals-row-actions"]);

export function stepCopy(step: ResolvedStep, t: (k: MessageKey) => string, opts: { empty?: boolean } = {}): { title: string; body: string } {
  return { title: t(stepKey(step.anchor, "title")), body: t(stepKey(step.anchor, opts.empty ? "bodyEmpty" : "body")) };
}

/** Same pathname (ignores ?query / #hash). */
export function samePath(a: string, b: string): boolean {
  return a.split(/[?#]/)[0] === b.split(/[?#]/)[0];
}
