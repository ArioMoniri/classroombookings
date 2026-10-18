"use client";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

/** a solver weight's planner name (`seasons.weight.*`); an unknown key still reads as words, never snake_case */
export function useWeightLabel() {
  const { t } = useI18n();
  return (key: string) => {
    const k = `seasons.weight.${key}` as MessageKey;
    const v = t(k);
    return v === k ? key.replace(/_/g, " ") : v;
  };
}
