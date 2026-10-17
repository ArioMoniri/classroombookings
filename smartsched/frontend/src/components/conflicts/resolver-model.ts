/**
 * The conflict resolver's decisions (P2), kept apart from React so they are unit-tested.
 *
 * One row per group (a 14-week series is one row): the planner picks an option (move to a room, an adjacent period,
 * another weekday, cancel, or keep = override) and a scope. A series row can be split ("Tek tek karar ver") so every
 * clashing date gets its own decision. `buildItems` turns the decisions into the `apply` payload:
 *
 * - a series row with scope `future` / `all`: one item for its earliest conflict with that scope (the backend moves
 *   or cancels the series from there and closes the series' other conflicts with it);
 * - scope `one` (and every split row, every single booking): one item per conflict.
 *
 * The backend validates everything again (all or nothing, 409 `invalid_items` with `problems[]`).
 */
import type { ApplyItem, ApplyResult, AutoPlan, ConflictGroup, ConflictOption, ConflictPlan, Problem, ResolveAction, ResolveScope } from "@/lib/api/booking-conflicts";

export interface Decision {
  /** null = no decision yet (the row is left out of the payload) */
  optionId: string | null;
  scope: ResolveScope;
  reason: string;
}

export interface ResolverState {
  groups: Record<string, Decision>;
  /** split rows: one decision per conflict id */
  split: Record<string, boolean>;
  perConflict: Record<number, Decision>;
}

export const EMPTY_DECISION: Decision = { optionId: null, scope: "one", reason: "" };

export function initialState(plan: ConflictPlan | undefined): ResolverState {
  const groups: Record<string, Decision> = {};
  for (const g of plan?.groups ?? []) groups[g.key] = { ...EMPTY_DECISION, scope: g.default_scope };
  return { groups, split: {}, perConflict: {} };
}

export function optionOf(group: ConflictGroup, optionId: string | null): ConflictOption | undefined {
  return optionId ? group.options.find((o) => o.id === optionId) : undefined;
}

/** The options a planner may choose: `override` only for `planning.admin`; `move_day` never with a series scope. */
export function choosableOptions(group: ConflictGroup, isAdmin: boolean): ConflictOption[] {
  return group.options.filter((o) => (o.kind !== "override" || isAdmin));
}

/** Scopes that make sense for the row: a single booking or a day move is `one` only. */
export function scopesFor(group: ConflictGroup, option: ConflictOption | undefined): ResolveScope[] {
  if (group.kind !== "series" || option?.kind === "move_day") return ["one"];
  return ["one", "future", "all"];
}

export function needsReason(option: ConflictOption | undefined): boolean {
  return option?.kind === "override";
}

export type RowIssue = "reason" | "override_forbidden";

/** What blocks a decided row before sending (the backend says the same; we say it next to the row first). */
export function rowIssue(group: ConflictGroup, d: Decision, isAdmin: boolean): RowIssue | null {
  const o = optionOf(group, d.optionId);
  if (!o) return null;
  if (o.kind === "override" && !isAdmin) return "override_forbidden";
  if (needsReason(o) && !d.reason.trim()) return "reason";
  return null;
}

function item(conflictId: number, o: ConflictOption, scope: ResolveScope, reason: string): ApplyItem {
  const text = reason.trim() || (o.kind === "cancel" ? (o.default_reason ?? "") : "");
  return { conflict_id: conflictId, action: o.kind as ResolveAction, option_id: o.kind.startsWith("move_") ? o.id : null, scope, reason: text || null };
}

export function buildItems(plan: ConflictPlan, state: ResolverState): ApplyItem[] {
  const out: ApplyItem[] = [];
  for (const g of plan.groups) {
    if (state.split[g.key]) {
      for (const c of g.conflicts) {
        const d = state.perConflict[c.conflict_id] ?? state.groups[g.key] ?? EMPTY_DECISION;
        const o = optionOf(g, d.optionId);
        if (o) out.push(item(c.conflict_id, o, "one", d.reason));
      }
      continue;
    }
    const d = state.groups[g.key] ?? EMPTY_DECISION;
    const o = optionOf(g, d.optionId);
    if (!o) continue;
    const scope = scopesFor(g, o).includes(d.scope) ? d.scope : "one";
    if (g.kind === "series" && scope !== "one") {
      const first = [...g.conflicts].sort((a, b) => a.date.localeCompare(b.date))[0];
      if (first) out.push(item(first.conflict_id, o, scope, d.reason));
    } else {
      for (const c of g.conflicts) out.push(item(c.conflict_id, o, "one", d.reason));
    }
  }
  return out;
}

