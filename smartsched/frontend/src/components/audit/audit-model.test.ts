import { describe, expect, it } from "vitest";
import { ACTION_SENTENCES, archivedCounts, auditQuery, auditReason, auditSubject, auditTail, canUndo, dedupeOptions, diffRows, emptyAuditFilters, ENTITY_ALIASES, ENTITY_TYPES, undoBlockers, undoReasonId, undoReasons, valueText } from "./audit-model";
import { auditSentence, entityLabel } from "./audit-view";
import { translate, type MessageKey } from "@/lib/i18n";

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

describe("programme undo (undo_via program_draft)", () => {
  const base = { reversible: true, undone: false, undo_of: null };
  it("offers Undo for a wizard programme, not for a catalogue programme", () => {
    expect(canUndo({ ...base, action: "program.create", undo_via: "program_draft" })).toBe(true);
    expect(canUndo({ ...base, action: "program.create", undo_via: null })).toBe(false);
    expect(canUndo({ ...base, action: "booking.create", undo_via: "bookings" })).toBe(true);
    expect(canUndo({ ...base, undone: true, action: "program.restore", undo_via: "program_draft" })).toBe(false);
  });
  it("counts what was archived, programme first, empty kinds dropped", () => {
    expect(archivedCounts({ sections: [1, 2, 3], requests: [4], people: [], program: [9], extra_kind: [1, 2] })).toEqual([
      ["program", 1],
      ["sections", 3],
      ["requests", 1],
      ["extra_kind", 2],
    ]);
    expect(archivedCounts(null)).toEqual([]);
  });
  it("reads the 409 blockers in the UI language, falling back to the other language, then the code", () => {
    const data = { code: "blocked", blockers: [{ code: "published", text: { tr: "Yayındaki planda", en: "In the published plan" } }, { code: "bookings", text: { tr: "", en: "Has bookings" } }, { code: "x" }] };
    expect(undoBlockers(data, "tr")).toEqual(["Yayındaki planda", "Has bookings", "x"]);
    expect(undoBlockers(data, "en")).toEqual(["In the published plan", "Has bookings", "x"]);
    expect(undoBlockers({ code: "not_reversible" }, "tr")).toEqual([]);
  });

  // T-R1-32 (R1-M-18): domain sentences, no raw keys in the summary column
  const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("tr", key, vars);
  const RAW = /\b[a-z]+[._][a-z_.]+\b/;
  it("names the record from its snapshot", () => {
    expect(auditSubject({ after: { id: 3, code: "TST101", display_code: "TST 101" }, before: null, entity_id: "3", entity_type: "course" })).toBe("TST 101");
    expect(auditSubject({ after: { kind: "erase" }, before: null, entity_id: "2", entity_type: "dsr_request" })).toBe("erase");
    expect(auditTail({ after: { full_name: "D. S." }, before: null, entity_id: "9", entity_type: "user" })).toBe("D. S. · #9");
    expect(auditTail({ after: null, before: null, entity_id: "9", entity_type: "user" })).toBe("#9");
    expect(auditTail({ after: { value: "***" }, before: null, entity_id: "policies.exam_period", entity_type: "setting" })).toBe("#policies.exam_period");
  });
  it("reads every action and entity the backend writes as a Turkish sentence", () => {
    const actions = [...Object.keys(ACTION_SENTENCES), "dsr_request.create", "notify_channel.update", "setting.update", "program.create", "course.create", "section.create", "sso_provider.update", "webhook.create", "run.activate", "booking.move", "role.create"];
    for (const action of actions) {
      const entity = action.split(".")[0]!;
      const sentence = auditSentence(action, entity, t);
      expect(sentence, action).not.toMatch(RAW);
      expect(sentence, action).not.toMatch(/^[a-z_]+ /);
    }
    for (const type of [...ENTITY_TYPES, ...Object.keys(ENTITY_ALIASES)]) expect(entityLabel(type, t), type).not.toMatch(RAW);
    expect(auditSentence("kvkk.dsr_refuse", "dsr_request", t)).toBe("Kişisel veri talebi reddedildi");
    expect(auditSentence("booking_policy.exam_period", "setting", t)).toBe("Sınav dönemi rezervasyon kuralı değiştirildi");
    expect(auditSentence("program.create", "program", t)).toBe("Program eklendi");
    expect(auditSentence("course.create", "course", t)).toBe("Ders eklendi");
  });
  it("deduplicates filter options by label", () => {
    const out = dedupeOptions([
      { value: "1", label: "A. T.", hint: "a.t" },
      { value: "2", label: "A. T.", hint: "at2" },
      { value: "1", label: "A. T.", hint: "a.t" },
      { value: "3", label: "P. L.", hint: "pl" },
    ]);
    expect(out.map((o) => o.label)).toEqual(["A. T. (a.t)", "A. T. (at2)", "P. L."]);
  });
  // T-R2-31 (R2-M-11): the undo writes a coded reason; the row renders it in the UI language, never "undo of #164"
  it("renders the coded undo reason in the UI language and free text as typed", () => {
    const tr = (k: MessageKey, v?: Record<string, string | number>) => translate("tr", k, v);
    const en = (k: MessageKey, v?: Record<string, string | number>) => translate("en", k, v);
    expect(undoReasonId("undo_of:164")).toBe(164);
    expect(undoReasonId("yanlışlık")).toBeNull();
    expect(undoReasonId(null)).toBeNull();
    expect(auditReason("undo_of:164", tr)).toBe("Geri alma: #164");
    expect(auditReason("undo_of:164", en)).toBe("Undo of #164");
    expect(auditReason("yanlışlık", tr)).toBe("yanlışlık");
    expect(auditReason(null, tr)).toBeNull();
    expect(auditReason("undo_of:164", tr)).not.toMatch(/undo of/i);
  });
  // R3-S-03 / R3-M-07 (loop-r3-laneF): "Booking series iptal edildi #1", "Council job işlendi" in the Turkish UI.
  // Every entity type the backend audits (an AST scan of app/**: audit.record / publish_event, 2026-10-17) has a
  // Turkish label of its own, never the capitalised raw key the fallback prints.
  const AUDITED = ["approval_request", "approval_rule", "assignment", "booking", "booking_policy", "booking_series", "channel_department_target", "consent", "constraint", "council_job", "course", "dsr_request", "exam", "exam_request", "faculty", "instructor", "invigilation_duty", "invigilation_plan", "invigilator_pool", "learning", "learning_reset", "meeting", "meeting_request", "notify_channel", "preset", "privacy_notice", "program", "program_draft", "retention_policy", "room", "room_feature", "run", "schedule_run", "section", "setting", "sso_provider", "sso_role_mapping", "studio_draft", "suggestion", "term", "user", "user_channel", "webhook"];
  it("labels every audited record kind in Turkish, never with its raw key", () => {
    const tr = (k: MessageKey, v?: Record<string, string | number>) => translate("tr", k, v);
    const raw = (type: string) => type.replace(/[._]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
    // "Webhook" and "Program" are the Turkish words too
    const missing = AUDITED.filter((type) => entityLabel(type, tr) === raw(type) && !["webhook", "program"].includes(type));
    expect(missing).toEqual([]);
    expect(auditSentence("booking.cancel", "booking_series", tr)).toBe("Tekrarlayan rezervasyon iptal edildi");
    expect(auditSentence("series.create", "booking_series", tr)).toBe("Tekrarlayan rezervasyon eklendi");
    expect(auditSentence("council.commit", "council_job", tr)).toBe("İçe aktarma işi işlendi");
    expect(auditSentence("council.review", "council_job", tr)).toBe("İçe aktarma işi değiştirildi");
    for (const type of AUDITED) expect(entityLabel(type, tr), type).not.toMatch(/\b(booking|series|council|job|learning|reset|draft|suggestion|assignment|request)\b/i);
  });
  it("keeps the English labels English", () => {
    const en = (k: MessageKey, v?: Record<string, string | number>) => translate("en", k, v);
    expect(auditSentence("booking.cancel", "booking_series", en)).toMatch(/^Recurring booking/);
    expect(entityLabel("council_job", en)).toBe("Import job");
  });
});
