/**
 * FIX-D / HB18-F06 (docs/testing/round4/2026-10-18-hb18.md): /admin/audit could not find the helper's events, and the
 * rows read "Helper action değiştirildi bad_token · #unknown". Now: an İşlem filter "helper.", a Kayıt türü
 * "Yardımcı işlemi", a verb per action, and the refusal reasons in Turkish (a refusal is not a write).
 */
import { describe, expect, it } from "vitest";
import { translate, type MessageKey } from "@/lib/i18n";
import { ACTION_PREFIXES, ENTITY_TYPES } from "./audit-model";
import { auditSentence, entityLabel, helperTail } from "./audit-view";

const tr = (key: MessageKey, vars?: Record<string, string | number>) => translate("tr", key, vars);
const en = (key: MessageKey, vars?: Record<string, string | number>) => translate("en", key, vars);

describe("helper events in the audit log (HB18-F06)", () => {
  it("can be filtered: İşlem 'helper.' and Kayıt türü 'Yardımcı işlemi'", () => {
    expect(ACTION_PREFIXES).toContain("helper.");
    expect(ENTITY_TYPES).toContain("helper_action");
    expect(entityLabel("helper_action", tr)).toBe("Yardımcı işlemi");
    expect(entityLabel("helper_thread", tr)).toBe("Yardımcı sohbeti");
  });

  it("each helper write reads as what it did", () => {
    expect(auditSentence("helper.action.create_booking", "helper_action", tr)).toBe("Yardımcıyla rezerve edildi");
    expect(auditSentence("helper.action.cancel_my_booking", "helper_action", tr)).toBe("Yardımcıyla rezervasyon iptal edildi");
    expect(auditSentence("helper.action.undo_last_helper_action", "helper_action", tr)).toBe("Yardımcıyla geri alındı");
    expect(auditSentence("helper.action.remember_note", "helper_action", tr)).toBe("Not kaydedildi");
    expect(auditSentence("helper.action.remember_note.undo", "helper_action", tr)).toBe("Not geri alındı");
    expect(auditSentence("helper.threads_deleted", "helper_thread", tr)).toBe("Sohbet geçmişi silindi");
    expect(auditSentence("helper.action.create_booking", "helper_action", en)).toBe("Booked with the helper");
  });

  it("a refused confirmation says it was refused and why, never 'değiştirildi'", () => {
    const row = (code: string, id = "create_booking") => ({ action: "helper.confirm_rejected", entity_type: "helper_action", entity_id: id, after: { code, via: "helper" }, before: null });
    expect(auditSentence("helper.confirm_rejected", "helper_action", tr, row("bad_token").after)).toBe("Onay reddedildi (geçersiz onay)");
    expect(auditSentence("helper.confirm_rejected", "helper_action", tr, row("other_user").after)).toBe("Onay reddedildi (başka bir hesabın onayı)");
    expect(auditSentence("helper.confirm_rejected", "helper_action", tr, row("already_done").after)).toBe("Onay reddedildi (zaten yapılmış)");
    expect(auditSentence("helper.confirm_rejected", "helper_action", tr, row("expired").after)).toBe("Onay reddedildi (süresi dolmuş)");
    expect(auditSentence("helper.confirm_rejected", "helper_action", tr, row("weird_new_code").after)).toBe("Onay reddedildi");
    expect(auditSentence("helper.confirm_rejected", "helper_action", tr)).not.toMatch(/değiştirildi/);
    expect(helperTail(row("already_done"), tr)).toBe("Rezervasyon");
    expect(helperTail(row("bad_token", "unknown"), tr)).toBe("");
    expect(helperTail({ action: "helper.action.create_booking", entity_type: "helper_action", entity_id: "5", after: { via: "helper" }, before: null }, tr)).toBe("#5");
    expect(helperTail({ action: "booking.create", entity_type: "booking", entity_id: "5", after: null, before: null }, tr)).toBeNull();
  });
});
