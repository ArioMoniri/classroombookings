"use client";
/**
 * Wave-3 feature hints (spec §4.5). The server decides eligibility (audience by permission, accounts created before the
 * release, 60-day expiry, `seen`, `hints_for_all`) and lists the eligible hints in `GET /welcome` `hints`; the client
 * keeps the product placement (HINTS in ../content) and hides a hint the moment it is closed in this tab.
 */
import { useRouter } from "next/navigation";
import { useWelcomeEvent } from "@/lib/api/welcome";
import { useI18n } from "@/lib/i18n/provider";
import { hintDef, hintKey, hintMsg, type HintDef } from "../content";
import { useWelcomeData } from "../checklist/checklist-list";
import { openWhatsNew, useWelcomeStore } from "../welcome-store";

export interface ActiveHint {
  def: HintDef;
  overrides: Record<string, string>;
}

/** Eligible, not yet closed hints (empty when the part is off or the guide state is unknown). */
export function useEligibleHints(): ActiveHint[] {
  const data = useWelcomeData();
  const dismissed = useWelcomeStore((s) => s.dismissedHints);
  if (!data?.enabled.hints) return [];
  const out: ActiveHint[] = [];
  for (const h of data.hints) {
    const def = hintDef(h.key);
    if (def && !dismissed.includes(def.key) && !out.some((o) => o.def.key === def.key)) out.push({ def, overrides: h.overrides ?? {} });
  }
  return out;
}

/** "Dene" / "Anladım" / "Tüm yenilikler": every one of them marks the hint `seen` (once per user, on the server). */
export function useHintActions() {
  const router = useRouter();
  const event = useWelcomeEvent();
  const dismiss = useWelcomeStore((s) => s.dismissHint);
  const setAutoHint = useWelcomeStore((s) => s.setAutoHint);
  const seen = (key: string) => {
    const k = hintKey(key);
    dismiss(k);
    setAutoHint(null);
    event.mutate({ guide_key: `hint.${k}`, event: "seen" });
  };
  return {
    seen,
    tryIt: (h: HintDef) => {
      seen(h.key);
      router.push(h.href);
    },
    allNews: (h: HintDef) => {
      seen(h.key);
      openWhatsNew();
    },
  };
}

export function useHintText() {
  const { t } = useI18n();
  return {
    title: (h: ActiveHint) => h.overrides.title?.trim() || t(hintMsg(h.def.key, "title")),
    body: (h: ActiveHint) => h.overrides.body?.trim() || t(hintMsg(h.def.key, "body")),
  };
}