/** Rows decided / all rows (a split row counts once it has a decision for every date). */
export function progress(plan: ConflictPlan | undefined, state: ResolverState): { decided: number; total: number } {
  const groups = plan?.groups ?? [];
  let decided = 0;
  for (const g of groups) {
    if (state.split[g.key]) {
      if (g.conflicts.every((c) => (state.perConflict[c.conflict_id] ?? state.groups[g.key])?.optionId)) decided++;
    } else if (state.groups[g.key]?.optionId) decided++;
  }
  return { decided, total: groups.length };
}

/**
 * The `auto` suggestions as decisions: a row whose conflicts all got the same option takes it as the row decision
 * (scope `one`); otherwise the row is split with one decision per suggested date. Conflicts left unresolved keep no
 * decision; their reasons come back keyed by conflict id.
 */
export function applyAuto(plan: ConflictPlan, auto: AutoPlan, prev: ResolverState): { state: ResolverState; unresolved: Map<number, { tr: string; en: string } | null> } {
  const byConflict = new Map(auto.items.map((i) => [i.conflict_id, i]));
  const state: ResolverState = { groups: { ...prev.groups }, split: { ...prev.split }, perConflict: { ...prev.perConflict } };
  for (const g of plan.groups) {
    const picks = g.conflicts.map((c) => byConflict.get(c.conflict_id));
    const ids = new Set(picks.map((p) => (p ? (p.option_id ?? p.action) : null)));
    if (picks.every(Boolean) && ids.size === 1) {
      const p = picks[0]!;
      const optionId = g.options.find((o) => o.id === p.option_id || (!p.option_id && o.kind === p.action))?.id ?? null;
      state.groups[g.key] = { optionId, scope: "one", reason: "" };
      state.split[g.key] = false;
    } else if (picks.some(Boolean)) {
      state.split[g.key] = true;
      for (const [i, c] of g.conflicts.entries()) {
        const p = picks[i];
        const optionId = p ? (g.options.find((o) => o.id === p.option_id)?.id ?? null) : null;
        state.perConflict[c.conflict_id] = { optionId, scope: "one", reason: "" };
      }
    }
  }
  const unresolved = new Map(auto.unresolved.map((u) => [u.conflict_id, u.reason ?? null]));
  return { state, unresolved };
}

/** 409 problems per row key (a problem names a conflict; its row is the group that holds it). */
export function problemsByGroup(plan: ConflictPlan | undefined, problems: readonly Problem[]): Map<string, Problem[]> {
  const out = new Map<string, Problem[]>();
  for (const p of problems) {
    const g = plan?.groups.find((x) => x.conflicts.some((c) => c.conflict_id === p.conflict_id));
    const key = g?.key ?? "_";
    out.set(key, [...(out.get(key) ?? []), p]);
  }
  return out;
}

export interface ResultSummary {
  moved: number;
  cancelled: number;
  kept: number;
  notified: number;
  unnotified: number;
  already: number;
}

export function summarise(r: ApplyResult): ResultSummary {
  return { moved: r.moved.length, cancelled: r.cancelled.length, kept: r.kept.length, notified: r.notified, unnotified: r.unnotified, already: r.already.length };
}

/** "08.03" from "2026-03-08" (day.month, the resolver's dense date). */
export function dayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return d && m ? `${d}.${m}` : iso;
}

/**
 * The row heading's time for a group: a submission (the periods of one request, T-R2-13) names its whole span
 * "P5–P6 (11:50–13:20)", not the first period alone; a lone booking or a series row keeps the first conflict's time.
 */
export function groupTime(g: Pick<ConflictGroup, "kind" | "conflicts">): string {
  const first = g.conflicts[0];
  if (!first) return "";
  // a submission: several conflicts of one request group that is not a series (the API's kind "submission")
  if (g.kind === "series" || g.conflicts.length < 2) return first.time;
  const sorted = [...g.conflicts].sort((a, b) => a.start_period - b.start_period || a.end_period - b.end_period);
  const lo = sorted[0]!;
  const hi = sorted.reduce((m, c) => (c.end_period > m.end_period ? c : m), sorted[0]!);
  return `P${lo.start_period}–P${hi.end_period} (${lo.time.split("-")[0] ?? ""}–${hi.time.split("-")[1] ?? ""})`;
}
