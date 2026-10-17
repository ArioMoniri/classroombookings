import { describe, expect, it } from "vitest";
import { Effective, emptyPolicy, parseLimit, Policy, policyToInput, toPayload, validatePolicy, violationText } from "@/lib/api/booking-policies";
import { GridSlot } from "@/lib/api/crbs";

describe("booking policy form helpers", () => {
  it("a blank rule has no limit and is refused before sending", () => {
    const p = emptyPolicy();
    expect(validatePolicy(p)).toEqual(["name", "empty"]);
    expect(validatePolicy({ ...p, name: "Laboratuvar", min_notice_workdays: 3 })).toEqual([]);
  });

  it("asks for the scope target, a whole quiet window and an ordered blackout", () => {
    const base = { ...emptyPolicy(), name: "x", buffer_minutes: 10 };
    expect(validatePolicy({ ...base, scope_type: "room" })).toContain("scope_id");
    expect(validatePolicy({ ...base, scope_type: "tag", tag: " " })).toContain("tag");
    expect(validatePolicy({ ...base, quiet_hours: [{ weekdays: [1], start: "12:40", end: "12:40" }] })).toContain("quiet");
    expect(validatePolicy({ ...base, quiet_hours: [{ weekdays: [], start: "12:40", end: "13:30" }] })).toContain("quiet");
    expect(validatePolicy({ ...base, blackouts: [{ from: "2026-04-24", to: "2026-04-23" }] })).toContain("blackout");
  });

  it("sends only the scope's own field, upper-case unique roles and a one-day blackout ending on its start", () => {
    const body = toPayload({ ...emptyPolicy(), name: "  Sınav haftası ", scope_type: "all", scope_id: 4, tag: "PC", role_codes: ["teacher", "TEACHER", " "], blackouts: [{ from: "2026-04-23", to: "", label: " 23 Nisan " }], note: "  " });
    expect(body).toMatchObject({ name: "Sınav haftası", scope_id: null, tag: null, role_codes: ["TEACHER"], blackouts: [{ from: "2026-04-23", to: "2026-04-23", label: "23 Nisan" }], note: null });
  });

  it("round-trips a stored rule into the form", () => {
    const p = Policy.parse({ id: 1, name: "Öğle arası", enabled: true, scope_type: "room_group", scope_id: 2, effect: "request", quiet_hours: [{ weekdays: [1, 2, 3, 4, 5], start: "12:40", end: "13:30" }], blackouts: [{ from: "2026-04-23", to: "2026-04-23", label: null }], summary: { tr: ["Rezervasyon yok: Pazartesi 12:40-13:30"], en: [] } });
    const f = policyToInput(p);
    expect(f).toMatchObject({ scope_type: "room_group", scope_id: 2, effect: "request", min_notice_workdays: null });
    expect(validatePolicy(f)).toEqual([]);
  });

  it("parses limit fields (empty = no limit)", () => {
    expect(parseLimit("")).toBeNull();
    expect(parseLimit(" 3 ")).toBe(3);
    expect(parseLimit("2.7")).toBe(2);
    expect(parseLimit("x")).toBeNull();
  });

  it("reads the effective verdict and the violation in the reader's language", () => {
    const e = Effective.parse({ room_id: 4, term_id: 1, exempt: false, policies: [], exam_period: { mode: "off", exam_room: false }, date: "2026-02-18", period_id: 2, violations: [{ rule: "min_notice", effect: "refuse", message_tr: "En az 3 iş günü önceden", message_en: "At least 3 working days ahead", policy_id: 1, policy_name: "Lab" }], verdict: "refuse" });
    expect(e.verdict).toBe("refuse");
    expect(violationText(e.violations![0]!, "tr")).toBe("En az 3 iş günü önceden");
    expect(violationText(e.violations![0]!, "en")).toBe("At least 3 working days ahead");
  });

  it("keeps the grid's policy marks (they were stripped before)", () => {
    const slot = GridSlot.parse({ date: "2026-02-18", period_id: 2, room_id: 4, status: "available", allow_single: true, request_only: true, policy: { rule: "quiet_hours", effect: "request", message_tr: "Sessiz saat", message_en: "Quiet hours", policy_id: 3, policy_name: "Öğle" } });
    expect(slot.request_only).toBe(true);
    expect(slot.policy?.rule).toBe("quiet_hours");
  });
});
