import { describe, expect, it } from "vitest";
import { ApprovalRequest } from "@/lib/api/wave1";
import { conflictAlternatives, groupInbox, normaliseScopes, openDates, requestSlots, ruleCovered, ruleTarget, statusTone, timeline, toggleScope } from "./approvals-model";

const booking = (date: string, status = "PENDING") => ({
  id: Number(date.replace(/-/g, "")),
  type: "recurring",
  status,
  date,
  weekday: 3,
  period_id: 3,
  period_name: "3. ders",
  start_period: 3,
  end_period: 3,
  room_id: 11,
  room_name: "A 202",
  headcount: 90,
});
const req = (over: Record<string, unknown> = {}) =>
  ApprovalRequest.parse({ id: 5, status: "PENDING", step: 1, steps: 1, room_id: 11, room_name: "A 202", requester_name: "Deniz Kaya", requested_at: "2026-02-16T08:00:00", bookings: [booking("2026-02-25"), booking("2026-02-18")], ...over });

describe("approval request helpers", () => {
  it("sorts dates and names the first booking's periods", () => {
    const s = requestSlots(req());
    expect(s.dates).toEqual(["2026-02-18", "2026-02-25"]);
    expect(s.periods).toBe("3. ders");
    expect(openDates(req({ bookings: [booking("2026-02-18"), booking("2026-02-25", "REJECTED")] }))).toEqual(["2026-02-18"]);
  });

  it("tones: waiting, approved, rejected, the rest muted", () => {
    expect(["PENDING", "APPROVED", "REJECTED", "EXPIRED", "WITHDRAWN"].map(statusTone)).toEqual(["pending", "ok", "bad", "muted", "muted"]);
  });

  it("timeline: requested, decisions, then waiting (open) or the final state", () => {
    const open = timeline(req({ steps: 2, step: 2, approvers: [{ id: 1, name: "Ayşe Y." }], decisions: [{ step: 1, approver_name: "Fatih B.", decision: "APPROVED", decided_at: "2026-02-16T09:00:00" }] }));
    expect(open.map((e) => e.kind)).toEqual(["requested", "decision", "waiting"]);
    expect(open[2]).toMatchObject({ step: 2, steps: 2, approvers: ["Ayşe Y."] });
    const done = timeline(req({ status: "REJECTED", decided_at: "2026-02-16T10:00:00", decisions: [{ step: 1, decision: "REJECTED", note: "Sınav var" }] }));
    expect(done.map((e) => e.kind)).toEqual(["requested", "decision", "final"]);
    expect(done[1]).toMatchObject({ decision: "reject", note: "Sınav var" });
  });

  it("names what a rule covers", () => {
    const l = { room: (id: number) => (id === 11 ? "A 202" : undefined), group: () => "Tıp Fakültesi" };
    expect(ruleTarget({ entity_type: "room", entity_id: 11, tag: null }, l)).toEqual({ kind: "room", label: "A 202" });
    expect(ruleTarget({ entity_type: "room_group", entity_id: 2, tag: null }, l).label).toBe("Tıp Fakültesi");
    expect(ruleTarget({ entity_type: "tag", entity_id: null, tag: "TIP" }, l)).toEqual({ kind: "tag", label: "TIP" });
  });

  it("scopes: 'all' replaces the rest, tags are upper-cased as ASCII solver tags (tip → TIP, never TİP), duplicates drop", () => {
    let s = toggleScope([], { type: "tag", tag: "tip" }, true);
    s = toggleScope(s, { type: "room", id: 3 }, true);
    expect(normaliseScopes([...s, { type: "tag", tag: "TIP" }])).toEqual([{ type: "tag", tag: "TIP" }, { type: "room", id: 3 }]);
    expect(toggleScope(s, { type: "all" }, true)).toEqual([{ type: "all" }]);
    expect(normaliseScopes([{ type: "all" }, { type: "room", id: 1 }])).toEqual([{ type: "all" }]);
  });

  it("reads the T1 alternatives of a 409 on approve", () => {
    const alts = conflictAlternatives({ code: "conflict", alternatives: [{ kind: "time", room_id: 2, name: "A 102", dates: ["2026-02-18"], start_period: 6, end_period: 8, reason: { tr: "boş", en: "free" } }, { nope: 1 }] });
    expect(alts).toEqual([{ roomId: 2, name: "A 102", date: "2026-02-18", start: 6, end: 8, reason: { tr: "boş", en: "free" } }]);
  });
});

