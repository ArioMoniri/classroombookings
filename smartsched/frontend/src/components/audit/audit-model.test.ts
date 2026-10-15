import { describe, expect, it } from "vitest";
import { auditQuery, canUndo, diffRows, emptyAuditFilters, undoReasons, valueText } from "./audit-model";

describe("audit model", () => {
  it("uses the backend diff when there is one", () => {
    expect(diffRows({ diff: { capacity: [60, 48] }, before: { capacity: 60 }, after: { capacity: 48 } })).toEqual([{ field: "capacity", before: 60, after: 48, changed: true }]);
  });
  it("falls back to before/after keys (create, delete)", () => {
    const rows = diffRows({ before: null, after: { room_id: 11, notes: "Seminer" }, diff: null });
    expect(rows.map((r) => [r.field, r.before, r.after, r.changed])).toEqual([
      ["room_id", undefined, 11, true],
      ["notes", undefined, "Seminer", true],
    ]);
  });
  it("prints values on one line", () => {
    expect(valueText(null)).toBe("—");
    expect(valueText(true, { yes: "evet", no: "hayır" })).toBe("evet");
    expect(valueText({ a: 1 })).toBe('{"a":1}');
  });
  it("builds the query from the filter form", () => {
    expect(auditQuery({ ...emptyAuditFilters, entityType: "booking", entityId: " 12 ", action: "booking.", actorId: "3", from: "2026-02-01", to: "bad" })).toEqual({ entity_type: "booking", entity_id: "12", action: "booking.", actor_id: 3, from: "2026-02-01" });
  });
  it("offers undo only for reversible booking events not undone yet", () => {
    expect(canUndo({ reversible: true, undone: false, action: "booking.create", undo_of: null })).toBe(true);
    expect(canUndo({ reversible: true, undone: true, action: "booking.create", undo_of: null })).toBe(false);
    expect(canUndo({ reversible: true, undone: false, action: "user.update", undo_of: null })).toBe(false);
  });
  it("reads the undo refusal", () => {
    expect(undoReasons({ code: "changed_since", later: [7, 8] })).toEqual({ later: 2, alternatives: [] });
    expect(undoReasons({ code: "conflict", alternatives: [{ name: "A 102" }, { code: "B201" }] }).alternatives).toEqual(["A 102", "B201"]);
  });
});
