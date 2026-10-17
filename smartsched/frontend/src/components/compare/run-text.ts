"use client";
import type { ScheduleRun } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

const KNOWN = new Set(["QUEUED", "RUNNING", "FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL", "INFEASIBLE", "TIMEOUT", "ERROR", "FAILED", "CANCELLED"]);

/** "#6 · Bahar 3. hafta (B) · Sınav · Kısmi" — the run's own label, never an invented name */
export function useRunText() {
  const { t } = useI18n();
  return (r: Pick<ScheduleRun, "id" | "label" | "kind" | "is_active"> & { status: string }) =>
    [
      `#${r.id}`,
      r.label?.trim() || null,
      t(r.kind === "EXAM" ? "compare.kind.EXAM" : "compare.kind.COURSE"),
      KNOWN.has(r.status) ? t(`runs.status.${r.status}` as MessageKey) : r.status,
      r.is_active ? t("compare.published") : null,
    ]
      .filter(Boolean)
      .join(" · ");
}
