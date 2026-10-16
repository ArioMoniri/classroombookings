/** Approval-first (owner requirement 2026-10-15): rejection reasons and the deep link to a whole submission. */
import { describe, expect, it } from "vitest";
import { ApprovalRequest } from "@/lib/api/wave1";
import { groupInbox, isBlank, pickAsked, reasonLine, rejectProblems, requestReason, timeline } from "./approvals-model";

const LABELS: Record<string, string> = { room_unavailable: "Oda uygun değil", capacity: "Kapasite yetersiz", policy: "Rezervasyon kurallarına uygun değil", other: "Diğer", slot_taken: "Aynı saat başka bir talebe verildi" };
const label = (c: string) => LABELS[c] ?? null;
const booking = (start: number) => ({ id: 100 + start, type: "single", status: "PENDING", date: "2026-02-19", weekday: 4, period_id: start, period_name: `${start}. ders`, start_period: start, end_period: start, room_id: 11, room_name: "C 303" });
const req = (over: Record<string, unknown> = {}) =>
  ApprovalRequest.parse({ id: 5, status: "PENDING", step: 1, steps: 1, room_id: 11, room_name: "C 303", requester_name: "P. T.", requested_at: "2026-02-16T08:00:00", bookings: [booking(7)], ...over });

describe("rejection reasons", () => {
  it("counts spaces, NBSP and zero-width characters as blank", () => {
    expect(isBlank("")).toBe(true);
    expect(isBlank("   ​ ")).toBe(true);
    expect(isBlank(" sınav ")).toBe(false);
  });

  it("needs a code and a written reason (stricter than the backend)", () => {
    expect(rejectProblems({ code: null, text: "" })).toEqual({ code: "required", text: "required" });
    expect(rejectProblems({ code: "other", text: "  " })).toEqual({ text: "required" });
    expect(rejectProblems({ code: "room_unavailable", text: "Bu saatte bölüm sınavı var." })).toEqual({});
    expect(rejectProblems({ code: "capacity", text: "x".repeat(11) }, 10)).toEqual({ text: "tooLong" });
  });

  it("reads like the backend's reason_text: label + text, 'other' and missing labels as text, system reasons as label", () => {
    expect(reasonLine("room_unavailable", "Bu saatte bölüm sınavı var.", label)).toBe("Oda uygun değil: Bu saatte bölüm sınavı var.");
    expect(reasonLine("other", "Bakım var", label)).toBe("Bakım var");
    expect(reasonLine("capacity", null, label)).toBe("Kapasite yetersiz");
    expect(reasonLine("slot_taken", "anything", label)).toBe("Aynı saat başka bir talebe verildi");
    expect(reasonLine(null, "Sadece metin", label)).toBe("Sadece metin");
    expect(reasonLine(null, " ", label)).toBeNull();
  });

  it("takes the request's own reason, else the rejecting decision's; nothing unless rejected", () => {
    expect(requestReason(req())).toBeNull();
    const own = req({ status: "REJECTED", note: "Bu saatte bölüm sınavı var.", reason: "Bu saatte bölüm sınavı var.", reason_code: "room_unavailable" });
    expect(requestReason(own)).toEqual({ code: "room_unavailable", text: "Bu saatte bölüm sınavı var." });
    // code only: `reason` repeats the code in both languages, which is not shown as text
    expect(requestReason(req({ status: "REJECTED", reason: "Kapasite yetersiz / not enough seats", reason_code: "capacity" }))).toEqual({ code: "capacity", text: null });
    const fromDecision = req({ status: "REJECTED", decisions: [{ step: 1, approver_name: "Administrator", decision: "REJECTED", note: "Sınav", reason_code: "policy", decided_at: "2026-02-16T09:00:00" }] });
    expect(requestReason(fromDecision)).toEqual({ code: "policy", text: "Sınav" });
  });

  it("puts the reason code on the timeline's rejection", () => {
    const r = req({ status: "REJECTED", decided_at: "2026-02-16T09:00:00", decisions: [{ step: 1, approver_name: "Administrator", decision: "REJECTED", note: "Sınav", reason_code: "room_unavailable", decided_at: "2026-02-16T09:00:00" }] });
    const d = timeline(r).find((e) => e.kind === "decision");
    expect(d).toMatchObject({ decision: "reject", by: "Administrator", note: "Sınav", reasonCode: "room_unavailable" });
  });
});

describe("approver deep links (?request= & ?group=)", () => {
  const p7 = req({ id: 21, group_id: 9, bookings: [booking(7)] });
  const p8 = req({ id: 22, group_id: 9, bookings: [booking(8)] });
  const solo = req({ id: 30, bookings: [booking(3)] });
  const entries = groupInbox([p8, solo, p7]);

  it("opens the submission's first open period, whatever request the link names", () => {
    expect(pickAsked(entries, 22, 9)).toBe(21);
    expect(pickAsked(entries, null, 9)).toBe(21);
  });

  it("skips decided periods and falls back to the link's request when the submission is not in the box", () => {
    const decided = groupInbox([{ ...p7, status: "APPROVED" }, p8]);
    expect(pickAsked(decided, 21, 9)).toBe(22);
    expect(pickAsked(groupInbox([solo]), 21, 9)).toBe(21);
    expect(pickAsked(entries, 30, null)).toBe(30);
    expect(pickAsked(entries, null, null)).toBeNull();
  });
});
