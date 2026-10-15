/**
 * Run counts from one definition each, shared by the Studio run card, the run report and the grid (admin persona
 * M-06/M-07/M-08: the report said "no rule broken" while 123 classes sat over capacity under a waiver, the grid
 * header said "308 conflicts" and an imported board said "Problems 0"; the Studio card said "716 placed" for 687).
 */
import { isConflictReason } from "@/components/timetable/model/index-model";

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v)) ? Number(v) : null);

/** `stats.placed` is what got a room; `stats.events` / `events_total` is how many were asked for. */
export function placedOf(stats: Record<string, unknown>): { placed: number | null; total: number | null } {
  const total = num(stats.events_total) ?? num(stats.events);
  return { placed: num(stats.placed) ?? total, total };
}

export interface Waiver {
  rules: string[];
  /** placed classes that break a waived rule */
  events: number;
  byKind: Record<string, number>;
}

/** Built-in hard rules run as soft in this run (solver `report_waived`: capacity, tags, trusted locks ...). */
export function waiverOf(stats: Record<string, unknown>, diagnosis: readonly { code?: string; params?: Record<string, unknown> }[]): Waiver {
  const rules = Array.isArray(stats.waived_rules) ? stats.waived_rules.map(String) : [];
  const raw = stats.waived_violations && typeof stats.waived_violations === "object" ? (stats.waived_violations as Record<string, unknown>) : {};
  const byKind = Object.fromEntries(Object.entries(raw).flatMap(([k, v]) => (num(v) ? [[k, num(v) as number]] : [])));
  const d = diagnosis.find((x) => x.code === "waived_rules");
  const events = num(d?.params?.events) ?? Object.values(byKind).reduce((a, b) => a + b, 0);
  return { rules, events, byKind };
}

/** The grid's definitions (`buildModel`): a conflict is a room overlap / block / seats reason; over capacity is a
 * capacity reason on a class without a conflict. Counted once per class over the whole run. */
export function runIssueCounts(assignments: readonly { id: number; reasons: readonly string[] }[]): { conflicts: number; overCapacity: number } {
  const conflict = new Set<number>();
  const capacity = new Set<number>();
  for (const a of assignments) {
    if (a.reasons.some(isConflictReason)) conflict.add(a.id);
    else if (a.reasons.some((r) => r.startsWith("capacity"))) capacity.add(a.id);
  }
  for (const id of conflict) capacity.delete(id);
  return { conflicts: conflict.size, overCapacity: capacity.size };
}

export type VerdictException = { key: "waived" | "conflicts" | "overCapacity" | "lockedTooSmall"; n: number; rules?: string[] };

/** What keeps a finished run from "no rule broken", in report order; empty = the green verdict is true. */
export function verdictExceptions(p: { waiver: Waiver; counts: { conflicts: number; overCapacity: number }; lockedTooSmall: number }): VerdictException[] {
  const out: VerdictException[] = [];
  if (p.waiver.rules.length && p.waiver.events > 0) out.push({ key: "waived", n: p.waiver.events, rules: p.waiver.rules });
  if (p.counts.conflicts > 0) out.push({ key: "conflicts", n: p.counts.conflicts });
  if (p.counts.overCapacity > 0) out.push({ key: "overCapacity", n: p.counts.overCapacity });
  if (p.lockedTooSmall > 0) out.push({ key: "lockedTooSmall", n: p.lockedTooSmall });
  return out;
}

export interface ForcedOverride {
  assignment_ids: number[];
  rules: string[];
  conflicts: string[];
  reason: string;
  by_name: string | null;
  at: string | null;
}

/**
 * Fields the run summary (`GET /runs/{id}/summary`) added on 2026-10-15: `data_issues.issues` (the planner's data
 * issues, already folded into the headline) and `stats.forced_overrides` (admin moves that broke a hard rule,
 * each with its reason). Parsed defensively: the summary schema passes unknown keys through.
 */
export function summaryExtras(summary: Record<string, unknown> | null | undefined): { dataIssues: number | null; forcedOverrides: ForcedOverride[] } {
  const di = summary?.data_issues;
  const dataIssues = di && typeof di === "object" ? num((di as Record<string, unknown>).issues) : null;
  const raw = Array.isArray(summary?.forced_overrides) ? (summary.forced_overrides as unknown[]) : [];
  const forcedOverrides = raw.flatMap((x): ForcedOverride[] => {
    if (!x || typeof x !== "object") return [];
    const o = x as Record<string, unknown>;
    const arr = (v: unknown) => (Array.isArray(v) ? v : []);
    return [
      {
        assignment_ids: arr(o.assignment_ids).map(Number).filter(Number.isFinite),
        rules: arr(o.rules).map(String),
        conflicts: arr(o.conflicts).map(String),
        reason: typeof o.reason === "string" ? o.reason : "",
        by_name: typeof o.by_name === "string" ? o.by_name : null,
        at: typeof o.at === "string" ? o.at : null,
      },
    ];
  });
  return { dataIssues, forcedOverrides };
}
