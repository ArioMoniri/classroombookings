"use client";
/** The guide's copy: `welcome.*` message keys, the admin's overrides on top, `{ad}` / `{bölüm}` filled in. */
import { useMeFull } from "@/lib/api/shell-extra";
import type { WelcomeState } from "@/lib/api/welcome";
import { useI18n } from "@/lib/i18n/provider";
import { audienceKey, cardKey, sheetKey } from "./content";
import { fillPlaceholders, firstNameOf, type ResolvedCard, type SheetModel } from "./model";

export function useGuideText(state: WelcomeState | undefined) {
  const { t, locale } = useI18n();
  const me = useMeFull();
  const name = firstNameOf(state, me.data?.full_name ?? me.data?.username ?? "");
  const department = state?.department?.trim() ?? "";
  const vars = { ad: name, name, department, "bölüm": department };
  const fill = (text: string) => fillPlaceholders(text, { name, department });
  /** override when non-empty, else the product text */
  const pick = (override: string | undefined, fallback: string) => (override && override.trim() ? fill(override) : fallback);
  return {
    t,
    locale,
    name,
    department,
    audience: (a: string) => t(audienceKey(a)),
    title: (m: SheetModel) => (m.kind === "delta" ? t("welcome.sheet.delta") : tidy(pick(m.overrides.title, t(sheetKey(m.primary, "title"), vars)))),
    lead: (m: SheetModel) => (m.kind === "delta" ? t("welcome.sheet.deltaLead") : pick(m.overrides.lead, t(sheetKey(m.primary, "lead"), vars))),
    cardTitle: (c: ResolvedCard) => pick(c.overrides.title, t(cardKey(c.audience, c.key, "title"))),
    cardBody: (c: ResolvedCard) => pick(c.overrides.body, t(cardKey(c.audience, c.key, "body"), vars)),
  };
}

/** "Hoş geldiniz, " when the name is unknown: drop the dangling comma. */
function tidy(text: string): string {
  return text.replace(/,\s*$/u, "").trim();
}
