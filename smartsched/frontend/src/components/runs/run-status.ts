/**
 * A run's status as the shell shows it (badge kind + label). Split from runs-list.tsx (F-CH-1, fix-c-2026-10-18):
 * the notification bell and the command palette import these helpers, and runs-list.tsx brings the data table,
 * the compare entry and the council helpers with it.
 */
import type { StatusKind } from "@/components/common/status-badge";
import type { RunStatus, ScheduleRun } from "@/lib/api/schemas";
import type { MessageKey, Vars } from "@/lib/i18n";

export const RUN_STATUS_KIND: Record<RunStatus, StatusKind> = { QUEUED: "preoccupied", RUNNING: "pclab", FEASIBLE: "feasible", OPTIMAL: "feasible", FEASIBLE_PARTIAL: "warning", INFEASIBLE: "infeasible", TIMEOUT: "infeasible", ERROR: "infeasible", FAILED: "infeasible", CANCELLED: "preoccupied" };

/** A best-effort run: status ``FEASIBLE_PARTIAL`` (older runs: INFEASIBLE with ``stats.partial``) with
 * ``placed`` of ``events_total`` events stored; shown as "Partial · placed/total" with the warning badge. */
export function partialCounts(r: ScheduleRun): { placed: number; total: number } | null {
  const placed = Number(r.stats.placed ?? 0);
  const total = Number(r.stats.events_total ?? 0);
  const partial = r.status === "FEASIBLE_PARTIAL" || (r.status === "INFEASIBLE" && Boolean(r.stats.partial ?? placed > 0));
  return partial && placed > 0 && total > 0 ? { placed, total } : null;
}

export function runStatusBadge(r: ScheduleRun, t: (k: MessageKey, p?: Vars) => string): { kind: StatusKind; label: string } {
  const partial = partialCounts(r);
  if (partial) return { kind: "warning", label: t("runs.partial", partial) };
  return { kind: RUN_STATUS_KIND[r.status], label: `${t(`runs.status.${r.status}`)}${r.status === "RUNNING" ? ` ${r.progress}%` : ""}` };
}