describe("groupInbox (A-12: one row per submission)", () => {
  const req = (id: number, group: number | null, start: number, room = 5) =>
    ({ id, group_id: group, room_id: room, status: "PENDING", bookings: [{ date: "2026-02-18", start_period: start, end_period: start }] }) as unknown as ApprovalRequest;
  it("puts the periods of one submission in one entry, in period order, and keeps single requests apart", () => {
    const entries = groupInbox([req(3, 9, 5), req(1, 9, 3), req(2, null, 1), req(4, 9, 4)]);
    expect(entries.map((e) => e.requests.map((r) => r.id))).toEqual([[1, 4, 3], [2]]);
    expect(entries[0]!.groupId).toBe(9);
  });
  it("does not merge the same group id in another room", () => {
    expect(groupInbox([req(1, 9, 3, 5), req(2, 9, 4, 6)])).toHaveLength(2);
  });
});

describe("T-R2-18 per-rule approver coverage", () => {
  const rooms = [
    { id: 1, name: "A 101", tags: ["PC"], groupId: 10 },
    { id: 2, name: "C 303", tags: [], groupId: 30 },
    { id: 3, name: "C 404", tags: ["PC"], groupId: 30 },
  ];
  const approver = (scopes: { type: "all" | "room" | "room_group" | "tag"; id?: number | null; tag?: string | null }[], can_decide = true) => ({ user_id: 7, name: "Fatih", email: null, can_decide, scopes });
  const roomRule = { entity_type: "room" as const, entity_id: 2, tag: null };
  const groupRule = { entity_type: "room_group" as const, entity_id: 30, tag: null };
  const tagRule = { entity_type: "tag" as const, entity_id: null, tag: "pc" };
  it("an approver whose scope touches the rule's rooms covers it; one scoped to another room does not", () => {
    expect(ruleCovered(roomRule, [approver([{ type: "room", id: 1 }])], rooms)).toBe(false);
    expect(ruleCovered(roomRule, [approver([{ type: "room", id: 2 }])], rooms)).toBe(true);
    expect(ruleCovered(roomRule, [approver([{ type: "room_group", id: 30 }])], rooms)).toBe(true);
    expect(ruleCovered(roomRule, [approver([{ type: "all" }])], rooms)).toBe(true);
    expect(ruleCovered(roomRule, [approver([{ type: "all" }], false)], rooms)).toBe(false);
    expect(ruleCovered(roomRule, [approver([])], rooms)).toBe(false);
  });
  it("a group rule is covered by a room inside the group, a tag rule by a room carrying the tag", () => {
    expect(ruleCovered(groupRule, [approver([{ type: "room", id: 3 }])], rooms)).toBe(true);
    expect(ruleCovered(groupRule, [approver([{ type: "room", id: 1 }])], rooms)).toBe(false);
    expect(ruleCovered(groupRule, [approver([{ type: "tag", tag: "PC" }])], rooms)).toBe(true);
    expect(ruleCovered(tagRule, [approver([{ type: "tag", tag: "PC" }])], rooms)).toBe(true);
    expect(ruleCovered(tagRule, [approver([{ type: "room", id: 2 }])], rooms)).toBe(false);
    expect(ruleCovered(tagRule, [approver([{ type: "room_group", id: 10 }])], rooms)).toBe(true);
  });
});
