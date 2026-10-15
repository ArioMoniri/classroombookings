/**
 * The planner's edits of a chat diff before applying it (ai-engineer follow-up 2026-10-15): which moves to keep,
 * per move whether the meeting request is updated too (`update_request`: the next solve keeps the new time), and
 * per include/exclude section edit whether it changes the term data (`term`) or only this draft run (`run`).
 * The backend's `POST /runs/{id}/chat/apply` takes the edited `diff` and re-validates every operation.
 */
import { z } from "zod";
import { request } from "@/lib/api/client";

export type Scope = "term" | "run";
type RawOp = { op?: string; assignment_id?: number; update_request?: boolean; scope?: Scope; edit?: { op?: string } } & Record<string, unknown>;
export type RawDiff = { id: string; operations: RawOp[] } & Record<string, unknown>;

export interface DiffEdits {
  keep: ReadonlySet<number>;
  updateRequest: ReadonlySet<number>;
  /** operation index → scope, for include / exclude section edits */
  scopes: Readonly<Record<number, Scope>>;
}

export function editedDiff(diff: RawDiff, e: DiffEdits): RawDiff {
  const operations: RawOp[] = [];
  diff.operations.forEach((op, i) => {
    if (op.op === "move") {
      if (op.assignment_id === undefined || !e.keep.has(op.assignment_id)) return;
      operations.push({ ...op, update_request: e.updateRequest.has(op.assignment_id) });
    } else if (op.op === "section_edit" && (op.edit?.op === "include" || op.edit?.op === "exclude") && e.scopes[i]) {
      operations.push({ ...op, scope: e.scopes[i] });
    } else operations.push(op);
  });
  return { ...diff, operations };
}

/** True when the edits change nothing (the stored diff can be applied by id). */
export function isUnchanged(diff: RawDiff, e: DiffEdits): boolean {
  return JSON.stringify(editedDiff(diff, e).operations) === JSON.stringify(diff.operations);
}

const RawHistory = z.array(z.object({ tool_calls: z.array(z.unknown()).default([]) }).passthrough());
const Out = z.object({ child_run_id: z.number().nullable() }).passthrough();

/** Apply a chat diff with the planner's edits (by id when nothing changed). */
export async function applyEdited(runId: number, diffId: string, edits: DiffEdits): Promise<{ child_run_id: number | null }> {
  const history = await request(`/runs/${runId}/chat`, { schema: RawHistory });
  const call = history
    .flatMap((m) => m.tool_calls as { type?: string; diff?: RawDiff }[])
    .find((tc) => tc && typeof tc === "object" && tc.type === "diff" && tc.diff?.id === diffId);
  if (!call?.diff || isUnchanged(call.diff, edits)) return request(`/runs/${runId}/chat/apply`, { method: "POST", body: { diff_id: diffId }, schema: Out });
  return request(`/runs/${runId}/chat/apply`, { method: "POST", body: { diff: editedDiff(call.diff, edits) }, schema: Out });
}
