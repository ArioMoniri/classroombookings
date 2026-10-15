import { describe, expect, it } from "vitest";
import * as adapt from "@/lib/api/adapters";
import { ChatProposal } from "@/lib/api/schemas";
import { editedDiff, type RawDiff } from "./diff-edits";

const raw = {
  id: "d1",
  run_id: 5,
  summary: "Move BME 419, leave PHAR 240 out",
  operations: [
    { op: "move", assignment_id: 11, label: "BME 419", before: { day: 1, periods: [1, 2], rooms: ["A 204"] }, after: { day: 2, periods: [3, 4], rooms: ["A 101"] } },
    { op: "move", assignment_id: 12, label: "MAT 112", update_request: true, before: { day: 1, periods: [5, 6] }, after: { day: 3, periods: [5, 6] } },
    { op: "section_edit", edit: { op: "exclude", section_ids: [7], nl_text: "PHAR 240 §1", labels: ["PHAR 240 §1"] }, scope: "term" },
    { op: "section_edit", edit: { op: "set_field", section_ids: [8], changes: { enrolment: 40 } }, scope: "term" },
  ],
} as unknown as RawDiff;

describe("chat diff edits (ai-engineer follow-up: update_request per move, term vs run scope for include/exclude)", () => {
  it("the proposal exposes each move's update_request and the include/exclude edits with their scope", () => {
    const p = ChatProposal.parse(adapt.proposalFromDiff(raw, null));
    expect(p.moves.map((m) => [m.assignment_id, m.update_request])).toEqual([[11, false], [12, true]]);
    expect(p.section_edits).toEqual([{ index: 2, op: "exclude", label: "PHAR 240 §1", scope: "term" }]);
  });

  it("builds the edited diff: unticked moves dropped, update_request and scopes as chosen, other ops untouched", () => {
    const out = editedDiff(raw, { keep: new Set([11, 12]), updateRequest: new Set([11]), scopes: { 2: "run" } });
    expect(out.operations).toHaveLength(4);
    expect(out.operations[0]).toMatchObject({ op: "move", assignment_id: 11, update_request: true });
    expect(out.operations[1]).toMatchObject({ op: "move", assignment_id: 12, update_request: false });
    expect(out.operations[2]).toMatchObject({ op: "section_edit", scope: "run" });
    expect(out.operations[3]).toEqual(raw.operations[3]);
    const fewer = editedDiff(raw, { keep: new Set([12]), updateRequest: new Set([12]), scopes: {} });
    expect(fewer.operations.filter((o) => o.op === "move").map((o) => o.assignment_id)).toEqual([12]);
  });
});
